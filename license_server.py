import sqlite3
from datetime import datetime, timezone
from fastapi import FastAPI
from pydantic import BaseModel


DB_PATH = "licenses.db"
app = FastAPI(title="Clipart License Server")


class LicensePayload(BaseModel):
    license_key: str
    device_fingerprint: str
    app_version: str | None = None


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            is_active INTEGER NOT NULL DEFAULT 1,
            bound_device TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensure_license_exists(license_key):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT license_key FROM licenses WHERE license_key = ?", (license_key,))
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO licenses (license_key, is_active, bound_device, updated_at) VALUES (?, 1, NULL, ?)",
            (license_key, now_iso()),
        )
    conn.commit()
    conn.close()


@app.on_event("startup")
def startup_event():
    init_db()


@app.post("/activate")
def activate(payload: LicensePayload):
    key = payload.license_key.strip()
    if not key:
        return {"ok": False, "message": "Пустой ключ"}
    ensure_license_exists(key)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT is_active, bound_device FROM licenses WHERE license_key = ?", (key,))
    row = cur.fetchone()
    if not row or int(row[0]) != 1:
        conn.close()
        return {"ok": False, "message": "Ключ неактивен"}

    bound_device = row[1]
    if bound_device and bound_device != payload.device_fingerprint:
        conn.close()
        return {"ok": False, "message": "Ключ уже активирован на другом устройстве"}

    cur.execute(
        "UPDATE licenses SET bound_device = ?, updated_at = ? WHERE license_key = ?",
        (payload.device_fingerprint, now_iso(), key),
    )
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "message": "Активация успешна",
        "license_key": key,
        "token": f"ok:{key}",
    }


@app.post("/validate")
def validate(payload: LicensePayload):
    key = payload.license_key.strip()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT is_active, bound_device FROM licenses WHERE license_key = ?", (key,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"ok": False, "message": "Ключ не найден"}
    if int(row[0]) != 1:
        return {"ok": False, "message": "Ключ отключён"}
    if row[1] != payload.device_fingerprint:
        return {"ok": False, "message": "Ключ привязан к другому устройству"}

    return {"ok": True, "message": "Лицензия валидна", "license_key": key, "token": f"ok:{key}"}


@app.post("/deactivate")
def deactivate(payload: LicensePayload):
    key = payload.license_key.strip()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT bound_device FROM licenses WHERE license_key = ?", (key,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"ok": False, "message": "Ключ не найден"}
    if row[0] != payload.device_fingerprint:
        conn.close()
        return {"ok": False, "message": "Деактивация разрешена только с привязанного устройства"}

    cur.execute(
        "UPDATE licenses SET bound_device = NULL, updated_at = ? WHERE license_key = ?",
        (now_iso(), key),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Активация сброшена"}
