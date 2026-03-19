import sys
import os
import json
import ast
import csv
import time
import uuid
import tempfile
import hashlib
import mimetypes
import re
import ssl
from io import BytesIO, StringIO
from urllib.parse import urlparse
from urllib import error as urlerror
from urllib import request, parse
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageChops
from license_client import LicenseClient

try:
    import certifi
except Exception:
    certifi = None

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QEvent, QSize
from PyQt6.QtGui import QKeySequence, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox,
    QSpinBox,
    QFileDialog,
    QMessageBox,
    QTextEdit,
    QProgressBar,
    QRadioButton,
    QButtonGroup,
    QGridLayout,
    QCheckBox,
    QComboBox,
    QTabWidget,
    QLineEdit,
    QHeaderView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
)

APP_VERSION = "0.2.5"
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/lana-info/Clipart-Generator-Updates/main/version.json"
REFERENCE_MODEL_SHORTLIST = {
    "flux-2/pro-image-to-image",
    "flux-2/flex-image-to-image",
    "gpt-image/1.5-image-to-image",
    "qwen/image-to-image",
    "grok-imagine/image-to-image",
    "google/nano-banana-edit",
}

GENERATION_MODELS = [
    # Text -> Image
    {"id": "gpt4o-image", "label": "GPTâ€‘4o Image", "type": "text_to_image"},
    {"id": "gpt-image/1.5-text-to-image", "label": "GPT Image 1.5 (Textâ†’Image)", "type": "text_to_image"},
    {"id": "z-image", "label": "Z-Image", "type": "text_to_image"},
    {"id": "google/imagen4", "label": "Google Imagen 4", "type": "text_to_image"},
    {"id": "google/imagen4-fast", "label": "Google Imagen 4 Fast", "type": "text_to_image"},
    {"id": "google/imagen4-ultra", "label": "Google Imagen 4 Ultra", "type": "text_to_image"},
    {"id": "google/nano-banana", "label": "Google Nano Banana", "type": "text_to_image"},
    {"id": "flux-2/flex-text-to-image", "label": "FLUX.2 Flex (Textâ†’Image)", "type": "text_to_image"},
    {"id": "flux-2/pro-text-to-image", "label": "FLUX.2 Pro (Textâ†’Image)", "type": "text_to_image"},
    {"id": "black-forest-labs/flux-kontext-pro", "label": "FLUX Kontext Pro", "type": "text_to_image"},
    {"id": "black-forest-labs/flux-kontext-max", "label": "FLUX Kontext Max", "type": "text_to_image"},
    {"id": "seedream", "label": "Seedream", "type": "text_to_image"},
    {"id": "seedream-v4-text-to-image", "label": "Seedream v4 (Textâ†’Image)", "type": "text_to_image"},
    {"id": "4.5-text-to-image", "label": "Seedream 4.5 (Textâ†’Image)", "type": "text_to_image"},
    {"id": "grok-imagine/text-to-image", "label": "Grok Imagine (Textâ†’Image)", "type": "text_to_image"},
    {"id": "qwen/text-to-image", "label": "Qwen (Textâ†’Image)", "type": "text_to_image"},

    # Image -> Image
    {"id": "google/pro-image-to-image", "label": "Google Pro (Imageâ†’Image)", "type": "image_to_image"},
    {"id": "flux-2/pro-image-to-image", "label": "FLUX.2 Pro (Imageâ†’Image)", "type": "image_to_image"},
    {"id": "flux-2/flex-image-to-image", "label": "FLUX.2 Flex (Imageâ†’Image)", "type": "image_to_image"},
    {"id": "grok-imagine/image-to-image", "label": "Grok Imagine (Imageâ†’Image)", "type": "image_to_image"},
    {"id": "gpt-image/1.5-image-to-image", "label": "GPT Image 1.5 (Imageâ†’Image)", "type": "image_to_image"},
    {"id": "qwen/image-to-image", "label": "Qwen (Imageâ†’Image)", "type": "image_to_image"},

    # Edit
    {"id": "google/nano-banana-edit", "label": "Google Nano Banana Edit", "type": "edit"},
    {"id": "seedream-v4-edit", "label": "Seedream v4 Edit", "type": "edit"},
    {"id": "4.5-edit", "label": "Seedream 4.5 Edit", "type": "edit"},
    {"id": "ideogram/v3-reframe", "label": "Ideogram v3 Reframe", "type": "edit"},
    {"id": "ideogram/character-edit", "label": "Ideogram Character Edit", "type": "edit"},
    {"id": "ideogram/character-remix", "label": "Ideogram Character Remix", "type": "edit"},
    {"id": "ideogram/character", "label": "Ideogram Character", "type": "edit"},
    {"id": "qwen/image-edit", "label": "Qwen Image Edit", "type": "edit"},
]

GENERATION_MODEL_META = {entry["id"]: entry for entry in GENERATION_MODELS}
MAX_REFERENCES_PER_PROMPT = 5


def split_references(raw_value):
    if isinstance(raw_value, list):
        values = [str(item).strip() for item in raw_value]
        return [item for item in values if item]
    text = str(raw_value or "").strip()
    if not text:
        return []
    chunks = [part.strip() for part in re.split(r"\s*\|\s*", text)]
    return [part for part in chunks if part]


def join_references(references):
    items = split_references(references)
    return " | ".join(items)


def get_user_data_dir():
    base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    user_data_dir = os.path.join(base_dir, "Clipart Generator")
    os.makedirs(user_data_dir, exist_ok=True)
    return user_data_dir


USER_DATA_DIR = get_user_data_dir()
CONFIG_FILE = os.path.join(USER_DATA_DIR, "config.json")
PROMPTS_STORAGE_FILE = os.path.join(USER_DATA_DIR, "prompts.json")
LICENSE_CACHE_FILE = os.path.join(USER_DATA_DIR, "license_cache.json")


def build_ssl_context():
    """Ð¡Ð¾Ð·Ð´Ð°Ñ‘Ñ‚ SSL-ÐºÐ¾Ð½Ñ‚ÐµÐºÑÑ‚ Ñ ÑÐ¸ÑÑ‚ÐµÐ¼Ð½Ñ‹Ð¼Ð¸ ÑÐµÑ€Ñ‚Ð¸Ñ„Ð¸ÐºÐ°Ñ‚Ð°Ð¼Ð¸ Ð¸ fallback Ð½Ð° certifi."""
    if certifi is not None:
        try:
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()


class WorkerThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress_value = pyqtSignal(int)

    def __init__(self, mode, work_dir, settings, selected_files=None, generated_prompts=None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.work_dir = work_dir
        self.settings = settings
        self.selected_files = selected_files or []
        self.generated_prompts = generated_prompts or []
        self.is_running = True
        self.run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        self.kie_api_key = settings.get("kie_api_key", "").strip()
        self.kie_upload_path = settings.get("kie_upload_path", "clipart-generator")
        self.text_generation_model = settings.get(
            "text_generation_model",
            settings.get("generation_model", "gpt4o-image"),
        )
        self.reference_generation_model = settings.get(
            "reference_generation_model",
            "qwen/image-to-image",
        )
        self.generation_size = settings.get("generation_size", "1:1")
        self.timeout = max(10, int(settings.get("timeout", 60)))
        self.retries = max(0, int(settings.get("retries", 3)))
        self.generation_wait_timeout = max(120, int(settings.get("generation_wait_timeout", 300)))
        self.status_poll_interval = max(5.0, min(60.0, float(settings.get("status_poll_interval", 20))))

        self.upscale = settings.get("upscale", True)
        self.remove_bg = settings.get("remove_bg", True)
        self.trim_enabled = bool(settings.get("trim_enabled", False))
        self.trim_mode = str(settings.get("trim_mode", "alpha") or "alpha")
        self.trim_position = str(settings.get("trim_position", "post") or "post")
        self.kie_upscale_model = settings.get("kie_upscale_model", "topaz/upscale")
        self.kie_remove_bg_model = settings.get("kie_remove_bg_model", "recraft/remove-background")
        self.upscale_factor = int(settings.get("upscale_factor", 4) or 4)

    def run(self):
        try:
            if self.mode == "mode1_full":
                self._mode1_generate(process_generated=True)
            elif self.mode == "mode1_generate_only":
                self._mode1_generate(process_generated=False)
            elif self.mode == "mode_both":
                self._mode1_generate(process_generated=True)
            else:
                self._mode2_process_files()
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self.is_running = False

    def _mode1_generate(self, process_generated, emit_final=True):
        self.progress.emit("Mode 1: Ð“ÐµÐ½ÐµÑ€Ð°Ñ†Ð¸Ñ Ð¸Ð· Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð²")
        self.progress.emit(f"Ð Ð°Ð±Ð¾Ñ‡Ð°Ñ Ð¿Ð°Ð¿ÐºÐ°: {self.work_dir}")
        if not self.kie_api_key:
            raise ValueError("ÐÐµ ÑƒÐºÐ°Ð·Ð°Ð½ KIE API Key")

        raw_dir = os.path.join(self.work_dir, "raw")
        output_dir = os.path.join(self.work_dir, "output")
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        entries = self._normalize_prompt_entries(self.generated_prompts)
        if not entries:
            if emit_final:
                self.finished.emit("Mode 1: ÐÐµÑ‚ Ð·Ð°Ð¿Ð¸ÑÐµÐ¹. Ð”Ð¾Ð±Ð°Ð²ÑŒÑ‚Ðµ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ñ‹")
            return

        total = len(entries)
        done = 0
        self.progress.emit(f"Ð—Ð°Ð¿Ð¸ÑÐµÐ¹ Ðº Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐµ: {total}")

        for idx, entry in enumerate(entries, start=1):
            if not self.is_running:
                self.progress.emit("ÐžÑÑ‚Ð°Ð½Ð¾Ð²Ð»ÐµÐ½Ð¾ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¼")
                return

            self.progress.emit(f"[{idx}/{total}] Ð“ÐµÐ½ÐµÑ€Ð°Ñ†Ð¸Ñ")
            self.progress_value.emit(int(((idx - 1) / total) * 100))
            try:
                prompt_text = entry.get("prompt", "")
                references = entry.get("references", [])
                image_url = self._kie_generate_image(prompt_text, references)
                gen_path = os.path.join(raw_dir, f"gen_{idx:03d}_{self.run_stamp}.png")
                self._download_file(image_url, gen_path)
                self.progress.emit(f"  Ð¡Ð³ÐµÐ½ÐµÑ€Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¾: {gen_path}")

                source_path = gen_path
                if process_generated and self.trim_enabled and self.trim_position == "pre":
                    pretrim_path = os.path.join(raw_dir, f"gen_pretrim_{idx:03d}_{self.run_stamp}.png")
                    source_path = self._trim_image_file(source_path, pretrim_path, "Ð´Ð¾ Ð°Ð¿ÑÐºÐµÐ¹Ð»Ð°")

                final_url = image_url
                if process_generated:
                    if self.upscale or self.remove_bg:
                        uploaded_url = self._kie_upload_file(source_path)
                        self.progress.emit("  Ð—Ð°Ð³Ñ€ÑƒÐ¶ÐµÐ½Ð¾ Ð² KIE")
                        final_url = self._run_kie_processing_pipeline(uploaded_url, raw_dir, idx, "gen", source_path)
                    else:
                        final_url = None

                out_path = os.path.join(output_dir, f"result_{idx:03d}_{self.run_stamp}.png")
                if final_url:
                    self._save_pipeline_result(final_url, out_path, raw_dir, idx, "gen")
                elif process_generated:
                    if self.trim_enabled and self.trim_position == "post":
                        self._trim_image_file(source_path, out_path, "Ð² ÐºÐ¾Ð½Ñ†Ðµ")
                    else:
                        self._save_image_as_png(source_path, out_path)
                else:
                    self._save_image_as_png(gen_path, out_path)
                self.progress.emit(f"  Ð˜Ñ‚Ð¾Ð³ ÑÐ¾Ñ…Ñ€Ð°Ð½Ñ‘Ð½: {out_path}")
                done += 1
            except Exception as e:
                self.progress.emit(f"  ÐžÑˆÐ¸Ð±ÐºÐ°: {e}")

        self.progress_value.emit(100)
        if emit_final:
            self.finished.emit(f"Mode 1: Ð“Ð¾Ñ‚Ð¾Ð²Ð¾ ({done}/{total})")

    def _normalize_prompt_entries(self, raw_entries):
        entries = []
        for item in raw_entries or []:
            if isinstance(item, dict):
                prompt_text = str(item.get("prompt", "")).strip()
                references = split_references(item.get("references", ""))
                if prompt_text or references:
                    entries.append({"prompt": prompt_text, "references": references})
                continue
            prompt_text = str(item).strip()
            if prompt_text:
                entries.append({"prompt": prompt_text, "references": []})
        return entries

    def _mode2_process_files(self, emit_final=True):
        self.progress.emit("Mode 2: ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÑŽÑ‰Ð¸Ñ… Ñ„Ð°Ð¹Ð»Ð¾Ð² Ñ‡ÐµÑ€ÐµÐ· KIE")
        self.progress.emit(f"Ð Ð°Ð±Ð¾Ñ‡Ð°Ñ Ð¿Ð°Ð¿ÐºÐ°: {self.work_dir}")

        if not (self.upscale or self.remove_bg or self.trim_enabled):
            raise ValueError("Ð’ÐºÐ»ÑŽÑ‡Ð¸Ñ‚Ðµ Ñ…Ð¾Ñ‚Ñ Ð±Ñ‹ Ð¾Ð´Ð¸Ð½ ÑÑ‚Ð°Ð¿: Ð°Ð¿ÑÐºÐµÐ¹Ð», ÑƒÐ´Ð°Ð»ÐµÐ½Ð¸Ðµ Ñ„Ð¾Ð½Ð° Ð¸Ð»Ð¸ trim")

        if (self.upscale or self.remove_bg) and not self.kie_api_key:
            raise ValueError("ÐÐµ ÑƒÐºÐ°Ð·Ð°Ð½ KIE API Key")

        if not self.selected_files:
            if emit_final:
                self.finished.emit("Mode 2: Ð¤Ð°Ð¹Ð»Ñ‹ Ð½Ðµ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ñ‹")
            return

        raw_dir = os.path.join(self.work_dir, "raw")
        output_dir = os.path.join(self.work_dir, "output")
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        total = len(self.selected_files)
        done = 0
        for idx, file_path in enumerate(self.selected_files, start=1):
            if not self.is_running:
                self.progress.emit("ÐžÑÑ‚Ð°Ð½Ð¾Ð²Ð»ÐµÐ½Ð¾ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¼")
                return

            self.progress.emit(f"[{idx}/{total}] ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ñ„Ð°Ð¹Ð»Ð°: {os.path.basename(file_path)}")
            self.progress_value.emit(int(((idx - 1) / total) * 100))
            try:
                if not os.path.isfile(file_path):
                    self.progress.emit(f"  Ð¤Ð°Ð¹Ð» Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½: {file_path}")
                    continue

                source_path = file_path
                if self.trim_enabled and self.trim_position == "pre":
                    pretrim_path = os.path.join(raw_dir, f"file_pretrim_{idx:03d}_{self.run_stamp}.png")
                    source_path = self._trim_image_file(source_path, pretrim_path, "Ð´Ð¾ Ð°Ð¿ÑÐºÐµÐ¹Ð»Ð°")

                if self.upscale or self.remove_bg:
                    uploaded_url = self._kie_upload_file(source_path)
                    self.progress.emit("  Ð—Ð°Ð³Ñ€ÑƒÐ¶ÐµÐ½Ð¾ Ð² KIE")
                    final_url = self._run_kie_processing_pipeline(uploaded_url, raw_dir, idx, "file", source_path)
                else:
                    final_url = None

                base = os.path.splitext(os.path.basename(file_path))[0]
                out_path = os.path.join(output_dir, f"{base}_processed_{self.run_stamp}.png")

                if final_url:
                    self._save_pipeline_result(final_url, out_path, raw_dir, idx, "file")
                else:
                    if self.trim_enabled and self.trim_position == "post":
                        self._trim_image_file(source_path, out_path, "Ð² ÐºÐ¾Ð½Ñ†Ðµ")
                    else:
                        self._save_image_as_png(source_path, out_path)

                self.progress.emit(f"  Ð˜Ñ‚Ð¾Ð³ ÑÐ¾Ñ…Ñ€Ð°Ð½Ñ‘Ð½: {out_path}")
                done += 1
            except Exception as e:
                self.progress.emit(f"  ÐžÑˆÐ¸Ð±ÐºÐ°: {e}")

        self.progress_value.emit(100)
        if emit_final:
            self.finished.emit(f"Mode 2: Ð“Ð¾Ñ‚Ð¾Ð²Ð¾ ({done}/{total})")

    def _run_kie_processing_pipeline(self, image_url, raw_dir, idx, prefix, source_image_path=""):
        pipeline_url = image_url

        if self.upscale:
            self.progress.emit(f"  ÐÐ¿ÑÐºÐµÐ¹Ð» Ñ‡ÐµÑ€ÐµÐ· {self.kie_upscale_model}...")
            upscale_factor = self._resolve_upscale_factor()
            if self.kie_upscale_model == "topaz/upscale":
                upscale_input = {
                    "image_url": pipeline_url,
                    "upscale_factor": str(upscale_factor),
                }
            elif self.kie_upscale_model == "recraft/crisp-upscale":
                upscale_input = None
            else:
                upscale_input = {"scale": upscale_factor}
            self.progress.emit(f"  ÐšÑ€Ð°Ñ‚Ð½Ð¾ÑÑ‚ÑŒ Ð°Ð¿ÑÐºÐµÐ¹Ð»Ð°: {upscale_factor}x")
            pipeline_url = self._kie_run_model_task(self.kie_upscale_model, pipeline_url, extra_input=upscale_input)
            upscaled_path = os.path.join(raw_dir, f"{prefix}_upscaled_{idx:03d}_{self.run_stamp}.png")
            self._download_file(pipeline_url, upscaled_path)
            self.progress.emit(f"  ÐŸÑ€Ð¾Ð¼ÐµÐ¶ÑƒÑ‚Ð¾Ñ‡Ð½Ñ‹Ð¹ Ð°Ð¿ÑÐºÐµÐ¹Ð»: {upscaled_path}")

        if self.remove_bg:
            self.progress.emit(f"  Ð£Ð´Ð°Ð»ÐµÐ½Ð¸Ðµ Ñ„Ð¾Ð½Ð° Ñ‡ÐµÑ€ÐµÐ· {self.kie_remove_bg_model}...")
            pipeline_url = self._kie_run_model_task(self.kie_remove_bg_model, pipeline_url)
            nobg_path = os.path.join(raw_dir, f"{prefix}_nobg_{idx:03d}_{self.run_stamp}.png")
            self._download_file(pipeline_url, nobg_path)
            self.progress.emit(f"  ÐŸÑ€Ð¾Ð¼ÐµÐ¶ÑƒÑ‚Ð¾Ñ‡Ð½Ñ‹Ð¹ Ð±ÐµÐ· Ñ„Ð¾Ð½Ð°: {nobg_path}")

        return pipeline_url

    def _save_pipeline_result(self, result_url, output_path, raw_dir, idx, prefix):
        if self.trim_enabled and self.trim_position == "post":
            pretrim_path = os.path.join(raw_dir, f"{prefix}_pretrim_{idx:03d}_{self.run_stamp}.png")
            self._download_file(result_url, pretrim_path)
            self._trim_image_file(pretrim_path, output_path, "Ð² ÐºÐ¾Ð½Ñ†Ðµ")
            return
        self._download_file(result_url, output_path)

    def _save_image_as_png(self, source_path, output_path):
        with Image.open(source_path) as img:
            if img.mode not in {"RGB", "RGBA"}:
                img = img.convert("RGBA")
            img.save(output_path, format="PNG")

    def _trim_image_file(self, source_path, output_path, stage_label):
        with Image.open(source_path) as img:
            bbox = self._detect_trim_bbox(img)
            if not bbox:
                self.progress.emit(f"  Trim {stage_label}: Ð¿ÑƒÑÑ‚Ñ‹Ðµ ÐºÑ€Ð°Ñ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ñ‹")
                self._save_image_as_png(source_path, output_path)
                return output_path

            if bbox == (0, 0, img.width, img.height):
                self.progress.emit(f"  Trim {stage_label}: Ð¾Ð±Ñ€ÐµÐ·ÐºÐ° Ð½Ðµ Ñ‚Ñ€ÐµÐ±ÑƒÐµÑ‚ÑÑ")
                self._save_image_as_png(source_path, output_path)
                return output_path

            cropped = img.crop(bbox)
            if cropped.mode not in {"RGB", "RGBA"}:
                cropped = cropped.convert("RGBA")
            cropped.save(output_path, format="PNG")
            self.progress.emit(f"  Trim {stage_label}: {img.width}x{img.height} â†’ {cropped.width}x{cropped.height}")
            return output_path

    def _detect_trim_bbox(self, image):
        mode = (self.trim_mode or "alpha").lower()
        if mode == "white":
            return self._detect_white_trim_bbox(image)
        return self._detect_alpha_trim_bbox(image)

    def _detect_alpha_trim_bbox(self, image):
        rgba = image.convert("RGBA")
        alpha = rgba.split()[-1]
        return alpha.getbbox()

    def _detect_white_trim_bbox(self, image):
        threshold = 255
        rgb = image.convert("RGB")
        r, g, b = rgb.split()
        mask_r = r.point(lambda v: 255 if v < threshold else 0)
        mask_g = g.point(lambda v: 255 if v < threshold else 0)
        mask_b = b.point(lambda v: 255 if v < threshold else 0)
        mask = ImageChops.lighter(mask_r, ImageChops.lighter(mask_g, mask_b))

        rgba = image.convert("RGBA")
        alpha_non_empty = rgba.split()[-1].point(lambda v: 255 if v > 0 else 0)
        mask = ImageChops.multiply(mask, alpha_non_empty)
        return mask.getbbox()

    def _resolve_upscale_factor(self):
        model_name = (self.kie_upscale_model or "").strip()
        if model_name == "recraft/crisp-upscale":
            return 4
        if model_name == "topaz/upscale":
            return self.upscale_factor if self.upscale_factor in {2, 4, 8} else 4
        return self.upscale_factor if self.upscale_factor in {2, 3, 4} else 4

    def _kie_headers(self):
        return {
            "Authorization": f"Bearer {self.kie_api_key}",
            "Accept": "application/json",
            "User-Agent": "ClipartGenerator/1.0 (+PyQt6)",
        }

    def _request_with_retries(self, req, timeout=None):
        req_timeout = timeout or self.timeout
        last_error = None
        ssl_context = build_ssl_context()
        for attempt in range(self.retries + 1):
            try:
                with request.urlopen(req, timeout=req_timeout, context=ssl_context) as resp:
                    return resp.read()
            except urlerror.HTTPError as e:
                response_body = ""
                try:
                    response_body = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    response_body = ""

                error_message = f"HTTP {e.code} {e.reason}"
                if response_body:
                    error_message = f"{error_message}: {response_body[:300]}"

                last_error = RuntimeError(error_message)

                # ÐÐµ Ñ€ÐµÑ‚Ñ€Ð°Ð¸Ð¼ Ð¾ÑˆÐ¸Ð±ÐºÐ¸ Ð°Ð²Ñ‚Ð¾Ñ€Ð¸Ð·Ð°Ñ†Ð¸Ð¸/Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð°, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð»Ð¾Ð³ Ð±Ñ‹Ð» Ð¿Ð¾Ð½ÑÑ‚Ð½ÐµÐµ.
                if e.code in {400, 401, 403, 404}:
                    break

                if attempt >= self.retries:
                    break
                self.progress.emit(f"  ÐŸÐ¾Ð²Ñ‚Ð¾Ñ€ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ° {attempt + 1}/{self.retries}")
                time.sleep(min(2 * (attempt + 1), 6))
            except Exception as e:
                last_error = e
                if attempt >= self.retries:
                    break
                self.progress.emit(f"  ÐŸÐ¾Ð²Ñ‚Ð¾Ñ€ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ° {attempt + 1}/{self.retries}")
                time.sleep(min(2 * (attempt + 1), 6))
        raise RuntimeError(f"ÐžÑˆÐ¸Ð±ÐºÐ° HTTP-Ð·Ð°Ð¿Ñ€Ð¾ÑÐ°: {last_error}")

    def _request_json(self, url, method="GET", payload=None, headers=None, timeout=None):
        req_headers = headers or {}
        data_bytes = None
        if payload is not None:
            data_bytes = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data_bytes, headers=req_headers, method=method)
        raw = self._request_with_retries(req, timeout=timeout)
        return json.loads(raw.decode("utf-8"))

    def _kie_upload_file(self, file_path):
        boundary = "----ClipartBoundary" + uuid.uuid4().hex
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        parts = []
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(b'Content-Disposition: form-data; name="uploadPath"\r\n\r\n')
        parts.append(self.kie_upload_path.encode("utf-8"))
        parts.append(b"\r\n")
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"))
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        parts.append(file_bytes)
        parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))

        upload_urls = [
            "https://api.kie.ai/api/file-stream-upload",
            "https://kieai.redpandaai.co/api/file-stream-upload",
        ]

        last_error = None
        body = b"".join(parts)

        for upload_url in upload_urls:
            try:
                headers = self._kie_headers()
                headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
                headers["x-api-key"] = self.kie_api_key

                self.progress.emit(f"  Upload endpoint: {upload_url}")
                req = request.Request(upload_url, data=body, headers=headers, method="POST")
                payload = json.loads(self._request_with_retries(req, timeout=max(30, self.timeout)).decode("utf-8"))

                # ÐŸÐ¾Ð´Ð´ÐµÑ€Ð¶ÐºÐ° Ñ€Ð°Ð·Ð½Ñ‹Ñ… Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ð¾Ð² Ð¾Ñ‚Ð²ÐµÑ‚Ð° API.
                if payload.get("success") is False:
                    raise RuntimeError(payload.get("msg") or "ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ Ñ„Ð°Ð¹Ð»Ð° Ð² KIE")

                data = payload.get("data") or {}
                download_url = data.get("downloadUrl") or data.get("url") or payload.get("url")
                if download_url:
                    return download_url

                raise RuntimeError("KIE upload Ð½Ðµ Ð²ÐµÑ€Ð½ÑƒÐ» downloadUrl/url")
            except Exception as e:
                last_error = e
                self.progress.emit(f"  Upload Ð¾ÑˆÐ¸Ð±ÐºÐ°: {e}")

        # Fallback: URL Upload API Ð¸Ð· Ð´Ð¾ÐºÑƒÐ¼ÐµÐ½Ñ‚Ð°Ñ†Ð¸Ð¸ KIE.
        # Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ data URL, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð½Ðµ Ñ‚Ñ€ÐµÐ±Ð¾Ð²Ð°Ñ‚ÑŒ Ð²Ð½ÐµÑˆÐ½Ð¸Ð¹ Ñ…Ð¾ÑÑ‚Ð¸Ð½Ð³ Ñ„Ð°Ð¹Ð»Ð°.
        try:
            import base64

            with open(file_path, "rb") as f:
                file_bytes = f.read()
            b64 = base64.b64encode(file_bytes).decode("ascii")
            data_url = f"data:{content_type};base64,{b64}"

            headers = self._kie_headers()
            headers["Content-Type"] = "application/json"
            payload = {
                "fileUrl": data_url,
                "uploadPath": self.kie_upload_path,
                "fileName": filename,
            }
            self.progress.emit("  Upload endpoint: https://kieai.redpandaai.co/api/file-url-upload (fallback)")
            result = self._request_json(
                "https://kieai.redpandaai.co/api/file-url-upload",
                method="POST",
                payload=payload,
                headers=headers,
                timeout=max(30, self.timeout),
            )

            if result.get("success") is False:
                raise RuntimeError(result.get("msg") or "ÐžÑˆÐ¸Ð±ÐºÐ° URL Upload Ð² KIE")
            data = result.get("data") or {}
            download_url = data.get("downloadUrl") or data.get("url") or result.get("url")
            if download_url:
                return download_url
            raise RuntimeError("KIE URL upload Ð½Ðµ Ð²ÐµÑ€Ð½ÑƒÐ» downloadUrl/url")
        except Exception as e:
            self.progress.emit(f"  URL Upload fallback Ð¾ÑˆÐ¸Ð±ÐºÐ°: {e}")

        raise RuntimeError(
            "ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð·Ð°Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ Ñ„Ð°Ð¹Ð» Ð² KIE. ÐŸÑ€Ð¾Ð²ÐµÑ€ÑŒÑ‚Ðµ API key, upload path Ð¸ Ð¿Ñ€Ð°Ð²Ð° Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð°. "
            f"ÐŸÐ¾ÑÐ»ÐµÐ´Ð½ÑÑ Ð¾ÑˆÐ¸Ð±ÐºÐ°: {last_error}"
        )

    def _kie_create_task(self, model, input_payload):
        headers = self._kie_headers()
        headers["Content-Type"] = "application/json"
        result = self._request_json(
            "https://api.kie.ai/api/v1/jobs/createTask",
            method="POST",
            payload={"model": model, "input": input_payload},
            headers=headers,
            timeout=max(30, self.timeout),
        )
        if int(result.get("code", 0)) != 200:
            raise RuntimeError(result.get("msg") or "ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ ÑÐ¾Ð·Ð´Ð°Ñ‚ÑŒ Ð·Ð°Ð´Ð°Ñ‡Ñƒ KIE")
        task_id = (result.get("data") or {}).get("taskId")
        if not task_id:
            raise RuntimeError("KIE createTask Ð½Ðµ Ð²ÐµÑ€Ð½ÑƒÐ» taskId")
        return task_id

    def _kie_run_model_task(self, model, image_url, extra_input=None):
        input_payload = {} if model == "topaz/upscale" else {"image": image_url}
        if isinstance(extra_input, dict):
            input_payload.update(extra_input)
        task_id = self._kie_create_task(model, input_payload)
        self.progress.emit(f"  Task ID: {task_id}")
        return self._kie_wait_result(task_id)

    def _resolve_reference_url(self, reference_value):
        ref = str(reference_value or "").strip()
        if not ref:
            return ""
        parsed = urlparse(ref)
        if parsed.scheme in {"http", "https"}:
            return ref
        if not os.path.isfile(ref):
            raise RuntimeError(f"Ð ÐµÑ„ÐµÑ€ÐµÐ½Ñ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½: {ref}")
        self.progress.emit(f"  Ð—Ð°Ð³Ñ€ÑƒÐ·ÐºÐ° Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÐ°: {os.path.basename(ref)}")
        return self._kie_upload_file(ref)

    def _resolve_reference_urls(self, references=None):
        ref_items = split_references(references or [])
        if len(ref_items) > MAX_REFERENCES_PER_PROMPT:
            raise RuntimeError(f"ÐœÐ°ÐºÑÐ¸Ð¼ÑƒÐ¼ {MAX_REFERENCES_PER_PROMPT} Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÐ¾Ð² Ð½Ð° Ð¾Ð´Ð¸Ð½ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚")
        urls = []
        for ref in ref_items:
            resolved = self._resolve_reference_url(ref)
            if resolved:
                urls.append(resolved)
        return urls

    def _kie_generate_image(self, prompt, references=None):
        reference_urls = self._resolve_reference_urls(references)
        normalized_model = self._select_generation_model(reference_urls)
        model_meta = GENERATION_MODEL_META.get(normalized_model, {})
        model_type = model_meta.get("type", "text_to_image")

        if model_type in {"image_to_image", "edit"} and not reference_urls:
            raise RuntimeError("Ð”Ð»Ñ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ð½Ð¾Ð¹ Ð¼Ð¾Ð´ÐµÐ»Ð¸ Ð½ÑƒÐ¶ÐµÐ½ Ñ€ÐµÑ„ÐµÑ€ÐµÐ½Ñ Ð¸Ð·Ð¾Ð±Ñ€Ð°Ð¶ÐµÐ½Ð¸Ñ")

        if normalized_model == "gpt4o-image":
            if reference_urls:
                raise RuntimeError("ÐœÐ¾Ð´ÐµÐ»ÑŒ GPTâ€‘4o Image Ð½Ðµ Ð¿Ð¾Ð´Ð´ÐµÑ€Ð¶Ð¸Ð²Ð°ÐµÑ‚ Ñ€ÐµÑ„ÐµÑ€ÐµÐ½Ñ Ð² ÑÑ‚Ð¾Ð¼ Ñ€ÐµÐ¶Ð¸Ð¼Ðµ")
            return self._kie_generate_4o_image(prompt)
        return self._kie_generate_generic_model(normalized_model, prompt, reference_urls=reference_urls)

    def _select_generation_model(self, reference_urls):
        has_references = bool(reference_urls)
        preferred_model = self.reference_generation_model if has_references else self.text_generation_model
        normalized = self._normalize_generation_model(preferred_model)
        model_meta = GENERATION_MODEL_META.get(normalized, {})
        model_type = model_meta.get("type")

        if has_references and model_type in {"image_to_image", "edit"}:
            return normalized
        if not has_references and model_type == "text_to_image":
            return normalized

        fallback = self._default_generation_model("image_to_image" if has_references else "text_to_image")
        self.progress.emit(
            (
                f"  Ð’Ñ‹Ð±Ñ€Ð°Ð½Ð½Ð°Ñ Ð¼Ð¾Ð´ÐµÐ»ÑŒ '{normalized}' Ð½Ðµ Ð¿Ð¾Ð´Ñ…Ð¾Ð´Ð¸Ñ‚ Ð´Ð»Ñ Ñ‚ÐµÐºÑƒÑ‰ÐµÐ³Ð¾ Ñ€ÐµÐ¶Ð¸Ð¼Ð°. "
                f"Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ '{fallback}'."
            )
        )
        return fallback

    def _default_generation_model(self, required_type):
        if required_type == "image_to_image" and "qwen/image-to-image" in GENERATION_MODEL_META:
            return "qwen/image-to-image"
        for entry in GENERATION_MODELS:
            if entry.get("type") == required_type:
                return entry.get("id")
        return "gpt4o-image"

    def _normalize_generation_model(self, model_name):
        model = (model_name or "").strip()
        if not model:
            self.progress.emit("  ÐœÐ¾Ð´ÐµÐ»ÑŒ Ð½Ðµ ÑƒÐºÐ°Ð·Ð°Ð½Ð°. Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ gpt4o-image.")
            return "gpt4o-image"

        if model in {"gpt4o-image", "gpt-image-1", "gpt-image-1.5"}:
            return "gpt4o-image"

        if model == "flux-kontext":
            return "black-forest-labs/flux-kontext-pro"

        if model in {"z-image", "zai-org/z-image"}:
            return "z-image"

        if model in {
            "google/nano-banana",
            "google/nano-banana-edit",
            "google/imagen4",
            "google/imagen4-fast",
            "google/imagen4-ultra",
            "flux-2/flex-text-to-image",
            "flux-2/pro-text-to-image",
            "black-forest-labs/flux-kontext-pro",
            "black-forest-labs/flux-kontext-max",
        }:
            return model

        # Ð’Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÐ¼ Ð¸ÑÑ…Ð¾Ð´Ð½Ð¾Ðµ Ð¸Ð¼Ñ, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð¿Ð¾Ð´Ð´ÐµÑ€Ð¶Ð¸Ð²Ð°Ñ‚ÑŒ Ð½Ð¾Ð²Ñ‹Ðµ Ð¼Ð¾Ð´ÐµÐ»Ð¸ Ð±ÐµÐ· Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ ÐºÐ¾Ð´Ð°.
        self.progress.emit(f"  Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ÑÑ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒÑÐºÐ°Ñ Ð¼Ð¾Ð´ÐµÐ»ÑŒ: {model}")
        return model

    def _kie_generate_4o_image(self, prompt):
        headers = self._kie_headers()
        headers["Content-Type"] = "application/json"
        ratio = self._normalize_ratio(self.generation_size)
        legacy_size = self._ratio_to_legacy_size(ratio)

        # Ð”Ð»Ñ 4o API Ñ‡Ð°Ñ‰Ðµ Ð²ÑÐµÐ³Ð¾ Ð½ÑƒÐ¶ÐµÐ½ size Ð² px, Ð½Ð¾ Ð¾ÑÑ‚Ð°Ð²Ð»ÑÐµÐ¼ fallback-Ð²Ð°Ñ€Ð¸Ð°Ð½Ñ‚Ñ‹.
        payload_variants = [
            {"prompt": prompt, "size": legacy_size},
            {"prompt": prompt, "size": ratio},
            {"prompt": prompt, "aspectRatio": ratio},
            {"prompt": prompt, "aspect_ratio": ratio},
        ]

        result = None
        last_error = None
        for payload in payload_variants:
            try:
                result = self._request_json(
                    "https://api.kie.ai/api/v1/gpt4o-image/generate",
                    method="POST",
                    payload=payload,
                    headers=headers,
                    timeout=max(30, self.timeout),
                )
                if int(result.get("code", 0)) == 200:
                    break
                last_error = RuntimeError(result.get("msg") or "ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ñ Ð·Ð°Ð´Ð°Ñ‡Ð¸ 4o Image")
            except Exception as e:
                last_error = e

        if result is None or int(result.get("code", 0)) != 200:
            if result is not None:
                raise RuntimeError(result.get("msg") or "ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ñ Ð·Ð°Ð´Ð°Ñ‡Ð¸ 4o Image")
            raise RuntimeError(str(last_error) if last_error else "ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ñ Ð·Ð°Ð´Ð°Ñ‡Ð¸ 4o Image")

        task_id = (result.get("data") or {}).get("taskId")
        if not task_id:
            raise RuntimeError("4o Image Ð½Ðµ Ð²ÐµÑ€Ð½ÑƒÐ» taskId")
        self.progress.emit(f"  4o Task ID: {task_id}")
        return self._kie_wait_4o_result(task_id)

    def _kie_generate_generic_model(self, model_name, prompt, reference_urls=None):
        reference_urls = reference_urls or []
        ratio = self._normalize_ratio(self.generation_size)
        legacy_size = self._ratio_to_legacy_size(ratio)

        if model_name == "z-image":
            model_candidates = ["z-image", "zai-org/z-image"]
        else:
            model_candidates = [model_name]

        if reference_urls:
            input_variants = self._build_reference_input_variants(model_name, prompt, reference_urls, ratio, legacy_size)
        else:
            if model_name == "gpt-image/1.5-text-to-image":
                input_variants = [
                    {"prompt": prompt, "aspect_ratio": ratio, "quality": "medium"},
                    {"prompt": prompt, "aspect_ratio": ratio, "quality": "high"},
                    {"prompt": prompt, "aspectRatio": ratio, "quality": "medium"},
                    {"prompt": prompt, "size": ratio, "quality": "medium"},
                    {"prompt": prompt, "size": legacy_size, "quality": "medium"},
                ]
            elif model_name in {"flux-2/pro-text-to-image", "flux-2/flex-text-to-image"}:
                input_variants = [
                    {"prompt": prompt, "aspect_ratio": ratio, "resolution": "2K"},
                    {"prompt": prompt, "aspect_ratio": ratio, "resolution": "1K"},
                    {"prompt": prompt, "aspectRatio": ratio, "resolution": "2K"},
                    {"prompt": prompt, "aspectRatio": ratio, "resolution": "1K"},
                    {"prompt": prompt, "aspect_ratio": ratio},
                    {"prompt": prompt, "size": ratio},
                ]
            elif model_name == "google/nano-banana":
                input_variants = [
                    {"prompt": prompt, "image_size": ratio},
                    {"prompt": prompt, "image_size": "auto"},
                    {"prompt": prompt, "output_format": "png", "image_size": ratio},
                    {"prompt": prompt, "output_format": "jpeg", "image_size": ratio},
                    {"prompt": prompt, "size": ratio},
                ]
            elif model_name == "qwen/text-to-image":
                input_variants = [
                    {"prompt": prompt, "image_size": "square_hd"},
                    {"prompt": prompt, "image_size": self._ratio_to_qwen_image_size(ratio)},
                    {"prompt": prompt, "output_format": "png", "image_size": self._ratio_to_qwen_image_size(ratio)},
                    {"prompt": prompt, "output_format": "jpeg", "image_size": self._ratio_to_qwen_image_size(ratio)},
                    {"prompt": prompt, "size": ratio},
                ]
            else:
                input_variants = [
                    {"prompt": prompt, "size": ratio},
                    {"prompt": prompt, "aspectRatio": ratio},
                    {"prompt": prompt, "aspect_ratio": ratio},
                    {"prompt": prompt, "size": legacy_size},
                    {"prompt": prompt, "image_size": legacy_size},
                ]

        prompt_variants = [prompt]
        if model_name == "z-image":
            compact_prompt = " ".join((prompt or "").split())
            if compact_prompt and compact_prompt != prompt:
                prompt_variants.append(compact_prompt)
            for limit in (1200, 900, 700, 500):
                if compact_prompt and len(compact_prompt) > limit:
                    prompt_variants.append(compact_prompt[:limit])

        last_error = None
        for candidate in model_candidates:
            for candidate_prompt in prompt_variants:
                for input_payload in input_variants:
                    payload = dict(input_payload)
                    payload["prompt"] = candidate_prompt
                    try:
                        task_id = self._kie_create_task(candidate, payload)
                        self.progress.emit(f"  Task ID: {task_id}")
                        return self._kie_wait_result(task_id)
                    except Exception as e:
                        last_error = e
                        self.progress.emit(f"  ÐœÐ¾Ð´ÐµÐ»ÑŒ {candidate} / input {list(payload.keys())} Ð½ÐµÐ´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð°: {e}")

        # Ð¤Ð¾Ð»Ð±ÑÐº Ð´Ð»Ñ ÑÑ‚Ð°Ñ€Ñ‹Ñ… Ñ€ÐµÐ°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ð¹ API.
        fallback_input = {
            "prompt": prompt,
            "size": legacy_size,
        }
        if reference_urls:
            fallback_input["image"] = reference_urls[0]
            if len(reference_urls) > 1:
                fallback_input["images"] = list(reference_urls)

        fallback_task_id = self._kie_create_task(model_name, fallback_input)
        self.progress.emit(f"  Task ID: {fallback_task_id}")
        return self._kie_wait_result(fallback_task_id)

    def _build_reference_input_variants(self, model_name, prompt, reference_urls, ratio, legacy_size):
        primary_ref = reference_urls[0]
        image_list = list(reference_urls)

        common_variants = [
            {"prompt": prompt, "image": primary_ref, "size": ratio},
            {"prompt": prompt, "image_url": primary_ref, "size": ratio},
            {"prompt": prompt, "imageUrl": primary_ref, "size": ratio},
            {"prompt": prompt, "fileUrl": primary_ref, "size": ratio},
            {"prompt": prompt, "inputImage": primary_ref, "size": ratio},
            {"prompt": prompt, "images": image_list, "size": ratio},
            {"prompt": prompt, "image_urls": image_list, "size": ratio},
            {"prompt": prompt, "imageUrls": image_list, "size": ratio},
            {"prompt": prompt, "input_urls": image_list, "size": ratio},
            {"prompt": prompt, "inputUrls": image_list, "size": ratio},
            {"prompt": prompt, "filesUrl": image_list, "size": ratio},
            {"prompt": prompt, "image": primary_ref, "aspectRatio": ratio},
            {"prompt": prompt, "image": primary_ref, "aspect_ratio": ratio},
            {"prompt": prompt, "input_urls": image_list, "aspectRatio": ratio},
            {"prompt": prompt, "input_urls": image_list, "aspect_ratio": ratio},
            {"prompt": prompt, "image": primary_ref, "size": legacy_size},
            {"prompt": prompt, "input_urls": image_list, "size": legacy_size},
            {"prompt": prompt, "filesUrl": image_list, "size": legacy_size},
            {"prompt": prompt, "fileUrl": primary_ref, "size": legacy_size},
        ]

        prioritized_variants = {
            "qwen/image-to-image": [
                {"prompt": prompt, "image_url": primary_ref},
                {"prompt": prompt, "image_url": primary_ref, "strength": 0.8},
                {"prompt": prompt, "image_url": primary_ref, "output_format": "png"},
                {"prompt": prompt, "image": primary_ref, "size": ratio},
                {"prompt": prompt, "imageUrl": primary_ref, "size": ratio},
            ],
            "google/nano-banana-edit": [
                {"prompt": prompt, "image_urls": image_list, "image_size": ratio},
                {"prompt": prompt, "image_urls": image_list, "image_size": "auto"},
                {"prompt": prompt, "image_urls": image_list, "output_format": "png", "image_size": ratio},
                {"prompt": prompt, "images": image_list, "size": ratio},
                {"prompt": prompt, "imageUrls": image_list, "size": ratio},
            ],
            "gpt-image/1.5-image-to-image": [
                {"prompt": prompt, "input_urls": image_list, "aspect_ratio": ratio, "quality": "medium"},
                {"prompt": prompt, "input_urls": image_list, "aspect_ratio": ratio, "quality": "high"},
                {"prompt": prompt, "input_urls": image_list, "aspect_ratio": "1:1", "quality": "medium"},
                {"prompt": prompt, "input_urls": image_list, "aspect_ratio": ratio},
                {"prompt": prompt, "inputUrls": image_list, "aspect_ratio": ratio, "quality": "medium"},
                {"prompt": prompt, "input_urls": image_list, "aspectRatio": ratio, "quality": "medium"},
            ],
            "flux-2/pro-image-to-image": [
                {"prompt": prompt, "input_urls": image_list, "aspect_ratio": ratio, "resolution": "2K"},
                {"prompt": prompt, "input_urls": image_list, "aspect_ratio": ratio, "resolution": "1K"},
                {"prompt": prompt, "inputUrls": image_list, "aspect_ratio": ratio, "resolution": "2K"},
                {"prompt": prompt, "inputUrls": image_list, "aspect_ratio": ratio, "resolution": "1K"},
                {"prompt": prompt, "input_urls": image_list, "aspect_ratio": ratio},
                {"prompt": prompt, "input_urls": image_list, "size": ratio},
                {"prompt": prompt, "inputUrls": image_list, "size": ratio},
                {"prompt": prompt, "input_urls": image_list, "aspectRatio": ratio},
                {"prompt": prompt, "input_urls": image_list, "size": legacy_size},
            ],
            "flux-2/flex-image-to-image": [
                {"prompt": prompt, "input_urls": image_list, "aspect_ratio": ratio, "resolution": "2K"},
                {"prompt": prompt, "input_urls": image_list, "aspect_ratio": ratio, "resolution": "1K"},
                {"prompt": prompt, "inputUrls": image_list, "aspect_ratio": ratio, "resolution": "2K"},
                {"prompt": prompt, "inputUrls": image_list, "aspect_ratio": ratio, "resolution": "1K"},
                {"prompt": prompt, "input_urls": image_list, "aspect_ratio": ratio},
                {"prompt": prompt, "input_urls": image_list, "size": ratio},
                {"prompt": prompt, "inputUrls": image_list, "size": ratio},
                {"prompt": prompt, "input_urls": image_list, "aspectRatio": ratio},
                {"prompt": prompt, "input_urls": image_list, "size": legacy_size},
            ],
            "grok-imagine/image-to-image": [
                {"prompt": prompt, "image_urls": image_list, "size": ratio},
                {"prompt": prompt, "images": image_list, "size": ratio},
                {"prompt": prompt, "imageUrls": image_list, "size": ratio},
            ],
        }

        variants = []
        seen = set()
        for payload in prioritized_variants.get(model_name, []) + common_variants:
            key = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            variants.append(payload)
        return variants

    def _build_reference_probe_variants(self, model_name, prompt, sample_image_url, ratio, legacy_size):
        reference_variants = self._build_reference_input_variants(
            model_name,
            prompt,
            [sample_image_url],
            ratio,
            legacy_size,
        )
        return [{"model": model_name, "input": payload} for payload in reference_variants]

    def _build_text_probe_variants(self, model_name, prompt, ratio, legacy_size):
        if model_name == "gpt-image/1.5-text-to-image":
            input_variants = [
                {"prompt": prompt, "aspect_ratio": ratio, "quality": "medium"},
                {"prompt": prompt, "aspect_ratio": ratio, "quality": "high"},
                {"prompt": prompt, "aspectRatio": ratio, "quality": "medium"},
                {"prompt": prompt, "size": ratio, "quality": "medium"},
                {"prompt": prompt, "size": legacy_size, "quality": "medium"},
            ]
        elif model_name in {"flux-2/pro-text-to-image", "flux-2/flex-text-to-image"}:
            input_variants = [
                {"prompt": prompt, "aspect_ratio": ratio, "resolution": "2K"},
                {"prompt": prompt, "aspect_ratio": ratio, "resolution": "1K"},
                {"prompt": prompt, "aspectRatio": ratio, "resolution": "2K"},
                {"prompt": prompt, "aspectRatio": ratio, "resolution": "1K"},
                {"prompt": prompt, "aspect_ratio": ratio},
                {"prompt": prompt, "size": ratio},
            ]
        elif model_name == "google/nano-banana":
            input_variants = [
                {"prompt": prompt, "image_size": ratio},
                {"prompt": prompt, "image_size": "auto"},
                {"prompt": prompt, "output_format": "png", "image_size": ratio},
                {"prompt": prompt, "output_format": "jpeg", "image_size": ratio},
                {"prompt": prompt, "size": ratio},
            ]
        elif model_name == "qwen/text-to-image":
            qwen_size = self._ratio_to_qwen_image_size(ratio)
            input_variants = [
                {"prompt": prompt, "image_size": "square_hd"},
                {"prompt": prompt, "image_size": qwen_size},
                {"prompt": prompt, "output_format": "png", "image_size": qwen_size},
                {"prompt": prompt, "output_format": "jpeg", "image_size": qwen_size},
                {"prompt": prompt, "size": ratio},
            ]
        else:
            input_variants = [
                {"prompt": prompt, "size": ratio},
                {"prompt": prompt, "aspectRatio": ratio},
                {"prompt": prompt, "aspect_ratio": ratio},
                {"prompt": prompt, "size": legacy_size},
                {"prompt": prompt, "image_size": legacy_size},
            ]

        return [{"model": model_name, "input": payload} for payload in input_variants]

    def _normalize_ratio(self, value):
        raw = (value or "").strip()
        allowed = {"1:1", "4:3", "3:4", "16:9", "9:16"}
        legacy_map = {
            "1024x1024": "1:1",
            "1024x1536": "3:4",
            "1536x1024": "4:3",
        }
        if raw in allowed:
            return raw
        if raw in legacy_map:
            return legacy_map[raw]
        return "1:1"

    def _ratio_to_legacy_size(self, ratio):
        return {
            "1:1": "1024x1024",
            "4:3": "1536x1024",
            "3:4": "1024x1536",
            "16:9": "1536x1024",
            "9:16": "1024x1536",
        }.get(ratio, "1024x1024")

    def _ratio_to_qwen_image_size(self, ratio):
        return {
            "1:1": "square_hd",
            "4:3": "landscape_4_3",
            "3:4": "portrait_4_3",
            "16:9": "landscape_16_9",
            "9:16": "portrait_16_9",
        }.get(ratio, "square_hd")

    def _kie_wait_4o_result(self, task_id):
        timeout_sec = self.generation_wait_timeout
        deadline = time.time() + timeout_sec
        headers = self._kie_headers()
        while time.time() < deadline:
            if not self.is_running:
                raise RuntimeError("ÐžÑÑ‚Ð°Ð½Ð¾Ð²Ð»ÐµÐ½Ð¾ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¼")

            url = f"https://api.kie.ai/api/v1/gpt4o-image/record-info?{parse.urlencode({'taskId': task_id})}"
            result = self._request_json(url, method="GET", headers=headers, timeout=30)
            if int(result.get("code", 0)) != 200:
                raise RuntimeError(result.get("msg") or "ÐžÑˆÐ¸Ð±ÐºÐ° ÑÑ‚Ð°Ñ‚ÑƒÑÐ° 4o Image")

            data = result.get("data") or {}
            status = str(data.get("status", "")).upper()
            self.progress.emit(f"  4o ÑÑ‚Ð°Ñ‚ÑƒÑ: {status}")
            if status == "SUCCESS":
                urls = ((data.get("response") or {}).get("resultUrls") or [])
                if urls:
                    return urls[0]
                raise RuntimeError("4o Image Ð½Ðµ Ð²ÐµÑ€Ð½ÑƒÐ» resultUrls")
            if status in {"FAILED", "FAIL", "ERROR"}:
                raise RuntimeError(data.get("errorMessage") or "4o Image Ð²ÐµÑ€Ð½ÑƒÐ» Ð¾ÑˆÐ¸Ð±ÐºÑƒ")
            time.sleep(self.status_poll_interval)
        raise TimeoutError("ÐŸÑ€ÐµÐ²Ñ‹ÑˆÐµÐ½Ð¾ Ð²Ñ€ÐµÐ¼Ñ Ð¾Ð¶Ð¸Ð´Ð°Ð½Ð¸Ñ 4o Image")

    def _kie_wait_result(self, task_id):
        timeout_sec = self.generation_wait_timeout
        deadline = time.time() + timeout_sec
        headers = self._kie_headers()
        while time.time() < deadline:
            if not self.is_running:
                raise RuntimeError("ÐžÑÑ‚Ð°Ð½Ð¾Ð²Ð»ÐµÐ½Ð¾ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¼")

            url = f"https://api.kie.ai/api/v1/jobs/recordInfo?{parse.urlencode({'taskId': task_id})}"
            result = self._request_json(url, method="GET", headers=headers, timeout=30)
            if int(result.get("code", 0)) != 200:
                raise RuntimeError(result.get("msg") or "ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ð¾Ð»ÑƒÑ‡ÐµÐ½Ð¸Ñ ÑÑ‚Ð°Ñ‚ÑƒÑÐ° KIE")

            data = result.get("data") or {}
            state = str(data.get("state", "")).lower()
            self.progress.emit(f"  Ð¡Ñ‚Ð°Ñ‚ÑƒÑ: {state}")
            if state in {"success", "succeeded"}:
                return self._extract_result_url(data.get("resultJson"))
            if state in {"fail", "failed", "error"}:
                raise RuntimeError(data.get("failMsg") or "KIE Ð²ÐµÑ€Ð½ÑƒÐ» fail")
            time.sleep(self.status_poll_interval)
        raise TimeoutError("ÐŸÑ€ÐµÐ²Ñ‹ÑˆÐµÐ½Ð¾ Ð²Ñ€ÐµÐ¼Ñ Ð¾Ð¶Ð¸Ð´Ð°Ð½Ð¸Ñ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ð° KIE")

    def _extract_result_url(self, result_json_raw):
        if not result_json_raw:
            raise RuntimeError("KIE Ð½Ðµ Ð²ÐµÑ€Ð½ÑƒÐ» resultJson")

        parsed = result_json_raw
        if isinstance(result_json_raw, str):
            parsed = json.loads(result_json_raw)

        if isinstance(parsed, dict):
            result_urls = parsed.get("resultUrls")
            if isinstance(result_urls, list) and result_urls:
                return result_urls[0]
            output = parsed.get("output")
            if isinstance(output, dict) and output.get("mediaUrl"):
                return output["mediaUrl"]

        raise RuntimeError("ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¸Ð·Ð²Ð»ÐµÑ‡ÑŒ URL Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ð° Ð¸Ð· resultJson")

    def _download_file(self, url, output_path):
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        }

        host = (urlparse(url).netloc or "").lower()
        # ÐÐµÐºÐ¾Ñ‚Ð¾Ñ€Ñ‹Ðµ CDN KIE/Redpanda Ð¾Ñ‚Ð´Ð°ÑŽÑ‚ 403 (Cloudflare 1010) Ð±ÐµÐ· auth-Ð·Ð°Ð³Ð¾Ð»Ð¾Ð²ÐºÐ¾Ð².
        if "redpandaai.co" in host or "kie.ai" in host:
            headers["Authorization"] = f"Bearer {self.kie_api_key}"
            headers["x-api-key"] = self.kie_api_key
            headers["Referer"] = "https://docs.kie.ai/"

        last_error = None
        attempts = [headers, {"User-Agent": headers["User-Agent"], "Accept": "*/*"}, {}]
        for idx, h in enumerate(attempts, start=1):
            try:
                req = request.Request(url, headers=h, method="GET")
                content = self._request_with_retries(req, timeout=60)
                if output_path.lower().endswith(".png"):
                    self._save_png_from_any_image_bytes(content, output_path)
                else:
                    with open(output_path, "wb") as f:
                        f.write(content)
                if output_path.lower().endswith(".png") and "output" in output_path.lower():
                    self._set_png_dpi(output_path, dpi=300)
                return
            except Exception as e:
                last_error = e
                self.progress.emit(f"  Download Ð¿Ð¾Ð¿Ñ‹Ñ‚ÐºÐ° {idx} Ð½Ðµ ÑƒÐ´Ð°Ð»Ð°ÑÑŒ: {e}")

        raise RuntimeError(f"ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ ÑÐºÐ°Ñ‡Ð°Ñ‚ÑŒ Ñ„Ð°Ð¹Ð» Ð¿Ð¾ URL ({host}): {last_error}")

    def _save_png_from_any_image_bytes(self, content, output_path):
        png_signature = b"\x89PNG\r\n\x1a\n"
        if content.startswith(png_signature):
            with open(output_path, "wb") as f:
                f.write(content)
            return

        try:
            with Image.open(BytesIO(content)) as img:
                img.save(output_path, format="PNG")
            self.progress.emit("  Ð¤Ð¾Ñ€Ð¼Ð°Ñ‚ Ð¾Ñ‚Ð²ÐµÑ‚Ð° Ð½Ðµ PNG: Ð²Ñ‹Ð¿Ð¾Ð»Ð½ÐµÐ½Ð° ÐºÐ¾Ð½Ð²ÐµÑ€Ñ‚Ð°Ñ†Ð¸Ñ Ð² PNG")
            return
        except Exception:
            pass

        head_hex = content[:16].hex().upper()
        head_text = content[:120].decode("utf-8", errors="ignore").strip().replace("\n", " ")
        raise RuntimeError(
            "Ð¡ÐµÑ€Ð²ÐµÑ€ Ð²ÐµÑ€Ð½ÑƒÐ» Ð½ÐµÐ²Ð°Ð»Ð¸Ð´Ð½Ñ‹Ð¹ ÐºÐ¾Ð½Ñ‚ÐµÐ½Ñ‚ Ð²Ð¼ÐµÑÑ‚Ð¾ Ð¸Ð·Ð¾Ð±Ñ€Ð°Ð¶ÐµÐ½Ð¸Ñ. "
            f"Ð¡Ð¸Ð³Ð½Ð°Ñ‚ÑƒÑ€Ð°: {head_hex}. ÐÐ°Ñ‡Ð°Ð»Ð¾ Ð¾Ñ‚Ð²ÐµÑ‚Ð°: {head_text[:100]}"
        )

    def _set_png_dpi(self, file_path, dpi=300):
        try:
            with Image.open(file_path) as img:
                if img.format != "PNG":
                    return
                img.save(file_path, format="PNG", dpi=(dpi, dpi))
            self.progress.emit(f"  Ð£ÑÑ‚Ð°Ð½Ð¾Ð²Ð»ÐµÐ½ DPI {dpi} Ð´Ð»Ñ {os.path.basename(file_path)}")
        except Exception as e:
            self.progress.emit(f"  ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ ÑƒÑÑ‚Ð°Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ DPI Ð´Ð»Ñ {os.path.basename(file_path)}: {e}")


class PromptTableWidget(QTableWidget):
    bulkTextPasted = pyqtSignal(str)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            text = QApplication.clipboard().text()
            if text:
                self.bulkTextPasted.emit(text)
                event.accept()
                return
        super().keyPressEvent(event)


class CsvImportDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._headers = []
        self._rows = []
        self._entries = []
        self._last_error = ""
        self._setup_ui()
        self._reload_data()

    def _setup_ui(self):
        self.setWindowTitle("Ð˜Ð¼Ð¿Ð¾Ñ€Ñ‚ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð² Ð¸Ð· CSV")
        self.resize(760, 520)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.delimiter_combo = QComboBox()
        self.delimiter_combo.addItem("ÐÐ²Ñ‚Ð¾", "auto")
        self.delimiter_combo.addItem(",", ",")
        self.delimiter_combo.addItem(";", ";")
        self.delimiter_combo.addItem("Ð¢Ð°Ð±", "\t")
        self.delimiter_combo.addItem("|", "|")

        self.header_checkbox = QCheckBox("ÐŸÐµÑ€Ð²Ð°Ñ ÑÑ‚Ñ€Ð¾ÐºÐ° â€” Ð·Ð°Ð³Ð¾Ð»Ð¾Ð²ÐºÐ¸")
        self.header_checkbox.setChecked(True)

        self.column_combo = QComboBox()
        self.references_column_combo = QComboBox()

        form.addRow("Ð Ð°Ð·Ð´ÐµÐ»Ð¸Ñ‚ÐµÐ»ÑŒ:", self.delimiter_combo)
        form.addRow("ÐšÐ¾Ð»Ð¾Ð½ÐºÐ° Ñ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð¼:", self.column_combo)
        form.addRow("ÐšÐ¾Ð»Ð¾Ð½ÐºÐ° Ñ Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÐ°Ð¼Ð¸:", self.references_column_combo)
        form.addRow("", self.header_checkbox)
        layout.addLayout(form)

        self.info_label = QLabel("")
        layout.addWidget(self.info_label)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Ð—Ð´ÐµÑÑŒ Ð±ÑƒÐ´ÐµÑ‚ Ð¿Ñ€ÐµÐ´Ð¿Ñ€Ð¾ÑÐ¼Ð¾Ñ‚Ñ€ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð²")
        layout.addWidget(self.preview_text)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("Ð˜Ð¼Ð¿Ð¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ")
        layout.addWidget(self.button_box)

        self.delimiter_combo.currentIndexChanged.connect(self._reload_data)
        self.header_checkbox.toggled.connect(self._reload_data)
        self.column_combo.currentIndexChanged.connect(self._refresh_preview)
        self.references_column_combo.currentIndexChanged.connect(self._refresh_preview)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def _read_csv_text(self):
        encodings = ["utf-8-sig", "cp1251", "utf-8"]
        last_error = None
        for enc in encodings:
            try:
                with open(self.file_path, "r", encoding=enc, newline="") as f:
                    return f.read()
            except Exception as e:
                last_error = e
        raise RuntimeError(f"ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¿Ñ€Ð¾Ñ‡Ð¸Ñ‚Ð°Ñ‚ÑŒ CSV: {last_error}")

    def _detect_delimiter(self, sample_text):
        selected = self.delimiter_combo.currentData()
        if selected and selected != "auto":
            return selected
        try:
            sniffed = csv.Sniffer().sniff(sample_text[:4096], delimiters=[",", ";", "\t", "|"])
            return sniffed.delimiter
        except Exception:
            return ","

    def _parse_rows(self, text, delimiter):
        reader = csv.reader(StringIO(text), delimiter=delimiter)
        rows = [row for row in reader if any(str(cell).strip() for cell in row)]
        if not rows:
            raise RuntimeError("CSV-Ñ„Ð°Ð¹Ð» Ð¿ÑƒÑÑ‚ Ð¸Ð»Ð¸ Ð½Ðµ ÑÐ¾Ð´ÐµÑ€Ð¶Ð¸Ñ‚ Ð´Ð°Ð½Ð½Ñ‹Ñ…")
        return rows

    def _reload_data(self):
        prev_column = self.column_combo.currentData()
        prev_references_column = self.references_column_combo.currentData()
        self._entries = []
        self._last_error = ""
        try:
            text = self._read_csv_text()
            delimiter = self._detect_delimiter(text)
            rows = self._parse_rows(text, delimiter)

            has_header = self.header_checkbox.isChecked()
            if has_header:
                headers = [str(h).strip() or f"ÐšÐ¾Ð»Ð¾Ð½ÐºÐ° {i + 1}" for i, h in enumerate(rows[0])]
                data_rows = rows[1:]
            else:
                max_cols = max(len(r) for r in rows)
                headers = [f"ÐšÐ¾Ð»Ð¾Ð½ÐºÐ° {i + 1}" for i in range(max_cols)]
                data_rows = rows

            max_cols = max(len(headers), max((len(r) for r in data_rows), default=0))
            headers = headers + [f"ÐšÐ¾Ð»Ð¾Ð½ÐºÐ° {i + 1}" for i in range(len(headers), max_cols)]
            normalized_rows = [r + [""] * (max_cols - len(r)) for r in data_rows]

            self._headers = headers
            self._rows = normalized_rows

            self.column_combo.blockSignals(True)
            self.column_combo.clear()
            for index, name in enumerate(self._headers):
                self.column_combo.addItem(name, index)
            target_index = prev_column if isinstance(prev_column, int) and 0 <= prev_column < len(self._headers) else 0
            self.column_combo.setCurrentIndex(target_index)
            self.column_combo.blockSignals(False)

            self.references_column_combo.blockSignals(True)
            self.references_column_combo.clear()
            self.references_column_combo.addItem("Ð‘ÐµÐ· Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÐ¾Ð²", -1)
            for index, name in enumerate(self._headers):
                self.references_column_combo.addItem(name, index)
            if isinstance(prev_references_column, int) and -1 <= prev_references_column < len(self._headers):
                ref_index = self.references_column_combo.findData(prev_references_column)
                self.references_column_combo.setCurrentIndex(ref_index if ref_index >= 0 else 0)
            else:
                self.references_column_combo.setCurrentIndex(0)
            self.references_column_combo.blockSignals(False)

            selected_col = self.column_combo.currentData()
            selected_refs_col = self.references_column_combo.currentData()
            self._entries = self._build_entries(selected_col, selected_refs_col)
            delim_name = "TAB" if delimiter == "\t" else delimiter
            self.info_label.setText(
                f"Ð¡Ñ‚Ñ€Ð¾Ðº Ð´Ð°Ð½Ð½Ñ‹Ñ…: {len(self._rows)} | Ð Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð½Ð¾ Ð·Ð°Ð¿Ð¸ÑÐµÐ¹: {len(self._entries)} | Ð Ð°Ð·Ð´ÐµÐ»Ð¸Ñ‚ÐµÐ»ÑŒ: {delim_name}"
            )
            self._refresh_preview()
        except Exception as e:
            self._headers = []
            self._rows = []
            self._last_error = str(e)
            self.info_label.setText(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¸Ð¼Ð¿Ð¾Ñ€Ñ‚Ð°: {self._last_error}")
            self.preview_text.setPlainText("")

    def _build_entries(self, prompt_column_index, references_column_index):
        if not isinstance(prompt_column_index, int):
            return []
        entries = []
        for row in self._rows:
            if prompt_column_index >= len(row):
                continue
            prompt_text = str(row[prompt_column_index]).strip()
            references_text = ""
            if isinstance(references_column_index, int) and 0 <= references_column_index < len(row):
                references_text = str(row[references_column_index]).strip()
            references = split_references(references_text)
            if prompt_text or references:
                entries.append({"prompt": prompt_text, "references": references})
        return entries

    def _refresh_preview(self):
        if self._last_error:
            self.preview_text.setPlainText("")
            return
        selected_col = self.column_combo.currentData()
        selected_refs_col = self.references_column_combo.currentData()
        self._entries = self._build_entries(selected_col, selected_refs_col)
        preview_items = self._entries[:8]
        if not preview_items:
            self.preview_text.setPlainText("ÐÐµÑ‚ Ð·Ð°Ð¿Ð¸ÑÐµÐ¹ Ð´Ð»Ñ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ð½Ñ‹Ñ… ÐºÐ¾Ð»Ð¾Ð½Ð¾Ðº")
            return
        parts = []
        for idx, entry in enumerate(preview_items, start=1):
            prompt_text = entry.get("prompt", "")
            references_text = join_references(entry.get("references", []))
            detail_lines = [f"{idx}. {prompt_text}"]
            if references_text:
                detail_lines.append(f"Ð ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹: {references_text}")
            parts.append("\n".join(detail_lines))
        self.preview_text.setPlainText("\n\nâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€\n\n".join(parts))

    def get_entries(self):
        result = []
        for entry in self._entries:
            prompt_text = str(entry.get("prompt", "")).strip()
            references = split_references(entry.get("references", []))
            if prompt_text or references:
                result.append({"prompt": prompt_text, "references": references})
        return result


class PromptReferencesDialog(QDialog):
    def __init__(self, prompt_text, references, parent=None, refs_only=False):
        super().__init__(parent)
        self.refs_only = refs_only
        self._source_prompt = str(prompt_text or "")
        self.setWindowTitle("Ð ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð°" if refs_only else "Ð ÐµÐ´Ð°ÐºÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð° Ð¸ Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÐ¾Ð²")
        self.resize(760, 520)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlainText(str(prompt_text or ""))

        self.references_list = QListWidget()
        self.references_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.references_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.references_list.setMovement(QListWidget.Movement.Static)
        self.references_list.setWordWrap(True)
        self.references_list.setSpacing(8)
        self.references_list.setIconSize(QSize(96, 96))
        self.references_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.references_list.setStyleSheet(
            "QListWidget::item {border: 2px solid transparent; border-radius: 8px; padding: 4px;}"
            "QListWidget::item:selected {border: 2px solid #14b8a6; background: rgba(20, 184, 166, 0.08);}"
            "QListWidget::item:selected:!active {border: 2px solid #14b8a6; background: rgba(20, 184, 166, 0.08);}"
        )
        for ref in split_references(references):
            self._append_reference_item(ref)

        main_layout = QVBoxLayout(self)
        if not self.refs_only:
            main_layout.addWidget(QLabel("ÐŸÑ€Ð¾Ð¼Ð¿Ñ‚:"))
            main_layout.addWidget(self.prompt_edit)

        refs_header = QHBoxLayout()
        refs_header.addWidget(QLabel("Ð ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹ (Ð´Ð¾ 5):"))
        refs_header.addStretch()
        main_layout.addLayout(refs_header)
        main_layout.addWidget(self.references_list)

        buttons_row = QHBoxLayout()
        self.btn_add_files = QPushButton("Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ñ„Ð°Ð¹Ð»Ñ‹")
        self.btn_remove_selected = QPushButton("Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ð½Ñ‹Ð¹")
        self.btn_clear_all = QPushButton("ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ Ð²ÑÐµ")
        buttons_row.addWidget(self.btn_add_files)
        buttons_row.addWidget(self.btn_remove_selected)
        buttons_row.addWidget(self.btn_clear_all)
        buttons_row.addStretch()
        main_layout.addLayout(buttons_row)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setText("ÐŸÑ€Ð¸Ð¼ÐµÐ½Ð¸Ñ‚ÑŒ" if self.refs_only else "Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ")
        main_layout.addWidget(self.button_box)

        self.btn_add_files.clicked.connect(self.add_files)
        self.btn_remove_selected.clicked.connect(self.remove_selected)
        self.btn_clear_all.clicked.connect(self.clear_all)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Ð’Ñ‹Ð±Ñ€Ð°Ñ‚ÑŒ Ð¸Ð·Ð¾Ð±Ñ€Ð°Ð¶ÐµÐ½Ð¸Ñ",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        if not files:
            return

        existing = [
            self.references_list.item(i).data(Qt.ItemDataRole.UserRole) or self.references_list.item(i).text()
            for i in range(self.references_list.count())
        ]
        merged = []
        for item in existing + [f for f in files if str(f).strip()]:
            if item not in merged:
                merged.append(item)

        if len(merged) > MAX_REFERENCES_PER_PROMPT:
            QMessageBox.warning(
                self,
                "ÐžÐ³Ñ€Ð°Ð½Ð¸Ñ‡ÐµÐ½Ð¸Ðµ",
                f"ÐœÐ¾Ð¶Ð½Ð¾ Ð´Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð¼Ð°ÐºÑÐ¸Ð¼ÑƒÐ¼ {MAX_REFERENCES_PER_PROMPT} Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÐ¾Ð²",
            )
            merged = merged[:MAX_REFERENCES_PER_PROMPT]

        self.references_list.clear()
        for ref in merged:
            self._append_reference_item(ref)

    def _append_reference_item(self, ref):
        reference_path = str(ref or "").strip()
        if not reference_path:
            return
        title = os.path.basename(reference_path) or reference_path
        item = QListWidgetItem(title)
        item.setData(Qt.ItemDataRole.UserRole, reference_path)
        if os.path.isfile(reference_path):
            pixmap = QPixmap(reference_path)
            if not pixmap.isNull():
                item.setIcon(QIcon(pixmap))
        self.references_list.addItem(item)

    def remove_selected(self):
        selected_items = self.references_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            self.references_list.takeItem(self.references_list.row(item))

    def clear_all(self):
        self.references_list.clear()

    def get_data(self):
        prompt = self._source_prompt if self.refs_only else self.prompt_edit.toPlainText().strip()
        refs = [
            str(self.references_list.item(i).data(Qt.ItemDataRole.UserRole) or self.references_list.item(i).text()).strip()
            for i in range(self.references_list.count())
        ]
        refs = [r for r in refs if r]
        return prompt, refs[:MAX_REFERENCES_PER_PROMPT]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Clipart Generator v{APP_VERSION}")
        self.resize(980, 780)

        self.work_dir = ""
        self.worker = None
        self.generated_prompts = []
        self.selected_files = []
        self.has_generated_output_in_run = False
        self.api_key_locked = True
        self.is_updating_prompts_table = False
        self.settings_save_timer = QTimer(self)
        self.settings_save_timer.setSingleShot(True)
        self.settings_save_timer.setInterval(400)
        self.settings_save_timer.timeout.connect(self.persist_ui_settings)
        self.api_key_mask_timer = QTimer(self)
        self.api_key_mask_timer.setSingleShot(True)
        self.api_key_mask_timer.setInterval(2500)
        self.api_key_mask_timer.timeout.connect(self.enforce_api_key_hidden)

        self.load_config()
        self.setup_ui()
        self.restore_last_work_dir()
        self.load_saved_prompts()
        self.setup_settings_autosave_connections()
        QTimer.singleShot(1200, lambda: self.check_for_updates(silent=True))

    def load_saved_prompts(self):
        try:
            if not os.path.exists(PROMPTS_STORAGE_FILE):
                return
            with open(PROMPTS_STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            entries = []
            if isinstance(data, dict):
                raw_prompts = data.get("prompts", [])
                if isinstance(raw_prompts, list):
                    for item in raw_prompts:
                        if isinstance(item, dict):
                            prompt_text = str(item.get("prompt", "")).strip()
                            references = split_references(item.get("references", ""))
                            if prompt_text or references:
                                entries.append({"prompt": prompt_text, "references": references})
                        else:
                            prompt_text = str(item).strip()
                            if prompt_text:
                                entries.append({"prompt": prompt_text, "references": []})
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        prompt_text = str(item.get("prompt", "")).strip()
                        references = split_references(item.get("references", ""))
                        if prompt_text or references:
                            entries.append({"prompt": prompt_text, "references": references})
                    else:
                        prompt_text = str(item).strip()
                        if prompt_text:
                            entries.append({"prompt": prompt_text, "references": []})

            self.generated_prompts = entries
            if hasattr(self, "table"):
                self.refresh_prompts_table()
        except Exception as e:
            self.log(f"ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð·Ð°Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ ÑÐ¾Ñ…Ñ€Ð°Ð½Ñ‘Ð½Ð½Ñ‹Ðµ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ñ‹: {e}")

    def save_prompts_storage(self):
        try:
            normalized_entries = []
            for item in self.generated_prompts:
                if isinstance(item, dict):
                    prompt_text = str(item.get("prompt", "")).strip()
                    references = split_references(item.get("references", []))
                else:
                    prompt_text = str(item).strip()
                    references = []
                if prompt_text or references:
                    normalized_entries.append({"prompt": prompt_text, "references": references})

            payload = {
                "prompts": normalized_entries,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            with open(PROMPTS_STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ ÑÐ¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ñ‹: {e}")

    def load_config(self):
        default_config = {
            "retries": 3,
            "timeout": 60,
            "generation_wait_timeout": 300,
            "status_poll_interval": 20,
            "app_version": APP_VERSION,
            "update_manifest_url": UPDATE_MANIFEST_URL,
            "kie_api_key": "",
            "kie_upload_path": "clipart-generator",
            "text_generation_model": "gpt4o-image",
            "reference_generation_model": "qwen/image-to-image",
            "generation_model": "gpt4o-image",
            "generation_size": "1:1",
            "remove_bg": True,
            "upscale": True,
            "trim_enabled": False,
            "trim_mode": "alpha",
            "trim_position": "post",
            "upscale_factor": 4,
            "kie_upscale_model": "topaz/upscale",
            "kie_remove_bg_model": "recraft/remove-background",
            "run_mode": "generate_only",
            "prompt_input_mode": "list",
            "last_work_dir": "",
            "license_key": "",
            "license_server_url": "",
            "license_backup_server_url": "",
            "last_updates_expired_notice_at": "",
        }
        self._migrate_legacy_local_files()
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self.config = json.load(f)
            for key, value in default_config.items():
                if key not in self.config:
                    self.config[key] = value
        else:
            self.config = default_config
        # URL Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ð¹ Ð²ÑÐµÐ³Ð´Ð° Ñ„Ð¸ÐºÑÐ¸Ñ€Ð¾Ð²Ð°Ð½Ð½Ñ‹Ð¹ Ð¸ Ð½Ðµ Ñ€ÐµÐ´Ð°ÐºÑ‚Ð¸Ñ€ÑƒÐµÑ‚ÑÑ Ð² UI.
        self.config["update_manifest_url"] = UPDATE_MANIFEST_URL

        legacy_generation_model = self._normalize_generation_model_id(self.config.get("generation_model", "gpt4o-image"))
        legacy_meta = GENERATION_MODEL_META.get(legacy_generation_model, {})
        legacy_type = legacy_meta.get("type", "text_to_image")

        text_model = self._normalize_generation_model_id(self.config.get("text_generation_model", ""))
        text_meta = GENERATION_MODEL_META.get(text_model, {})
        if text_meta.get("type") != "text_to_image":
            if legacy_type == "text_to_image":
                text_model = legacy_generation_model
            else:
                text_model = "gpt4o-image"
        self.config["text_generation_model"] = text_model

        reference_model = self._normalize_generation_model_id(self.config.get("reference_generation_model", ""))
        if reference_model not in REFERENCE_MODEL_SHORTLIST:
            if legacy_generation_model in REFERENCE_MODEL_SHORTLIST:
                reference_model = legacy_generation_model
            else:
                reference_model = "qwen/image-to-image"
        self.config["reference_generation_model"] = reference_model

        # ÐžÑÑ‚Ð°Ð²Ð»ÑÐµÐ¼ legacy-ÐºÐ»ÑŽÑ‡ Ð´Ð»Ñ Ð¾Ð±Ñ€Ð°Ñ‚Ð½Ð¾Ð¹ ÑÐ¾Ð²Ð¼ÐµÑÑ‚Ð¸Ð¼Ð¾ÑÑ‚Ð¸.
        self.config["generation_model"] = self.config["text_generation_model"]

        # Ð¢ÐµÐºÑƒÑ‰Ð°Ñ Ð²ÐµÑ€ÑÐ¸Ñ Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ Ð±ÐµÑ€Ñ‘Ñ‚ÑÑ Ð¸Ð· ÐºÐ¾Ð´Ð° ÑÐ±Ð¾Ñ€ÐºÐ¸, Ð° Ð½Ðµ Ð¸Ð· Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒÑÐºÐ¾Ð³Ð¾ ÐºÐ¾Ð½Ñ„Ð¸Ð³Ð°.
        # Ð­Ñ‚Ð¾ Ð¿Ñ€ÐµÐ´Ð¾Ñ‚Ð²Ñ€Ð°Ñ‰Ð°ÐµÑ‚ Ñ†Ð¸ÐºÐ» Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ð¹, ÐµÑÐ»Ð¸ Ð² ÐºÐ¾Ð½Ñ„Ð¸Ð³Ðµ Ð¾ÑÑ‚Ð°Ð»Ð¾ÑÑŒ ÑÑ‚Ð°Ñ€Ð¾Ðµ Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ðµ.
        self.config["app_version"] = APP_VERSION

    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def _migrate_legacy_local_files(self):
        try:
            legacy_config = os.path.join(os.getcwd(), "config.json")
            legacy_prompts = os.path.join(os.getcwd(), "prompts.json")
            if os.path.exists(legacy_config) and not os.path.exists(CONFIG_FILE):
                with open(legacy_config, "r", encoding="utf-8") as src, open(CONFIG_FILE, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
            if os.path.exists(legacy_prompts) and not os.path.exists(PROMPTS_STORAGE_FILE):
                with open(legacy_prompts, "r", encoding="utf-8") as src, open(PROMPTS_STORAGE_FILE, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
        except Exception:
            pass

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(8)

        self.primary_button_style = (
            "QPushButton {background:#14b8a6; color:white; font-weight:700; border-radius:8px; padding:8px 16px;}"
            "QPushButton:hover {background:#0f9f90;}"
            "QPushButton:disabled {background:#9ca3af; color:white;}"
        )
        self.compact_button_style = (
            "QPushButton {background:#14b8a6; color:white; font-weight:700; border-radius:7px; padding:5px 10px;}"
            "QPushButton:hover {background:#0f9f90;}"
            "QPushButton:disabled {background:#9ca3af; color:white;}"
        )
        self.standard_button_width = 140
        self.standard_button_height = 36

        self.setStyleSheet(
            "QRadioButton::indicator, QCheckBox::indicator {width: 16px; height: 16px;}"
            "QRadioButton::indicator:unchecked, QCheckBox::indicator:unchecked {"
            "border: 2px solid #14b8a6; background: #ffffff; border-radius: 8px;}"
            "QRadioButton::indicator:checked, QCheckBox::indicator:checked {"
            "border: 2px solid #14b8a6; background: #14b8a6; border-radius: 8px;}"
        )

        top_layout = QHBoxLayout()
        self.lbl_work_dir = QLabel("Ð Ð°Ð±Ð¾Ñ‡Ð°Ñ Ð¿Ð°Ð¿ÐºÐ°: Ð½Ðµ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ð°")
        self.btn_select_dir = QPushButton("Ð’Ñ‹Ð±Ñ€Ð°Ñ‚ÑŒ Ð¿Ð°Ð¿ÐºÑƒ")
        self.btn_select_dir.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_select_dir.setStyleSheet(self.primary_button_style)
        self.btn_select_dir.clicked.connect(self.select_work_dir)
        top_layout.addWidget(self.lbl_work_dir)
        top_layout.addSpacing(8)
        top_layout.addWidget(self.btn_select_dir)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        run_mode_group = QGroupBox("Ð¡Ñ†ÐµÐ½Ð°Ñ€Ð¸Ð¹ Ð·Ð°Ð¿ÑƒÑÐºÐ°")
        run_mode_layout = QHBoxLayout()
        self.run_mode_group = QButtonGroup()

        self.radio_run_generate = QRadioButton("Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð³ÐµÐ½ÐµÑ€Ð°Ñ†Ð¸Ñ Ð¸Ð·Ð¾Ð±Ñ€Ð°Ð¶ÐµÐ½Ð¸Ð¹")
        self.radio_run_process = QRadioButton("Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ñ„Ð°Ð¹Ð»Ð¾Ð²")
        self.radio_run_both = QRadioButton("Ð’ÑÐµ Ð²Ð¼ÐµÑÑ‚Ðµ")

        run_mode = self.config.get("run_mode", "generate_only")
        if run_mode == "process_only":
            self.radio_run_process.setChecked(True)
        elif run_mode == "both":
            self.radio_run_both.setChecked(True)
        else:
            self.radio_run_generate.setChecked(True)

        self.radio_run_generate.toggled.connect(self.on_mode_changed)
        self.radio_run_process.toggled.connect(self.on_mode_changed)
        self.radio_run_both.toggled.connect(self.on_mode_changed)

        self.run_mode_group.addButton(self.radio_run_generate, 1)
        self.run_mode_group.addButton(self.radio_run_process, 2)
        self.run_mode_group.addButton(self.radio_run_both, 3)
        run_mode_layout.addWidget(self.radio_run_generate)
        run_mode_layout.addWidget(self.radio_run_process)
        run_mode_layout.addWidget(self.radio_run_both)
        run_mode_layout.addStretch()
        run_mode_group.setLayout(run_mode_layout)
        main_layout.addWidget(run_mode_group)

        self.tabs = QTabWidget()
        prompt_tab = QWidget()
        prompt_tab_layout = QVBoxLayout(prompt_tab)
        process_tab = QWidget()
        process_tab_layout = QVBoxLayout(process_tab)
        settings_tab = QWidget()
        settings_tab_layout = QVBoxLayout(settings_tab)
        settings_tab_layout.setSpacing(8)
        self.tabs.addTab(prompt_tab, "ÐŸÑ€Ð¾Ð¼Ð¿Ñ‚Ñ‹")
        self.tabs.addTab(process_tab, "ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ°")
        self.tabs.addTab(settings_tab, "ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸")
        main_layout.addWidget(self.tabs)

        prompt_btn_layout = QHBoxLayout()
        self.btn_add_prompt_row = QPushButton("+")
        self.btn_add_prompt_row.clicked.connect(self.add_prompt_row)
        self.btn_add_prompt_row.setToolTip("Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ ÑÑ‚Ñ€Ð¾ÐºÑƒ")
        self.btn_add_refs_selected = QPushButton("ðŸ–¼+")
        self.btn_add_refs_selected.clicked.connect(self.add_references_to_selected_prompts)
        self.btn_add_refs_selected.setToolTip("Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹ Ðº Ð²Ñ‹Ð´ÐµÐ»ÐµÐ½Ð½Ñ‹Ð¼ ÑÑ‚Ñ€Ð¾ÐºÐ°Ð¼")
        self.btn_clear_refs_selected = QPushButton("ðŸ–¼âˆ’")
        self.btn_clear_refs_selected.clicked.connect(self.clear_references_for_selected_prompts)
        self.btn_clear_refs_selected.setToolTip("ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹ Ñƒ Ð²Ñ‹Ð´ÐµÐ»ÐµÐ½Ð½Ñ‹Ñ… ÑÑ‚Ñ€Ð¾Ðº")
        self.btn_import_csv = QPushButton("Ð˜Ð¼Ð¿Ð¾Ñ€Ñ‚ CSV")
        self.btn_import_csv.clicked.connect(self.import_prompts_from_csv)
        self.btn_import_csv.setToolTip("Ð˜Ð¼Ð¿Ð¾Ñ€Ñ‚Ð¸Ñ€ÑƒÐµÑ‚ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ñ‹ Ð¸Ð· CSV-Ñ„Ð°Ð¹Ð»Ð°")
        self.btn_export_csv = QPushButton("Ð­ÐºÑÐ¿Ð¾Ñ€Ñ‚ CSV")
        self.btn_export_csv.clicked.connect(self.export_prompts)
        self.btn_export_csv.setToolTip("Ð­ÐºÑÐ¿Ð¾Ñ€Ñ‚Ð¸Ñ€ÑƒÐµÑ‚ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ñ‹ Ð¸ Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹ Ð² CSV-Ñ„Ð°Ð¹Ð»")
        self.btn_clear_prompts = QPushButton("Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð²ÑÐµ")
        self.btn_clear_prompts.clicked.connect(self.clear_all_prompts)
        self.btn_clear_prompts.setToolTip("ÐžÑ‡Ð¸Ñ‰Ð°ÐµÑ‚ ÑÐ¿Ð¸ÑÐ¾Ðº Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð² Ð² Ð¿Ñ€ÐµÐ´Ð¿Ñ€Ð¾ÑÐ¼Ð¾Ñ‚Ñ€Ðµ")
        self.btn_import_csv.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_export_csv.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_clear_prompts.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_add_refs_selected.setFixedSize(72, self.standard_button_height)
        self.btn_clear_refs_selected.setFixedSize(72, self.standard_button_height)
        self.btn_add_prompt_row.setStyleSheet(self.primary_button_style)
        self.btn_add_refs_selected.setStyleSheet(self.primary_button_style)
        self.btn_clear_refs_selected.setStyleSheet(self.primary_button_style)
        self.btn_import_csv.setStyleSheet(self.primary_button_style)
        self.btn_export_csv.setStyleSheet(self.primary_button_style)
        self.btn_clear_prompts.setStyleSheet(self.primary_button_style)
        prompt_btn_layout.addWidget(self.btn_add_prompt_row)
        prompt_btn_layout.addWidget(self.btn_add_refs_selected)
        prompt_btn_layout.addWidget(self.btn_clear_refs_selected)
        prompt_btn_layout.addWidget(self.btn_import_csv)
        prompt_btn_layout.addWidget(self.btn_export_csv)
        prompt_btn_layout.addStretch()
        prompt_btn_layout.addWidget(self.btn_clear_prompts)
        prompt_tab_layout.addLayout(prompt_btn_layout)

        preview_group = QGroupBox("Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð·Ð°Ð¿Ð¸ÑÐµÐ¹")
        preview_layout = QVBoxLayout()
        self.table = PromptTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ÐŸÑ€Ð¾Ð¼Ð¿Ñ‚", "ðŸ–¼", "", ""])
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.verticalHeader().setFixedWidth(24)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 52)
        self.table.setColumnWidth(2, 44)
        self.table.setColumnWidth(3, 44)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setMinimumHeight(280)
        self.table.bulkTextPasted.connect(self.on_table_bulk_paste)
        self.table.itemChanged.connect(self.on_prompt_item_changed)
        self.table.itemDoubleClicked.connect(self.on_prompt_item_double_clicked)
        preview_layout.addWidget(self.table)
        preview_group.setLayout(preview_layout)
        prompt_tab_layout.addWidget(preview_group)

        files_group = QGroupBox("Ð¤Ð°Ð¹Ð»Ñ‹ Ð´Ð»Ñ Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ¸")
        files_layout = QVBoxLayout()
        self.btn_select_files = QPushButton("Ð’Ñ‹Ð±Ñ€Ð°Ñ‚ÑŒ Ñ„Ð°Ð¹Ð»Ñ‹")
        self.btn_select_files.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_select_files.setStyleSheet(self.primary_button_style)
        self.btn_select_files.clicked.connect(self.select_files)
        self.lbl_files_count = QLabel("Ð¤Ð°Ð¹Ð»Ð¾Ð² Ð½Ðµ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ð¾")
        files_layout.addWidget(self.btn_select_files)
        files_layout.addWidget(self.lbl_files_count)
        files_group.setLayout(files_layout)
        process_tab_layout.addWidget(files_group)

        process_flags_group = QGroupBox("ÐŸÐ°Ñ€Ð°Ð¼ÐµÑ‚Ñ€Ñ‹ Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ¸")
        process_flags_layout = QGridLayout()
        process_flags_layout.setHorizontalSpacing(12)
        process_flags_layout.setVerticalSpacing(8)
        self.chk_upscale = QCheckBox("ÐÐ¿ÑÐºÐµÐ¹Ð»")
        self.chk_upscale.setChecked(self.config.get("upscale", True))
        self.chk_remove_bg = QCheckBox("Ð£Ð´Ð°Ð»ÐµÐ½Ð¸Ðµ Ñ„Ð¾Ð½Ð°")
        self.chk_remove_bg.setChecked(self.config.get("remove_bg", True))
        self.chk_trim = QCheckBox("Trim (Ð¾Ð±Ñ€ÐµÐ·ÐºÐ° Ð¿ÑƒÑÑ‚Ñ‹Ñ… ÐºÑ€Ð°Ñ‘Ð²)")
        self.chk_trim.setChecked(bool(self.config.get("trim_enabled", False)))
        self.trim_mode_combo = QComboBox()
        self.trim_mode_combo.addItem("ÐŸÑ€Ð¾Ð·Ñ€Ð°Ñ‡Ð½Ñ‹Ðµ ÐºÑ€Ð°Ñ", "alpha")
        self.trim_mode_combo.addItem("Ð‘ÐµÐ»Ñ‹Ðµ ÐºÑ€Ð°Ñ", "white")
        trim_mode = str(self.config.get("trim_mode", "alpha") or "alpha")
        trim_mode_index = self.trim_mode_combo.findData(trim_mode)
        self.trim_mode_combo.setCurrentIndex(trim_mode_index if trim_mode_index >= 0 else 0)
        self.trim_position_combo = QComboBox()
        self.trim_position_combo.addItem("Ð’ ÐºÐ¾Ð½Ñ†Ðµ", "post")
        self.trim_position_combo.addItem("Ð”Ð¾ Ð°Ð¿ÑÐºÐµÐ¹Ð»Ð°", "pre")
        self.trim_position_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.trim_position_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        trim_position = str(self.config.get("trim_position", "post") or "post")
        trim_position_index = self.trim_position_combo.findData(trim_position)
        self.trim_position_combo.setCurrentIndex(trim_position_index if trim_position_index >= 0 else 0)

        process_flags_layout.addWidget(self.chk_upscale, 0, 0)
        process_flags_layout.addWidget(self.chk_remove_bg, 0, 1)
        process_flags_layout.addWidget(self.chk_trim, 1, 0)
        process_flags_layout.addWidget(self.trim_mode_combo, 1, 1)
        process_flags_layout.addWidget(self.trim_position_combo, 1, 2)
        process_flags_layout.setAlignment(self.trim_position_combo, Qt.AlignmentFlag.AlignLeft)
        process_flags_layout.setColumnStretch(3, 1)
        process_flags_group.setLayout(process_flags_layout)
        process_tab_layout.addWidget(process_flags_group)

        process_tab_layout.addStretch()

        kie_group = QGroupBox("KIE: Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ Ð¸ Ð³ÐµÐ½ÐµÑ€Ð°Ñ†Ð¸Ñ")
        kie_group.setMaximumWidth(720)
        kie_layout = QGridLayout()
        kie_layout.setHorizontalSpacing(6)
        kie_layout.setVerticalSpacing(6)
        self.kie_api_key_input = QLineEdit()
        self.kie_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.kie_api_key_input.setText(self.config.get("kie_api_key", ""))
        self.kie_api_key_input.setReadOnly(True)

        self.btn_api_key_lock = QPushButton("ðŸ”’")
        self.btn_api_key_lock.setFixedSize(40, 32)
        self.btn_api_key_lock.setToolTip("ÐšÐ»ÑŽÑ‡ Ð·Ð°Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ð½")
        self.btn_api_key_lock.clicked.connect(self.toggle_api_key_lock)

        self.text_generation_model_combo = QComboBox()
        self.populate_generation_models(self.text_generation_model_combo, {"text_to_image"})
        self.set_generation_model_selection(
            self.text_generation_model_combo,
            self.config.get("text_generation_model", "gpt4o-image"),
            {"text_to_image"},
            "gpt4o-image",
        )

        self.reference_generation_model_combo = QComboBox()
        self.populate_generation_models(
            self.reference_generation_model_combo,
            set(),
            include_model_ids=REFERENCE_MODEL_SHORTLIST,
        )
        self.set_generation_model_selection(
            self.reference_generation_model_combo,
            self.config.get("reference_generation_model", "qwen/image-to-image"),
            set(),
            "qwen/image-to-image",
            include_model_ids=REFERENCE_MODEL_SHORTLIST,
        )

        self.generation_size_combo = QComboBox()
        self.generation_size_combo.addItems(["1:1", "4:3", "3:4", "16:9", "9:16"])
        size_value = str(self.config.get("generation_size", "1:1"))
        legacy_map = {"1024x1024": "1:1", "1024x1536": "3:4", "1536x1024": "4:3"}
        if size_value in legacy_map:
            size_value = legacy_map[size_value]
        self.generation_size_combo.setCurrentText(size_value if size_value else "1:1")
        self.btn_check_balance = QPushButton("ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ Ð±Ð°Ð»Ð°Ð½Ñ")
        self.btn_check_balance.setFixedSize(130, 32)
        self.btn_check_balance.setStyleSheet(self.compact_button_style)
        self.btn_check_balance.clicked.connect(self.check_kie_balance)

        self.api_key_buttons_widget = QWidget()
        self.api_key_buttons_layout = QHBoxLayout(self.api_key_buttons_widget)
        self.api_key_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.api_key_buttons_layout.setSpacing(6)
        self.api_key_buttons_layout.addWidget(self.btn_api_key_lock)
        self.api_key_buttons_layout.addWidget(self.btn_check_balance)

        settings_field_width = 220
        self.kie_api_key_input.setFixedSize(settings_field_width, 32)
        self.text_generation_model_combo.setFixedSize(settings_field_width, 32)
        self.reference_generation_model_combo.setFixedSize(settings_field_width, 32)
        self.generation_size_combo.setFixedSize(settings_field_width, 32)

        lbl_api_key = QLabel("KIE API Key:")
        lbl_api_key.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_text_model = QLabel("Ð”Ð»Ñ Ñ‚ÐµÐºÑÑ‚Ð¾Ð²Ñ‹Ñ… Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð²:")
        lbl_text_model.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_reference_model = QLabel("Ð”Ð»Ñ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð² Ñ Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÐ°Ð¼Ð¸:")
        lbl_reference_model.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_gen_size = QLabel("Ð¡Ð¾Ð¾Ñ‚Ð½Ð¾ÑˆÐµÐ½Ð¸Ðµ:")
        lbl_gen_size.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        kie_layout.addWidget(lbl_api_key, 0, 0)
        kie_layout.addWidget(self.kie_api_key_input, 0, 1)
        kie_layout.addWidget(self.api_key_buttons_widget, 0, 2)
        kie_layout.addWidget(lbl_text_model, 1, 0)
        kie_layout.addWidget(self.text_generation_model_combo, 1, 1)
        kie_layout.addWidget(lbl_reference_model, 2, 0)
        kie_layout.addWidget(self.reference_generation_model_combo, 2, 1)
        kie_layout.addWidget(lbl_gen_size, 3, 0)
        kie_layout.addWidget(self.generation_size_combo, 3, 1)
        kie_group.setLayout(kie_layout)
        settings_tab_layout.addWidget(kie_group, alignment=Qt.AlignmentFlag.AlignHCenter)

        process_settings_group = QGroupBox("ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ñ‡ÐµÑ€ÐµÐ· KIE")
        process_settings_group.setMaximumWidth(720)
        process_settings_layout = QGridLayout()
        process_settings_layout.setHorizontalSpacing(6)
        process_settings_layout.setVerticalSpacing(6)

        self.kie_upscale_model_combo = QComboBox()
        self.kie_upscale_model_combo.addItems(["topaz/upscale", "recraft/crisp-upscale"])
        uim = self.config.get("kie_upscale_model", "topaz/upscale")
        ui_index = self.kie_upscale_model_combo.findText(uim)
        self.kie_upscale_model_combo.setCurrentIndex(ui_index if ui_index >= 0 else 0)

        self.kie_remove_bg_model_combo = QComboBox()
        self.kie_remove_bg_model_combo.addItems(["recraft/remove-background"])
        rim = self.config.get("kie_remove_bg_model", "recraft/remove-background")
        ri_index = self.kie_remove_bg_model_combo.findText(rim)
        self.kie_remove_bg_model_combo.setCurrentIndex(ri_index if ri_index >= 0 else 0)

        self.upscale_factor_combo = QComboBox()
        self.upscale_factor_combo.addItems(["2", "4", "8"])
        self.upscale_factor_combo.setCurrentText(str(self.config.get("upscale_factor", 4)))

        self.kie_upscale_model_combo.setFixedSize(settings_field_width, 32)
        self.upscale_factor_combo.setFixedSize(settings_field_width, 32)
        self.kie_remove_bg_model_combo.setFixedSize(settings_field_width, 32)

        lbl_upscale_model = QLabel("ÐÐ¿ÑÐºÐµÐ¹Ð» Ð¼Ð¾Ð´ÐµÐ»ÑŒ:")
        lbl_upscale_model.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_upscale_factor = QLabel("ÐšÑ€Ð°Ñ‚Ð½Ð¾ÑÑ‚ÑŒ:")
        lbl_upscale_factor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_remove_bg = QLabel("Ð£Ð´Ð°Ð»ÐµÐ½Ð¸Ðµ Ñ„Ð¾Ð½Ð°:")
        lbl_remove_bg.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        process_settings_layout.addWidget(lbl_upscale_model, 0, 0)
        process_settings_layout.addWidget(self.kie_upscale_model_combo, 0, 1)
        process_settings_layout.addWidget(lbl_upscale_factor, 1, 0)
        process_settings_layout.addWidget(self.upscale_factor_combo, 1, 1)
        process_settings_layout.addWidget(lbl_remove_bg, 2, 0)
        process_settings_layout.addWidget(self.kie_remove_bg_model_combo, 2, 1)
        process_settings_group.setLayout(process_settings_layout)
        settings_tab_layout.addWidget(process_settings_group, alignment=Qt.AlignmentFlag.AlignHCenter)

        settings_tab_layout.addStretch()

        log_group = QGroupBox("Ð›Ð¾Ð³ Ð¸ Ð¿Ñ€Ð¾Ð³Ñ€ÐµÑÑ")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(80)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        run_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_start.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_start.clicked.connect(self.start_work)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_stop.clicked.connect(self.stop_work)
        self.btn_stop.setEnabled(False)
        self.btn_start.setStyleSheet(self.primary_button_style)
        self.btn_stop.setStyleSheet(self.primary_button_style)
        run_layout.addWidget(self.btn_start)
        run_layout.addWidget(self.btn_stop)
        run_layout.addStretch()

        log_layout.addWidget(self.log_text)
        log_layout.addWidget(self.progress_bar)
        log_layout.addLayout(run_layout)
        log_group.setLayout(log_layout)
        log_group.setMinimumHeight(220)
        log_group.setMaximumHeight(260)
        main_layout.setStretch(2, 1)
        main_layout.setStretch(3, 0)
        main_layout.addWidget(log_group)

        self.refresh_upscale_factor_options()
        self.update_trim_controls_state()
        self.chk_trim.toggled.connect(self.update_trim_controls_state)
        self.trim_mode_combo.currentIndexChanged.connect(self.update_trim_controls_state)
        self.on_mode_changed(True)

    def _normalize_generation_model_id(self, model_id):
        model = (model_id or "").strip()
        alias_map = {
            "gpt-image-1": "gpt4o-image",
            "gpt-image-1.5": "gpt4o-image",
            "flux-kontext": "black-forest-labs/flux-kontext-pro",
            "zai-org/z-image": "z-image",
        }
        if not model:
            return "gpt4o-image"
        return alias_map.get(model, model)

    def _model_type_title(self, model_type):
        return {
            "text_to_image": "Textâ†’Image",
            "image_to_image": "Imageâ†’Image",
            "edit": "Edit",
        }.get(model_type or "", "Other")

    def populate_generation_models(self, combo_box, allowed_types, include_model_ids=None):
        combo_box.clear()
        extra_ids = set(include_model_ids or set())
        for entry in GENERATION_MODELS:
            model_id = entry.get("id")
            model_type = entry.get("type")
            if model_type not in allowed_types and model_id not in extra_ids:
                continue
            label = entry.get("label", model_id or "")
            combo_box.addItem(label, model_id)

    def set_generation_model_selection(self, combo_box, model_id, allowed_types, fallback_id, include_model_ids=None):
        normalized = self._normalize_generation_model_id(model_id)
        model_meta = GENERATION_MODEL_META.get(normalized, {})
        extra_ids = set(include_model_ids or set())
        if model_meta.get("type") not in allowed_types and normalized not in extra_ids:
            normalized = fallback_id

        idx = combo_box.findData(normalized)
        if idx >= 0:
            combo_box.setCurrentIndex(idx)
            return

        label_idx = combo_box.findText(str(model_id or "").strip())
        if label_idx >= 0:
            combo_box.setCurrentIndex(label_idx)
            return

        fallback_idx = combo_box.findData(fallback_id)
        combo_box.setCurrentIndex(fallback_idx if fallback_idx >= 0 else 0)

    def get_selected_generation_model_id(self, combo_box):
        model_id = combo_box.currentData()
        if not model_id:
            model_id = combo_box.currentText()
        return self._normalize_generation_model_id(model_id)

    def create_template_values_table(self, placeholder_prefix):
        table = QTableWidget(0, 2)
        table.horizontalHeader().hide()
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(1, 36)
        table.setWordWrap(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setMinimumHeight(100)
        table.setProperty("placeholderPrefix", placeholder_prefix)
        return table

    def create_template_column(self, title, table):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(f"{title}:"))
        header_layout.addStretch()
        layout.addLayout(header_layout)
        layout.addWidget(table)
        return container

    def add_template_value_row(self, table):
        row = table.rowCount()
        table.insertRow(row)
        prefix = str(table.property("placeholderPrefix") or "")
        item = QTableWidgetItem("")
        item.setToolTip(f"{prefix}: Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ðµ Ð´Ð»Ñ Ð¿Ð¾Ð´ÑÑ‚Ð°Ð½Ð¾Ð²ÐºÐ¸")
        table.setItem(row, 0, item)

        delete_btn = QPushButton("ðŸ—‘")
        delete_btn.setToolTip("Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÑÑ‚Ñ€Ð¾ÐºÑƒ")
        delete_btn.setMinimumHeight(24)
        delete_btn.clicked.connect(lambda _, r=row, t=table: self.remove_template_value_row(t, r))
        table.setCellWidget(row, 1, delete_btn)
        table.setCurrentCell(row, 0)
        table.editItem(item)

    def remove_template_value_row(self, table, row_index):
        if 0 <= row_index < table.rowCount():
            table.removeRow(row_index)
            self.refresh_template_value_delete_buttons(table)

    def refresh_template_value_delete_buttons(self, table):
        for row in range(table.rowCount()):
            delete_btn = QPushButton("ðŸ—‘")
            delete_btn.setToolTip("Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÑÑ‚Ñ€Ð¾ÐºÑƒ")
            delete_btn.setMinimumHeight(24)
            delete_btn.clicked.connect(lambda _, r=row, t=table: self.remove_template_value_row(t, r))
            table.setCellWidget(row, 1, delete_btn)

    def get_template_values(self, table):
        values = []
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            text = (item.text() if item else "").strip()
            if text:
                values.append(text)
        return values

    def setup_settings_autosave_connections(self):
        self.kie_api_key_input.textChanged.connect(self.schedule_settings_save)
        self.kie_api_key_input.textChanged.connect(self.on_api_key_changed)
        if hasattr(self, "license_key_input"):
            self.license_key_input.textChanged.connect(self.schedule_settings_save)
        if hasattr(self, "license_server_url_input"):
            self.license_server_url_input.textChanged.connect(self.schedule_settings_save)
        if hasattr(self, "license_backup_server_url_input"):
            self.license_backup_server_url_input.textChanged.connect(self.schedule_settings_save)
        self.text_generation_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.reference_generation_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.generation_size_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.chk_upscale.toggled.connect(self.schedule_settings_save)
        self.chk_remove_bg.toggled.connect(self.schedule_settings_save)
        self.chk_trim.toggled.connect(self.schedule_settings_save)
        self.trim_mode_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.trim_position_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.kie_upscale_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.kie_upscale_model_combo.currentTextChanged.connect(self.on_upscale_model_changed)
        self.kie_remove_bg_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.upscale_factor_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.radio_run_generate.toggled.connect(self.schedule_settings_save)
        self.radio_run_process.toggled.connect(self.schedule_settings_save)
        self.radio_run_both.toggled.connect(self.schedule_settings_save)

    def schedule_settings_save(self, *_):
        self.settings_save_timer.start()

    def on_upscale_model_changed(self, *_):
        self.refresh_upscale_factor_options()

    def update_trim_controls_state(self, *_):
        trim_enabled = self.chk_trim.isChecked()
        self.trim_mode_combo.setEnabled(trim_enabled)
        self.trim_position_combo.setEnabled(trim_enabled)

    def refresh_upscale_factor_options(self):
        model_name = self.kie_upscale_model_combo.currentText().strip()
        if model_name == "recraft/crisp-upscale":
            factors = ["4"]
        elif model_name == "topaz/upscale":
            factors = ["2", "4", "8"]
        else:
            factors = ["2", "3", "4"]

        current_factor = self.upscale_factor_combo.currentText().strip()
        self.upscale_factor_combo.blockSignals(True)
        self.upscale_factor_combo.clear()
        self.upscale_factor_combo.addItems(factors)
        if current_factor in factors:
            self.upscale_factor_combo.setCurrentText(current_factor)
        elif "4" in factors:
            self.upscale_factor_combo.setCurrentText("4")
        else:
            self.upscale_factor_combo.setCurrentIndex(0)
        self.upscale_factor_combo.setEnabled(model_name != "recraft/crisp-upscale")
        self.upscale_factor_combo.blockSignals(False)
        self.schedule_settings_save()

    def on_mode_changed(self, checked):
        is_process = self.radio_run_process.isChecked()
        if hasattr(self, "tabs"):
            self.tabs.setCurrentIndex(1 if is_process else 0)

    def select_work_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Ð’Ñ‹Ð±Ñ€Ð°Ñ‚ÑŒ Ñ€Ð°Ð±Ð¾Ñ‡ÑƒÑŽ Ð¿Ð°Ð¿ÐºÑƒ")
        if path:
            self.work_dir = path
            self.lbl_work_dir.setText(f"Ð Ð°Ð±Ð¾Ñ‡Ð°Ñ Ð¿Ð°Ð¿ÐºÐ°: {path}")
            os.makedirs(os.path.join(path, "raw"), exist_ok=True)
            os.makedirs(os.path.join(path, "output"), exist_ok=True)
            self.config["last_work_dir"] = path
            self.save_config()
            self.log(f"Ð¡Ð¾Ð·Ð´Ð°Ð½Ñ‹/Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐµÐ½Ñ‹ Ð¿Ð°Ð¿ÐºÐ¸ raw Ð¸ output Ð² {path}")

    def restore_last_work_dir(self):
        last_work_dir = str(self.config.get("last_work_dir", "")).strip()
        if not last_work_dir or not os.path.isdir(last_work_dir):
            return
        self.work_dir = last_work_dir
        self.lbl_work_dir.setText(f"Ð Ð°Ð±Ð¾Ñ‡Ð°Ñ Ð¿Ð°Ð¿ÐºÐ°: {last_work_dir}")
        os.makedirs(os.path.join(last_work_dir, "raw"), exist_ok=True)
        os.makedirs(os.path.join(last_work_dir, "output"), exist_ok=True)

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Ð’Ñ‹Ð±Ñ€Ð°Ñ‚ÑŒ Ð¸Ð·Ð¾Ð±Ñ€Ð°Ð¶ÐµÐ½Ð¸Ñ",
            "",
            "Images (*.png *.jpg *.jpeg *.webp);;All files (*.*)",
        )
        if files:
            self.selected_files = files
            self.lbl_files_count.setText(f"Ð’Ñ‹Ð±Ñ€Ð°Ð½Ð¾ Ñ„Ð°Ð¹Ð»Ð¾Ð²: {len(files)}")
            self.log(f"Ð’Ñ‹Ð±Ñ€Ð°Ð½Ð¾ Ñ„Ð°Ð¹Ð»Ð¾Ð²: {len(files)}")

    def add_prompt_row(self):
        self.generated_prompts.append({"prompt": "", "references": []})
        self.refresh_prompts_table()
        self.save_prompts_storage()
        row_index = len(self.generated_prompts) - 1
        self.table.setCurrentCell(row_index, 0)
        self.table.editItem(self.table.item(row_index, 0))

    def _normalize_prompt_entry(self, entry):
        parsed_entry = entry
        if isinstance(entry, str):
            raw_text = entry.strip()
            if raw_text.startswith("{") and raw_text.endswith("}"):
                for parser in (json.loads, ast.literal_eval):
                    try:
                        candidate = parser(raw_text)
                        if isinstance(candidate, dict):
                            parsed_entry = candidate
                            break
                    except Exception:
                        continue

        if isinstance(parsed_entry, dict):
            prompt_text = str(parsed_entry.get("prompt", "")).strip()
            references = split_references(parsed_entry.get("references", []))
            return {"prompt": prompt_text, "references": references[:MAX_REFERENCES_PER_PROMPT]}

        return {"prompt": str(entry).strip(), "references": []}

    def _pick_reference_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Ð’Ñ‹Ð±Ñ€Ð°Ñ‚ÑŒ Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        return [f for f in files if str(f).strip()]

    def _merge_references(self, existing, additions):
        result = []
        for item in split_references(existing) + split_references(additions):
            if item not in result:
                result.append(item)
        if len(result) > MAX_REFERENCES_PER_PROMPT:
            result = result[:MAX_REFERENCES_PER_PROMPT]
        return result

    def _set_row_references(self, row_index, references):
        if not (0 <= row_index < len(self.generated_prompts)):
            return
        current_entry = self.generated_prompts[row_index]
        if not isinstance(current_entry, dict):
            current_entry = {"prompt": str(current_entry), "references": []}
        current_entry["references"] = split_references(references)[:MAX_REFERENCES_PER_PROMPT]
        self.generated_prompts[row_index] = current_entry
        self.refresh_prompts_table()
        self.save_prompts_storage()

    def _get_selected_prompt_rows(self):
        selection_model = self.table.selectionModel()
        if selection_model is None:
            return []
        rows = sorted({index.row() for index in selection_model.selectedRows()})
        return [row for row in rows if 0 <= row < len(self.generated_prompts)]

    def add_references_to_selected_prompts(self):
        if not self.generated_prompts:
            QMessageBox.warning(self, "Ð ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹", "Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð² Ð¿ÑƒÑÑ‚")
            return

        selected_rows = self._get_selected_prompt_rows()
        if not selected_rows:
            QMessageBox.warning(self, "Ð ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹", "Ð’Ñ‹Ð´ÐµÐ»Ð¸Ñ‚Ðµ Ñ…Ð¾Ñ‚Ñ Ð±Ñ‹ Ð¾Ð´Ð½Ñƒ ÑÑ‚Ñ€Ð¾ÐºÑƒ")
            return

        files = self._pick_reference_files()
        if not files:
            return

        for idx in selected_rows:
            current = self._normalize_prompt_entry(self.generated_prompts[idx])
            current["references"] = self._merge_references(current.get("references", []), files)
            self.generated_prompts[idx] = current

        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log(f"Ð ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹ Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ñ‹ Ðº ÑÑ‚Ñ€Ð¾ÐºÐ°Ð¼: {len(selected_rows)} | Ð¤Ð°Ð¹Ð»Ð¾Ð²: {len(files)}")

    def clear_references_for_selected_prompts(self):
        if not self.generated_prompts:
            QMessageBox.warning(self, "Ð ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹", "Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð² Ð¿ÑƒÑÑ‚")
            return

        selected_rows = self._get_selected_prompt_rows()
        if not selected_rows:
            QMessageBox.warning(self, "Ð ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹", "Ð’Ñ‹Ð´ÐµÐ»Ð¸Ñ‚Ðµ Ñ…Ð¾Ñ‚Ñ Ð±Ñ‹ Ð¾Ð´Ð½Ñƒ ÑÑ‚Ñ€Ð¾ÐºÑƒ")
            return

        for idx in selected_rows:
            current = self._normalize_prompt_entry(self.generated_prompts[idx])
            current["references"] = []
            self.generated_prompts[idx] = current

        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log(f"Ð ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹ Ð¾Ñ‡Ð¸Ñ‰ÐµÐ½Ñ‹ Ñƒ ÑÑ‚Ñ€Ð¾Ðº: {len(selected_rows)}")

    def open_prompt_editor(self, row_index):
        if not (0 <= row_index < len(self.generated_prompts)):
            return
        entry = self._normalize_prompt_entry(self.generated_prompts[row_index])
        self.generated_prompts[row_index] = entry

        dialog = PromptReferencesDialog(entry.get("prompt", ""), entry.get("references", []), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        prompt_text, references = dialog.get_data()
        self.generated_prompts[row_index] = {
            "prompt": prompt_text,
            "references": split_references(references),
        }
        self.refresh_prompts_table()
        self.save_prompts_storage()

    def open_prompt_references(self, row_index):
        if not (0 <= row_index < len(self.generated_prompts)):
            return
        entry = self._normalize_prompt_entry(self.generated_prompts[row_index])
        self.generated_prompts[row_index] = entry

        dialog = PromptReferencesDialog(entry.get("prompt", ""), entry.get("references", []), self, refs_only=True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        _, references = dialog.get_data()
        entry["references"] = split_references(references)
        self.generated_prompts[row_index] = entry
        self.refresh_prompts_table()
        self.save_prompts_storage()

    def pick_references_for_prompt_row(self, row_index):
        if not (0 <= row_index < len(self.generated_prompts)):
            return
        files = self._pick_reference_files()
        if not files:
            return

        entry = self._normalize_prompt_entry(self.generated_prompts[row_index])
        entry["references"] = self._merge_references(entry.get("references", []), files)
        self.generated_prompts[row_index] = entry
        self.refresh_prompts_table()
        self.save_prompts_storage()

    def on_prompt_item_double_clicked(self, item):
        if item.column() in {0, 1}:
            self.open_prompt_editor(item.row())

    def build_prompts(self):
        if not hasattr(self, "master_prompt"):
            self.log("Ð¨Ð°Ð±Ð»Ð¾Ð½Ð½Ñ‹Ð¹ Ñ€ÐµÐ¶Ð¸Ð¼ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð² Ð¾Ñ‚ÐºÐ»ÑŽÑ‡Ñ‘Ð½ Ð² Ñ‚ÐµÐºÑƒÑ‰ÐµÐ¼ Ð¸Ð½Ñ‚ÐµÑ€Ñ„ÐµÐ¹ÑÐµ")
            return
        template = self.master_prompt.toPlainText().strip()
        a = self.get_template_values(self.field_a)
        b = self.get_template_values(self.field_b)
        c = self.get_template_values(self.field_c)

        if not template:
            QMessageBox.warning(self, "ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð’Ð²ÐµÐ´Ð¸Ñ‚Ðµ Master Prompt")
            return

        self.generated_prompts = []
        max_len = max(len(a), len(b), len(c))
        if max_len == 0:
            self.generated_prompts = [{"prompt": template, "references": []}]
        else:
            for i in range(max_len):
                prompt = template
                if a and i < len(a):
                    prompt = prompt.replace("{A}", a[i])
                if b and i < len(b):
                    prompt = prompt.replace("{B}", b[i])
                if c and i < len(c):
                    prompt = prompt.replace("{C}", c[i])
                self.generated_prompts.append({"prompt": prompt, "references": []})
        self.refresh_prompts_table()

        self.log(f"Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¾ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð²: {len(self.generated_prompts)}")

    def build_prompts_from_template_inputs(self):
        if not hasattr(self, "master_prompt"):
            return []
        template = self.master_prompt.toPlainText().strip()
        if not template:
            return []

        a = self.get_template_values(self.field_a)
        b = self.get_template_values(self.field_b)
        c = self.get_template_values(self.field_c)

        prompts = []
        max_len = max(len(a), len(b), len(c))
        if max_len == 0:
            prompts = [template]
        else:
            for i in range(max_len):
                prompt = template
                if a and i < len(a):
                    prompt = prompt.replace("{A}", a[i])
                if b and i < len(b):
                    prompt = prompt.replace("{B}", b[i])
                if c and i < len(c):
                    prompt = prompt.replace("{C}", c[i])
                prompts.append(prompt)
        return [p.strip() for p in prompts if p.strip()]

    def get_list_mode_prompts(self):
        entries = []
        for entry in self.generated_prompts:
            normalized_entry = self._normalize_prompt_entry(entry)
            prompt_text = str(normalized_entry.get("prompt", "")).strip()
            references = split_references(normalized_entry.get("references", []))
            if prompt_text or references:
                entries.append({"prompt": prompt_text, "references": references})
        return entries

    def import_prompts_from_template(self):
        if not hasattr(self, "master_prompt"):
            QMessageBox.warning(self, "ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð¨Ð°Ð±Ð»Ð¾Ð½Ð½Ñ‹Ð¹ Ñ€ÐµÐ¶Ð¸Ð¼ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð² Ð½ÐµÐ´Ð¾ÑÑ‚ÑƒÐ¿ÐµÐ½")
            return
        raw_text = self.master_prompt.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð’ÑÑ‚Ð°Ð²ÑŒÑ‚Ðµ ÑÐ¿Ð¸ÑÐ¾Ðº Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð² Ð² Ð¿Ð¾Ð»Ðµ Master Prompt")
            return

        prompts = self._split_prompts_text(raw_text)
        if not prompts:
            QMessageBox.warning(self, "ÐžÑˆÐ¸Ð±ÐºÐ°", "ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ñ‚ÑŒ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ñ‹")
            return

        self.generated_prompts = [{"prompt": p, "references": []} for p in prompts]
        self.refresh_prompts_table()
        self.log(f"Ð˜Ð¼Ð¿Ð¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¾ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð²: {len(self.generated_prompts)}")

    def on_table_bulk_paste(self, raw_text):
        prompts = self._split_prompts_text(raw_text)
        self.generated_prompts = [{"prompt": p, "references": []} for p in prompts]
        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log(f"Ð’ÑÑ‚Ð°Ð²Ð»ÐµÐ½Ð¾ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð²: {len(self.generated_prompts)}")

    def import_prompts_from_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Ð’Ñ‹Ð±Ñ€Ð°Ñ‚ÑŒ CSV-Ñ„Ð°Ð¹Ð» Ñ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð°Ð¼Ð¸",
            "",
            "CSV files (*.csv);;All files (*.*)",
        )
        if not file_path:
            return

        dialog = CsvImportDialog(file_path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        imported_entries = dialog.get_entries()
        if not imported_entries:
            QMessageBox.warning(self, "Ð˜Ð¼Ð¿Ð¾Ñ€Ñ‚ CSV", "ÐÐµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð¾ Ð½Ð¸ Ð¾Ð´Ð½Ð¾Ð¹ Ð·Ð°Ð¿Ð¸ÑÐ¸ Ð´Ð»Ñ Ð¸Ð¼Ð¿Ð¾Ñ€Ñ‚Ð°")
            return

        choice_box = QMessageBox(self)
        choice_box.setIcon(QMessageBox.Icon.Question)
        choice_box.setWindowTitle("Ð˜Ð¼Ð¿Ð¾Ñ€Ñ‚ CSV")
        choice_box.setText(f"ÐÐ°Ð¹Ð´ÐµÐ½Ð¾ Ð·Ð°Ð¿Ð¸ÑÐµÐ¹: {len(imported_entries)}")
        choice_box.setInformativeText("ÐšÐ°Ðº Ð¸Ð¼Ð¿Ð¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº?")
        replace_btn = choice_box.addButton("Ð—Ð°Ð¼ÐµÐ½Ð¸Ñ‚ÑŒ Ñ‚ÐµÐºÑƒÑ‰Ð¸Ðµ", QMessageBox.ButtonRole.AcceptRole)
        append_btn = choice_box.addButton("Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ðº Ñ‚ÐµÐºÑƒÑ‰Ð¸Ð¼", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = choice_box.addButton("ÐžÑ‚Ð¼ÐµÐ½Ð°", QMessageBox.ButtonRole.RejectRole)
        choice_box.setDefaultButton(replace_btn)
        choice_box.exec()

        clicked = choice_box.clickedButton()
        if clicked == cancel_btn or clicked is None:
            return
        if clicked == replace_btn:
            self.generated_prompts = imported_entries
            self.log(f"CSV Ð¸Ð¼Ð¿Ð¾Ñ€Ñ‚: Ð·Ð°Ð¼ÐµÐ½ÐµÐ½Ð¾ Ð·Ð°Ð¿Ð¸ÑÐµÐ¹: {len(imported_entries)}")
        elif clicked == append_btn:
            self.generated_prompts.extend(imported_entries)
            self.log(f"CSV Ð¸Ð¼Ð¿Ð¾Ñ€Ñ‚: Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¾ Ð·Ð°Ð¿Ð¸ÑÐµÐ¹: {len(imported_entries)}")
        else:
            return

        self.refresh_prompts_table()
        self.save_prompts_storage()

    def _split_prompts_text(self, raw_text):
        text = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return []

        if "\t" in text:
            prompts = []
            for line in text.split("\n"):
                for cell in line.split("\t"):
                    item = cell.strip()
                    if item:
                        prompts.append(item)
            if prompts:
                return prompts

        blocks = [b.strip() for b in re.split(r"\n\s*\n+", text) if b.strip()]
        if blocks:
            return blocks

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if len(lines) > 1:
            return lines

        return [text]

    def refresh_prompts_table(self):
        self.is_updating_prompts_table = True
        self.table.setRowCount(0)
        for index, entry in enumerate(self.generated_prompts):
            normalized_entry = self._normalize_prompt_entry(entry)
            self.generated_prompts[index] = normalized_entry
            row = self.table.rowCount()
            self.table.insertRow(row)
            prompt_text = str(normalized_entry.get("prompt", ""))
            references_count = len(split_references(normalized_entry.get("references", [])))
            references_text = str(references_count)

            prompt_item = QTableWidgetItem(prompt_text)
            references_item = QTableWidgetItem(references_text)
            references_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            references_item.setFlags(references_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, prompt_item)
            self.table.setItem(row, 1, references_item)

            delete_btn = QPushButton("ðŸ—‘")
            delete_btn.setToolTip("Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð·Ð°Ð¿Ð¸ÑÑŒ")
            delete_btn.setMinimumHeight(28)
            delete_btn.clicked.connect(lambda _, r=index: self.remove_prompt_row(r))

            edit_btn = QPushButton("ðŸ–¼")
            edit_btn.setToolTip("Ð’Ñ‹Ð±Ñ€Ð°Ñ‚ÑŒ Ñ„Ð°Ð¹Ð»Ñ‹ Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÐ¾Ð²")
            edit_btn.setMinimumHeight(28)
            edit_btn.clicked.connect(lambda _, r=index: self.pick_references_for_prompt_row(r))

            self.table.setCellWidget(row, 2, edit_btn)
            self.table.setCellWidget(row, 3, delete_btn)
        self.is_updating_prompts_table = False

    def _build_references_tooltip(self, references):
        items = split_references(references)
        if not items:
            return ""
        html_parts = ["<div><b>Ð ÐµÑ„ÐµÑ€ÐµÐ½ÑÑ‹:</b></div>"]
        for ref in items[:3]:
            normalized_path = os.path.abspath(ref) if os.path.isfile(ref) else ""
            label = os.path.basename(ref) or ref
            if normalized_path:
                img_src = normalized_path.replace("\\", "/")
                html_parts.append(f"<div style='margin-top:4px;'><div>{label}</div><img src='file:///{img_src}' width='140'></div>")
            else:
                html_parts.append(f"<div style='margin-top:4px;'>{label}</div>")
        if len(items) > 3:
            html_parts.append(f"<div style='margin-top:4px;'>Ð˜ ÐµÑ‰Ñ‘: {len(items) - 3}</div>")
        return "".join(html_parts)

    def on_prompt_item_changed(self, item):
        if self.is_updating_prompts_table:
            return
        if item.column() != 0:
            return
        row = item.row()
        if 0 <= row < len(self.generated_prompts):
            current_entry = self._normalize_prompt_entry(self.generated_prompts[row])
            current_entry["prompt"] = item.text()
            self.generated_prompts[row] = current_entry
            self.save_prompts_storage()

    def remove_prompt_row(self, row_index):
        if row_index < 0 or row_index >= len(self.generated_prompts):
            return
        del self.generated_prompts[row_index]
        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log(f"Ð£Ð´Ð°Ð»ÐµÐ½Ð° Ð·Ð°Ð¿Ð¸ÑÑŒ. ÐžÑÑ‚Ð°Ð»Ð¾ÑÑŒ: {len(self.generated_prompts)}")

    def clear_all_prompts(self):
        self.generated_prompts = []
        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log("Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð·Ð°Ð¿Ð¸ÑÐµÐ¹ Ð¾Ñ‡Ð¸Ñ‰ÐµÐ½")

    def export_prompts(self):
        entries = self.get_list_mode_prompts()
        if not entries:
            QMessageBox.warning(self, "Ð­ÐºÑÐ¿Ð¾Ñ€Ñ‚ CSV", "ÐÐµÑ‚ Ð·Ð°Ð¿Ð¸ÑÐµÐ¹ Ð´Ð»Ñ ÑÐºÑÐ¿Ð¾Ñ€Ñ‚Ð°")
            return

        base_dir = self.work_dir if self.work_dir else os.getcwd()
        default_path = os.path.join(base_dir, "prompts_export.csv")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ CSV Ñ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð°Ð¼Ð¸",
            default_path,
            "CSV files (*.csv)",
        )
        if not file_path:
            return

        if not file_path.lower().endswith(".csv"):
            file_path = f"{file_path}.csv"

        try:
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Prompt", "References"])
                for entry in entries:
                    prompt_text = str(entry.get("prompt", "")).strip()
                    references_text = join_references(entry.get("references", []))
                    writer.writerow([prompt_text, references_text])
            self.log(f"CSV ÑÐºÑÐ¿Ð¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½: {file_path}")
            QMessageBox.information(
                self,
                "Ð­ÐºÑÐ¿Ð¾Ñ€Ñ‚ CSV",
                "Ð¤Ð°Ð¹Ð» ÑƒÑÐ¿ÐµÑˆÐ½Ð¾ ÑÐºÑÐ¿Ð¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Ð­ÐºÑÐ¿Ð¾Ñ€Ñ‚ CSV", f"ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ ÑÐ¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ CSV: {e}")

    def start_work(self):
        if not self.work_dir:
            QMessageBox.warning(self, "ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ Ñ€Ð°Ð±Ð¾Ñ‡ÑƒÑŽ Ð¿Ð°Ð¿ÐºÑƒ")
            return

        self.persist_ui_settings()
        current_api_key = self.config.get("kie_api_key", "").strip()

        needs_kie_api = not self.radio_run_process.isChecked() or self.chk_upscale.isChecked() or self.chk_remove_bg.isChecked()
        if needs_kie_api and not current_api_key:
            QMessageBox.warning(self, "ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð£ÐºÐ°Ð¶Ð¸Ñ‚Ðµ KIE API Key Ð½Ð° Ð²ÐºÐ»Ð°Ð´ÐºÐµ Â«ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸Â»")
            return

        runtime_settings = dict(self.config)
        runtime_settings["kie_api_key"] = current_api_key
        self.has_generated_output_in_run = False

        run_mode = self.config.get("run_mode", "generate_only")
        if run_mode == "process_only":
            mode = "mode2_process"
            if not self.selected_files:
                QMessageBox.warning(self, "ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð”Ð»Ñ Ñ€ÐµÐ¶Ð¸Ð¼Ð° Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ¸ Ð²Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ Ñ„Ð°Ð¹Ð»Ñ‹")
                return
            if not (self.chk_upscale.isChecked() or self.chk_remove_bg.isChecked() or self.chk_trim.isChecked()):
                QMessageBox.warning(self, "ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð’ÐºÐ»ÑŽÑ‡Ð¸Ñ‚Ðµ Ñ…Ð¾Ñ‚Ñ Ð±Ñ‹ Ð¾Ð´Ð¸Ð½ ÑÑ‚Ð°Ð¿: Ð°Ð¿ÑÐºÐµÐ¹Ð», ÑƒÐ´Ð°Ð»ÐµÐ½Ð¸Ðµ Ñ„Ð¾Ð½Ð° Ð¸Ð»Ð¸ trim")
                return
        elif run_mode == "both":
            active_prompts = self.get_list_mode_prompts()
            if not active_prompts:
                QMessageBox.warning(self, "ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð”Ð¾Ð±Ð°Ð²ÑŒÑ‚Ðµ Ñ…Ð¾Ñ‚Ñ Ð±Ñ‹ Ð¾Ð´Ð½Ñƒ Ð·Ð°Ð¿Ð¸ÑÑŒ")
                return
            self.generated_prompts = active_prompts
            self.refresh_prompts_table()
            mode = "mode_both"
        else:
            active_prompts = self.get_list_mode_prompts()
            if not active_prompts:
                QMessageBox.warning(self, "ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð”Ð¾Ð±Ð°Ð²ÑŒÑ‚Ðµ Ñ…Ð¾Ñ‚Ñ Ð±Ñ‹ Ð¾Ð´Ð½Ñƒ Ð·Ð°Ð¿Ð¸ÑÑŒ")
                return

            self.generated_prompts = active_prompts
            self.refresh_prompts_table()
            mode = "mode1_generate_only"

        self.worker = WorkerThread(
            mode=mode,
            work_dir=self.work_dir,
            settings=runtime_settings,
            selected_files=self.selected_files,
            generated_prompts=self.generated_prompts,
        )
        self.worker.progress.connect(self.log)
        self.worker.progress_value.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.worker.start()

    def stop_work(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait()
            self.worker = None
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log("ÐžÑÑ‚Ð°Ð½Ð¾Ð²Ð»ÐµÐ½Ð¾")
        self.offer_open_output_folder_after_stop()

    def on_finished(self, message):
        self.log(message)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(100)
        self.offer_open_output_folder(message)

    def offer_open_output_folder(self, message):
        if "Ð“Ð¾Ñ‚Ð¾Ð²Ð¾" not in (message or ""):
            return
        if not self.work_dir:
            return
        output_dir = os.path.join(self.work_dir, "output")
        if not os.path.isdir(output_dir):
            return
        answer = QMessageBox.question(
            self,
            "Ð“Ð¾Ñ‚Ð¾Ð²Ð¾",
            "ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ð·Ð°Ð²ÐµÑ€ÑˆÐµÐ½Ð°. ÐžÑ‚ÐºÑ€Ñ‹Ñ‚ÑŒ Ð¿Ð°Ð¿ÐºÑƒ Ñ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ð°Ð¼Ð¸?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            try:
                os.startfile(output_dir)
            except Exception as e:
                self.log(f"ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¾Ñ‚ÐºÑ€Ñ‹Ñ‚ÑŒ Ð¿Ð°Ð¿ÐºÑƒ output: {e}")

    def offer_open_output_folder_after_stop(self):
        output_dir = os.path.join(self.work_dir, "output") if self.work_dir else ""
        if not output_dir or not os.path.isdir(output_dir):
            return
        if not self.has_generated_output_in_run:
            return
        answer = QMessageBox.question(
            self,
            "ÐžÑÑ‚Ð°Ð½Ð¾Ð²ÐºÐ°",
            "ÐžÑÑ‚Ð°Ð½Ð¾Ð²ÐºÐ° Ð²Ñ‹Ð¿Ð¾Ð»Ð½ÐµÐ½Ð°. ÐžÑ‚ÐºÑ€Ñ‹Ñ‚ÑŒ Ð¿Ð°Ð¿ÐºÑƒ Ñ ÑƒÐ¶Ðµ Ð³Ð¾Ñ‚Ð¾Ð²Ñ‹Ð¼Ð¸ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ð°Ð¼Ð¸?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            try:
                os.startfile(output_dir)
            except Exception as e:
                self.log(f"ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¾Ñ‚ÐºÑ€Ñ‹Ñ‚ÑŒ Ð¿Ð°Ð¿ÐºÑƒ output: {e}")

    def on_error(self, err):
        self.log(f"ÐžÑˆÐ¸Ð±ÐºÐ°: {err}")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def log(self, msg):
        if "Ð˜Ñ‚Ð¾Ð³ ÑÐ¾Ñ…Ñ€Ð°Ð½Ñ‘Ð½:" in (msg or ""):
            self.has_generated_output_in_run = True
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")

    def on_api_key_changed(self, *_):
        self.api_key_mask_timer.start()

    def enforce_api_key_hidden(self):
        if self.api_key_locked:
            self.kie_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

    def toggle_api_key_lock(self):
        self.api_key_locked = not self.api_key_locked
        if self.api_key_locked:
            self.kie_api_key_input.setReadOnly(True)
            self.kie_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_api_key_lock.setText("ðŸ”’")
            self.btn_api_key_lock.setToolTip("ÐšÐ»ÑŽÑ‡ Ð·Ð°Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ð½")
            self.log("KIE API Key Ð·Ð°Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ð½")
            return

        self.kie_api_key_input.setReadOnly(False)
        self.kie_api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        self.btn_api_key_lock.setText("ðŸ”“")
        self.btn_api_key_lock.setToolTip("ÐšÐ»ÑŽÑ‡ Ñ€Ð°Ð·Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ð½")
        self.log("KIE API Key Ñ€Ð°Ð·Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ð½: Ð¼Ð¾Ð¶Ð½Ð¾ ÑÐ¼Ð¾Ñ‚Ñ€ÐµÑ‚ÑŒ Ð¸ Ñ€ÐµÐ´Ð°ÐºÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ")

    def check_generation_model(self):
        api_key = self.kie_api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð¡Ð½Ð°Ñ‡Ð°Ð»Ð° ÑƒÐºÐ°Ð¶Ð¸Ñ‚Ðµ KIE API Key")
            return

        text_model = self.get_selected_generation_model_id(self.text_generation_model_combo)
        reference_model = self.get_selected_generation_model_id(self.reference_generation_model_combo)
        timeout = max(10, int(self.config.get("timeout", 60)))
        ratio = self.generation_size_combo.currentText().strip() or "1:1"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        reference_model_type = (GENERATION_MODEL_META.get(reference_model) or {}).get("type", "text_to_image")

        try:
            text_ok, text_msg, text_task_id = self._probe_model_with_ratio(text_model, "1:1", headers, timeout)
            if not text_ok:
                raise RuntimeError(f"ÐÐµÐ´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð° Ð¼Ð¾Ð´ÐµÐ»ÑŒ Ð´Ð»Ñ Ñ‚ÐµÐºÑÑ‚Ð¾Ð²Ñ‹Ñ… Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð²: {text_model}. {text_msg}")

            # Ð•ÑÐ»Ð¸ ÑƒÐ¶Ðµ Ð¿Ñ€Ð¾Ð²ÐµÑ€Ð¸Ð»Ð¸ 1:1 Ð¸ Ð²Ñ‹Ð±Ñ€Ð°Ð½ Ñ‚Ð¾Ð¶Ðµ 1:1, Ð¿Ð¾Ð²Ñ‚Ð¾Ñ€Ð½Ñ‹Ð¹ ÑÐµÑ‚ÐµÐ²Ð¾Ð¹ Ð·Ð°Ð¿Ñ€Ð¾Ñ Ð½Ðµ Ð½ÑƒÐ¶ÐµÐ½.
            if ratio != "1:1":
                ratio_ok, ratio_msg, _ = self._probe_model_with_ratio(text_model, ratio, headers, timeout)
                if not ratio_ok:
                    raise RuntimeError(
                        f"ÐÐµÐ´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð¾ ÑÐ¾Ð¾Ñ‚Ð½Ð¾ÑˆÐµÐ½Ð¸Ðµ {ratio} Ð´Ð»Ñ Ð¼Ð¾Ð´ÐµÐ»Ð¸ {text_model}. {ratio_msg}"
                    )

            ref_ok, ref_msg, ref_task_id = self._probe_model_with_ratio(reference_model, "1:1", headers, timeout)
            if (
                not ref_ok
                and reference_model == "gpt-image/1.5-image-to-image"
                and "This field is required" in str(ref_msg)
            ):
                self.log(
                    "ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° image-to-image Ð´Ð»Ñ gpt-image/1.5-image-to-image Ð¿Ñ€Ð¾Ð¿ÑƒÑ‰ÐµÐ½Ð°: "
                    "API Ð²Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÑ‚ schema-Ð¾ÑˆÐ¸Ð±ÐºÑƒ Ð½Ð° Ñ‚ÐµÑÑ‚Ð¾Ð²Ð¾Ð¼ Ð·Ð°Ð¿Ñ€Ð¾ÑÐµ, Ð½Ð¾ Ð¼Ð¾Ð´ÐµÐ»ÑŒ Ð¼Ð¾Ð¶ÐµÑ‚ Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ñ‚ÑŒ Ð² Ñ€ÐµÐ°Ð»ÑŒÐ½Ð¾Ð¼ Ð·Ð°Ð¿ÑƒÑÐºÐµ."
                )
                ref_ok = True
                ref_task_id = "schema-check-skipped"
            elif (
                not ref_ok
                and reference_model_type in {"image_to_image", "edit"}
                and self._is_schema_required_error(ref_msg)
            ):
                self.log(
                    "ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° image-to-image/edit Ð¼Ð¾Ð´ÐµÐ»Ð¸ Ð¿ÐµÑ€ÐµÐ²ÐµÐ´ÐµÐ½Ð° Ð² Ð¼ÑÐ³ÐºÐ¸Ð¹ Ñ€ÐµÐ¶Ð¸Ð¼: "
                    "API Ð²ÐµÑ€Ð½ÑƒÐ» schema-Ð¾ÑˆÐ¸Ð±ÐºÑƒ Ð½Ð° Ñ‚ÐµÑÑ‚Ð¾Ð²Ð¾Ð¼ Ð·Ð°Ð¿Ñ€Ð¾ÑÐµ. ÐœÐ¾Ð´ÐµÐ»ÑŒ Ð±ÑƒÐ´ÐµÑ‚ Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐµÐ½Ð° Ñ€ÐµÐ°Ð»ÑŒÐ½Ñ‹Ð¼ Ð·Ð°Ð¿ÑƒÑÐºÐ¾Ð¼."
                )
                ref_ok = True
                ref_task_id = "schema-check-skipped"
            if not ref_ok:
                raise RuntimeError(f"ÐÐµÐ´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð° Ð¼Ð¾Ð´ÐµÐ»ÑŒ Ð´Ð»Ñ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð¾Ð² Ñ Ñ€ÐµÑ„ÐµÑ€ÐµÐ½ÑÐ°Ð¼Ð¸: {reference_model}. {ref_msg}")

            if ratio != "1:1":
                ref_ratio_ok, ref_ratio_msg, _ = self._probe_model_with_ratio(reference_model, ratio, headers, timeout)
                if (
                    not ref_ratio_ok
                    and reference_model == "gpt-image/1.5-image-to-image"
                    and "This field is required" in str(ref_ratio_msg)
                ):
                    self.log(
                        "ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° ÑÐ¾Ð¾Ñ‚Ð½Ð¾ÑˆÐµÐ½Ð¸Ñ Ð´Ð»Ñ gpt-image/1.5-image-to-image Ð¿Ñ€Ð¾Ð¿ÑƒÑ‰ÐµÐ½Ð°: "
                        "API Ð²Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÑ‚ schema-Ð¾ÑˆÐ¸Ð±ÐºÑƒ Ð½Ð° Ñ‚ÐµÑÑ‚Ð¾Ð²Ð¾Ð¼ Ð·Ð°Ð¿Ñ€Ð¾ÑÐµ."
                    )
                    ref_ratio_ok = True
                elif (
                    not ref_ratio_ok
                    and reference_model_type in {"image_to_image", "edit"}
                    and self._is_schema_required_error(ref_ratio_msg)
                ):
                    self.log(
                        "ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° ÑÐ¾Ð¾Ñ‚Ð½Ð¾ÑˆÐµÐ½Ð¸Ñ Ð´Ð»Ñ image-to-image/edit Ð¼Ð¾Ð´ÐµÐ»Ð¸ Ð¿Ñ€Ð¾Ð¿ÑƒÑ‰ÐµÐ½Ð°: "
                        "API Ð²ÐµÑ€Ð½ÑƒÐ» schema-Ð¾ÑˆÐ¸Ð±ÐºÑƒ Ð½Ð° Ñ‚ÐµÑÑ‚Ð¾Ð²Ð¾Ð¼ Ð·Ð°Ð¿Ñ€Ð¾ÑÐµ."
                    )
                    ref_ratio_ok = True
                if not ref_ratio_ok:
                    raise RuntimeError(
                        f"ÐÐµÐ´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð¾ ÑÐ¾Ð¾Ñ‚Ð½Ð¾ÑˆÐµÐ½Ð¸Ðµ {ratio} Ð´Ð»Ñ Ð¼Ð¾Ð´ÐµÐ»Ð¸ {reference_model}. {ref_ratio_msg}"
                    )

            self.log(
                (
                    "ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹ ÑƒÑÐ¿ÐµÑˆÐ½Ð°. "
                    f"Textâ†’Image: {text_model} (Task ID: {text_task_id}) | "
                    f"Imageâ†’Image: {reference_model} (Task ID: {ref_task_id})"
                )
            )
            QMessageBox.information(self, "ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹", "ÐžÐ±Ðµ Ð¼Ð¾Ð´ÐµÐ»Ð¸ Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ñ‹")
        except urlerror.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            msg = f"HTTP {e.code} {e.reason}"
            if body:
                msg = f"{msg}: {body[:400]}"
            self.log(f"ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹ Ð½Ðµ Ð¿Ñ€Ð¾Ð¹Ð´ÐµÐ½Ð°: {msg}")
            QMessageBox.warning(self, "ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹", f"ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð½Ðµ Ð¿Ñ€Ð¾Ð¹Ð´ÐµÐ½Ð°\n{msg}")
        except Exception as e:
            self.log(f"ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹ Ð½Ðµ Ð¿Ñ€Ð¾Ð¹Ð´ÐµÐ½Ð°: {e}")
            QMessageBox.warning(self, "ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹", f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÐ¸: {e}")

    def _is_schema_required_error(self, message):
        text = str(message or "").lower()
        return (
            "is required" in text
            or "field is required" in text
            or "required field" in text
            or "missing required" in text
        )

    def _extract_credit_value(self, payload):
        priority_keys = [
            "remainingCredits",
            "remainingCredit",
            "remaining_credits",
            "remaining_credit",
            "availableCredits",
            "available_credits",
            "credits",
            "credit",
            "balance",
            "amount",
            "totalCredits",
            "total_credits",
        ]

        def _looks_like_number(value):
            if isinstance(value, (int, float)):
                return True
            if isinstance(value, str):
                text = value.strip().replace(",", ".")
                if not text:
                    return False
                try:
                    float(text)
                    return True
                except Exception:
                    return False
            return False

        if isinstance(payload, dict):
            for key in priority_keys:
                if key in payload:
                    return key, payload.get(key)

            # Ð§Ð°ÑÑ‚Ñ‹Ð¹ Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚: data = Ñ‡Ð¸ÑÐ»Ð¾/ÑÑ‚Ñ€Ð¾ÐºÐ° Ñ Ñ‡Ð¸ÑÐ»Ð¾Ð¼
            if "data" in payload and _looks_like_number(payload.get("data")):
                return "data", payload.get("data")

            for value in payload.values():
                found = self._extract_credit_value(value)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = self._extract_credit_value(item)
                if found is not None:
                    return found
        elif _looks_like_number(payload):
            return "value", payload
        return None

    def check_kie_balance(self):
        api_key = self.kie_api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð¡Ð½Ð°Ñ‡Ð°Ð»Ð° ÑƒÐºÐ°Ð¶Ð¸Ñ‚Ðµ KIE API Key")
            return

        timeout = max(10, int(self.config.get("timeout", 60)))
        headers = {
            "Authorization": f"Bearer {api_key}",
            "x-api-key": api_key,
            "Accept": "application/json",
            "User-Agent": "ClipartGenerator/1.0 (+PyQt6)",
        }

        self.btn_check_balance.setEnabled(False)
        self.btn_check_balance.setText("ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ°...")
        try:
            req = request.Request("https://api.kie.ai/api/v1/chat/credit", headers=headers, method="GET")
            with request.urlopen(req, timeout=timeout, context=build_ssl_context()) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            if int(result.get("code", 200)) not in {0, 200}:
                raise RuntimeError(result.get("msg") or "KIE Ð²ÐµÑ€Ð½ÑƒÐ» Ð¾ÑˆÐ¸Ð±ÐºÑƒ Ð¿Ñ€Ð¸ Ð¿Ð¾Ð»ÑƒÑ‡ÐµÐ½Ð¸Ð¸ Ð±Ð°Ð»Ð°Ð½ÑÐ°")

            extracted = self._extract_credit_value(result)
            if extracted is None:
                preview = json.dumps(result, ensure_ascii=False)[:1200]
                self.log(f"Ð‘Ð°Ð»Ð°Ð½Ñ KIE: Ð¿Ð¾Ð»Ðµ Ñ ÐºÑ€ÐµÐ´Ð¸Ñ‚Ð°Ð¼Ð¸ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð¾. ÐŸÐ¾Ð»Ð½Ñ‹Ð¹ Ð¾Ñ‚Ð²ÐµÑ‚: {preview}")
                QMessageBox.information(
                    self,
                    "Ð‘Ð°Ð»Ð°Ð½Ñ KIE",
                    "Ð—Ð°Ð¿Ñ€Ð¾Ñ Ð²Ñ‹Ð¿Ð¾Ð»Ð½ÐµÐ½, Ð½Ð¾ Ð¿Ð¾Ð»Ðµ Ð±Ð°Ð»Ð°Ð½ÑÐ° Ð½Ðµ Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð½Ð¾.\n"
                    "ÐžÑ‚Ð²ÐµÑ‚ ÑÐµÑ€Ð²ÐµÑ€Ð° ÑÐ¾Ñ…Ñ€Ð°Ð½Ñ‘Ð½ Ð² Ð»Ð¾Ð³Ðµ (Ð½Ð¸Ð¶Ð½ÑÑ Ð¿Ð°Ð½ÐµÐ»ÑŒ).",
                )
                return

            key, value = extracted
            self.log(f"Ð‘Ð°Ð»Ð°Ð½Ñ KIE: {value} ÐºÑ€ÐµÐ´Ð¸Ñ‚Ð¾Ð²")
            QMessageBox.information(self, "Ð‘Ð°Ð»Ð°Ð½Ñ KIE", f"{value} ÐºÑ€ÐµÐ´Ð¸Ñ‚Ð¾Ð²")
        except urlerror.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            msg = f"HTTP {e.code} {e.reason}"
            if body:
                msg = f"{msg}: {body[:400]}"
            self.log(f"ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð±Ð°Ð»Ð°Ð½ÑÐ° Ð½Ðµ Ð¿Ñ€Ð¾Ð¹Ð´ÐµÐ½Ð°: {msg}")
            QMessageBox.warning(self, "Ð‘Ð°Ð»Ð°Ð½Ñ KIE", f"ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð½Ðµ Ð¿Ñ€Ð¾Ð¹Ð´ÐµÐ½Ð°\n{msg}")
        except Exception as e:
            self.log(f"ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð±Ð°Ð»Ð°Ð½ÑÐ° Ð½Ðµ Ð¿Ñ€Ð¾Ð¹Ð´ÐµÐ½Ð°: {e}")
            QMessageBox.warning(self, "Ð‘Ð°Ð»Ð°Ð½Ñ KIE", f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÐ¸: {e}")
        finally:
            self.btn_check_balance.setEnabled(True)
            self.btn_check_balance.setText("ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ Ð±Ð°Ð»Ð°Ð½Ñ")

    def check_license_key(self):
        license_key = self.license_key_input.text().strip()
        if not license_key:
            QMessageBox.warning(self, "Ð›Ð¸Ñ†ÐµÐ½Ð·Ð¸Ñ", "Ð’Ð²ÐµÐ´Ð¸Ñ‚Ðµ Ð»Ð¸Ñ†ÐµÐ½Ð·Ð¸Ð¾Ð½Ð½Ñ‹Ð¹ ÐºÐ»ÑŽÑ‡")
            return

        try:
            license_client = self._build_license_client()
            if not (license_client.server_url or license_client.backup_server_url):
                QMessageBox.warning(
                    self,
                    "Ð›Ð¸Ñ†ÐµÐ½Ð·Ð¸Ñ",
                    "ÐÐµ Ð·Ð°Ð´Ð°Ð½ URL ÑÐµÑ€Ð²ÐµÑ€Ð° Ð»Ð¸Ñ†ÐµÐ½Ð·Ð¸Ð¹ Ð² config.json",
                )
                return

            result = license_client.status(license_key, use_offline=True)
            activated_now = False
            if not result.get("ok"):
                activation_result = license_client.activate(license_key)
                if activation_result.get("ok"):
                    result = activation_result
                    activated_now = True

            if not result.get("ok"):
                message = str(result.get("message") or "ÐšÐ»ÑŽÑ‡ Ð½Ðµ Ð¿Ñ€Ð¾ÑˆÑ‘Ð» Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÑƒ")
                self.log(f"Ð›Ð¸Ñ†ÐµÐ½Ð·Ð¸Ñ Ð½Ðµ Ð¿Ñ€Ð¾ÑˆÐ»Ð° Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÑƒ: {message}")
                QMessageBox.warning(self, "Ð›Ð¸Ñ†ÐµÐ½Ð·Ð¸Ñ", message)
                return

            self.config["license_key"] = license_key
            self.save_config()

            expires_at = str(result.get("expires_at") or "-")
            updates_until = str(result.get("updates_until") or "-")
            updates_allowed = "Ð”Ð°" if result.get("updates_allowed", True) else "ÐÐµÑ‚"
            state_text = "Ð›Ð¸Ñ†ÐµÐ½Ð·Ð¸Ñ Ð°ÐºÑ‚Ð¸Ð²Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð°" if activated_now else "Ð›Ð¸Ñ†ÐµÐ½Ð·Ð¸Ñ Ð¿Ð¾Ð´Ñ‚Ð²ÐµÑ€Ð¶Ð´ÐµÐ½Ð°"
            message = (
                f"{state_text}\n"
                f"Ð¡Ñ€Ð¾Ðº Ð»Ð¸Ñ†ÐµÐ½Ð·Ð¸Ð¸: {expires_at}\n"
                f"ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ Ð´Ð¾: {updates_until}\n"
                f"ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ñ‹: {updates_allowed}"
            )
            self.log(f"ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð»Ð¸Ñ†ÐµÐ½Ð·Ð¸Ð¸ ÑƒÑÐ¿ÐµÑˆÐ½Ð°: {state_text}")
            QMessageBox.information(self, "Ð›Ð¸Ñ†ÐµÐ½Ð·Ð¸Ñ", message)
        except Exception as e:
            self.log(f"ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð»Ð¸Ñ†ÐµÐ½Ð·Ð¸Ð¸ Ð½Ðµ Ð¿Ñ€Ð¾Ð¹Ð´ÐµÐ½Ð°: {e}")
            QMessageBox.warning(self, "Ð›Ð¸Ñ†ÐµÐ½Ð·Ð¸Ñ", f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÐ¸: {e}")

    def _probe_model_with_ratio(self, raw_model, ratio, headers, timeout):
        prompt = "simple test image"
        legacy_size = self._ratio_to_legacy_size_ui(ratio)
        sample_image_url = "https://picsum.photos/768/768"
        probe_timeout = min(max(8, timeout), 20)

        model = self._normalize_generation_model_id(raw_model)
        if model in {"gpt4o-image", "gpt-image-1", "gpt-image-1.5"}:
            model = "gpt4o-image"

        if not model:
            model = "gpt4o-image"

        model_type = (GENERATION_MODEL_META.get(model) or {}).get("type", "text_to_image")

        if model == "gpt4o-image":
            url = "https://api.kie.ai/api/v1/gpt4o-image/generate"
            payload_variants = [
                {"prompt": prompt, "size": legacy_size},
                {"prompt": prompt, "size": ratio},
                {"prompt": prompt, "aspectRatio": ratio},
                {"prompt": prompt, "aspect_ratio": ratio},
            ]
        else:
            url = "https://api.kie.ai/api/v1/jobs/createTask"
            test_model = model
            if model_type == "text_to_image":
                payload_variants = self._build_text_probe_variants(
                    test_model,
                    prompt,
                    ratio,
                    legacy_size,
                )
            else:
                # Ð”Ð»Ñ image/edit Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹ Ð·Ð°Ð´Ð°Ñ‘Ð¼ Ð¿Ñ€Ð¸Ð¾Ñ€Ð¸Ñ‚ÐµÑ‚Ñ‹ Ð¿Ð¾ ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½Ð¾Ð¹ Ð¼Ð¾Ð´ÐµÐ»Ð¸,
                # Ð° Ð·Ð°Ñ‚ÐµÐ¼ ÑƒÐ¶Ðµ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ Ð¾Ð±Ñ‰Ð¸Ð¹ fallback-Ð½Ð°Ð±Ð¾Ñ€ ÑÑ…ÐµÐ¼.
                payload_variants = self._build_reference_probe_variants(
                    test_model,
                    prompt,
                    sample_image_url,
                    ratio,
                    legacy_size,
                )

        last_error = "ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð²Ñ‹Ð¿Ð¾Ð»Ð½Ð¸Ñ‚ÑŒ Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÑƒ"
        for payload in payload_variants:
            try:
                req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with request.urlopen(req, timeout=probe_timeout, context=build_ssl_context()) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if int(data.get("code", 0)) == 200:
                    task_id = (data.get("data") or {}).get("taskId", "-")
                    return True, "OK", task_id
                last_error = data.get("msg") or "ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð½Ðµ Ð¿Ñ€Ð¾Ð¹Ð´ÐµÐ½Ð°"
            except Exception as e:
                last_error = str(e)

        return False, last_error, "-"

    def _parse_version_tuple(self, version_text):
        parts = str(version_text or "0.0.0").strip().split(".")
        numbers = []
        for part in parts:
            try:
                numbers.append(int(part))
            except Exception:
                numbers.append(0)
        while len(numbers) < 3:
            numbers.append(0)
        return tuple(numbers[:3])

    def _is_newer_version(self, latest, current):
        return self._parse_version_tuple(latest) > self._parse_version_tuple(current)

    def _sha256_file(self, file_path):
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest().lower()

    def _download_update_installer(self, download_url, expected_sha256=None):
        req = request.Request(
            download_url,
            headers={
                "User-Agent": "ClipartGenerator-Updater/1.0",
                "Accept": "application/octet-stream,*/*",
            },
            method="GET",
        )
        with request.urlopen(req, timeout=120, context=build_ssl_context()) as resp:
            content = resp.read()

        temp_dir = tempfile.gettempdir()
        filename = f"ClipartGenerator-Update-{int(time.time())}.exe"
        installer_path = os.path.join(temp_dir, filename)
        with open(installer_path, "wb") as f:
            f.write(content)

        if expected_sha256:
            actual = self._sha256_file(installer_path)
            if actual != expected_sha256.lower().strip():
                try:
                    os.remove(installer_path)
                except Exception:
                    pass
                raise RuntimeError("ÐšÐ¾Ð½Ñ‚Ñ€Ð¾Ð»ÑŒÐ½Ð°Ñ ÑÑƒÐ¼Ð¼Ð° Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ Ð½Ðµ ÑÐ¾Ð²Ð¿Ð°Ð»Ð°")

        return installer_path

    def _run_downloaded_installer(self, installer_path):
        if not os.path.isfile(installer_path):
            raise RuntimeError("Ð¤Ð°Ð¹Ð» ÑƒÑÑ‚Ð°Ð½Ð¾Ð²Ñ‰Ð¸ÐºÐ° Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½")
        os.startfile(installer_path)

    def _build_license_client(self):
        license_server_url = str(self.config.get("license_server_url", "")).strip()
        license_backup_server_url = str(self.config.get("license_backup_server_url", "")).strip()
        return LicenseClient(
            server_url=license_server_url,
            backup_server_url=license_backup_server_url,
            cache_path=LICENSE_CACHE_FILE,
            app_version=APP_VERSION,
            timeout=max(5, int(self.config.get("timeout", 60))),
        )

    def _should_show_updates_expired_notice(self):
        last_notice_raw = str(self.config.get("last_updates_expired_notice_at", "")).strip()
        if not last_notice_raw:
            return True
        try:
            last_notice_at = datetime.fromisoformat(last_notice_raw)
            if last_notice_at.tzinfo is None:
                last_notice_at = last_notice_at.replace(tzinfo=timezone.utc)
        except Exception:
            return True
        return (datetime.now(timezone.utc) - last_notice_at) >= timedelta(days=30)

    def _mark_updates_expired_notice_shown(self):
        self.config["last_updates_expired_notice_at"] = datetime.now(timezone.utc).isoformat()
        self.save_config()

    def check_for_updates(self, silent=False):
        manifest_url = UPDATE_MANIFEST_URL
        if not manifest_url:
            if not silent:
                QMessageBox.warning(self, "ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ", "ÐÐµ Ð·Ð°Ð´Ð°Ð½ URL version.json")
            return

        try:
            req = request.Request(
                manifest_url,
                headers={
                    "User-Agent": "ClipartGenerator-Updater/1.0",
                    "Accept": "application/json",
                },
                method="GET",
            )
            with request.urlopen(req, timeout=20, context=build_ssl_context()) as resp:
                # ÐŸÐ¾Ð´Ð´ÐµÑ€Ð¶ÐºÐ° BOM Ð² JSON (Ð½Ð°Ð¿Ñ€Ð¸Ð¼ÐµÑ€, ÐµÑÐ»Ð¸ version.json ÑÐ¾Ñ…Ñ€Ð°Ð½Ñ‘Ð½ PowerShell Ñ UTF-8 BOM).
                manifest = json.loads(resp.read().decode("utf-8-sig"))

            latest_version = str(manifest.get("latest_version", "")).strip()
            download_url = str(manifest.get("download_url", "")).strip()
            checksum = str(manifest.get("sha256", "")).strip()

            if not latest_version or not download_url:
                raise RuntimeError("version.json Ð½Ðµ ÑÐ¾Ð´ÐµÑ€Ð¶Ð¸Ñ‚ latest_version/download_url")

            # Ð˜ÑÑ‚Ð¾Ñ‡Ð½Ð¸Ðº Ð¸ÑÑ‚Ð¸Ð½Ñ‹ Ð¾ Ñ‚ÐµÐºÑƒÑ‰ÐµÐ¹ Ð²ÐµÑ€ÑÐ¸Ð¸ â€” ÐºÐ¾Ð½ÑÑ‚Ð°Ð½Ñ‚Ð° Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ Ð¸Ð· Ñ‚ÐµÐºÑƒÑ‰ÐµÐ¹ ÑÐ±Ð¾Ñ€ÐºÐ¸.
            current_version = APP_VERSION
            if not self._is_newer_version(latest_version, current_version):
                if not silent:
                    QMessageBox.information(self, "ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ", f"Ð£ Ð²Ð°Ñ Ð°ÐºÑ‚ÑƒÐ°Ð»ÑŒÐ½Ð°Ñ Ð²ÐµÑ€ÑÐ¸Ñ: {current_version}")
                return

            # Ð’ silent-Ñ€ÐµÐ¶Ð¸Ð¼Ðµ Ð¾Ð±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ÑÑ Ð±ÐµÐ· Ð´Ð¸Ð°Ð»Ð¾Ð³Ð¾Ð².
            if silent:
                self.log(f"Ð”Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð¾ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ {latest_version}. Ð¡ÐºÐ°Ñ‡Ð¸Ð²Ð°Ð½Ð¸Ðµ...")
                installer_path = self._download_update_installer(download_url, expected_sha256=checksum or None)
                self.log(f"Ð£ÑÑ‚Ð°Ð½Ð¾Ð²Ñ‰Ð¸Ðº ÑÐºÐ°Ñ‡Ð°Ð½: {installer_path}")
                self._run_downloaded_installer(installer_path)
                QApplication.instance().quit()
                return

            answer = QMessageBox.question(
                self,
                "Ð”Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð¾ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ",
                (
                    f"Ð”Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð° Ð½Ð¾Ð²Ð°Ñ Ð²ÐµÑ€ÑÐ¸Ñ: {latest_version}\n"
                    f"Ð¢ÐµÐºÑƒÑ‰Ð°Ñ Ð²ÐµÑ€ÑÐ¸Ñ: {current_version}\n\n"
                    "Ð£ÑÑ‚Ð°Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐµÐ¹Ñ‡Ð°Ñ?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.log("ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ Ð¾Ñ‚Ð»Ð¾Ð¶ÐµÐ½Ð¾ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¼")
                return

            self.log(f"Ð¡ÐºÐ°Ñ‡Ð¸Ð²Ð°Ð½Ð¸Ðµ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ {latest_version}...")
            installer_path = self._download_update_installer(download_url, expected_sha256=checksum or None)
            self.log(f"Ð£ÑÑ‚Ð°Ð½Ð¾Ð²Ñ‰Ð¸Ðº ÑÐºÐ°Ñ‡Ð°Ð½: {installer_path}")
            self._run_downloaded_installer(installer_path)
            QMessageBox.information(
                self,
                "ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ",
                "Ð£ÑÑ‚Ð°Ð½Ð¾Ð²Ñ‰Ð¸Ðº Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ Ð·Ð°Ð¿ÑƒÑ‰ÐµÐ½. ÐŸÐ¾ÑÐ»Ðµ Ð·Ð°Ð²ÐµÑ€ÑˆÐµÐ½Ð¸Ñ ÑƒÑÑ‚Ð°Ð½Ð¾Ð²ÐºÐ¸ Ð¾Ñ‚ÐºÑ€Ð¾Ð¹Ñ‚Ðµ Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ðµ ÑÐ½Ð¾Ð²Ð°.",
            )
            QApplication.instance().quit()
        except Exception as e:
            human_error = str(e)
            if isinstance(e, urlerror.URLError):
                reason = getattr(e, "reason", None)
                if reason is not None and ("11001" in str(reason) or "getaddrinfo" in str(reason).lower()):
                    human_error = "ÐÐµÑ‚ Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð° Ðº ÑÐµÑ‚Ð¸ Ð¸Ð»Ð¸ DNS Ð½Ðµ Ð¼Ð¾Ð¶ÐµÑ‚ Ñ€Ð°Ð·Ñ€ÐµÑˆÐ¸Ñ‚ÑŒ Ð°Ð´Ñ€ÐµÑ ÑÐµÑ€Ð²ÐµÑ€Ð° Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ð¹"
                elif reason is not None and "certificate_verify_failed" in str(reason).lower():
                    human_error = (
                        "ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¿Ñ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ SSL-ÑÐµÑ€Ñ‚Ð¸Ñ„Ð¸ÐºÐ°Ñ‚. ÐŸÑ€Ð¾Ð²ÐµÑ€ÑŒÑ‚Ðµ Ð´Ð°Ñ‚Ñƒ/Ð²Ñ€ÐµÐ¼Ñ Windows, "
                        "Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ ÐºÐ¾Ñ€Ð½ÐµÐ²Ñ‹Ñ… ÑÐµÑ€Ñ‚Ð¸Ñ„Ð¸ÐºÐ°Ñ‚Ð¾Ð² Ð¸ Ð´Ð¾ÑÑ‚ÑƒÐ¿ Ðº github.com"
                    )
            self.log(f"ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ð¹: {human_error}")
            if not silent:
                QMessageBox.warning(self, "ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ", f"ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¿Ñ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ: {human_error}")

    def _ratio_to_legacy_size_ui(self, ratio):
        return {
            "1:1": "1024x1024",
            "4:3": "1536x1024",
            "3:4": "1024x1536",
            "16:9": "1536x1024",
            "9:16": "1024x1536",
        }.get(ratio, "1024x1024")

    def persist_ui_settings(self):
        self.config["kie_api_key"] = self.kie_api_key_input.text().strip()
        if hasattr(self, "license_key_input"):
            self.config["license_key"] = self.license_key_input.text().strip()
        if hasattr(self, "license_server_url_input"):
            self.config["license_server_url"] = self.license_server_url_input.text().strip()
        if hasattr(self, "license_backup_server_url_input"):
            self.config["license_backup_server_url"] = self.license_backup_server_url_input.text().strip()
        self.config["text_generation_model"] = self.get_selected_generation_model_id(self.text_generation_model_combo)
        self.config["reference_generation_model"] = self.get_selected_generation_model_id(
            self.reference_generation_model_combo
        )
        self.config["generation_model"] = self.config["text_generation_model"]
        self.config["generation_size"] = self.generation_size_combo.currentText()
        self.config["remove_bg"] = self.chk_remove_bg.isChecked()
        self.config["upscale"] = self.chk_upscale.isChecked()
        self.config["trim_enabled"] = self.chk_trim.isChecked()
        self.config["trim_mode"] = str(self.trim_mode_combo.currentData() or "alpha")
        self.config["trim_position"] = str(self.trim_position_combo.currentData() or "post")
        self.config["upscale_factor"] = int(self.upscale_factor_combo.currentText())
        self.config["kie_upscale_model"] = self.kie_upscale_model_combo.currentText()
        self.config["kie_remove_bg_model"] = self.kie_remove_bg_model_combo.currentText()
        self.config["update_manifest_url"] = UPDATE_MANIFEST_URL
        self.config["prompt_input_mode"] = "list"
        if self.radio_run_process.isChecked():
            self.config["run_mode"] = "process_only"
        elif self.radio_run_both.isChecked():
            self.config["run_mode"] = "both"
        else:
            self.config["run_mode"] = "generate_only"
        self.save_config()

    def closeEvent(self, event):
        try:
            self.settings_save_timer.stop()
            self.persist_ui_settings()
            self.save_prompts_storage()
        except Exception:
            pass
        super().closeEvent(event)


if __name__ == "__main__":
    # Ð—Ð°Ñ‰Ð¸Ñ‚Ð° Ð¾Ñ‚ ÑÐ»ÑƒÑ‡Ð°Ð¹Ð½Ð¾Ð³Ð¾ Ð·Ð°Ð¿ÑƒÑÐºÐ° Ð² offscreen-Ñ€ÐµÐ¶Ð¸Ð¼Ðµ Ð² Ñ€Ð°Ð±Ð¾Ñ‡ÐµÐ¼ Ñ‚ÐµÑ€Ð¼Ð¸Ð½Ð°Ð»Ðµ.
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        os.environ["QT_QPA_PLATFORM"] = "windows"
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())



