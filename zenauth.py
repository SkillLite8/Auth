import os
import threading
import time

from endstone.plugin import Plugin
from endstone.event import event_handler
from endstone.event.player import (
    PlayerJoinEvent,
    PlayerQuitEvent,
    PlayerChatEvent,
    PlayerMoveEvent,
)

from endstone_zenauth.managers.config_manager import ConfigManager
from endstone_zenauth.managers.data_manager import DataManager
from endstone_zenauth.managers.session_manager import SessionManager
from endstone_zenauth.managers.security_manager import SecurityManager
from endstone_zenauth.managers.log_manager import LogManager
from endstone_zenauth.managers.form_manager import FormManager


class ZenAuth(Plugin):

    api_version = "0.10"

    commands = {
        "auth": {
            "description": "Команда авторизации ZenAuth",
            "usage": "/auth [secret|changepass|admin|logs]",
            "permission": "zenauth.use"
        }
    }

    permissions = {
        "zenauth.use": {
            "description": "Базовое использование ZenAuth",
            "default": True
        },
        "zenauth.admin": {
            "description": "Доступ к ZenAdmin панели",
            "default": False
        }
    }

    def on_load(self):
        self.logger.info("ZenAuth: загрузка...")

    def on_enable(self):
        plugin_dir = self.data_folder
        os.makedirs(plugin_dir, exist_ok=True)

        ConfigManager.write_default(plugin_dir)
        ConfigManager.write_setup_guide(plugin_dir)

        self.cfg = ConfigManager(plugin_dir)
        self.data = DataManager(plugin_dir)
        self.log_mgr = LogManager(plugin_dir)
        self.security = SecurityManager(self.cfg)
        self.session = SessionManager(self.cfg, self.data, plugin_dir)
        self.forms = FormManager(self, self.cfg, self.data, self.session, self.security, self.log_mgr)

        self.register_events(self)
        self._start_tick_loop()
        self.logger.info("ZenAuth: включён.")

    def on_disable(self):
        self.logger.info("ZenAuth: выключен.")

    def on_command(self, sender, command, args):
        if command.name != "auth":
            return False

        if not hasattr(sender, "send_form"):
            if args and args[0] == "logs" and len(args) >= 2:
                logs = self.log_mgr.format_for_display(args[1])
                if not logs:
                    sender.send_message(
                        self.cfg.get_message("logs_no_data").replace("{player}", args[1])
                    )
                else:
                    for line in logs:
                        sender.send_message(line)
            else:
                sender.send_message("§bZenAuth v2.0 активен.")
            return True

        player = sender

        if not args:
            if self.session.is_authenticated(player.name):
                self.forms.show_changepass_form(player)
            else:
                self.forms.show_login_form(player)
            return True

        sub = args[0].lower()

        if sub == "secret":
            if not self.session.is_authenticated(player.name):
                player.send_message(self.cfg.get_message("not_logged"))
                return True
            if len(args) >= 2:
                secret = args[1]
                if not self.security.validate_secret_word(secret):
                    player.send_message(self.cfg.get_message("secret_invalid"))
                    return True
                self.data.set_secret(player.name, secret)
                player.send_message(self.cfg.get_message("secret_set"))
                self.log_mgr.log(player.name, self._ip(player), "set_secret", "success")
            else:
                self.forms.show_secret_form(player)
            return True

        if sub == "changepass":
            if not self.session.is_authenticated(player.name):
                player.send_message(self.cfg.get_message("not_logged"))
                return True
            if len(args) >= 3:
                old_or_secret = args[1]
                new_pass = args[2]
                if not self.security.validate_password(new_pass):
                    player.send_message(self.cfg.get_message("password_invalid"))
                    return True
                valid = (
                    self.data.check_password(player.name, old_or_secret) or
                    self.data.check_secret(player.name, old_or_secret)
                )
                if not valid:
                    player.send_message(self.cfg.get_message("old_password_wrong"))
                    return True
                self.data.change_password(player.name, new_pass)
                self.session.save_session(player.name)
                player.send_message(self.cfg.get_message("password_changed"))
                self.log_mgr.log(player.name, self._ip(player), "changepass", "success")
            else:
                self.forms.show_changepass_form(player)
            return True

        if sub == "admin":
            if not player.has_permission("zenauth.admin"):
                player.send_message(self.cfg.get_message("no_permission"))
                return True
            self.forms.show_admin_panel(player)
            return True

        if sub == "logs":
            if not player.has_permission("zenauth.admin"):
                player.send_message(self.cfg.get_message("no_permission"))
                return True
            if len(args) < 2:
                player.send_message(self.cfg.get_message("provide_nick"))
                return True
            self.forms.show_logs_form(player, args[1])
            return True

        self.forms.show_login_form(player)
        return True

    @event_handler
    def on_player_join(self, event: PlayerJoinEvent):
        player = event.player
        if player is None:
            return

        ip = self._ip(player)

        if self.security.get_bruteforce_ban(ip):
            player.kick(
                self.cfg.get_message("kick_banned").replace(
                    "{time}", self.security.get_bruteforce_remaining(ip)
                )
            )
            return

        if self.security.get_spam_ban(ip):
            player.kick(
                self.cfg.get_message("kick_banned").replace(
                    "{time}", self.security.get_spam_remaining(ip)
                )
            )
            return

        device_id = self._device_id(player)

        if self.session.check_session(player.name, ip, device_id):
            self.session.mark_authenticated(player.name)
            player.send_message(
                self.cfg.get_message("auto_login").replace("{player}", player.name)
            )
            self.log_mgr.log(player.name, ip, "auto_login", "success")
            if not self.data.has_secret(player.name):
                player.send_message(self.cfg.get_message("secret_remind"))
            return

        self.security.track_join(ip)
        self.apply_effects(player)
        self.session.start_kick_timer(player.name)
        threading.Timer(0.5, lambda: self.forms.show_login_form(player)).start()

    @event_handler
    def on_player_quit(self, event: PlayerQuitEvent):
        if event.player:
            self.session.cancel_kick_timer(event.player.name)
            self.session.remove_authenticated(event.player.name)

    @event_handler
    def on_player_move(self, event: PlayerMoveEvent):
        if event.player and not self.session.is_authenticated(event.player.name):
            event.cancelled = True

    @event_handler
    def on_player_chat(self, event: PlayerChatEvent):
        if event.player and not self.session.is_authenticated(event.player.name):
            event.cancelled = True

    def apply_effects(self, player):
        try:
            player.send_title(
                self.cfg.get("title.main_title", "§bSPAM"),
                self.cfg.get("title.main_subtitle", "§fПожалуйста, авторизуйтесь."),
                fade_in=20,
                stay=99999,
                fade_out=20
            )
        except Exception:
            pass
        try:
            player.add_effect("darkness", 99999, 0, False)
        except Exception:
            pass

    def remove_effects(self, player):
        try:
            player.reset_title()
        except Exception:
            pass
        try:
            player.remove_effect("darkness")
        except Exception:
            pass

    def _ip(self, player) -> str:
        try:
            return str(player.address.hostname)
        except Exception:
            return "unknown"

    def _device_id(self, player) -> str:
        try:
            return str(player.device_id)
        except Exception:
            try:
                return str(player.unique_id)
            except Exception:
                return player.name

    def _start_tick_loop(self):
        def loop():
            while True:
                time.sleep(1)
                try:
                    self.session.tick_kick_timers(self._do_kick)
                except Exception:
                    pass
        threading.Thread(target=loop, daemon=True).start()

    def _do_kick(self, player_name: str):
        try:
            player = self.server.get_player(player_name)
            if player and not self.session.is_authenticated(player_name):
                player.kick(self.cfg.get_message("kick_timeout"))
        except Exception:
            pass
