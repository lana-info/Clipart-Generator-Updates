import random
import sqlite3
import string
from datetime import datetime, timedelta, timezone
import os
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field


DB_PATH = os.environ.get("LICENSE_DB_PATH", "licenses.db")
ADMIN_TOKEN = os.environ.get("LICENSE_ADMIN_TOKEN", "").strip()
app = FastAPI(title="Clipart License Server")


class LicensePayload(BaseModel):
    license_key: str
    device_fingerprint: str
    app_version: str | None = None


class GeneratePayload(BaseModel):
    count: int = Field(default=1, ge=1, le=100)
    prefix: str = "CG"
    mode: str = "random"  # random | serial
    expires_days: int = Field(default=365, ge=1, le=3650)
    updates_days: int | None = Field(default=None, ge=1, le=3650)
    max_devices: int = Field(default=1, ge=1, le=20)
    serial_start: int = Field(default=1, ge=1)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            is_active INTEGER NOT NULL DEFAULT 1,
            expires_at TEXT,
            updates_until TEXT,
            max_devices INTEGER NOT NULL DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS activations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT NOT NULL,
            device_fingerprint TEXT NOT NULL,
            activated_at TEXT,
            UNIQUE(license_key, device_fingerprint)
        )
        """
    )

    cur.execute("PRAGMA table_info(licenses)")
    columns = {row[1] for row in cur.fetchall()}
    if "expires_at" not in columns:
        cur.execute("ALTER TABLE licenses ADD COLUMN expires_at TEXT")
    if "updates_until" not in columns:
        cur.execute("ALTER TABLE licenses ADD COLUMN updates_until TEXT")
    if "max_devices" not in columns:
        cur.execute("ALTER TABLE licenses ADD COLUMN max_devices INTEGER NOT NULL DEFAULT 1")
    if "created_at" not in columns:
        cur.execute("ALTER TABLE licenses ADD COLUMN created_at TEXT")

    conn.commit()
    conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def is_expired(expires_at):
    if not expires_at:
        return False
    try:
        return datetime.now(timezone.utc) > datetime.fromisoformat(expires_at)
    except Exception:
        return True


def updates_allowed_for(updates_until, expires_at):
    effective_until = updates_until or expires_at
    if not effective_until:
        return True
    return not is_expired(effective_until)


def build_license_state_row(cur, key):
    cur.execute(
        """
        SELECT is_active, expires_at, updates_until, max_devices
        FROM licenses
        WHERE license_key = ?
        """,
        (key,),
    )
    row = cur.fetchone()
    if not row:
        return None
    max_devices = int(row[3] or 1)
    cur.execute("SELECT COUNT(*) FROM activations WHERE license_key = ?", (key,))
    used_devices = int(cur.fetchone()[0])
    return {
        "is_active": bool(row[0]),
        "expires_at": row[1],
        "updates_until": row[2],
        "updates_allowed": updates_allowed_for(row[2], row[1]),
        "max_devices": max_devices,
        "used_devices": used_devices,
    }


def success_payload(key, state, message):
    return {
        "ok": True,
        "message": message,
        "license_key": key,
        "token": f"ok:{key}",
        "is_active": state["is_active"],
        "expires_at": state["expires_at"],
        "updates_until": state["updates_until"],
        "updates_allowed": state["updates_allowed"],
        "max_devices": state["max_devices"],
        "used_devices": state["used_devices"],
    }


def random_key(prefix):
    chunks = ["".join(random.choices(string.ascii_uppercase + string.digits, k=4)) for _ in range(3)]
    return f"{prefix}-{'-'.join(chunks)}"


def serial_key(prefix, index):
    return f"{prefix}-{index:06d}"


def verify_admin_token(x_admin_token: str | None = None, admin_token: str | None = None):
    expected_token = ADMIN_TOKEN
    if not expected_token:
        raise HTTPException(status_code=503, detail="Админ-токен не настроен на сервере")

    provided_token = (x_admin_token or admin_token or "").strip()
    if provided_token != expected_token:
        raise HTTPException(status_code=401, detail="Неверный админ-токен")


@app.on_event("startup")
def startup_event():
    init_db()


@app.post("/activate")
def activate(payload: LicensePayload):
    key = payload.license_key.strip()
    if not key:
        return {"ok": False, "message": "Пустой ключ"}

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    state = build_license_state_row(cur, key)
    if not state:
        conn.close()
        return {"ok": False, "message": "Ключ не найден"}
    if not state["is_active"]:
        conn.close()
        return {"ok": False, "message": "Ключ отключён"}
    if is_expired(state["expires_at"]):
        conn.close()
        return {"ok": False, "message": "Срок действия ключа истёк"}

    max_devices = state["max_devices"]
    used_devices = state["used_devices"]

    cur.execute(
        "SELECT id FROM activations WHERE license_key = ? AND device_fingerprint = ?",
        (key, payload.device_fingerprint),
    )
    existing_activation = cur.fetchone()

    if not existing_activation and used_devices >= max_devices:
        conn.close()
        return {"ok": False, "message": "Достигнут лимит устройств для этого ключа"}

    if not existing_activation:
        cur.execute(
            "INSERT INTO activations (license_key, device_fingerprint, activated_at) VALUES (?, ?, ?)",
            (key, payload.device_fingerprint, now_iso()),
        )

    cur.execute(
        "UPDATE licenses SET updated_at = ? WHERE license_key = ?",
        (now_iso(), key),
    )
    conn.commit()
    state = build_license_state_row(cur, key)
    conn.close()
    return success_payload(key, state, "Активация успешна")


@app.post("/validate")
def validate(payload: LicensePayload):
    key = payload.license_key.strip()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    state = build_license_state_row(cur, key)
    if not state:
        conn.close()
        return {"ok": False, "message": "Ключ не найден"}
    if not state["is_active"]:
        conn.close()
        return {"ok": False, "message": "Ключ отключён"}
    if is_expired(state["expires_at"]):
        conn.close()
        return {"ok": False, "message": "Срок действия ключа истёк"}

    cur.execute(
        "SELECT id FROM activations WHERE license_key = ? AND device_fingerprint = ?",
        (key, payload.device_fingerprint),
    )
    activation = cur.fetchone()
    conn.close()
    if not activation:
        return {"ok": False, "message": "Ключ привязан к другому устройству"}

    return success_payload(key, state, "Лицензия валидна")


@app.post("/status")
def status(payload: LicensePayload):
    return validate(payload)


@app.post("/deactivate")
def deactivate(payload: LicensePayload):
    key = payload.license_key.strip()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT license_key FROM licenses WHERE license_key = ?", (key,))
    if not cur.fetchone():
        conn.close()
        return {"ok": False, "message": "Ключ не найден"}

    cur.execute(
        "DELETE FROM activations WHERE license_key = ? AND device_fingerprint = ?",
        (key, payload.device_fingerprint),
    )
    if cur.rowcount <= 0:
        conn.close()
        return {"ok": False, "message": "Деактивация разрешена только с привязанного устройства"}

    cur.execute(
        "UPDATE licenses SET updated_at = ? WHERE license_key = ?",
        (now_iso(), key),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Активация сброшена"}


@app.post("/admin/generate")
def admin_generate(
    payload: GeneratePayload,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    admin_token: str | None = Query(default=None),
):
    verify_admin_token(x_admin_token, admin_token)
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    created = []

    expires_at = (datetime.now(timezone.utc) + timedelta(days=payload.expires_days)).isoformat()
    updates_days = payload.updates_days if payload.updates_days else payload.expires_days
    updates_until = (datetime.now(timezone.utc) + timedelta(days=updates_days)).isoformat()

    for i in range(payload.count):
        if payload.mode == "serial":
            key_value = serial_key(payload.prefix.strip().upper() or "CG", payload.serial_start + i)
        else:
            key_value = random_key(payload.prefix.strip().upper() or "CG")

        cur.execute(
            """
            INSERT OR IGNORE INTO licenses (
                license_key, is_active, expires_at, updates_until, max_devices, created_at, updated_at
            )
            VALUES (?, 1, ?, ?, ?, ?, ?)
            """,
            (key_value, expires_at, updates_until, payload.max_devices, now_iso(), now_iso()),
        )
        if cur.rowcount > 0:
            created.append(key_value)

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "message": f"Создано ключей: {len(created)}",
        "keys": created,
        "expires_at": expires_at,
        "updates_until": updates_until,
        "max_devices": payload.max_devices,
    }


@app.get("/admin/list")
def admin_list(
    limit: int = 50,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    admin_token: str | None = Query(default=None),
):
    verify_admin_token(x_admin_token, admin_token)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT license_key, is_active, expires_at, updates_until, max_devices, created_at, updated_at
        FROM licenses
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (max(1, min(limit, 500)),),
    )
    rows = cur.fetchall()

    data = []
    for row in rows:
        cur.execute("SELECT COUNT(*) FROM activations WHERE license_key = ?", (row[0],))
        used = int(cur.fetchone()[0])
        data.append(
            {
                "license_key": row[0],
                "is_active": bool(row[1]),
                "expires_at": row[2],
                "updates_until": row[3],
                "updates_allowed": updates_allowed_for(row[3], row[2]),
                "max_devices": int(row[4] or 1),
                "used_devices": used,
                "created_at": row[5],
                "updated_at": row[6],
            }
        )

    conn.close()
    return {"ok": True, "items": data}


@app.get("/health")
def health():
    return {"ok": True, "status": "up", "db_path": DB_PATH}
