import json
import os
import threading
from datetime import datetime
from typing import List, Dict


class LogManager:

    _ACTION_LABELS = {
        "login": "Вход",
        "register": "Регистрация",
        "auto_login": "Авто-вход",
        "changepass": "Смена пароля",
        "set_secret": "Уст. секрета",
        "failed_login": "Неудачный вход",
        "admin_reset": "Сброс пароля (адм)",
        "admin_wipe": "Вайп (адм)",
        "admin_delete_secret": "Удал. секрета (адм)"
    }

    def __init__(self, plugin_dir: str):
        self._log_file = os.path.join(plugin_dir, "logs.txt")
        self._player_logs_dir = os.path.join(plugin_dir, "player_logs")
        os.makedirs(self._player_logs_dir, exist_ok=True)
        self._lock = threading.Lock()

    def log(self, player_name: str, ip: str, action: str, status: str):
        now = datetime.now()
        entry = {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "ip": ip,
            "action": action,
            "status": status
        }
        line = f"[{entry['date']} {entry['time']}] [{player_name}] [{ip}] {action} -> {status}\n"

        def write():
            with self._lock:
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(line)
                self._append_player_log(player_name, entry)

        threading.Thread(target=write, daemon=True).start()

    def _append_player_log(self, name: str, entry: dict):
        path = self._player_path(name)
        logs: List[dict] = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        logs.append(entry)
        if len(logs) > 200:
            logs = logs[-200:]
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def get_player_logs(self, name: str) -> List[Dict]:
        path = self._player_path(name)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def format_for_display(self, name: str, limit: int = 30) -> List[str]:
        logs = self.get_player_logs(name)
        if not logs:
            return []
        result = []
        for entry in reversed(logs[-limit:]):
            status = entry.get("status", "?")
            color = "§a" if status == "success" else "§c"
            label = self._ACTION_LABELS.get(entry.get("action", ""), entry.get("action", "?"))
            status_text = "успех" if status == "success" else status
            result.append(
                f"§7{entry.get('date', '?')} {entry.get('time', '?')} "
                f"§b{entry.get('ip', '?')} "
                f"§e{label} {color}{status_text}"
            )
        return result

    def _player_path(self, name: str) -> str:
        return os.path.join(self._player_logs_dir, f"{name.lower()}.json")
