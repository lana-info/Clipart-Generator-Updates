import sys
import os
import json
import time
import uuid
import tempfile
import hashlib
import mimetypes
import re
from urllib.parse import urlparse
from urllib import error as urlerror
from urllib import request, parse
from datetime import datetime
from PIL import Image

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QKeySequence
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
)

APP_VERSION = "0.1.0"
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/lana-info/Clipart-Generator-Updates/main/version.json"
PROMPTS_STORAGE_FILE = "prompts.json"


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

        self.kie_api_key = settings.get("kie_api_key", "").strip()
        self.kie_upload_path = settings.get("kie_upload_path", "clipart-generator")
        self.generation_model = settings.get("generation_model", "gpt4o-image")
        self.generation_size = settings.get("generation_size", "1:1")
        self.timeout = max(10, int(settings.get("timeout", 60)))
        self.retries = max(0, int(settings.get("retries", 3)))
        self.generation_wait_timeout = max(120, int(settings.get("generation_wait_timeout", 300)))

        self.upscale = settings.get("upscale", True)
        self.remove_bg = settings.get("remove_bg", True)
        self.kie_upscale_model = settings.get("kie_upscale_model", "topaz/upscale")
        self.kie_remove_bg_model = settings.get("kie_remove_bg_model", "recraft/remove-background")
        self.upscale_factor = int(settings.get("upscale_factor", 4) or 4)
        self.upscale_target_size = str(settings.get("upscale_target_size", "")).strip()

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
        self.progress.emit("Mode 1: Генерация из промптов")
        self.progress.emit(f"Рабочая папка: {self.work_dir}")
        if not self.kie_api_key:
            raise ValueError("Не указан KIE API Key")

        raw_dir = os.path.join(self.work_dir, "raw")
        output_dir = os.path.join(self.work_dir, "output")
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        prompts = [p.strip() for p in self.generated_prompts if p.strip()]
        if not prompts:
            if emit_final:
                self.finished.emit("Mode 1: Нет промптов. Нажмите «Создать промпты»")
            return

        total = len(prompts)
        done = 0
        self.progress.emit(f"Промптов к обработке: {total}")

        for idx, prompt in enumerate(prompts, start=1):
            if not self.is_running:
                self.progress.emit("Остановлено пользователем")
                return

            self.progress.emit(f"[{idx}/{total}] Генерация")
            self.progress_value.emit(int(((idx - 1) / total) * 100))
            try:
                image_url = self._kie_generate_image(prompt)
                gen_path = os.path.join(raw_dir, f"gen_{idx:03d}.png")
                self._download_file(image_url, gen_path)
                self.progress.emit(f"  Сгенерировано: {gen_path}")

                final_url = image_url
                if process_generated:
                    uploaded_url = self._kie_upload_file(gen_path)
                    self.progress.emit("  Загружено в KIE")
                    final_url = self._run_kie_processing_pipeline(uploaded_url, raw_dir, idx, "gen", gen_path)

                out_path = os.path.join(output_dir, f"result_{idx:03d}.png")
                self._download_file(final_url, out_path)
                self.progress.emit(f"  Итог сохранён: {out_path}")
                done += 1
            except Exception as e:
                self.progress.emit(f"  Ошибка: {e}")

        self.progress_value.emit(100)
        if emit_final:
            self.finished.emit(f"Mode 1: Готово ({done}/{total})")

    def _mode2_process_files(self, emit_final=True):
        self.progress.emit("Mode 2: Обработка существующих файлов через KIE")
        self.progress.emit(f"Рабочая папка: {self.work_dir}")

        if not self.kie_api_key:
            raise ValueError("Не указан KIE API Key")

        if not self.selected_files:
            if emit_final:
                self.finished.emit("Mode 2: Файлы не выбраны")
            return

        raw_dir = os.path.join(self.work_dir, "raw")
        output_dir = os.path.join(self.work_dir, "output")
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        total = len(self.selected_files)
        done = 0
        for idx, file_path in enumerate(self.selected_files, start=1):
            if not self.is_running:
                self.progress.emit("Остановлено пользователем")
                return

            self.progress.emit(f"[{idx}/{total}] Обработка файла: {os.path.basename(file_path)}")
            self.progress_value.emit(int(((idx - 1) / total) * 100))
            try:
                if not os.path.isfile(file_path):
                    self.progress.emit(f"  Файл не найден: {file_path}")
                    continue

                uploaded_url = self._kie_upload_file(file_path)
                self.progress.emit("  Загружено в KIE")
                final_url = self._run_kie_processing_pipeline(uploaded_url, raw_dir, idx, "file", file_path)

                base = os.path.splitext(os.path.basename(file_path))[0]
                out_path = os.path.join(output_dir, f"{base}_processed.png")
                self._download_file(final_url, out_path)
                self.progress.emit(f"  Итог сохранён: {out_path}")
                done += 1
            except Exception as e:
                self.progress.emit(f"  Ошибка: {e}")

        self.progress_value.emit(100)
        if emit_final:
            self.finished.emit(f"Mode 2: Готово ({done}/{total})")

    def _run_kie_processing_pipeline(self, image_url, raw_dir, idx, prefix, source_image_path=""):
        pipeline_url = image_url

        if self.upscale:
            self.progress.emit(f"  Апскейл через {self.kie_upscale_model}...")
            upscale_input = {}
            max_side = self._parse_max_side(self.upscale_target_size)
            target_size = self._calculate_target_size(source_image_path, max_side)
            if target_size:
                upscale_input["size"] = target_size
                self.progress.emit(f"  Целевой размер по максимальной стороне: {target_size}")
            elif self.upscale_factor in {2, 3, 4}:
                upscale_input["scale"] = self.upscale_factor
            pipeline_url = self._kie_run_model_task(self.kie_upscale_model, pipeline_url, extra_input=upscale_input)
            upscaled_path = os.path.join(raw_dir, f"{prefix}_upscaled_{idx:03d}.png")
            self._download_file(pipeline_url, upscaled_path)
            self.progress.emit(f"  Промежуточный апскейл: {upscaled_path}")

        if self.remove_bg:
            self.progress.emit(f"  Удаление фона через {self.kie_remove_bg_model}...")
            pipeline_url = self._kie_run_model_task(self.kie_remove_bg_model, pipeline_url)
            nobg_path = os.path.join(raw_dir, f"{prefix}_nobg_{idx:03d}.png")
            self._download_file(pipeline_url, nobg_path)
            self.progress.emit(f"  Промежуточный без фона: {nobg_path}")

        return pipeline_url

    def _parse_max_side(self, raw_value):
        text = str(raw_value or "").strip().lower()
        if not text:
            return 0
        if text.isdigit():
            return max(0, int(text))
        numbers = [int(x) for x in re.findall(r"\d+", text)]
        if not numbers:
            return 0
        return max(numbers)

    def _calculate_target_size(self, image_path, max_side):
        if max_side <= 0:
            return ""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
        except Exception as e:
            self.progress.emit(f"  Не удалось прочитать размер изображения: {e}")
            return ""

        if width <= 0 or height <= 0:
            return ""

        if width >= height:
            new_width = max_side
            new_height = max(1, int(round((height / width) * max_side)))
        else:
            new_height = max_side
            new_width = max(1, int(round((width / height) * max_side)))

        return f"{new_width}x{new_height}"

    def _kie_headers(self):
        return {
            "Authorization": f"Bearer {self.kie_api_key}",
            "Accept": "application/json",
            "User-Agent": "ClipartGenerator/1.0 (+PyQt6)",
        }

    def _request_with_retries(self, req, timeout=None):
        req_timeout = timeout or self.timeout
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                with request.urlopen(req, timeout=req_timeout) as resp:
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

                # Не ретраим ошибки авторизации/доступа, чтобы лог был понятнее.
                if e.code in {400, 401, 403, 404}:
                    break

                if attempt >= self.retries:
                    break
                self.progress.emit(f"  Повтор запроса {attempt + 1}/{self.retries}")
                time.sleep(min(2 * (attempt + 1), 6))
            except Exception as e:
                last_error = e
                if attempt >= self.retries:
                    break
                self.progress.emit(f"  Повтор запроса {attempt + 1}/{self.retries}")
                time.sleep(min(2 * (attempt + 1), 6))
        raise RuntimeError(f"Ошибка HTTP-запроса: {last_error}")

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

                # Поддержка разных форматов ответа API.
                if payload.get("success") is False:
                    raise RuntimeError(payload.get("msg") or "Ошибка загрузки файла в KIE")

                data = payload.get("data") or {}
                download_url = data.get("downloadUrl") or data.get("url") or payload.get("url")
                if download_url:
                    return download_url

                raise RuntimeError("KIE upload не вернул downloadUrl/url")
            except Exception as e:
                last_error = e
                self.progress.emit(f"  Upload ошибка: {e}")

        # Fallback: URL Upload API из документации KIE.
        # Используем data URL, чтобы не требовать внешний хостинг файла.
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
                raise RuntimeError(result.get("msg") or "Ошибка URL Upload в KIE")
            data = result.get("data") or {}
            download_url = data.get("downloadUrl") or data.get("url") or result.get("url")
            if download_url:
                return download_url
            raise RuntimeError("KIE URL upload не вернул downloadUrl/url")
        except Exception as e:
            self.progress.emit(f"  URL Upload fallback ошибка: {e}")

        raise RuntimeError(
            "Не удалось загрузить файл в KIE. Проверьте API key, upload path и права доступа. "
            f"Последняя ошибка: {last_error}"
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
            raise RuntimeError(result.get("msg") or "Не удалось создать задачу KIE")
        task_id = (result.get("data") or {}).get("taskId")
        if not task_id:
            raise RuntimeError("KIE createTask не вернул taskId")
        return task_id

    def _kie_run_model_task(self, model, image_url, extra_input=None):
        input_payload = {"image": image_url}
        if isinstance(extra_input, dict):
            input_payload.update(extra_input)
        task_id = self._kie_create_task(model, input_payload)
        self.progress.emit(f"  Task ID: {task_id}")
        return self._kie_wait_result(task_id)

    def _kie_generate_image(self, prompt):
        normalized_model = self._normalize_generation_model(self.generation_model)
        if normalized_model == "gpt4o-image":
            return self._kie_generate_4o_image(prompt)
        if normalized_model == "flux-kontext":
            return self._kie_generate_generic_model("black-forest-labs/flux-kontext-pro", prompt)
        return self._kie_generate_generic_model(normalized_model, prompt)

    def _normalize_generation_model(self, model_name):
        model = (model_name or "").strip()
        if model in {"gpt4o-image", "gpt-image-1", "gpt-image-1.5"}:
            return "gpt4o-image"
        if model in {
            "flux-kontext",
            "black-forest-labs/flux-kontext-pro",
            "black-forest-labs/flux-kontext-max",
        }:
            return "flux-kontext"
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
        }:
            return model
        self.progress.emit(
            f"  Модель '{model}' не поддерживается в этом пайплайне. Используем gpt4o-image."
        )
        return "gpt4o-image"

    def _kie_generate_4o_image(self, prompt):
        headers = self._kie_headers()
        headers["Content-Type"] = "application/json"
        ratio = self._normalize_ratio(self.generation_size)
        legacy_size = self._ratio_to_legacy_size(ratio)

        # Для 4o API чаще всего нужен size в px, но оставляем fallback-варианты.
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
                last_error = RuntimeError(result.get("msg") or "Ошибка создания задачи 4o Image")
            except Exception as e:
                last_error = e

        if result is None or int(result.get("code", 0)) != 200:
            if result is not None:
                raise RuntimeError(result.get("msg") or "Ошибка создания задачи 4o Image")
            raise RuntimeError(str(last_error) if last_error else "Ошибка создания задачи 4o Image")

        task_id = (result.get("data") or {}).get("taskId")
        if not task_id:
            raise RuntimeError("4o Image не вернул taskId")
        self.progress.emit(f"  4o Task ID: {task_id}")
        return self._kie_wait_4o_result(task_id)

    def _kie_generate_generic_model(self, model_name, prompt):
        ratio = self._normalize_ratio(self.generation_size)
        legacy_size = self._ratio_to_legacy_size(ratio)

        if model_name == "z-image":
            model_candidates = ["z-image", "zai-org/z-image"]
        else:
            model_candidates = [model_name]

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
                        self.progress.emit(f"  Модель {candidate} / input {list(payload.keys())} недоступна: {e}")

        # Фолбэк для старых реализаций API.
        fallback_task_id = self._kie_create_task(
            model_name,
            {
                "prompt": prompt,
                "size": legacy_size,
            },
        )
        self.progress.emit(f"  Task ID: {fallback_task_id}")
        return self._kie_wait_result(fallback_task_id)

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

    def _kie_wait_4o_result(self, task_id):
        timeout_sec = self.generation_wait_timeout
        deadline = time.time() + timeout_sec
        headers = self._kie_headers()
        while time.time() < deadline:
            if not self.is_running:
                raise RuntimeError("Остановлено пользователем")

            url = f"https://api.kie.ai/api/v1/gpt4o-image/record-info?{parse.urlencode({'taskId': task_id})}"
            result = self._request_json(url, method="GET", headers=headers, timeout=30)
            if int(result.get("code", 0)) != 200:
                raise RuntimeError(result.get("msg") or "Ошибка статуса 4o Image")

            data = result.get("data") or {}
            status = str(data.get("status", "")).upper()
            self.progress.emit(f"  4o статус: {status}")
            if status == "SUCCESS":
                urls = ((data.get("response") or {}).get("resultUrls") or [])
                if urls:
                    return urls[0]
                raise RuntimeError("4o Image не вернул resultUrls")
            if status in {"FAILED", "FAIL", "ERROR"}:
                raise RuntimeError(data.get("errorMessage") or "4o Image вернул ошибку")
            time.sleep(2)
        raise TimeoutError("Превышено время ожидания 4o Image")

    def _kie_wait_result(self, task_id):
        timeout_sec = self.generation_wait_timeout
        deadline = time.time() + timeout_sec
        headers = self._kie_headers()
        while time.time() < deadline:
            if not self.is_running:
                raise RuntimeError("Остановлено пользователем")

            url = f"https://api.kie.ai/api/v1/jobs/recordInfo?{parse.urlencode({'taskId': task_id})}"
            result = self._request_json(url, method="GET", headers=headers, timeout=30)
            if int(result.get("code", 0)) != 200:
                raise RuntimeError(result.get("msg") or "Ошибка получения статуса KIE")

            data = result.get("data") or {}
            state = str(data.get("state", "")).lower()
            self.progress.emit(f"  Статус: {state}")
            if state in {"success", "succeeded"}:
                return self._extract_result_url(data.get("resultJson"))
            if state in {"fail", "failed", "error"}:
                raise RuntimeError(data.get("failMsg") or "KIE вернул fail")
            time.sleep(2)
        raise TimeoutError("Превышено время ожидания результата KIE")

    def _extract_result_url(self, result_json_raw):
        if not result_json_raw:
            raise RuntimeError("KIE не вернул resultJson")

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

        raise RuntimeError("Не удалось извлечь URL результата из resultJson")

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
        # Некоторые CDN KIE/Redpanda отдают 403 (Cloudflare 1010) без auth-заголовков.
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
                with open(output_path, "wb") as f:
                    f.write(content)
                if output_path.lower().endswith(".png") and "output" in output_path.lower():
                    self._set_png_dpi(output_path, dpi=300)
                return
            except Exception as e:
                last_error = e
                self.progress.emit(f"  Download попытка {idx} не удалась: {e}")

        raise RuntimeError(f"Не удалось скачать файл по URL ({host}): {last_error}")

    def _set_png_dpi(self, file_path, dpi=300):
        try:
            with Image.open(file_path) as img:
                if img.format != "PNG":
                    return
                img.save(file_path, format="PNG", dpi=(dpi, dpi))
            self.progress.emit(f"  Установлен DPI {dpi} для {os.path.basename(file_path)}")
        except Exception as e:
            self.progress.emit(f"  Не удалось установить DPI для {os.path.basename(file_path)}: {e}")


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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Clipart Generator")
        self.resize(980, 780)

        self.work_dir = ""
        self.worker = None
        self.generated_prompts = []
        self.selected_files = []
        self.is_updating_prompts_table = False
        self.settings_save_timer = QTimer(self)
        self.settings_save_timer.setSingleShot(True)
        self.settings_save_timer.setInterval(400)
        self.settings_save_timer.timeout.connect(self.persist_ui_settings)

        self.load_config()
        self.setup_ui()
        self.load_saved_prompts()
        self.setup_settings_autosave_connections()
        QTimer.singleShot(1200, lambda: self.check_for_updates(silent=True))

    def load_saved_prompts(self):
        try:
            if not os.path.exists(PROMPTS_STORAGE_FILE):
                return
            with open(PROMPTS_STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            prompts = []
            if isinstance(data, dict):
                raw_prompts = data.get("prompts", [])
                if isinstance(raw_prompts, list):
                    prompts = [str(p).strip() for p in raw_prompts if str(p).strip()]
            elif isinstance(data, list):
                prompts = [str(p).strip() for p in data if str(p).strip()]

            self.generated_prompts = prompts
            if hasattr(self, "table"):
                self.refresh_prompts_table()
        except Exception as e:
            self.log(f"Не удалось загрузить сохранённые промпты: {e}")

    def save_prompts_storage(self):
        try:
            payload = {
                "prompts": [p.strip() for p in self.generated_prompts if p.strip()],
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            with open(PROMPTS_STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Не удалось сохранить промпты: {e}")

    def load_config(self):
        default_config = {
            "retries": 3,
            "timeout": 60,
            "generation_wait_timeout": 300,
            "app_version": APP_VERSION,
            "update_manifest_url": UPDATE_MANIFEST_URL,
            "kie_api_key": "",
            "kie_upload_path": "clipart-generator",
            "generation_model": "gpt4o-image",
            "generation_size": "1:1",
            "remove_bg": True,
            "upscale": True,
            "upscale_factor": 4,
            "upscale_target_size": "",
            "kie_upscale_model": "topaz/upscale",
            "kie_remove_bg_model": "recraft/remove-background",
            "run_mode": "generate_only",
            "prompt_input_mode": "list",
        }
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                self.config = json.load(f)
            for key, value in default_config.items():
                if key not in self.config:
                    self.config[key] = value
        else:
            self.config = default_config
        # URL обновлений всегда фиксированный и не редактируется в UI.
        self.config["update_manifest_url"] = UPDATE_MANIFEST_URL

    def save_config(self):
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

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

        self.setStyleSheet(
            "QRadioButton::indicator, QCheckBox::indicator {width: 16px; height: 16px;}"
            "QRadioButton::indicator:unchecked, QCheckBox::indicator:unchecked {"
            "border: 2px solid #14b8a6; background: #ffffff; border-radius: 8px;}"
            "QRadioButton::indicator:checked, QCheckBox::indicator:checked {"
            "border: 2px solid #14b8a6; background: #14b8a6; border-radius: 8px;}"
        )

        top_layout = QHBoxLayout()
        self.lbl_work_dir = QLabel("Рабочая папка: не выбрана")
        self.btn_select_dir = QPushButton("Выбрать папку")
        self.btn_select_dir.setMinimumHeight(44)
        self.btn_select_dir.setStyleSheet(self.primary_button_style)
        self.btn_select_dir.clicked.connect(self.select_work_dir)
        top_layout.addWidget(self.lbl_work_dir)
        top_layout.addSpacing(8)
        top_layout.addWidget(self.btn_select_dir)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        run_mode_group = QGroupBox("Сценарий запуска")
        run_mode_layout = QHBoxLayout()
        self.run_mode_group = QButtonGroup()

        self.radio_run_generate = QRadioButton("Только генерация изображений")
        self.radio_run_process = QRadioButton("Только обработка файлов")
        self.radio_run_both = QRadioButton("Все вместе")

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
        self.tabs.addTab(prompt_tab, "Промпты")
        self.tabs.addTab(process_tab, "Обработка")
        self.tabs.addTab(settings_tab, "Настройки")
        main_layout.addWidget(self.tabs)

        prompt_btn_layout = QHBoxLayout()
        self.btn_export = QPushButton("Экспорт промптов")
        self.btn_export.clicked.connect(self.export_prompts)
        self.btn_add_prompt_row = QPushButton("+")
        self.btn_add_prompt_row.clicked.connect(self.add_prompt_row)
        self.btn_add_prompt_row.setToolTip("Добавить строку промпта")
        self.btn_clear_prompts = QPushButton("Удалить все")
        self.btn_clear_prompts.clicked.connect(self.clear_all_prompts)
        self.btn_clear_prompts.setToolTip("Очищает список промптов в предпросмотре")
        self.btn_export.setStyleSheet(self.primary_button_style)
        self.btn_add_prompt_row.setStyleSheet(self.primary_button_style)
        self.btn_clear_prompts.setStyleSheet(self.primary_button_style)
        prompt_btn_layout.addWidget(self.btn_export)
        prompt_btn_layout.addWidget(self.btn_add_prompt_row)
        prompt_btn_layout.addStretch()
        prompt_btn_layout.addWidget(self.btn_clear_prompts)
        prompt_tab_layout.addLayout(prompt_btn_layout)

        preview_group = QGroupBox("Список промптов")
        preview_layout = QVBoxLayout()
        self.table = PromptTableWidget(0, 2)
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 44)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(280)
        self.table.bulkTextPasted.connect(self.on_table_bulk_paste)
        self.table.itemChanged.connect(self.on_prompt_item_changed)
        preview_layout.addWidget(self.table)
        preview_group.setLayout(preview_layout)
        prompt_tab_layout.addWidget(preview_group)

        files_group = QGroupBox("Файлы для обработки")
        files_layout = QVBoxLayout()
        self.btn_select_files = QPushButton("Выбрать файлы")
        self.btn_select_files.setMinimumHeight(44)
        self.btn_select_files.setStyleSheet(self.primary_button_style)
        self.btn_select_files.clicked.connect(self.select_files)
        self.lbl_files_count = QLabel("Файлов не выбрано")
        files_layout.addWidget(self.btn_select_files)
        files_layout.addWidget(self.lbl_files_count)
        files_group.setLayout(files_layout)
        process_tab_layout.addWidget(files_group)

        process_flags_group = QGroupBox("Параметры обработки")
        process_flags_layout = QHBoxLayout()
        self.chk_upscale = QCheckBox("Апскейл")
        self.chk_upscale.setChecked(self.config.get("upscale", True))
        self.chk_remove_bg = QCheckBox("Удаление фона")
        self.chk_remove_bg.setChecked(self.config.get("remove_bg", True))
        process_flags_layout.addWidget(self.chk_upscale)
        process_flags_layout.addWidget(self.chk_remove_bg)
        process_flags_layout.addStretch()
        process_flags_group.setLayout(process_flags_layout)
        process_tab_layout.addWidget(process_flags_group)

        process_tab_layout.addStretch()

        kie_group = QGroupBox("KIE: подключение и генерация")
        kie_layout = QGridLayout()
        kie_layout.setHorizontalSpacing(8)
        self.kie_api_key_input = QLineEdit()
        self.kie_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.kie_api_key_input.setText(self.config.get("kie_api_key", ""))
        self.btn_toggle_api_key = QPushButton("Показать")
        self.btn_toggle_api_key.setMinimumHeight(34)
        self.btn_toggle_api_key.setStyleSheet(self.primary_button_style)
        self.btn_toggle_api_key.clicked.connect(self.toggle_api_key_visibility)
        self.kie_upload_path_input = QLineEdit(self.config.get("kie_upload_path", "clipart-generator"))

        self.generation_model_combo = QComboBox()
        self.generation_model_combo.addItems([
            "gpt4o-image",
            "z-image",
            "google/nano-banana",
            "google/nano-banana-edit",
            "google/imagen4",
            "google/imagen4-fast",
            "google/imagen4-ultra",
            "flux-2/flex-text-to-image",
            "flux-2/pro-text-to-image",
            "black-forest-labs/flux-kontext-pro",
            "black-forest-labs/flux-kontext-max",
        ])
        model = self.config.get("generation_model", "gpt4o-image")
        mi = self.generation_model_combo.findText(model)
        self.generation_model_combo.setCurrentIndex(mi if mi >= 0 else 0)

        self.generation_size_combo = QComboBox()
        self.generation_size_combo.addItems(["1:1", "4:3", "3:4", "16:9", "9:16"])
        size_value = str(self.config.get("generation_size", "1:1"))
        legacy_map = {"1024x1024": "1:1", "1024x1536": "3:4", "1536x1024": "4:3"}
        if size_value in legacy_map:
            size_value = legacy_map[size_value]
        self.generation_size_combo.setCurrentText(size_value if size_value else "1:1")
        self.btn_check_model = QPushButton("Проверить модель")
        self.btn_check_model.setMinimumHeight(34)
        self.btn_check_model.setStyleSheet(self.primary_button_style)
        self.btn_check_model.clicked.connect(self.check_generation_model)

        self.retries = QSpinBox()
        self.retries.setRange(0, 10)
        self.retries.setValue(int(self.config.get("retries", 3)))
        self.timeout = QSpinBox()
        self.timeout.setRange(10, 600)
        self.timeout.setValue(int(self.config.get("timeout", 60)))
        self.generation_wait_timeout = QSpinBox()
        self.generation_wait_timeout.setRange(120, 1800)
        self.generation_wait_timeout.setValue(int(self.config.get("generation_wait_timeout", 300)))

        lbl_api_key = QLabel("KIE API Key:")
        lbl_api_key.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_upload_path = QLabel("KIE Upload Path:")
        lbl_upload_path.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_gen_model = QLabel("Модель генерации:")
        lbl_gen_model.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_gen_size = QLabel("Соотношение сторон:")
        lbl_gen_size.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_retries = QLabel("Retries:")
        lbl_retries.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_timeout = QLabel("Timeout (s):")
        lbl_timeout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_generation_wait = QLabel("Ожидание генерации (s):")
        lbl_generation_wait.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        kie_layout.addWidget(lbl_api_key, 0, 0)
        kie_layout.addWidget(self.kie_api_key_input, 0, 1, 1, 2)
        kie_layout.addWidget(self.btn_toggle_api_key, 0, 3)
        kie_layout.addWidget(lbl_upload_path, 1, 0)
        kie_layout.addWidget(self.kie_upload_path_input, 1, 1, 1, 3)
        kie_layout.addWidget(lbl_gen_model, 2, 0)
        kie_layout.addWidget(self.generation_model_combo, 2, 1)
        kie_layout.addWidget(lbl_gen_size, 2, 2)
        kie_layout.addWidget(self.generation_size_combo, 2, 3)
        kie_layout.addWidget(lbl_retries, 3, 0)
        kie_layout.addWidget(self.retries, 3, 1)
        kie_layout.addWidget(lbl_timeout, 3, 2)
        kie_layout.addWidget(self.timeout, 3, 3)
        kie_layout.addWidget(lbl_generation_wait, 4, 0)
        kie_layout.addWidget(self.generation_wait_timeout, 4, 1)
        kie_layout.addWidget(self.btn_check_model, 5, 1, 1, 2)
        kie_group.setLayout(kie_layout)
        settings_tab_layout.addWidget(kie_group)

        process_settings_group = QGroupBox("Обработка через KIE")
        process_settings_layout = QGridLayout()

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
        self.upscale_factor_combo.addItems(["2", "3", "4"])
        self.upscale_factor_combo.setCurrentText(str(self.config.get("upscale_factor", 4)))
        self.upscale_target_size_input = QLineEdit(str(self.config.get("upscale_target_size", "")))
        self.upscale_target_size_input.setPlaceholderText("Опционально, например 3000")

        process_settings_layout.addWidget(QLabel("Модель апскейла:"), 0, 0)
        process_settings_layout.addWidget(self.kie_upscale_model_combo, 0, 1)
        process_settings_layout.addWidget(QLabel("Кратность апскейла:"), 1, 0)
        process_settings_layout.addWidget(self.upscale_factor_combo, 1, 1)
        process_settings_layout.addWidget(QLabel("Максимальная сторона (px):"), 2, 0)
        process_settings_layout.addWidget(self.upscale_target_size_input, 2, 1)
        process_settings_layout.addWidget(QLabel("Модель удаления фона:"), 3, 0)
        process_settings_layout.addWidget(self.kie_remove_bg_model_combo, 3, 1)
        process_settings_group.setLayout(process_settings_layout)
        settings_tab_layout.addWidget(process_settings_group)

        settings_tab_layout.addStretch()

        log_group = QGroupBox("Лог и прогресс")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(80)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        run_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_start.setMinimumHeight(40)
        self.btn_start.clicked.connect(self.start_work)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setMinimumHeight(40)
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

        self.on_mode_changed(True)

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
        item.setToolTip(f"{prefix}: значение для подстановки")
        table.setItem(row, 0, item)

        delete_btn = QPushButton("🗑")
        delete_btn.setToolTip("Удалить строку")
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
            delete_btn = QPushButton("🗑")
            delete_btn.setToolTip("Удалить строку")
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
        self.kie_upload_path_input.textChanged.connect(self.schedule_settings_save)
        self.generation_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.generation_size_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.retries.valueChanged.connect(self.schedule_settings_save)
        self.timeout.valueChanged.connect(self.schedule_settings_save)
        self.generation_wait_timeout.valueChanged.connect(self.schedule_settings_save)
        self.chk_upscale.toggled.connect(self.schedule_settings_save)
        self.chk_remove_bg.toggled.connect(self.schedule_settings_save)
        self.kie_upscale_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.kie_remove_bg_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.upscale_factor_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.upscale_target_size_input.textChanged.connect(self.schedule_settings_save)
        self.radio_run_generate.toggled.connect(self.schedule_settings_save)
        self.radio_run_process.toggled.connect(self.schedule_settings_save)
        self.radio_run_both.toggled.connect(self.schedule_settings_save)

    def schedule_settings_save(self, *_):
        self.settings_save_timer.start()

    def on_mode_changed(self, checked):
        is_process = self.radio_run_process.isChecked()
        if hasattr(self, "tabs"):
            self.tabs.setCurrentIndex(1 if is_process else 0)

    def select_work_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Выбрать рабочую папку")
        if path:
            self.work_dir = path
            self.lbl_work_dir.setText(f"Рабочая папка: {path}")
            os.makedirs(os.path.join(path, "raw"), exist_ok=True)
            os.makedirs(os.path.join(path, "output"), exist_ok=True)
            self.log(f"Созданы/проверены папки raw и output в {path}")

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выбрать изображения",
            "",
            "Images (*.png *.jpg *.jpeg *.webp);;All files (*.*)",
        )
        if files:
            self.selected_files = files
            self.lbl_files_count.setText(f"Выбрано файлов: {len(files)}")
            self.log(f"Выбрано файлов: {len(files)}")

    def add_prompt_row(self):
        self.generated_prompts.append("")
        self.refresh_prompts_table()
        self.save_prompts_storage()
        row_index = len(self.generated_prompts) - 1
        self.table.setCurrentCell(row_index, 0)
        self.table.editItem(self.table.item(row_index, 0))

    def build_prompts(self):
        template = self.master_prompt.toPlainText().strip()
        a = self.get_template_values(self.field_a)
        b = self.get_template_values(self.field_b)
        c = self.get_template_values(self.field_c)

        if not template:
            QMessageBox.warning(self, "Ошибка", "Введите Master Prompt")
            return

        self.generated_prompts = []
        max_len = max(len(a), len(b), len(c))
        if max_len == 0:
            self.generated_prompts = [template]
        else:
            for i in range(max_len):
                prompt = template
                if a and i < len(a):
                    prompt = prompt.replace("{A}", a[i])
                if b and i < len(b):
                    prompt = prompt.replace("{B}", b[i])
                if c and i < len(c):
                    prompt = prompt.replace("{C}", c[i])
                self.generated_prompts.append(prompt)
        self.refresh_prompts_table()

        self.log(f"Создано промптов: {len(self.generated_prompts)}")

    def build_prompts_from_template_inputs(self):
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
        prompts = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            text = (item.text() if item else "").strip()
            if text:
                prompts.append(text)
        return prompts

    def import_prompts_from_template(self):
        raw_text = self.master_prompt.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "Ошибка", "Вставьте список промптов в поле Master Prompt")
            return

        prompts = self._split_prompts_text(raw_text)
        if not prompts:
            QMessageBox.warning(self, "Ошибка", "Не удалось распознать промпты")
            return

        self.generated_prompts = prompts
        self.refresh_prompts_table()
        self.log(f"Импортировано промптов: {len(self.generated_prompts)}")

    def on_table_bulk_paste(self, raw_text):
        prompts = self._split_prompts_text(raw_text)
        self.generated_prompts = prompts
        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log(f"Вставлено промптов: {len(self.generated_prompts)}")

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
        for index, prompt in enumerate(self.generated_prompts):
            row = self.table.rowCount()
            self.table.insertRow(row)
            item = QTableWidgetItem(prompt)
            self.table.setItem(row, 0, item)

            delete_btn = QPushButton("🗑")
            delete_btn.setToolTip("Удалить промпт")
            delete_btn.setMinimumHeight(28)
            delete_btn.clicked.connect(lambda _, r=index: self.remove_prompt_row(r))
            self.table.setCellWidget(row, 1, delete_btn)
        self.is_updating_prompts_table = False

    def on_prompt_item_changed(self, item):
        if self.is_updating_prompts_table:
            return
        if item.column() != 0:
            return
        row = item.row()
        if 0 <= row < len(self.generated_prompts):
            self.generated_prompts[row] = item.text()
            self.save_prompts_storage()

    def remove_prompt_row(self, row_index):
        if row_index < 0 or row_index >= len(self.generated_prompts):
            return
        del self.generated_prompts[row_index]
        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log(f"Удалён промпт. Осталось: {len(self.generated_prompts)}")

    def clear_all_prompts(self):
        self.generated_prompts = []
        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log("Список промптов очищен")

    def export_prompts(self):
        if not self.work_dir:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите рабочую папку")
            return
        if not self.generated_prompts:
            QMessageBox.warning(self, "Ошибка", "Сначала создайте промпты")
            return

        txt_path = os.path.join(self.work_dir, "prompts.txt")
        csv_path = os.path.join(self.work_dir, "prompts.csv")
        with open(txt_path, "w", encoding="utf-8") as f:
            for p in self.generated_prompts:
                f.write(p + "\n")
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            f.write("Prompt\n")
            for p in self.generated_prompts:
                f.write(f'"{p.replace("\"", "\"\"")}"\n')
        self.log(f"Экспортировано: {txt_path}, {csv_path}")
        QMessageBox.information(self, "Готово", "Промпты экспортированы")

    def start_work(self):
        if not self.work_dir:
            QMessageBox.warning(self, "Ошибка", "Выберите рабочую папку")
            return

        self.persist_ui_settings()
        current_api_key = self.config.get("kie_api_key", "").strip()

        if not current_api_key:
            QMessageBox.warning(self, "Ошибка", "Укажите KIE API Key на вкладке «Настройки»")
            return

        runtime_settings = dict(self.config)
        runtime_settings["kie_api_key"] = current_api_key

        active_prompts = self.get_list_mode_prompts()
        if not active_prompts:
            QMessageBox.warning(self, "Ошибка", "Добавьте хотя бы один промпт")
            return

        self.generated_prompts = active_prompts
        self.refresh_prompts_table()

        run_mode = self.config.get("run_mode", "generate_only")

        if run_mode == "process_only":
            mode = "mode2_process"
            if not self.selected_files:
                QMessageBox.warning(self, "Ошибка", "Для режима обработки выберите файлы")
                return
        elif run_mode == "both":
            mode = "mode_both"
        else:
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
        self.log("Остановлено")

    def on_finished(self, message):
        self.log(message)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(100)

    def on_error(self, err):
        self.log(f"Ошибка: {err}")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")

    def toggle_api_key_visibility(self):
        is_password = self.kie_api_key_input.echoMode() == QLineEdit.EchoMode.Password
        if is_password:
            self.kie_api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_api_key.setText("Скрыть")
        else:
            self.kie_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_api_key.setText("Показать")

    def check_generation_model(self):
        api_key = self.kie_api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Ошибка", "Сначала укажите KIE API Key")
            return

        raw_model = self.generation_model_combo.currentText().strip()
        model = raw_model
        if raw_model in {"gpt4o-image", "gpt-image-1", "gpt-image-1.5"}:
            model = "gpt4o-image"
        elif raw_model in {"flux-kontext", "black-forest-labs/flux-kontext-pro", "black-forest-labs/flux-kontext-max"}:
            model = "flux-kontext"

        timeout = max(10, int(self.timeout.value()))
        prompt = "simple test image"
        ratio = self.generation_size_combo.currentText().strip() or "1:1"
        legacy_size = self._ratio_to_legacy_size_ui(ratio)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
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
                if model == "flux-kontext":
                    test_model = "black-forest-labs/flux-kontext-pro"
                elif model == "z-image":
                    test_model = "z-image"
                else:
                    test_model = raw_model
                payload_variants = [
                    {"model": test_model, "input": {"prompt": prompt, "size": ratio}},
                    {"model": test_model, "input": {"prompt": prompt, "aspectRatio": ratio}},
                    {"model": test_model, "input": {"prompt": prompt, "aspect_ratio": ratio}},
                    {"model": test_model, "input": {"prompt": prompt, "size": legacy_size}},
                ]

            data = None
            last_error = None
            for payload in payload_variants:
                try:
                    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                    with request.urlopen(req, timeout=timeout) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    if int(data.get("code", 0)) == 200:
                        break
                    last_error = data.get("msg") or "Модель недоступна"
                except Exception as e:
                    last_error = str(e)

            if data is None or int(data.get("code", 0)) != 200:
                raise RuntimeError(last_error or "Модель недоступна")

            task_id = (data.get("data") or {}).get("taskId", "-")
            self.log(f"Проверка модели '{raw_model}' успешна. Task ID: {task_id}")
            QMessageBox.information(self, "Проверка модели", f"Модель доступна: {raw_model}")
        except urlerror.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            msg = f"HTTP {e.code} {e.reason}"
            if body:
                msg = f"{msg}: {body[:400]}"
            self.log(f"Проверка модели '{raw_model}' не пройдена: {msg}")
            QMessageBox.warning(self, "Проверка модели", f"Модель недоступна: {raw_model}\n{msg}")
        except Exception as e:
            self.log(f"Проверка модели '{raw_model}' не пройдена: {e}")
            QMessageBox.warning(self, "Проверка модели", f"Ошибка проверки: {e}")

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
        with request.urlopen(req, timeout=120) as resp:
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
                raise RuntimeError("Контрольная сумма обновления не совпала")

        return installer_path

    def _run_downloaded_installer(self, installer_path):
        if not os.path.isfile(installer_path):
            raise RuntimeError("Файл установщика не найден")
        os.startfile(installer_path)

    def check_for_updates(self, silent=False):
        manifest_url = UPDATE_MANIFEST_URL
        if not manifest_url:
            if not silent:
                QMessageBox.warning(self, "Обновления", "Не задан URL version.json")
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
            with request.urlopen(req, timeout=20) as resp:
                # Поддержка BOM в JSON (например, если version.json сохранён PowerShell с UTF-8 BOM).
                manifest = json.loads(resp.read().decode("utf-8-sig"))

            latest_version = str(manifest.get("latest_version", "")).strip()
            download_url = str(manifest.get("download_url", "")).strip()
            checksum = str(manifest.get("sha256", "")).strip()

            if not latest_version or not download_url:
                raise RuntimeError("version.json не содержит latest_version/download_url")

            current_version = str(self.config.get("app_version", APP_VERSION)).strip()
            if not self._is_newer_version(latest_version, current_version):
                if not silent:
                    QMessageBox.information(self, "Обновления", f"У вас актуальная версия: {current_version}")
                return

            QMessageBox.warning(
                self,
                "Обязательное обновление",
                (
                    f"Доступна новая версия: {latest_version}\n"
                    f"Текущая версия: {current_version}\n\n"
                    "Сейчас будет запущен установщик обновления."
                ),
            )
            self.log(f"Скачивание обновления {latest_version}...")
            installer_path = self._download_update_installer(download_url, expected_sha256=checksum or None)
            self.log(f"Установщик скачан: {installer_path}")
            self._run_downloaded_installer(installer_path)
            QMessageBox.information(
                self,
                "Обновление",
                "Установщик обновления запущен. После завершения установки откройте приложение снова.",
            )
            QApplication.instance().quit()
        except Exception as e:
            self.log(f"Проверка обновлений: {e}")
            if not silent:
                QMessageBox.warning(self, "Обновления", f"Не удалось проверить обновления: {e}")

    def _ratio_to_legacy_size_ui(self, ratio):
        return {
            "1:1": "1024x1024",
            "4:3": "1536x1024",
            "3:4": "1024x1536",
            "16:9": "1536x1024",
            "9:16": "1024x1536",
        }.get(ratio, "1024x1024")

    def persist_ui_settings(self):
        self.config["retries"] = self.retries.value()
        self.config["timeout"] = self.timeout.value()
        self.config["generation_wait_timeout"] = self.generation_wait_timeout.value()
        self.config["kie_api_key"] = self.kie_api_key_input.text().strip()
        self.config["kie_upload_path"] = self.kie_upload_path_input.text().strip() or "clipart-generator"
        self.config["generation_model"] = self.generation_model_combo.currentText()
        self.config["generation_size"] = self.generation_size_combo.currentText()
        self.config["remove_bg"] = self.chk_remove_bg.isChecked()
        self.config["upscale"] = self.chk_upscale.isChecked()
        self.config["upscale_factor"] = int(self.upscale_factor_combo.currentText())
        self.config["upscale_target_size"] = self.upscale_target_size_input.text().strip()
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
    # Защита от случайного запуска в offscreen-режиме в рабочем терминале.
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        os.environ["QT_QPA_PLATFORM"] = "windows"
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
