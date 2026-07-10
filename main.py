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

# ==================== Windows API SendInput ====================
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

def send_mouse_click(button='left'):
    flags_map = {
        'left':   (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        'middle': (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
        'right':  (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
    }
    if button not in flags_map:
        return
    down, up = flags_map[button]
    inputs = (INPUT * 2)()
    
    for i, flag in enumerate((down, up)):
        inputs[i].type = INPUT_MOUSE
        inputs[i]._input.mi = MOUSEINPUT(0, 0, 0, flag, 0, None)
        
    ctypes.windll.user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))


# ==================== ЛОГИКА КЛИКЕРА (СЕРВИС) ====================
class ClickerCore:
    def __init__(self, ui_update_callback, state_change_callback):
        self.lock = threading.Lock()
        self.ui_callback = ui_update_callback
        self.state_callback = state_change_callback
        
        # Состояние
        self.clicking = False
        self.click_count = 0
        self.limit_reached = False
        
        # Настройки
        self.button = 'left'
        self.limit_enabled = False
        self.limit_count = 500
        self.interval = 0.0625  # 16 CPS
        
        # Управление потоком
        self.stop_event = threading.Event()
        self.trigger_event = threading.Event() # Решает проблему Busy Wait
        
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def toggle(self):
        with self.lock:
            if self.clicking:
                self.clicking = False
                self.trigger_event.clear()
            else:
                if self.limit_enabled and self.click_count >= self.limit_count:
                    return False, "Лимит достигнут. Сбросьте счётчик."
                self.clicking = True
                self.limit_reached = False
                self.trigger_event.set()
            return True, self.clicking

    def update_config(self, button, limit_enabled, limit_count):
        with self.lock:
            self.button = button.lower()
            self.limit_enabled = limit_enabled
            self.limit_count = limit_count

    def reset_counter(self):
        with self.lock:
            self.click_count = 0
            self.limit_reached = False
            self.clicking = False
            self.trigger_event.clear()

    def _run(self):
        while not self.stop_event.is_set():
            # Если не кликаем, поток спит мертвым сном, не нагружая CPU
            self.trigger_event.wait(timeout=0.5) 
            
            with self.lock:
                if not self.clicking or self.limit_reached:
                    continue
                
                if self.limit_enabled and self.click_count >= self.limit_count:
                    self.limit_reached = True
                    self.clicking = False
                    self.trigger_event.clear()
                    self.state_callback(False, msg="Лимит достигнут. Сбросьте счётчик.")
                    continue
                
                self.click_count += 1
                current_count = self.click_count
                current_button = self.button

            # Выполняем клик вне блокировки lock
            send_mouse_click(current_button)
            self.ui_callback(current_count)
            
            time.sleep(self.interval)


# ==================== ИНТЕРФЕЙС ПРИЛОЖЕНИЯ ====================
class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Clicker Pro")
        self.root.geometry("380x580")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Переменные управления хоткеями
        self.current_hotkey = 'r'
        self.hotkey_hook = None
        self.listening_for_hotkey = False

        # Инициализация ядра кликера
        self.clicker = ClickerCore(
            ui_update_callback=self.async_update_counter,
            state_change_callback=self.async_state_change
        )

        self.create_widgets()
        self.setup_hotkey_listener()
        self.check_admin_rights()

    def create_widgets(self):
        # Верхнее меню
        menu_frame = ttk.Frame(self.root)
        menu_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(menu_frame, text="Auto Clicker", width=12).pack(side="left", padx=2)
        ttk.Button(menu_frame, text="Reset All", width=10, command=self.reset_all).pack(side="left", padx=2)

        # Горячая клавиша
        hotkey_frame = ttk.Frame(self.root)
        hotkey_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(hotkey_frame, text="Hotkey:").pack(side="left")
        
        self.hotkey_var = tk.StringVar(value=self.current_hotkey.upper())
        self.hotkey_entry = ttk.Entry(hotkey_frame, textvariable=self.hotkey_var, width=15, state="readonly")
        self.hotkey_entry.pack(side="left", padx=5)
        
        self.change_hk_btn = ttk.Button(hotkey_frame, text="Change", command=self.start_listening_hotkey)
        self.change_hk_btn.pack(side="left", padx=5)

        # Настройки
        main_frame = ttk.LabelFrame(self.root, text="Configuration", padding=10)
        main_frame.pack(fill="x", padx=10, pady=5)

        # Тип клика
        ttk.Label(main_frame, text="Mouse Button").pack(anchor="w", pady=(5,0))
        self.click_type_var = tk.StringVar(value="Left")
        type_frame = ttk.Frame(main_frame)
        type_frame.pack(fill="x", pady=2)
        for btn in ["Left", "Middle", "Right"]:
            ttk.Radiobutton(type_frame, text=btn, variable=self.click_type_var,
                            value=btn, command=self.sync_settings_to_core).pack(side="left", padx=5)

        # Ограничения
        ttk.Label(main_frame, text="Click Limitation").pack(anchor="w", pady=(10,0))
        self.limit_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(main_frame, text="Enable Limit",
                        variable=self.limit_enabled_var, command=self.sync_settings_to_core).pack(anchor="w")
        
        limit_frame = ttk.Frame(main_frame)
        limit_frame.pack(fill="x", pady=5)
        ttk.Label(limit_frame, text="Max Clicks:").pack(side="left")
        
        # Валидация ввода (только цифры)
        vcmd = (self.root.register(self.validate_number), '%P')
        self.limit_entry = ttk.Entry(limit_frame, width=10, validate="key", validatecommand=vcmd)
        self.limit_entry.insert(0, "500")
        self.limit_entry.pack(side="left", padx=5)
        self.limit_entry.bind("<KeyRelease>", lambda e: self.sync_settings_to_core())

        # Мониторинг кликов
        ttk.Label(main_frame, text="Progress").pack(anchor="w", pady=(10,0))
        self.current_label = ttk.Label(main_frame, text="0", font=("Consolas", 20, "bold"))
        self.current_label.pack(anchor="w", pady=2)

        # Главная управляющая кнопка
        self.start_stop_btn = ttk.Button(self.root, text="Start", command=self.on_toggle_action, width=20)
        self.start_stop_btn.pack(pady=20)

        self.sync_settings_to_core()

    def validate_number(self, text):
        return text.isdigit() or text == ""

    def sync_settings_to_core(self):
        try:
            val = self.limit_entry.get()
            limit_count = int(val) if val else 500
        except ValueError:
            limit_count = 500
        
        self.clicker.update_config(
            button=self.click_type_var.get(),
            limit_enabled=self.limit_enabled_var.get(),
            limit_count=limit_count
        )

    def on_toggle_action(self):
        success, result = self.clicker.toggle()
        if not success:
            messagebox.showwarning("Внимание", result)
            return
        self.update_btn_ui(result)

    def update_btn_ui(self, is_clicking):
        self.start_stop_btn.config(text="Stop" if is_clicking else "Start")

    def async_update_counter(self, count):
        if self.root.winfo_exists():
            self.root.after(0, lambda: self.current_label.config(text=str(count)))

    def async_state_change(self, is_clicking, msg=None):
        if self.root.winfo_exists():
            self.root.after(0, lambda: self.update_btn_ui(is_clicking))
            if msg:
                self.root.after(0, lambda: messagebox.showwarning("Инфо", msg))

    # ==================== БЕЗОПАСНЫЙ ХОТКЕЙ ====================
    def setup_hotkey_listener(self):
        if self.hotkey_hook:
            keyboard.unhook(self.hotkey_hook)
        # Suppress=False позволяет клавише работать и в системе
        self.hotkey_hook = keyboard.on_press_key(self.current_hotkey, lambda e: self.on_hotkey_pressed(), suppress=False)

    def on_hotkey_pressed(self):
        if self.listening_for_hotkey:
            return
        self.on_toggle_action()

    def start_listening_hotkey(self):
        if self.listening_for_hotkey:
            return
        self.listening_for_hotkey = True
        self.change_hk_btn.config(state="disabled")
        self.hotkey_var.set("[Нажмите клавишу...]")
        
        # Запускаем чтение клавиши в отдельном потоке, чтобы не вешать GUI
        threading.Thread(target=self._capture_next_key, daemon=True).start()

    def _capture_next_key(self):
        # Безопасный метод перехвата одной клавиши без утечек памяти
        event = keyboard.read_event(suppress=True)
        if event.event_type == keyboard.KEY_DOWN:
            new_key = event.name
            
            # Обновляем хоткей через безопасный UI-поток
            self.root.after(0, lambda: self.finalize_new_hotkey(new_key))

    def finalize_new_hotkey(self, new_key):
        self.current_hotkey = new_key
        self.hotkey_var.set(new_key.upper())
        self.setup_hotkey_listener()
        self.listening_for_hotkey = False
        self.change_hk_btn.config(state="normal")

    def reset_all(self):
        self.clicker.reset_counter()
        self.current_label.config(text="0")
        self.update_btn_ui(False)
        messagebox.showinfo("Сброс", "Все счетчики сброшены.")

    def check_admin_rights(self):
        try:
            if not ctypes.windll.shell32.IsUserAnAdmin():
                messagebox.showwarning("Права доступа", "Рекомендуется запустить от имени Администратора для работы в играх.")
        except:
            pass

    def on_close(self):
        self.clicker.stop_event.set()
        self.clicker.trigger_event.set() # Просыпаемся для закрытия
        if self.hotkey_hook:
            keyboard.unhook(self.hotkey_hook)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.mainloop()
