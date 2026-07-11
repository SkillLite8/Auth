import customtkinter as ctk
import threading
import time
import ctypes
from ctypes import wintypes
import sys

try:
    import keyboard
except ImportError:
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
    def __init__(self, update_ui_callback):
        self.lock = threading.Lock()
        self.update_ui_callback = update_ui_callback
        self.clicking = False
        self.click_count = 0
        self.button = 'left'
        self.mode = 'switch'
        self.cps = 16
        self.limit_enabled = False
        self.limit_count = 500
        self.stop_event = threading.Event()
        self.trigger_event = threading.Event()
        self.thread = threading.Thread(target=self._run_clicker, daemon=True)
        self.thread.start()

    def set_clicking(self, state):
        with self.lock:
            if state:
                if self.limit_enabled and self.click_count >= self.limit_count:
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
            self.update_ui_callback(0)

    def update_config(self, button, mode, cps, limit_enabled, limit_count):
        with self.lock:
            self.button = button.lower()
            self.mode = mode.lower()
            self.cps = max(1, min(cps, 1000))
            self.limit_enabled = limit_enabled
            self.limit_count = limit_count

    def _run_clicker(self):
        last_ui_update = time.perf_counter()
        while not self.stop_event.is_set():
            self.trigger_event.wait(timeout=0.1)
            if not self.clicking:
                continue
            with self.lock:
                current_button = self.button
                current_cps = self.cps
                limit_on = self.limit_enabled
                limit_max = self.limit_count
            start_time = time.perf_counter()
            send_mouse_event('down', current_button)
            time.sleep(0.015)
            send_mouse_event('up', current_button)
            with self.lock:
                self.click_count += 1
                current_count = self.click_count
                if limit_on and self.click_count >= limit_max:
                    self.clicking = False
                    self.trigger_event.clear()
            now = time.perf_counter()
            if now - last_ui_update > 0.1 or not self.clicking:
                self.update_ui_callback(current_count)
                last_ui_update = now
            delay = 1.0 / current_cps
            while time.perf_counter() - start_time < delay:
                time.sleep(0.001)

ctk.set_appearance_mode("dark")

class AutoClickerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Auto Clicker")
        self.geometry("900x550")
        self.resizable(False, False)
        self.configure(fg_color="#121317")
        self.COLOR_BG = "#121317"
        self.COLOR_PANEL = "#1A1C20"
        self.COLOR_RED = "#D32F2F"
        self.COLOR_RED_HOVER = "#B71C1C"
        self.COLOR_BTN_DARK = "#23252A"
        self.hotkey = 'r'
        self.listening_for_key = False
        self.clicker = ClickerCore(self.update_counter_ui)
        self.hk_hook_press = None
        self.hk_hook_release = None
        self.build_ui()
        self.setup_hotkey()

    def build_ui(self):
        self.sidebar = ctk.CTkFrame(self, width=200, fg_color="#17191D", corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        logo_lbl = ctk.CTkLabel(self.sidebar, text="🖱", font=("Segoe UI", 50), text_color=self.COLOR_RED)
        logo_lbl.pack(pady=(30, 0))
        title_lbl = ctk.CTkLabel(self.sidebar, text="Auto Clicker", font=("Segoe UI", 18, "bold"))
        title_lbl.pack(pady=(0, 30))
        btn_ac = ctk.CTkButton(self.sidebar, text="  Auto Clicker", fg_color="#1A1C20", hover_color="#23252A",
                               anchor="w", font=("Segoe UI", 13), border_width=2, border_color=self.COLOR_RED)
        btn_ac.pack(fill="x", padx=10, pady=5)
        btn_upd = ctk.CTkButton(self.sidebar, text="  Updates", fg_color="transparent", hover_color="#23252A", anchor="w", font=("Segoe UI", 13))
        btn_upd.pack(fill="x", padx=10, pady=5)
        btn_reset = ctk.CTkButton(self.sidebar, text="RESET ALL", fg_color="transparent", hover_color="#23252A",
                                  border_width=1, border_color="#333", text_color="#AAA", command=self.reset_all)
        btn_reset.pack(side="bottom", pady=20, padx=20, fill="x")
        self.main_area = ctk.CTkFrame(self, fg_color=self.COLOR_BG, corner_radius=0)
        self.main_area.pack(side="right", fill="both", expand=True, padx=20, pady=20)
        top_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        top_frame.pack(fill="x", pady=(0, 15))
        self.btn_hotkey = ctk.CTkButton(top_frame, text=self.hotkey.upper(), fg_color=self.COLOR_RED, hover_color=self.COLOR_RED_HOVER,
                                        font=("Segoe UI", 18, "bold"), width=150, height=45, corner_radius=6, command=self.start_listen_hotkey)
        self.btn_hotkey.pack(side="left", padx=(0, 10))
        ctk.CTkButton(top_frame, text="Choose Button", fg_color=self.COLOR_BTN_DARK, hover_color="#333", height=45).pack(side="left", padx=10)
        ctk.CTkButton(top_frame, text="Choose Apps", fg_color=self.COLOR_BTN_DARK, hover_color="#333", height=45).pack(side="left", padx=10)
        self.click_type_var = ctk.StringVar(value="Left")
        self.mode_var = ctk.StringVar(value="Switch")
        self.row_click_type = self.create_setting_row("Mouse Click Type")
        self.create_radio_group(self.row_click_type, ["Left", "Middle", "Right"], self.click_type_var)
        self.row_mode = self.create_setting_row("Activation Mode")
        self.create_radio_group(self.row_mode, ["Hold", "Switch"], self.mode_var)
        self.row_rate = self.create_setting_row("Click Rate (CPS)")
        self.cb_variation = ctk.CTkCheckBox(self.row_rate, text="Variation", fg_color=self.COLOR_RED, hover_color=self.COLOR_RED_HOVER)
        self.cb_variation.pack(side="left", padx=20)
        self.cps_entry = ctk.CTkEntry(self.row_rate, width=80, justify="center", font=("Segoe UI", 14), fg_color=self.COLOR_BG, border_color="#333")
        self.cps_entry.insert(0, "16")
        self.cps_entry.pack(side="right", padx=15)
        self.cps_entry.bind("<KeyRelease>", self.sync_settings)
        self.row_limit = self.create_setting_row("Click Limitation")
        self.limit_var = ctk.BooleanVar(value=True)
        self.cb_limit = ctk.CTkCheckBox(self.row_limit, text="Active", variable=self.limit_var, fg_color=self.COLOR_RED,
                                        hover_color=self.COLOR_RED_HOVER, command=self.sync_settings)
        self.cb_limit.pack(side="left", padx=20)
        self.limit_entry = ctk.CTkEntry(self.row_limit, width=80, justify="center", font=("Segoe UI", 14), fg_color=self.COLOR_BG, border_color="#333")
        self.limit_entry.insert(0, "500")
        self.limit_entry.pack(side="right", padx=15)
        self.limit_entry.bind("<KeyRelease>", self.sync_settings)
        self.row_current = self.create_setting_row("Currently")
        self.lbl_current = ctk.CTkLabel(self.row_current, text="0", font=("Segoe UI", 18, "bold"), text_color=self.COLOR_RED)
        self.lbl_current.pack(side="right", padx=30)
        self.sync_settings()

    def create_setting_row(self, title):
        frame = ctk.CTkFrame(self.main_area, fg_color=self.COLOR_PANEL, height=60, corner_radius=6)
        frame.pack(fill="x", pady=6)
        frame.pack_propagate(False)
        ctk.CTkLabel(frame, text=title, font=("Segoe UI", 13)).pack(side="left", padx=20)
        return frame

    def create_radio_group(self, parent, options, variable):
        for opt in reversed(options):
            btn = ctk.CTkButton(parent, text=opt, fg_color=self.COLOR_BTN_DARK, hover_color="#333",
                                width=90, command=lambda o=opt: self.select_radio(variable, o, parent))
            btn.pack(side="right", padx=5)
            if opt == variable.get():
                btn.configure(fg_color=self.COLOR_RED, hover_color=self.COLOR_RED_HOVER)

    def select_radio(self, variable, value, parent_frame):
        variable.set(value)
        for widget in parent_frame.winfo_children():
            if isinstance(widget, ctk.CTkButton):
                if widget.cget("text") == value:
                    widget.configure(fg_color=self.COLOR_RED, hover_color=self.COLOR_RED_HOVER)
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
            limit_count=limit
        )

    def update_counter_ui(self, count):
        self.after(0, lambda: self.lbl_current.configure(text=str(count)))

    def reset_all(self):
        self.clicker.reset()
        self.select_radio(self.click_type_var, "Left", self.row_click_type)
        self.select_radio(self.mode_var, "Switch", self.row_mode)
        self.cps_entry.delete(0, 'end')
        self.cps_entry.insert(0, "16")
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
        self.btn_hotkey.configure(text="PRESS KEY...")
        threading.Thread(target=self._capture_key, daemon=True).start()

    def _capture_key(self):
        event = keyboard.read_event(suppress=True)
        if event.event_type == keyboard.KEY_DOWN:
            self.after(0, self._apply_key, event.name)

    def _apply_key(self, new_key):
        self.hotkey = new_key
        self.btn_hotkey.configure(text=new_key.upper())
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
