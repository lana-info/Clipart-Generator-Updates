import sqlite3
import argparse
from datetime import datetime, timezone


DB_PATH = "licenses.db"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def reset_activation(license_key):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE licenses SET bound_device = NULL, updated_at = ? WHERE license_key = ?",
        (now_iso(), license_key),
    )
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return changed > 0


def create_key(license_key):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO licenses (license_key, is_active, bound_device, updated_at) VALUES (?, 1, NULL, ?)",
        (license_key, now_iso()),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Админ-утилита лицензий")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create")
    p_create.add_argument("license_key")

    p_reset = sub.add_parser("reset")
    p_reset.add_argument("license_key")

    args = parser.parse_args()
    if args.cmd == "create":
        create_key(args.license_key)
        print("Ключ создан/подтверждён")
    elif args.cmd == "reset":
        ok = reset_activation(args.license_key)
        print("Сброс выполнен" if ok else "Ключ не найден")
