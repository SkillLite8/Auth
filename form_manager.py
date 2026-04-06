import threading


class FormManager:

    def __init__(self, plugin, cfg, data, session, security, log_mgr):
        self._plugin = plugin
        self._cfg = cfg
        self._data = data
        self._session = session
        self._security = security
        self._log = log_mgr

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

    def _play_sound(self, player, key: str):
        sound = self._cfg.get(f"sounds.{key}", "")
        if not sound:
            return
        try:
            player.play_sound(player.location, sound, 1.0, 1.0)
        except Exception:
            pass

    def show_login_form(self, player):
        from endstone.form import ActionForm
        self._play_sound(player, "form_open")
        form = ActionForm(
            title=self._cfg.get_form("login", "title", "§bАвторизация"),
            content=self._cfg.get_form("login", "label", "§7Введите пароль:")
        )
        form.add_button(
            self._cfg.get_form("login", "submit_button", "§aВойти"),
            on_click=lambda p: self._open_login_input(p)
        )
        form.add_button(
            self._cfg.get_form("login", "register_button", "§eРегистрация"),
            on_click=lambda p: self.show_register_form(p)
        )
        form.on_close = lambda p: threading.Timer(0.3, lambda: self.show_login_form(p)).start()
        player.send_form(form)

    def _open_login_input(self, player):
        from endstone.form import CustomForm
        form = CustomForm(title=self._cfg.get_form("login", "title", "§bАвторизация"))
        form.add_input(
            label=self._cfg.get_form("login", "label", "§7Пароль:"),
            placeholder=self._cfg.get_form("login", "password_placeholder", "Пароль")
        )
        form.on_submit = lambda p, r: self._handle_login(p, r)
        form.on_close = lambda p: self.show_login_form(p)
        player.send_form(form)

    def _handle_login(self, player, response):
        ip = self._ip(player)

        if self._security.get_bruteforce_ban(ip):
            msg = self._cfg.get_message("kick_banned").replace(
                "{time}", self._security.get_bruteforce_remaining(ip)
            )
            player.kick(msg)
            return

        password = str(response[0]).strip() if response and response[0] else ""

        if not self._data.player_exists(player.name):
            self._play_sound(player, "login_fail")
            player.send_message(
                self._cfg.get_message("player_not_found").replace("{player}", player.name)
            )
            self.show_login_form(player)
            return

        if self._data.has_null_password(player.name):
            player.send_message("§eВаш пароль сброшен администратором. Зарегистрируйтесь заново.")
            self.show_register_form(player)
            return

        if self._data.check_password(player.name, password):
            self._security.reset_attempts(ip)
            self._session.mark_authenticated(player.name)
            self._session.cancel_kick_timer(player.name)
            self._session.save_session(player.name)
            self._data.update_ip(player.name, ip)
            self._plugin.remove_effects(player)
            self._play_sound(player, "login_success")
            player.send_message(
                self._cfg.get_message("login_success").replace("{player}", player.name)
            )
            self._log.log(player.name, ip, "login", "success")
            if not self._data.has_secret(player.name):
                player.send_message(self._cfg.get_message("secret_remind"))
        else:
            count = self._security.record_failed_attempt(ip)
            self._play_sound(player, "login_fail")
            self._log.log(player.name, ip, "failed_login", f"attempt_{count}")
            if self._security.is_bruteforce(ip):
                self._security.apply_bruteforce_ban(ip)
                mins = self._cfg.get("security.bruteforce_ban_minutes", 15)
                msg = self._cfg.get_message("bruteforce_ban").replace("{minutes}", str(mins))
                player.send_message(msg)
                player.kick(msg)
            else:
                remaining = self._security.get_remaining_attempts(ip)
                player.send_message(
                    self._cfg.get_message("login_fail").replace("{attempts}", str(remaining))
                )
                self.show_login_form(player)

    def show_register_form(self, player):
        from endstone.form import CustomForm
        device_id = self._device_id(player)
        max_acc = self._cfg.get("session.max_accounts_per_device", 3)

        if self._data.count_accounts_by_device(device_id) >= max_acc:
            player.send_message(self._cfg.get_message("too_many_accounts"))
            self.show_login_form(player)
            return

        if self._data.player_exists(player.name):
            player.send_message(self._cfg.get_message("account_exists"))
            self.show_login_form(player)
            return

        self._play_sound(player, "form_open")
        form = CustomForm(title=self._cfg.get_form("register", "title", "§aРегистрация"))
        form.add_input(
            label=self._cfg.get_form("register", "label", "§7Придумайте пароль:"),
            placeholder=self._cfg.get_form("register", "password_placeholder", "Пароль")
        )
        form.add_input(
            label="§7Подтвердите пароль:",
            placeholder=self._cfg.get_form("register", "confirm_placeholder", "Повтор пароля")
        )
        form.add_input(
            label="§7Секретное слово §8(необязательно, только буквы):",
            placeholder=self._cfg.get_form("register", "secret_placeholder", "Секретное слово")
        )
        form.on_submit = lambda p, r: self._handle_register(p, r)
        form.on_close = lambda p: self.show_login_form(p)
        player.send_form(form)

    def _handle_register(self, player, response):
        ip = self._ip(player)
        device_id = self._device_id(player)

        password = str(response[0]).strip() if response and response[0] else ""
        confirm = str(response[1]).strip() if response and len(response) > 1 and response[1] else ""
        secret_raw = str(response[2]).strip() if response and len(response) > 2 and response[2] else ""

        if not self._security.validate_password(password):
            self._play_sound(player, "login_fail")
            player.send_message(self._cfg.get_message("password_invalid"))
            self.show_register_form(player)
            return

        if password != confirm:
            self._play_sound(player, "login_fail")
            player.send_message(self._cfg.get_message("passwords_not_match"))
            self.show_register_form(player)
            return

        if self._data.player_exists(player.name):
            player.send_message(self._cfg.get_message("account_exists"))
            self.show_login_form(player)
            return

        if self._data.count_accounts_by_device(device_id) >= self._cfg.get("session.max_accounts_per_device", 3):
            player.send_message(self._cfg.get_message("too_many_accounts"))
            self.show_login_form(player)
            return

        secret_to_save = None
        if secret_raw:
            if not self._security.validate_secret_word(secret_raw):
                self._play_sound(player, "login_fail")
                player.send_message(self._cfg.get_message("secret_invalid"))
                self.show_register_form(player)
                return
            secret_to_save = secret_raw

        self._data.register_player(player.name, password, ip, device_id, secret_to_save)
        self._session.mark_authenticated(player.name)
        self._session.cancel_kick_timer(player.name)
        self._session.save_session(player.name)
        self._plugin.remove_effects(player)
        self._play_sound(player, "login_success")
        player.send_message(
            self._cfg.get_message("register_success").replace("{player}", player.name)
        )
        self._log.log(player.name, ip, "register", "success")

        if not secret_to_save:
            player.send_message(self._cfg.get_message("secret_remind"))

    def show_changepass_form(self, player):
        from endstone.form import CustomForm
        self._play_sound(player, "form_open")
        form = CustomForm(title=self._cfg.get_form("changepass", "title", "§eСмена пароля"))
        form.add_input(
            label=self._cfg.get_form("changepass", "label", "§7Старый пароль или секретное слово:"),
            placeholder=self._cfg.get_form("changepass", "old_placeholder", "Старый пароль")
        )
        form.add_input(
            label="§7Новый пароль:",
            placeholder=self._cfg.get_form("changepass", "new_placeholder", "Новый пароль")
        )
        form.add_input(
            label="§7Подтвердите новый пароль:",
            placeholder=self._cfg.get_form("changepass", "confirm_placeholder", "Повтор")
        )
        form.on_submit = lambda p, r: self._handle_changepass(p, r)
        player.send_form(form)

    def _handle_changepass(self, player, response):
        ip = self._ip(player)
        old_or_secret = str(response[0]).strip() if response and response[0] else ""
        new_pass = str(response[1]).strip() if response and len(response) > 1 and response[1] else ""
        confirm = str(response[2]).strip() if response and len(response) > 2 and response[2] else ""

        if not self._security.validate_password(new_pass):
            self._play_sound(player, "login_fail")
            player.send_message(self._cfg.get_message("password_invalid"))
            return

        if new_pass != confirm:
            self._play_sound(player, "login_fail")
            player.send_message(self._cfg.get_message("passwords_not_match"))
            return

        valid = (
            self._data.check_password(player.name, old_or_secret) or
            self._data.check_secret(player.name, old_or_secret)
        )
        if not valid:
            self._play_sound(player, "login_fail")
            player.send_message(self._cfg.get_message("old_password_wrong"))
            return

        self._data.change_password(player.name, new_pass)
        self._session.save_session(player.name)
        self._play_sound(player, "login_success")
        player.send_message(self._cfg.get_message("password_changed"))
        self._log.log(player.name, ip, "changepass", "success")

    def show_secret_form(self, player):
        from endstone.form import CustomForm
        self._play_sound(player, "form_open")
        form = CustomForm(title=self._cfg.get_form("secret", "title", "§eСекретное слово"))
        form.add_input(
            label=self._cfg.get_form("secret", "label", "§7Введите секретное слово:"),
            placeholder=self._cfg.get_form("secret", "secret_placeholder", "Только буквы")
        )
        form.on_submit = lambda p, r: self._handle_secret(p, r)
        player.send_form(form)

    def _handle_secret(self, player, response):
        ip = self._ip(player)
        secret = str(response[0]).strip() if response and response[0] else ""

        if not self._security.validate_secret_word(secret):
            self._play_sound(player, "login_fail")
            player.send_message(self._cfg.get_message("secret_invalid"))
            return

        self._data.set_secret(player.name, secret)
        self._play_sound(player, "login_success")
        player.send_message(self._cfg.get_message("secret_set"))
        self._log.log(player.name, ip, "set_secret", "success")

    def show_admin_panel(self, player):
        from endstone.form import ActionForm
        self._play_sound(player, "form_open")
        form = ActionForm(
            title=self._cfg.get_form("admin", "title", "§4ZenAdmin §cPanel"),
            content="§7Выберите игрока для управления:"
        )
        online_players = []
        try:
            online_players = list(self._plugin.server.online_players)
        except Exception:
            pass

        if online_players:
            form.add_button(
                self._cfg.get_form("admin", "online_players_button", "§a▶ Онлайн игроки"),
                on_click=lambda p: self._show_online_list(p)
            )
        form.add_button(
            "§7✎ Найти по нику",
            on_click=lambda p: self._show_search_form(p)
        )
        player.send_form(form)

    def _show_online_list(self, player):
        from endstone.form import ActionForm
        try:
            online = list(self._plugin.server.online_players)
        except Exception:
            online = []

        if not online:
            player.send_message("§cОнлайн игроков нет.")
            self.show_admin_panel(player)
            return

        form = ActionForm(title="§a▶ Онлайн игроки", content="§7Выберите игрока:")
        for p in online:
            reg = "§a✔" if self._data.player_exists(p.name) else "§c✘"
            auth = "§a[авт]" if self._session.is_authenticated(p.name) else "§c[нет]"
            form.add_button(
                f"§f{p.name} {reg} {auth}",
                on_click=lambda adm, target=p.name: self._show_player_actions(adm, target)
            )
        form.add_button("§7← Назад", on_click=lambda p: self.show_admin_panel(p))
        player.send_form(form)

    def _show_search_form(self, player):
        from endstone.form import CustomForm
        form = CustomForm(title="§7Поиск игрока")
        form.add_input(
            label="§7Введите ник:",
            placeholder=self._cfg.get_form("admin", "search_placeholder", "Ник игрока")
        )
        form.on_submit = lambda p, r: self._handle_search(p, r)
        form.on_close = lambda p: self.show_admin_panel(p)
        player.send_form(form)

    def _handle_search(self, player, response):
        target_name = str(response[0]).strip() if response and response[0] else ""
        if not target_name:
            player.send_message(self._cfg.get_message("provide_nick"))
            return
        self._show_player_actions(player, target_name)

    def _show_player_actions(self, player, target_name: str):
        from endstone.form import ActionForm
        exists = self._data.player_exists(target_name)
        status = "§aЗарегистрирован" if exists else "§cНе найден"
        has_sec = "§aДа" if exists and self._data.has_secret(target_name) else "§cНет"
        is_online = "§aОнлайн" if self._session.is_authenticated(target_name) else "§7Оффлайн"
        content = (
            f"§eИгрок: §f{target_name}\n"
            f"§7Статус в БД: {status}\n"
            f"§7Секретное слово: {has_sec}\n"
            f"§7Сессия: {is_online}"
        )
        form = ActionForm(title=f"§c{target_name}", content=content)
        form.add_button(
            self._cfg.get_form("admin", "reset_pass_button", "§e⚙ Сбросить пароль"),
            on_click=lambda p: self._admin_reset(p, target_name)
        )
        form.add_button(
            self._cfg.get_form("admin", "delete_secret_button", "§e⚙ Удалить секретное слово"),
            on_click=lambda p: self._admin_del_secret(p, target_name)
        )
        form.add_button(
            self._cfg.get_form("admin", "wipe_button", "§c✘ Wipe"),
            on_click=lambda p: self._admin_wipe(p, target_name)
        )
        form.add_button(
            self._cfg.get_form("admin", "logs_button", "§b✦ Логи"),
            on_click=lambda p: self.show_logs_form(p, target_name)
        )
        form.add_button(
            self._cfg.get_form("admin", "back_button", "§7← Назад"),
            on_click=lambda p: self.show_admin_panel(p)
        )
        player.send_form(form)

    def _admin_reset(self, player, target_name: str):
        ip = self._ip(player)
        self._data.reset_password(target_name)
        self._session.invalidate_session(target_name)
        player.send_message(
            self._cfg.get_message("admin_reset_success").replace("{player}", target_name)
        )
        self._log.log(target_name, ip, "admin_reset", f"by_{player.name}")
        target = self._get_online(target_name)
        if target:
            self._session.remove_authenticated(target_name)
            self._plugin.apply_effects(target)
            target.send_message(self._cfg.get_message("admin_kick_reset"))
            threading.Timer(0.5, lambda: self.show_register_form(target)).start()

    def _admin_del_secret(self, player, target_name: str):
        ip = self._ip(player)
        self._data.delete_secret(target_name)
        player.send_message(
            self._cfg.get_message("admin_secret_deleted").replace("{player}", target_name)
        )
        self._log.log(target_name, ip, "admin_delete_secret", f"by_{player.name}")

    def _admin_wipe(self, player, target_name: str):
        ip = self._ip(player)
        self._data.wipe_player(target_name)
        self._session.remove_authenticated(target_name)
        self._session.invalidate_session(target_name)
        player.send_message(
            self._cfg.get_message("admin_wipe_success").replace("{player}", target_name)
        )
        self._log.log(target_name, ip, "admin_wipe", f"by_{player.name}")
        target = self._get_online(target_name)
        if target:
            target.kick(self._cfg.get_message("admin_kick_wipe"))

    def show_logs_form(self, player, target_name: str):
        from endstone.form import ActionForm
        logs = self._log.format_for_display(target_name)
        if not logs:
            player.send_message(
                self._cfg.get_message("logs_no_data").replace("{player}", target_name)
            )
            return

        content_lines = []
        total = 0
        for line in logs:
            clean_len = len(line.replace("§a", "").replace("§c", "").replace("§7", "")
                            .replace("§b", "").replace("§e", ""))
            total += clean_len + 1
            if total > 1500:
                content_lines.append("§8... (показаны последние записи)")
                break
            content_lines.append(line)

        form = ActionForm(
            title=f"§bЛоги: {target_name}",
            content="\n".join(content_lines)
        )
        form.add_button("§7✔ Закрыть")
        form.add_button("§7← Назад", on_click=lambda p: self._show_player_actions(p, target_name))
        player.send_form(form)

    def _get_online(self, name: str):
        try:
            return self._plugin.server.get_player(name)
        except Exception:
            return None
