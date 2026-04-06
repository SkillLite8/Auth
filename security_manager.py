import re
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List


class SecurityManager:

    def __init__(self, cfg):
        self._cfg = cfg
        self._attempts: Dict[str, int] = {}
        self._bf_bans: Dict[str, datetime] = {}
        self._spam_bans: Dict[str, datetime] = {}
        self._login_times: Dict[str, List[datetime]] = {}
        self._lock = threading.Lock()

    def validate_password(self, password: str) -> bool:
        min_len = self._cfg.get("security.password_min_length", 6)
        max_len = self._cfg.get("security.password_max_length", 15)
        if not (min_len <= len(password) <= max_len):
            return False
        return bool(re.match(r'^[a-zA-Z0-9]+$', password))

    def validate_secret_word(self, secret: str) -> bool:
        if not secret:
            return False
        return bool(re.match(r'^[a-zA-Zа-яА-ЯёЁ]+$', secret))

    def record_failed_attempt(self, ip: str) -> int:
        with self._lock:
            self._attempts[ip] = self._attempts.get(ip, 0) + 1
            return self._attempts[ip]

    def get_remaining_attempts(self, ip: str) -> int:
        max_att = self._cfg.get("security.max_attempts", 3)
        return max(0, max_att - self._attempts.get(ip, 0))

    def is_bruteforce(self, ip: str) -> bool:
        return self._attempts.get(ip, 0) >= self._cfg.get("security.max_attempts", 3)

    def apply_bruteforce_ban(self, ip: str):
        minutes = self._cfg.get("security.bruteforce_ban_minutes", 15)
        with self._lock:
            self._bf_bans[ip] = datetime.now() + timedelta(minutes=minutes)
            self._attempts[ip] = 0

    def get_bruteforce_ban(self, ip: str) -> Optional[datetime]:
        ban_until = self._bf_bans.get(ip)
        if ban_until and datetime.now() < ban_until:
            return ban_until
        if ban_until:
            with self._lock:
                self._bf_bans.pop(ip, None)
        return None

    def get_bruteforce_remaining(self, ip: str) -> str:
        ban_until = self._bf_bans.get(ip)
        if not ban_until:
            return "0м"
        delta = ban_until - datetime.now()
        return f"{int(delta.total_seconds() / 60) + 1}м"

    def track_join(self, ip: str):
        window = self._cfg.get("session.spam_login_window_minutes", 15)
        threshold = self._cfg.get("session.spam_login_count", 3)
        ban_mins = self._cfg.get("session.spam_ban_minutes", 30)
        now = datetime.now()
        cutoff = now - timedelta(minutes=window)
        with self._lock:
            times = [t for t in self._login_times.get(ip, []) if t > cutoff]
            times.append(now)
            self._login_times[ip] = times
            if len(times) > threshold:
                self._spam_bans[ip] = now + timedelta(minutes=ban_mins)
                self._login_times[ip] = []

    def get_spam_ban(self, ip: str) -> Optional[datetime]:
        ban_until = self._spam_bans.get(ip)
        if ban_until and datetime.now() < ban_until:
            return ban_until
        if ban_until:
            with self._lock:
                self._spam_bans.pop(ip, None)
        return None

    def get_spam_remaining(self, ip: str) -> str:
        ban_until = self._spam_bans.get(ip)
        if not ban_until:
            return "0м"
        delta = ban_until - datetime.now()
        return f"{int(delta.total_seconds() / 60) + 1}м"

    def reset_attempts(self, ip: str):
        with self._lock:
            self._attempts.pop(ip, None)
