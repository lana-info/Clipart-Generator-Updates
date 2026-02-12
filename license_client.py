import json
import os
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from urllib import request, error


class LicenseClient:
    def __init__(self, server_url, cache_path, app_version, timeout=10):
        self.server_url = (server_url or "").rstrip("/")
        self.cache_path = cache_path
        self.app_version = app_version
        self.timeout = timeout

    def device_fingerprint(self):
        node = str(uuid.getnode())
        uname = "|".join(os.uname()) if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "")
        raw = f"{node}|{uname}|clipart-generator"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def activate(self, license_key):
        payload = {
            "license_key": (license_key or "").strip(),
            "device_fingerprint": self.device_fingerprint(),
            "app_version": self.app_version,
        }
        result = self._post("/activate", payload)
        if result.get("ok"):
            self._save_cache(result)
        return result

    def validate(self, license_key, use_offline=True):
        payload = {
            "license_key": (license_key or "").strip(),
            "device_fingerprint": self.device_fingerprint(),
            "app_version": self.app_version,
        }
        try:
            result = self._post("/validate", payload)
            if result.get("ok"):
                self._save_cache(result)
            return result
        except Exception as e:
            if use_offline:
                offline = self._validate_offline_cache(payload["license_key"], payload["device_fingerprint"])
                if offline.get("ok"):
                    return offline
            return {"ok": False, "message": f"Ошибка проверки лицензии: {e}"}

    def deactivate(self, license_key):
        payload = {
            "license_key": (license_key or "").strip(),
            "device_fingerprint": self.device_fingerprint(),
        }
        result = self._post("/deactivate", payload)
        if result.get("ok") and os.path.exists(self.cache_path):
            try:
                os.remove(self.cache_path)
            except Exception:
                pass
        return result

    def _post(self, path, payload):
        if not self.server_url:
            raise RuntimeError("Не указан URL сервера лицензий")
        url = f"{self.server_url}{path}"
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {e.code}: {body[:300]}")

    def _save_cache(self, response_payload):
        expires_at = datetime.now(timezone.utc) + timedelta(days=3)
        cache = {
            "license_key": response_payload.get("license_key", ""),
            "device_fingerprint": self.device_fingerprint(),
            "cached_until": expires_at.isoformat(),
            "token": response_payload.get("token", ""),
        }
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

    def _validate_offline_cache(self, license_key, fingerprint):
        if not os.path.exists(self.cache_path):
            return {"ok": False, "message": "Нет офлайн-кеша лицензии"}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if cache.get("license_key") != license_key:
                return {"ok": False, "message": "Ключ не совпадает с офлайн-кешем"}
            if cache.get("device_fingerprint") != fingerprint:
                return {"ok": False, "message": "Устройство не совпадает с офлайн-кешем"}
            until = datetime.fromisoformat(cache.get("cached_until"))
            if datetime.now(timezone.utc) > until:
                return {"ok": False, "message": "Офлайн-кеш лицензии истёк"}
            return {"ok": True, "message": "Офлайн-проверка лицензии успешна", "offline": True}
        except Exception as e:
            return {"ok": False, "message": f"Ошибка офлайн-кеша: {e}"}
