import sqlite3
import argparse
import random
import string
from datetime import datetime, timezone, timedelta


DB_PATH = "licenses.db"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            is_active INTEGER NOT NULL DEFAULT 1,
            expires_at TEXT,
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
    if "max_devices" not in columns:
        cur.execute("ALTER TABLE licenses ADD COLUMN max_devices INTEGER NOT NULL DEFAULT 1")
    if "created_at" not in columns:
        cur.execute("ALTER TABLE licenses ADD COLUMN created_at TEXT")

    conn.commit()
    conn.close()


def reset_activation(license_key):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT license_key FROM licenses WHERE license_key = ?", (license_key,))
    if not cur.fetchone():
        conn.close()
        return False

    cur.execute(
        "DELETE FROM activations WHERE license_key = ?",
        (license_key,),
    )
    changed = cur.rowcount
    cur.execute(
        "UPDATE licenses SET updated_at = ? WHERE license_key = ?",
        (now_iso(), license_key),
    )
    conn.commit()
    conn.close()
    return changed >= 0


def create_key(license_key):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    cur.execute(
        """
        INSERT OR IGNORE INTO licenses (
            license_key, is_active, expires_at, max_devices, created_at, updated_at
        ) VALUES (?, 1, ?, 1, ?, ?)
        """,
        (license_key, expires_at, now_iso(), now_iso()),
    )
    conn.commit()
    conn.close()


def random_key(prefix):
    chunks = ["".join(random.choices(string.ascii_uppercase + string.digits, k=4)) for _ in range(3)]
    return f"{prefix}-{'-'.join(chunks)}"


def serial_key(prefix, index):
    return f"{prefix}-{index:06d}"


def generate_keys(count, prefix, mode, expires_days, max_devices, serial_start):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()
    created = []

    for i in range(count):
        if mode == "serial":
            key = serial_key(prefix, serial_start + i)
        else:
            key = random_key(prefix)

        cur.execute(
            """
            INSERT OR IGNORE INTO licenses (
                license_key, is_active, expires_at, max_devices, created_at, updated_at
            ) VALUES (?, 1, ?, ?, ?, ?)
            """,
            (key, expires_at, max_devices, now_iso(), now_iso()),
        )
        if cur.rowcount > 0:
            created.append(key)

    conn.commit()
    conn.close()
    return created


def list_keys(limit=50):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT license_key, is_active, expires_at, max_devices, created_at
        FROM licenses
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (max(1, min(limit, 500)),),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser(description="Админ-утилита лицензий")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create")
    p_create.add_argument("license_key")

    p_reset = sub.add_parser("reset")
    p_reset.add_argument("license_key")

    p_generate = sub.add_parser("generate")
    p_generate.add_argument("--count", type=int, default=10)
    p_generate.add_argument("--prefix", type=str, default="CG")
    p_generate.add_argument("--mode", type=str, choices=["random", "serial"], default="random")
    p_generate.add_argument("--expires-days", type=int, default=365)
    p_generate.add_argument("--max-devices", type=int, default=1)
    p_generate.add_argument("--serial-start", type=int, default=1)

    p_list = sub.add_parser("list")
    p_list.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()
    if args.cmd == "create":
        create_key(args.license_key)
        print("Ключ создан/подтверждён")
    elif args.cmd == "reset":
        ok = reset_activation(args.license_key)
        print("Сброс выполнен" if ok else "Ключ не найден")
    elif args.cmd == "generate":
        generated = generate_keys(
            count=max(1, args.count),
            prefix=(args.prefix or "CG").upper(),
            mode=args.mode,
            expires_days=max(1, args.expires_days),
            max_devices=max(1, args.max_devices),
            serial_start=max(1, args.serial_start),
        )
        print(f"Создано ключей: {len(generated)}")
        for key in generated:
            print(key)
    elif args.cmd == "list":
        for row in list_keys(args.limit):
            print(f"{row[0]} | active={bool(row[1])} | expires={row[2]} | max_devices={row[3]} | created={row[4]}")
