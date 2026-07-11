import customtkinter as ctk
import threading
import time
import ctypes
from ctypes import wintypes
import sys

try:
    import keyboard
except ImportError:
    print("Пожалуйста, установите модуль keyboard: pip install keyboard")
    sys.exit(1)

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP   = 0x0040
MOUSEEVENTF_RIGHTDOWN  = 0x0008
MOUSEEVENTF_RIGHTUP    = 0x0010

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p)
    ]

class INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _fields_ = [("type", wintypes.DWORD), ("_input", _INPUT_UNION)]

def send_mouse_event(flag, button='left'):
    btn_map = {
        'left': (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        'middle': (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
        'right': (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
    }
    down, up = btn_map.get(button, (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP))
    actual_flag = down if flag == 'down' else up
    inp = INPUT(INPUT_MOUSE, INPUT._INPUT_UNION(mi=MOUSEINPUT(0, 0, 0, actual_flag, 0, None)))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

class ClickerCore:
    def __init__(self):
        self.lock = threading.Lock()
        self.clicking = False
        self.click_count = 0
        self.button = 'left'
        self.mode = 'switch'
        self.cps = 16
        self.limit_enabled = False
        self.limit_count = 500
        self.unlimited = False
        self.stop_event = threading.Event()
        self.trigger_event = threading.Event()
        self.thread = threading.Thread(target=self._run_clicker, daemon=True)
        self.thread.start()

    def set_clicking(self, state):
        with self.lock:
            if state:
                if self.limit_enabled and not self.unlimited and self.click_count >= self.limit_count:
                    self.clicking = False
                    self.trigger_event.clear()
                    return
                self.clicking = True
                self.trigger_event.set()
            else:
                self.clicking = False
                self.trigger_event.clear()

    def toggle(self):
        with self.lock:
            new_state = not self.clicking
        self.set_clicking(new_state)

    def reset(self):
        with self.lock:
            self.click_count = 0
            self.clicking = False
            self.trigger_event.clear()

    def update_config(self, button, mode, cps, limit_enabled, limit_count, unlimited):
        with self.lock:
            self.button = button.lower()
            self.mode = mode.lower()
            self.cps = max(1, min(cps, 1000))
            self.limit_enabled = limit_enabled
            self.limit_count = limit_count
            self.unlimited = unlimited

    def _run_clicker(self):
        while not self.stop_event.is_set():
            self.trigger_event.wait(timeout=0.1)
            if not self.clicking:
                continue
            with self.lock:
                current_button = self.button
                current_cps = self.cps
                limit_on = self.limit_enabled
                limit_max = self.limit_count
                is_unlimited = self.unlimited
                
            start_time = time.perf_counter()
            send_mouse_event('down', current_button)
            time.sleep(0.015)
            send_mouse_event('up', current_button)
            
            with self.lock:
                self.click_count += 1
                if limit_on and not is_unlimited and self.click_count >= limit_max:
                    self.clicking = False
                    self.trigger_event.clear()

            delay = 1.0 / current_cps
            while time.perf_counter() - start_time < delay:
                time.sleep(0.001)

ctk.set_appearance_mode("dark")

class AutoClickerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Auto Clicker")
        self.geometry("980x620")
        self.resizable(False, False)
        
        # Цветовая палитра из дизайна
        self.COLOR_BG = "#0D0E12"        # Основной темный фон
        self.COLOR_PANEL = "#16181D"     # Фон блоков/строк
        self.COLOR_SIDEBAR = "#121318"   # Фон боковой панели
        self.COLOR_ACCENT = "#5C55E9"    # Сине-фиолетовый акцент
        self.COLOR_ACCENT_HOVER = "#4A44CC"
        self.COLOR_BTN_DARK = "#20232A"  # Темные неактивные кнопки
        
        self.configure(fg_color=self.COLOR_BG)
        
        self.hotkey = 'r'
        self.listening_for_key = False
        self.clicker = ClickerCore()
        
        self.hk_hook_press = None
        self.hk_hook_release = None
        
        self.build_ui()
        self.setup_hotkey()

    def build_ui(self):
        # САЙДБАР (Слева)
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color=self.COLOR_SIDEBAR, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        
        # Логотип
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(pady=(40, 30))
        ctk.CTkLabel(logo_frame, text="🖱", font=("Segoe UI", 48), text_color=self.COLOR_ACCENT).pack()
        
        title_frame = ctk.CTkFrame(logo_frame, fg_color="transparent")
        title_frame.pack(pady=(5, 0))
        ctk.CTkLabel(title_frame, text="Auto ", font=("Segoe UI", 20, "bold"), text_color="white").pack(side="left")
        ctk.CTkLabel(title_frame, text="Clicker", font=("Segoe UI", 20, "bold"), text_color=self.COLOR_ACCENT).pack(side="left")
        
        # Кнопки сайдбара
        self.create_sidebar_btn(" 🖰   Auto Clicker", active=True).pack(fill="x", padx=15, pady=5)
        self.create_sidebar_btn(" 📥   Updates").pack(fill="x", padx=15, pady=5)
        self.create_sidebar_btn(" 🔄   Reset All", command=self.reset_all).pack(fill="x", padx=15, pady=5)
        self.create_sidebar_btn(" ❓   FAQ / Help").pack(fill="x", padx=15, pady=5)
        
        # Кнопка Reset All внизу сайдбара
        btn_reset_bottom = ctk.CTkButton(self.sidebar, text="↻ Reset All", fg_color="transparent", hover_color=self.COLOR_BTN_DARK,
                                  border_width=1, border_color="#333", text_color="#AAA", height=40, command=self.reset_all)
        btn_reset_bottom.pack(side="bottom", pady=30, padx=20, fill="x")

        # ОСНОВНАЯ ОБЛАСТЬ (Справа)
        self.main_area = ctk.CTkFrame(self, fg_color=self.COLOR_BG, corner_radius=0)
        self.main_area.pack(side="right", fill="both", expand=True, padx=30, pady=30)
        
        # Верхний ряд кнопок
        top_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        top_frame.pack(fill="x", pady=(0, 20))
        
        # Дисплей горячей клавиши (Широкая кнопка)
        self.btn_hotkey_display = ctk.CTkButton(top_frame, text=self.hotkey.upper(), 
                                                fg_color=self.COLOR_ACCENT, hover_color=self.COLOR_ACCENT,
                                                font=("Segoe UI", 18, "bold"), height=60, corner_radius=6, state="disabled", text_color_disabled="white")
        self.btn_hotkey_display.pack(side="left", fill="x", expand=True, padx=(0, 15))
        
        # Кнопка "Choose Button" для изменения бинда
        btn_choose = ctk.CTkButton(top_frame, text="🖱 Choose Button", 
                                   fg_color=self.COLOR_PANEL, hover_color=self.COLOR_BTN_DARK, 
                                   font=("Segoe UI", 14), height=60, width=160, corner_radius=6, command=self.start_listen_hotkey)
        btn_choose.pack(side="left", padx=(0, 15))
        
        # Кнопка "Choose Apps"
        btn_apps = ctk.CTkButton(top_frame, text="⊞ Choose Apps", 
                                 fg_color=self.COLOR_PANEL, hover_color=self.COLOR_BTN_DARK, 
                                 font=("Segoe UI", 14), height=60, width=160, corner_radius=6)
        btn_apps.pack(side="left")

        # Настройки
        self.click_type_var = ctk.StringVar(value="Left")
        self.mode_var = ctk.StringVar(value="Switch")
        
        # 1. Mouse Click Type
        self.row_click_type = self.create_setting_row("Mouse Click Type")
        self.create_radio_group(self.row_click_type, ["Left", "Middle", "Right"], self.click_type_var)
        
        # 2. Activation Mode
        self.row_mode = self.create_setting_row("Activation Mode")
        self.create_radio_group(self.row_mode, ["Hold", "Switch"], self.mode_var)
        
        # 3. Click Rate (CPS)
        self.row_rate = self.create_setting_row("Click Rate (CPS)")
        
        self.cb_variation = ctk.CTkCheckBox(self.row_rate, text="Variation (Anti-Detection)", 
                                            fg_color=self.COLOR_ACCENT, hover_color=self.COLOR_ACCENT_HOVER, checkbox_height=20, checkbox_width=20)
        self.cb_variation.pack(side="left", padx=(20, 10))
        self.cb_variation.select()
        
        self.unlimited_var = ctk.BooleanVar(value=False)
        self.cb_unlimited = ctk.CTkCheckBox(self.row_rate, text="Unlimited", variable=self.unlimited_var,
                                            fg_color=self.COLOR_ACCENT, hover_color=self.COLOR_ACCENT_HOVER, checkbox_height=20, checkbox_width=20, command=self.sync_settings)
        self.cb_unlimited.pack(side="left", padx=10)
        
        self.cps_entry = ctk.CTkEntry(self.row_rate, width=100, justify="center", font=("Segoe UI", 16, "bold"), 
                                      fg_color=self.COLOR_BG, border_color="#333", height=38)
        self.cps_entry.insert(0, "16")
        self.cps_entry.pack(side="right", padx=15)
        self.cps_entry.bind("<KeyRelease>", self.sync_settings)
        
        # 4. Click Limitation
        self.row_limit = self.create_setting_row("Click Limitation")
        self.limit_var = ctk.BooleanVar(value=True)
        self.cb_limit = ctk.CTkCheckBox(self.row_limit, text="Active", variable=self.limit_var, 
                                        fg_color=self.COLOR_ACCENT, hover_color=self.COLOR_ACCENT_HOVER, checkbox_height=20, checkbox_width=20, command=self.sync_settings)
        self.cb_limit.pack(side="left", padx=20)
        
        self.limit_entry = ctk.CTkEntry(self.row_limit, width=100, justify="center", font=("Segoe UI", 16, "bold"), 
                                        fg_color=self.COLOR_BG, border_color="#333", height=38)
        self.limit_entry.insert(0, "500")
        self.limit_entry.pack(side="right", padx=15)
        self.limit_entry.bind("<KeyRelease>", self.sync_settings)
        
        self.sync_settings()

    def create_sidebar_btn(self, text, active=False, command=None):
        bg = self.COLOR_ACCENT if active else "transparent"
        hover = self.COLOR_ACCENT_HOVER if active else self.COLOR_BTN_DARK
        return ctk.CTkButton(self.sidebar, text=text, fg_color=bg, hover_color=hover,
                             anchor="w", font=("Segoe UI", 14), height=45, corner_radius=8, command=command)

    def create_setting_row(self, title):
        frame = ctk.CTkFrame(self.main_area, fg_color=self.COLOR_PANEL, height=75, corner_radius=8)
        frame.pack(fill="x", pady=8)
        frame.pack_propagate(False)
        ctk.CTkLabel(frame, text=title, font=("Segoe UI", 15, "bold")).pack(side="left", padx=20)
        return frame

    def create_radio_group(self, parent, options, variable):
        group = ctk.CTkFrame(parent, fg_color="transparent")
        group.pack(side="right", padx=15)
        for opt in options:
            btn = ctk.CTkButton(group, text=opt, fg_color=self.COLOR_BTN_DARK, hover_color="#333",
                                width=95, height=38, font=("Segoe UI", 14),
                                command=lambda o=opt: self.select_radio(variable, o, group))
            btn.pack(side="left", padx=3)
            if opt == variable.get():
                btn.configure(fg_color=self.COLOR_ACCENT, hover_color=self.COLOR_ACCENT_HOVER)

    def select_radio(self, variable, value, parent_frame):
        variable.set(value)
        for widget in parent_frame.winfo_children():
            if isinstance(widget, ctk.CTkButton):
                if widget.cget("text") == value:
                    widget.configure(fg_color=self.COLOR_ACCENT, hover_color=self.COLOR_ACCENT_HOVER)
                else:
                    widget.configure(fg_color=self.COLOR_BTN_DARK, hover_color="#333")
        self.sync_settings()
        self.setup_hotkey()

    def sync_settings(self, event=None):
        try:
            cps = int(self.cps_entry.get())
        except ValueError:
            cps = 16
        try:
            limit = int(self.limit_entry.get())
        except ValueError:
            limit = 500
            
        self.clicker.update_config(
            button=self.click_type_var.get(),
            mode=self.mode_var.get(),
            cps=cps,
            limit_enabled=self.limit_var.get(),
            limit_count=limit,
            unlimited=self.unlimited_var.get()
        )

    def reset_all(self):
        self.clicker.reset()
        self.select_radio(self.click_type_var, "Left", self.row_click_type.winfo_children()[1])
        self.select_radio(self.mode_var, "Switch", self.row_mode.winfo_children()[1])
        self.cps_entry.delete(0, 'end')
        self.cps_entry.insert(0, "16")
        self.cb_variation.select()
        self.unlimited_var.set(False)
        self.limit_var.set(True)
        self.limit_entry.delete(0, 'end')
        self.limit_entry.insert(0, "500")
        self.sync_settings()

    def setup_hotkey(self):
        if self.hk_hook_press: keyboard.unhook(self.hk_hook_press)
        if self.hk_hook_release: keyboard.unhook(self.hk_hook_release)
        self.hk_hook_press, self.hk_hook_release = None, None
        
        if self.mode_var.get() == "Hold":
            self.hk_hook_press = keyboard.on_press_key(self.hotkey, self.on_press, suppress=False)
            self.hk_hook_release = keyboard.on_release_key(self.hotkey, self.on_release, suppress=False)
        else:
            self.hk_hook_press = keyboard.on_press_key(self.hotkey, self.on_press, suppress=False)

    def on_press(self, e=None):
        if self.listening_for_key: return
        if self.mode_var.get() == "Hold":
            self.clicker.set_clicking(True)
        else:
            self.clicker.toggle()

    def on_release(self, e=None):
        if self.listening_for_key: return
        if self.mode_var.get() == "Hold":
            self.clicker.set_clicking(False)

    def start_listen_hotkey(self):
        if self.listening_for_key: return
        self.listening_for_key = True
        if self.hk_hook_press: keyboard.unhook(self.hk_hook_press)
        if self.hk_hook_release: keyboard.unhook(self.hk_hook_release)
        self.hk_hook_press, self.hk_hook_release = None, None
        
        self.btn_hotkey_display.configure(text="PRESS KEY...", text_color="white")
        threading.Thread(target=self._capture_key, daemon=True).start()

    def _capture_key(self):
        event = keyboard.read_event(suppress=True)
        if event.event_type == keyboard.KEY_DOWN:
            self.after(0, self._apply_key, event.name)

    def _apply_key(self, new_key):
        self.hotkey = new_key
        self.btn_hotkey_display.configure(text=new_key.upper())
        self.listening_for_key = False
        self.setup_hotkey()

    def on_close(self):
        self.clicker.stop_event.set()
        self.clicker.trigger_event.set()
        self.destroy()

if __name__ == "__main__":
    app = AutoClickerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
