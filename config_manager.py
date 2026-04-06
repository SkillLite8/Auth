import json
import os


class ConfigManager:

    def __init__(self, plugin_dir: str):
        self._path = os.path.join(plugin_dir, "config.json")
        self._data = {}
        self._load()

    def _load(self):
        if not os.path.exists(self._path):
            return
        with open(self._path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    def get(self, key: str, default=None):
        keys = key.split(".")
        val = self._data
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

    def get_message(self, key: str) -> str:
        return str(self.get(f"messages.{key}", f"[missing:{key}]"))

    def get_form(self, form: str, key: str, default: str = "") -> str:
        return str(self.get(f"forms.{form}.{key}", default))

    @staticmethod
    def write_default(plugin_dir: str):
        config_path = os.path.join(plugin_dir, "config.json")
        if os.path.exists(config_path):
            return
        default = {
            "session": {
                "duration_hours": 24,
                "kick_timeout_seconds": 60,
                "max_accounts_per_device": 3,
                "spam_login_count": 3,
                "spam_login_window_minutes": 15,
                "spam_ban_minutes": 30
            },
            "security": {
                "max_attempts": 3,
                "bruteforce_ban_minutes": 15,
                "password_min_length": 6,
                "password_max_length": 15
            },
            "title": {
                "main_title": "§bSPAM",
                "main_subtitle": "§fПожалуйста, авторизуйтесь."
            },
            "sounds": {
                "form_open": "random.click",
                "login_success": "random.levelup",
                "login_fail": "mob.villager.no"
            },
            "forms": {
                "login": {
                    "title": "§bАвторизация",
                    "label": "§7Введите пароль для входа в аккаунт:",
                    "password_placeholder": "Пароль",
                    "submit_button": "§aВойти",
                    "register_button": "§eРегистрация"
                },
                "register": {
                    "title": "§aРегистрация",
                    "label": "§7Придумайте надёжный пароль:",
                    "password_placeholder": "Пароль (6-15 символов, a-z, A-Z, 0-9)",
                    "confirm_placeholder": "Подтвердите пароль",
                    "secret_placeholder": "Секретное слово (необязательно, только буквы)",
                    "submit_button": "§aЗарегистрироваться"
                },
                "changepass": {
                    "title": "§eСмена пароля",
                    "label": "§7Введите старый пароль или секретное слово:",
                    "old_placeholder": "Старый пароль или секретное слово",
                    "new_placeholder": "Новый пароль",
                    "confirm_placeholder": "Подтвердите новый пароль",
                    "submit_button": "§aСменить пароль"
                },
                "secret": {
                    "title": "§eСекретное слово",
                    "label": "§7Введите новое секретное слово:",
                    "secret_placeholder": "Только буквы (лат. или рус.)",
                    "submit_button": "§aУстановить"
                },
                "admin": {
                    "title": "§4ZenAdmin §cPanel",
                    "search_placeholder": "Ник игрока",
                    "reset_pass_button": "§e⚙ Сбросить пароль",
                    "delete_secret_button": "§e⚙ Удалить секретное слово",
                    "wipe_button": "§c✘ Полная очистка (Wipe)",
                    "logs_button": "§b✦ Логи игрока",
                    "back_button": "§7← Назад",
                    "online_players_button": "§a▶ Онлайн игроки"
                }
            },
            "messages": {
                "login_success": "§a✔ Добро пожаловать, §e{player}§a!",
                "login_fail": "§c✘ Неверный пароль! Осталось попыток: §e{attempts}",
                "register_success": "§a✔ Аккаунт создан! Добро пожаловать, §e{player}§a!",
                "not_logged": "§c✘ Сначала авторизуйтесь.",
                "password_invalid": "§c✘ Пароль: только латинские буквы и цифры, 6-15 символов.",
                "passwords_not_match": "§c✘ Пароли не совпадают.",
                "account_exists": "§c✘ Аккаунт с таким именем уже существует.",
                "too_many_accounts": "§c✘ С вашего устройства зарегистрировано слишком много аккаунтов.",
                "bruteforce_ban": "§c✘ Слишком много неудачных попыток. Бан на §e{minutes} мин.",
                "kick_timeout": "§c✘ Время авторизации истекло. Подключитесь снова.",
                "kick_banned": "§c✘ Вы заблокированы. Осталось: §e{time}",
                "secret_set": "§a✔ Секретное слово успешно установлено.",
                "secret_invalid": "§c✘ Секретное слово: только буквы (латинские или русские).",
                "secret_remind": "§e⚠ Установите секретное слово: §b/auth secret §eдля защиты аккаунта.",
                "password_changed": "§a✔ Пароль успешно изменён.",
                "old_password_wrong": "§c✘ Неверный старый пароль или секретное слово.",
                "no_permission": "§c✘ Недостаточно прав.",
                "player_not_found": "§c✘ Игрок §e{player} §cне найден в базе данных.",
                "admin_reset_success": "§a✔ Пароль игрока §e{player} §aсброшен.",
                "admin_secret_deleted": "§a✔ Секретное слово игрока §e{player} §aудалено.",
                "admin_wipe_success": "§a✔ Данные игрока §e{player} §aполностью удалены.",
                "auto_login": "§a✔ Добро пожаловать обратно, §e{player}§a!",
                "provide_nick": "§c✘ Укажите ник игрока.",
                "logs_no_data": "§c✘ Логи игрока §e{player} §cне найдены.",
                "admin_kick_reset": "§cАдминистратор сбросил ваш пароль. Авторизуйтесь заново.",
                "admin_kick_wipe": "§cВаши данные удалены администратором. Зарегистрируйтесь заново."
            }
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)

    @staticmethod
    def write_setup_guide(plugin_dir: str):
        guide_path = os.path.join(plugin_dir, "НАСТРОЙКА.txt")
        if os.path.exists(guide_path):
            return
        lines = [
            "╔══════════════════════════════════════════════════════════╗",
            "║           ZenAuth v2.0 — Руководство по настройке        ║",
            "╚══════════════════════════════════════════════════════════╝",
            "",
            "Все настройки хранятся в файле config.json рядом с этим файлом.",
            "В код лезть НЕ нужно — всё управляется через конфиг.",
            "",
            "═══════════════════════════════════════",
            "РАЗДЕЛ: session",
            "═══════════════════════════════════════",
            "duration_hours            Время жизни авто-сессии в часах.         По умолчанию: 24",
            "kick_timeout_seconds      Секунд до кика неавторизованного игрока. По умолчанию: 60",
            "max_accounts_per_device   Макс. аккаунтов на одно устройство.      По умолчанию: 3",
            "spam_login_count          Входов за окно времени до спам-бана.      По умолчанию: 3",
            "spam_login_window_minutes Ширина окна проверки спама (минут).       По умолчанию: 15",
            "spam_ban_minutes          Длительность бана за спам-входы (минут).  По умолчанию: 30",
            "",
            "═══════════════════════════════════════",
            "РАЗДЕЛ: security",
            "═══════════════════════════════════════",
            "max_attempts              Попыток ввода пароля до бана (брутфорс).  По умолчанию: 3",
            "bruteforce_ban_minutes    Длительность бана за брутфорс (минут).    По умолчанию: 15",
            "password_min_length       Минимальная длина пароля.                 По умолчанию: 6",
            "password_max_length       Максимальная длина пароля.                По умолчанию: 15",
            "",
            "═══════════════════════════════════════",
            "РАЗДЕЛ: title",
            "═══════════════════════════════════════",
            "main_title    Крупный заголовок на экране при входе. Поддерживает §-коды.",
            "main_subtitle Подзаголовок на экране при входе. Поддерживает §-коды.",
            "",
            "═══════════════════════════════════════",
            "РАЗДЕЛ: sounds",
            "═══════════════════════════════════════",
            "form_open     Звук при открытии формы авторизации.",
            "login_success Звук при успешном входе.",
            "login_fail    Звук при неверном пароле.",
            "Примеры: random.click, random.levelup, mob.villager.no, note.pling",
            "",
            "═══════════════════════════════════════",
            "РАЗДЕЛ: forms",
            "═══════════════════════════════════════",
            "Подразделы: login, register, changepass, secret, admin",
            "В каждом подразделе: title, label, тексты кнопок, placeholder-ы.",
            "Все значения поддерживают §-коды цветов Minecraft.",
            "",
            "═══════════════════════════════════════",
            "РАЗДЕЛ: messages",
            "═══════════════════════════════════════",
            "Все сообщения в чате. Плейсхолдеры:",
            "  {player}   — имя игрока",
            "  {attempts} — оставшиеся попытки",
            "  {minutes}  — длительность бана в минутах",
            "  {time}     — оставшееся время бана",
            "",
            "═══════════════════════════════════════",
            "КОМАНДЫ",
            "═══════════════════════════════════════",
            "/auth                              Форма входа (или смены пароля если авторизован)",
            "/auth secret [слово]               Установить секретное слово",
            "/auth changepass [старый] [новый]  Сменить пароль через команду",
            "/auth admin                        ZenAdmin панель (zenauth.admin)",
            "/auth logs [ник]                   Логи игрока (zenauth.admin)",
            "",
            "═══════════════════════════════════════",
            "ПРАВА",
            "═══════════════════════════════════════",
            "zenauth.use    Все игроки (по умолчанию)",
            "zenauth.admin  Только OP (по умолчанию)",
            "",
            "═══════════════════════════════════════",
            "ФАЙЛЫ ДАННЫХ",
            "═══════════════════════════════════════",
            "config.json    — конфигурация",
            "НАСТРОЙКА.txt  — этот файл",
            "players/       — JSON игроков",
            "sessions/      — авто-сессии",
            "player_logs/   — история действий",
            "logs.txt       — общий лог",
            "",
            "После изменения config.json — /reload или перезапуск сервера.",
        ]
        with open(guide_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
