import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import ctypes
from ctypes import wintypes
import sys

try:
    import keyboard
except ImportError:
    messagebox.showerror("Ошибка", "Установите библиотеку keyboard: pip install keyboard")
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

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", INPUT_UNION)
    ]

def send_mouse_event(flag, button='left'):
    btn_map = {
        'left': (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        'middle': (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
        'right': (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
    }
    down, up = btn_map[button]
    actual_flag = down if flag == 'down' else up

    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp._input.mi = MOUSEINPUT(0, 0, 0, actual_flag, 0, None)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

class ClickerCore:
    def __init__(self, ui_update_callback, state_change_callback):
        self.lock = threading.Lock()
        self.ui_callback = ui_update_callback
        self.state_callback = state_change_callback
        
        self.clicking = False
        self.click_count = 0
        self.limit_reached = False
        
        self.button = 'left'
        self.mode = 'switch'
        self.limit_enabled = False
        self.limit_count = 500
        self.cps = 15
        
        self.stop_event = threading.Event()
        self.trigger_event = threading.Event()
        
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def set_clicking(self, state):
        with self.lock:
            if state:
                if self.limit_enabled and self.click_count >= self.limit_count:
                    self.clicking = False
                    self.trigger_event.clear()
                    return False
                self.clicking = True
                self.limit_reached = False
                self.trigger_event.set()
            else:
                self.clicking = False
                self.trigger_event.clear()
            self.state_callback(self.clicking)
            return True

    def toggle(self):
        with self.lock:
            new_state = not self.clicking
        return self.set_clicking(new_state)

    def update_config(self, button, mode, cps, limit_enabled, limit_count):
        with self.lock:
            self.button = button.lower()
            self.mode = mode.lower()
            self.cps = max(1, min(cps, 1000))
            self.limit_enabled = limit_enabled
            self.limit_count = limit_count
            
            if self.clicking and self.limit_enabled and self.click_count >= self.limit_count:
                self.clicking = False
                self.trigger_event.clear()
                self.state_callback(self.clicking)

    def reset_counter(self):
        with self.lock:
            self.click_count = 0
            self.limit_reached = False
            self.clicking = False
            self.trigger_event.clear()
            self.state_callback(self.clicking)
            self.ui_callback(self.click_count)

    def _run(self):
        while not self.stop_event.is_set():
            self.trigger_event.wait(timeout=0.2)
            
            with self.lock:
                if not self.clicking or self.limit_reached:
                    continue
                
                if self.limit_enabled and self.click_count >= self.limit_count:
                    self.limit_reached = True
                    self.clicking = False
                    self.trigger_event.clear()
                    self.state_callback(False)
                    continue
                
                self.click_count += 1
                current_count = self.click_count
                current_button = self.button
                current_cps = self.cps

            send_mouse_event('down', current_button)
            time.sleep(0.018)
            send_mouse_event('up', current_button)
            
            self.ui_callback(current_count)
            
            total_delay = 1.0 / current_cps
            remaining_delay = max(0.001, total_delay - 0.018)
            time.sleep(remaining_delay)

class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Clicker")
        self.root.geometry("850x450")
        self.root.resizable(False, False)
        self.root.configure(bg="#121212")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.COLOR_BG = "#121212"
        self.COLOR_SIDEBAR = "#1A1A1A"
        self.COLOR_ROW = "#222222"
        self.COLOR_ACTIVE = "#D32F2F"
        self.COLOR_INACTIVE = "#333333"
        self.COLOR_TEXT = "#FFFFFF"
        self.COLOR_HOVER = "#F44336"

        self.current_hotkey = 'r'
        self.listening_for_hotkey = False
        
        self.click_type_var = tk.StringVar(value="Left")
        self.mode_var = tk.StringVar(value="Switch")
        self.cps_var = tk.StringVar(value="15")
        self.limit_enabled_var = tk.BooleanVar(value=False)
        self.limit_count_var = tk.StringVar(value="500")

        self.cps_var.trace_add("write", self.sync_settings_trace)
        self.limit_count_var.trace_add("write", self.sync_settings_trace)

        self.clicker = ClickerCore(
            ui_update_callback=self.async_update_counter,
            state_change_callback=self.async_state_change
        )

        self.hotkey_hook_press = None
        self.hotkey_hook_release = None

        self.create_widgets()
        self.setup_hotkey_listener()
        self.check_admin_rights()

    def create_widgets(self):
        sidebar = tk.Frame(self.root, bg=self.COLOR_SIDEBAR, width=180)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        logo_lbl = tk.Label(sidebar, text="🖱", font=("Segoe UI", 48), bg=self.COLOR_SIDEBAR, fg=self.COLOR_ACTIVE)
        logo_lbl.pack(pady=(20, 0))
        
        title_lbl = tk.Label(sidebar, text="Auto Clicker", font=("Segoe UI", 16, "bold"), bg=self.COLOR_SIDEBAR, fg=self.COLOR_TEXT)
        title_lbl.pack(pady=(0, 30))

        menu_buttons = ["Auto Clicker", "Updates", "FAQ/Help"]
        for i, btn_txt in enumerate(menu_buttons):
            bg_color = self.COLOR_ROW if i == 0 else self.COLOR_SIDEBAR
            b = tk.Label(sidebar, text=btn_txt, bg=bg_color, fg=self.COLOR_TEXT, 
                         font=("Segoe UI", 12), anchor="w", padx=20, pady=10)
            b.pack(fill="x", pady=2)

        reset_btn = tk.Button(sidebar, text="Reset All", bg=self.COLOR_INACTIVE, fg=self.COLOR_TEXT, bd=0,
                              activebackground=self.COLOR_ACTIVE, activeforeground=self.COLOR_TEXT, 
                              font=("Segoe UI", 12), command=self.reset_all, pady=8)
        reset_btn.pack(fill="x", side="bottom", pady=20, padx=20)

        main_container = tk.Frame(self.root, bg=self.COLOR_BG)
        main_container.pack(side="right", fill="both", expand=True)

        top_frame = tk.Frame(main_container, bg=self.COLOR_BG, height=60)
        top_frame.pack(fill="x", padx=20, pady=(20, 10))
        top_frame.pack_propagate(False)

        self.hk_btn = tk.Button(top_frame, text=f"Hotkey: {self.current_hotkey.upper()}", 
                                bg=self.COLOR_ACTIVE, fg=self.COLOR_TEXT, font=("Segoe UI", 12, "bold"),
                                bd=0, activebackground=self.COLOR_HOVER, activeforeground=self.COLOR_TEXT,
                                command=self.start_listening_hotkey, width=15)
        self.hk_btn.pack(side="left", fill="y", padx=(0, 10))
        
        status_lbl = tk.Label(top_frame, text="Status:", bg=self.COLOR_BG, fg=self.COLOR_TEXT, font=("Segoe UI", 12))
        status_lbl.pack(side="left", padx=10)
        
        self.status_val_lbl = tk.Label(top_frame, text="Stopped", bg=self.COLOR_BG, fg=self.COLOR_INACTIVE, font=("Segoe UI", 12, "bold"))
        self.status_val_lbl.pack(side="left")

        settings_frame = tk.Frame(main_container, bg=self.COLOR_BG)
        settings_frame.pack(fill="both", expand=True, padx=20)

        self.create_row(settings_frame, "Mouse Click Type", ["Left", "Middle", "Right"], self.click_type_var)
        self.create_row(settings_frame, "Activation Mode", ["Hold", "Switch"], self.mode_var)
        
        rate_frame = self.create_base_row(settings_frame, "Click Rate (CPS)")
        vcmd = (self.root.register(self.validate_number), '%P')
        tk.Entry(rate_frame, textvariable=self.cps_var, width=10, bg=self.COLOR_INACTIVE, fg=self.COLOR_TEXT, 
                 font=("Segoe UI", 11), bd=0, justify="center", validate="key", validatecommand=vcmd).pack(side="right", ipady=4, padx=5)

        limit_frame = self.create_base_row(settings_frame, "Click Limitation")
        tk.Entry(limit_frame, textvariable=self.limit_count_var, width=10, bg=self.COLOR_INACTIVE, fg=self.COLOR_TEXT, 
                 font=("Segoe UI", 11), bd=0, justify="center", validate="key", validatecommand=vcmd).pack(side="right", ipady=4, padx=5)
        
        self.limit_cb = tk.Button(limit_frame, text="Inactive", bg=self.COLOR_INACTIVE, fg=self.COLOR_TEXT,
                                  font=("Segoe UI", 10), bd=0, command=self.toggle_limit, width=10)
        self.limit_cb.pack(side="right", padx=10, ipady=3)

        current_frame = self.create_base_row(settings_frame, "Currently")
        self.current_label = tk.Label(current_frame, text="0", bg=self.COLOR_ROW, fg=self.COLOR_ACTIVE, font=("Segoe UI", 14, "bold"))
        self.current_label.pack(side="right", padx=15)
        
        self.sync_settings()

    def create_base_row(self, parent, label_text):
        row = tk.Frame(parent, bg=self.COLOR_ROW, height=50)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)
        tk.Label(row, text=label_text, bg=self.COLOR_ROW, fg=self.COLOR_TEXT, font=("Segoe UI", 11)).pack(side="left", padx=20)
        return row

    def create_row(self, parent, label_text, options, variable):
        row = self.create_base_row(parent, label_text)
        buttons = []
        for opt in reversed(options):
            btn = tk.Button(row, text=opt, font=("Segoe UI", 10), bd=0, width=10)
            btn.config(command=lambda o=opt, b=btn: self.select_option(variable, o, buttons))
            btn.pack(side="right", padx=5, pady=8, ipady=2)
            buttons.append((opt, btn))
            
            if opt == variable.get():
                btn.config(bg=self.COLOR_ACTIVE, fg=self.COLOR_TEXT)
            else:
                btn.config(bg=self.COLOR_INACTIVE, fg=self.COLOR_TEXT)
        return row

    def select_option(self, variable, value, buttons):
        variable.set(value)
        for opt, btn in buttons:
            if opt == value:
                btn.config(bg=self.COLOR_ACTIVE, activebackground=self.COLOR_HOVER)
            else:
                btn.config(bg=self.COLOR_INACTIVE, activebackground=self.COLOR_INACTIVE)
        self.sync_settings()

    def toggle_limit(self):
        current = self.limit_enabled_var.get()
        self.limit_enabled_var.set(not current)
        if not current:
            self.limit_cb.config(text="Active", bg=self.COLOR_ACTIVE)
        else:
            self.limit_cb.config(text="Inactive", bg=self.COLOR_INACTIVE)
        self.sync_settings()

    def validate_number(self, text):
        return text.isdigit() or text == ""

    def sync_settings_trace(self, *args):
        self.sync_settings()

    def sync_settings(self):
        try:
            cps_val = int(self.cps_var.get()) if self.cps_var.get() else 15
        except ValueError:
            cps_val = 15

        try:
            limit_val = int(self.limit_count_var.get()) if self.limit_count_var.get() else 500
        except ValueError:
            limit_val = 500
            
        self.clicker.update_config(
            button=self.click_type_var.get(),
            mode=self.mode_var.get(),
            cps=cps_val,
            limit_enabled=self.limit_enabled_var.get(),
            limit_count=limit_val
        )

    def async_update_counter(self, count):
        if self.root.winfo_exists():
            self.root.after(0, lambda: self.current_label.config(text=str(count)))

    def async_state_change(self, is_clicking):
        if self.root.winfo_exists():
            self.root.after(0, lambda: self.update_status_ui(is_clicking))

    def update_status_ui(self, is_clicking):
        if is_clicking:
            self.status_val_lbl.config(text="Running", fg=self.COLOR_ACTIVE)
        else:
            self.status_val_lbl.config(text="Stopped", fg=self.COLOR_INACTIVE)

    def setup_hotkey_listener(self):
        self.remove_hotkey_hooks()
        if self.mode_var.get() == "Hold":
            self.hotkey_hook_press = keyboard.on_press_key(self.current_hotkey, self.on_hotkey_press, suppress=False)
            self.hotkey_hook_release = keyboard.on_release_key(self.current_hotkey, self.on_hotkey_release, suppress=False)
        else:
            self.hotkey_hook_press = keyboard.on_press_key(self.current_hotkey, self.on_hotkey_press, suppress=False)

    def remove_hotkey_hooks(self):
        if self.hotkey_hook_press:
            keyboard.unhook(self.hotkey_hook_press)
            self.hotkey_hook_press = None
        if self.hotkey_hook_release:
            keyboard.unhook(self.hotkey_hook_release)
            self.hotkey_hook_release = None

    def on_hotkey_press(self, event=None):
        if self.listening_for_hotkey:
            return
        if self.mode_var.get() == "Hold":
            if not self.clicker.clicking:
                self.clicker.set_clicking(True)
        else:
            self.clicker.toggle()

    def on_hotkey_release(self, event=None):
        if self.listening_for_hotkey:
            return
        if self.mode_var.get() == "Hold":
            self.clicker.set_clicking(False)

    def start_listening_hotkey(self):
        if self.listening_for_hotkey:
            return
        self.listening_for_hotkey = True
        self.remove_hotkey_hooks()
        self.hk_btn.config(text="Press Key...")
        threading.Thread(target=self._capture_next_key, daemon=True).start()

    def _capture_next_key(self):
        event = keyboard.read_event(suppress=True)
        if event.event_type == keyboard.KEY_DOWN:
            new_key = event.name
            self.root.after(0, lambda: self.finalize_new_hotkey(new_key))

    def finalize_new_hotkey(self, new_key):
        self.current_hotkey = new_key
        self.hk_btn.config(text=f"Hotkey: {new_key.upper()}")
        self.listening_for_hotkey = False
        self.setup_hotkey_listener()

    def reset_all(self):
        self.clicker.reset_counter()
        self.click_type_var.set("Left")
        self.mode_var.set("Switch")
        self.cps_var.set("15")
        self.limit_enabled_var.set(False)
        self.limit_cb.config(text="Inactive", bg=self.COLOR_INACTIVE)
        self.limit_count_var.set("500")
        self.sync_settings()
        self.setup_hotkey_listener()
        
        for child in self.root.winfo_children():
            self.update_option_colors(child)

    def update_option_colors(self, widget):
        if isinstance(widget, tk.Button) and widget.cget('text') in ["Left", "Middle", "Right", "Hold", "Switch"]:
            if widget.cget('text') in [self.click_type_var.get(), self.mode_var.get()]:
                widget.config(bg=self.COLOR_ACTIVE)
            else:
                widget.config(bg=self.COLOR_INACTIVE)
        for child in widget.winfo_children():
            self.update_option_colors(child)

    def check_admin_rights(self):
        try:
            if not ctypes.windll.shell32.IsUserAnAdmin():
                messagebox.showwarning(
                    "Admin Rights", 
                    "Run as Administrator is recommended for games."
                )
        except:
            pass

    def on_close(self):
        self.clicker.stop_event.set()
        self.clicker.trigger_event.set()
        self.remove_hotkey_hooks()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.mainloop()
