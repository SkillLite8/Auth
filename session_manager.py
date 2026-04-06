import json
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, Callable


class SessionManager:

    def __init__(self, cfg, data, plugin_dir: str):
        self._cfg = cfg
        self._data = data
        self._sessions_dir = os.path.join(plugin_dir, "sessions")
        os.makedirs(self._sessions_dir, exist_ok=True)
        self._authenticated: set = set()
        self._kick_timers: Dict[str, int] = {}
        self._lock = threading.Lock()

    def is_authenticated(self, name: str) -> bool:
        return name.lower() in self._authenticated

    def mark_authenticated(self, name: str):
        self._authenticated.add(name.lower())

    def remove_authenticated(self, name: str):
        self._authenticated.discard(name.lower())
        self.cancel_kick_timer(name)

    def check_session(self, name: str, ip: str, device_id: str) -> bool:
        if not self._data.player_exists(name):
            return False
        if self._data.get_ip(name) != ip:
            return False
        if self._data.get_device_id(name) != device_id:
            return False
        path = self._session_path(name)
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            expires = datetime.strptime(d["expires"], "%Y-%m-%d %H:%M:%S")
            if datetime.now() > expires:
                os.remove(path)
                return False
            return True
        except Exception:
            return False

    def save_session(self, name: str):
        hours = self._cfg.get("session.duration_hours", 24)
        expires = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        path = self._session_path(name)
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"expires": expires}, f)
            os.replace(tmp, path)
        except Exception:
            pass

    def invalidate_session(self, name: str):
        path = self._session_path(name)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    def start_kick_timer(self, name: str):
        seconds = self._cfg.get("session.kick_timeout_seconds", 60)
        with self._lock:
            self._kick_timers[name.lower()] = int(seconds)

    def cancel_kick_timer(self, name: str):
        with self._lock:
            self._kick_timers.pop(name.lower(), None)

    def tick_kick_timers(self, kick_callback: Callable[[str], None]):
        with self._lock:
            to_kick = []
            for name in list(self._kick_timers.keys()):
                if name in self._authenticated:
                    del self._kick_timers[name]
                    continue
                self._kick_timers[name] -= 1
                if self._kick_timers[name] <= 0:
                    to_kick.append(name)
                    del self._kick_timers[name]
        for name in to_kick:
            try:
                kick_callback(name)
            except Exception:
                pass

    def _session_path(self, name: str) -> str:
        return os.path.join(self._sessions_dir, f"{name.lower()}.json")
