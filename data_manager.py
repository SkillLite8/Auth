import json
import os
import hashlib
import threading
from datetime import datetime
from typing import Optional


class DataManager:

    def __init__(self, plugin_dir: str):
        self._players_dir = os.path.join(plugin_dir, "players")
        os.makedirs(self._players_dir, exist_ok=True)
        self._lock = threading.Lock()

    def _player_path(self, name: str) -> str:
        return os.path.join(self._players_dir, f"{name.lower()}.json")

    def _load(self, name: str) -> dict:
        path = self._player_path(name)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_async(self, name: str, data: dict):
        def write():
            with self._lock:
                path = self._player_path(name)
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
        threading.Thread(target=write, daemon=True).start()

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def player_exists(self, name: str) -> bool:
        return os.path.exists(self._player_path(name))

    def has_null_password(self, name: str) -> bool:
        return self._load(name).get("password_hash") is None

    def register_player(self, name: str, password: str, ip: str,
                        device_id: str, secret: Optional[str] = None):
        data = {
            "name": name,
            "password_hash": self._hash(password),
            "ip": ip,
            "device_id": device_id,
            "secret_hash": self._hash(secret) if secret else None,
            "registered_at": self._now()
        }
        self._save_async(name, data)

    def check_password(self, name: str, password: str) -> bool:
        d = self._load(name)
        stored = d.get("password_hash")
        if not stored:
            return False
        return stored == self._hash(password)

    def check_secret(self, name: str, secret: str) -> bool:
        d = self._load(name)
        stored = d.get("secret_hash")
        if not stored:
            return False
        return stored == self._hash(secret)

    def has_secret(self, name: str) -> bool:
        return bool(self._load(name).get("secret_hash"))

    def set_secret(self, name: str, secret: str):
        d = self._load(name)
        if not d:
            return
        d["secret_hash"] = self._hash(secret)
        self._save_async(name, d)

    def delete_secret(self, name: str):
        d = self._load(name)
        if not d:
            return
        d["secret_hash"] = None
        self._save_async(name, d)

    def change_password(self, name: str, new_password: str):
        d = self._load(name)
        if not d:
            return
        d["password_hash"] = self._hash(new_password)
        self._save_async(name, d)

    def reset_password(self, name: str):
        d = self._load(name)
        if not d:
            return
        d["password_hash"] = None
        self._save_async(name, d)

    def wipe_player(self, name: str):
        path = self._player_path(name)
        if os.path.exists(path):
            os.remove(path)

    def get_ip(self, name: str) -> Optional[str]:
        return self._load(name).get("ip")

    def get_device_id(self, name: str) -> Optional[str]:
        return self._load(name).get("device_id")

    def update_ip(self, name: str, ip: str):
        d = self._load(name)
        if not d:
            return
        d["ip"] = ip
        self._save_async(name, d)

    def count_accounts_by_device(self, device_id: str) -> int:
        count = 0
        try:
            for fname in os.listdir(self._players_dir):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(self._players_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    if d.get("device_id") == device_id:
                        count += 1
                except Exception:
                    pass
        except Exception:
            pass
        return count
