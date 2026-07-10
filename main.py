import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import random
import sys
import ctypes
from ctypes import wintypes

# Проверка наличия библиотеки keyboard
try:
    import keyboard
except ImportError:
    messagebox.showerror(
        "Ошибка импорта",
        "Библиотека 'keyboard' не установлена.\nУстановите: pip install keyboard"
    )
    sys.exit(1)

# ==================== КОНСТАНТЫ И СТРУКТУРЫ ДЛЯ SENDINPUT ====================
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
        ("dwExtraInfo", ctypes.c_void_p)   # Исправлено: указатель заменён на void*
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", INPUT_UNION)
    ]

def send_mouse_click(button='left'):
    """
    Отправляет клик через SendInput (низкоуровневый API).
    Возвращает True при успехе, иначе False.
    """
    flags_map = {
        'left':   (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        'middle': (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
        'right':  (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
    }
    down_flag, up_flag = flags_map[button]
    inputs = []
    for flag in (down_flag, up_flag):
        mi = MOUSEINPUT(0, 0, 0, flag, 0, 0)   # dwExtraInfo = 0 (NULL)
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp._input.mi = mi
        inputs.append(inp)

    result = ctypes.windll.user32.SendInput(
        len(inputs),
        ctypes.byref(inputs[0]),
        ctypes.sizeof(INPUT)
    )
    return result == len(inputs)

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
clicking = False
click_count = 0
limit_reached = False
current_hotkey = 'f6'
stop_threads = False
app_running = True
lock = threading.RLock()   # рекурсивная блокировка для всех операций

settings = {
    'button': 'left',
    'mode': 'hold',
    'delay_min': 0.08,
    'delay_max': 0.12,
    'variation': True,
    'limit_enabled': False,
    'limit_count': 500,
    'current': 0
}

# ==================== ЛОГИКА КЛИКЕРА ====================
def perform_click():
    global click_count, limit_reached
    with lock:
        if settings['limit_enabled'] and click_count >= settings['limit_count']:
            limit_reached = True
            return
        click_count += 1
        settings['current'] = click_count
        button = settings['button']
    # Отправляем клик вне блокировки
    send_mouse_click(button)
    update_ui()

def get_delay():
    with lock:
        if settings['variation']:
            return random.uniform(settings['delay_min'], settings['delay_max'])
        return settings['delay_min']

def click_loop():
    global clicking, limit_reached, stop_threads
    while True:
        with lock:
            if not clicking or limit_reached or stop_threads:
                break
        perform_click()
        time.sleep(get_delay())

    # Выход из цикла – синхронизируем состояние
    with lock:
        if clicking:
            clicking = False
        if limit_reached and app_running:
            root.after(0, lambda: messagebox.showinfo(
                "Лимит",
                f"Достигнут лимит кликов: {settings['limit_count']}"
            ))

# ==================== УПРАВЛЕНИЕ ====================
def start_clicking():
    global clicking, click_count, limit_reached
    with lock:
        if clicking:
            return
        if settings['limit_enabled'] and click_count >= settings['limit_count']:
            if app_running:
                root.after(0, lambda: messagebox.showwarning(
                    "Лимит",
                    "Лимит кликов уже достигнут. Сбросьте счётчик."
                ))
            return
        clicking = True
        limit_reached = False
    threading.Thread(target=click_loop, daemon=True).start()
    update_ui()

def stop_clicking():
    global clicking
    with lock:
        clicking = False
    update_ui()

def toggle_clicking():
    with lock:
        if clicking:
            stop_clicking()
        else:
            start_clicking()

def reset_click_counter():
    global click_count, limit_reached
    with lock:
        click_count = 0
        limit_reached = False
        settings['current'] = 0
    update_ui()

# ==================== ОБНОВЛЕНИЕ UI ====================
def update_ui():
    def _update():
        if not app_running:
            return
        with lock:
            try:
                current_label.config(text=str(click_count))
                start_stop_btn.config(text="Stop" if clicking else "Start")
            except (tk.TclError, AttributeError):
                pass   # окно уже уничтожено
    root.after(0, _update)

# ==================== ГЛАВНОЕ ОКНО ====================
class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Clicker")
        self.root.geometry("380x600")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.hotkey_var = tk.StringVar(value="F6")
        self.listening_for_hotkey = False
        self.temp_hook = None
        self.hook_press = None
        self.hook_release = None

        self.create_widgets()
        self.setup_hotkey()

        # Проверка прав администратора (предупреждение)
        try:
            import ctypes
            if not ctypes.windll.shell32.IsUserAnAdmin():
                messagebox.showwarning(
                    "Права администратора",
                    "Для стабильной работы с играми рекомендуется запускать программу от имени администратора."
                )
        except:
            pass

    def create_widgets(self):
        # Верхнее меню
        menu_frame = ttk.Frame(self.root)
        menu_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(menu_frame, text="Auto Clicker", width=12).pack(side="left", padx=2)
        ttk.Button(menu_frame, text="Updates", width=8).pack(side="left", padx=2)
        ttk.Button(menu_frame, text="Reset All", width=8, command=self.reset_all).pack(side="left", padx=2)
        ttk.Button(menu_frame, text="FAQ/Help", width=8).pack(side="left", padx=2)

        # Горячая клавиша
        hotkey_frame = ttk.Frame(self.root)
        hotkey_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(hotkey_frame, text="Hotkey:").pack(side="left")
        self.hotkey_entry = ttk.Entry(hotkey_frame, textvariable=self.hotkey_var, width=10, state="readonly")
        self.hotkey_entry.pack(side="left", padx=5)
        ttk.Button(hotkey_frame, text="Change", command=self.start_listening_hotkey).pack(side="left", padx=5)

        # Основные настройки
        main_frame = ttk.LabelFrame(self.root, text="Auto Clicker", padding=10)
        main_frame.pack(fill="x", padx=10, pady=5)

        # Mouse Click Type
        ttk.Label(main_frame, text="Mouse Click Type").pack(anchor="w", pady=(5,0))
        self.click_type_var = tk.StringVar(value="Left")
        type_frame = ttk.Frame(main_frame)
        type_frame.pack(fill="x", pady=2)
        for btn in ["Left", "Middle", "Right"]:
            ttk.Radiobutton(type_frame, text=btn, variable=self.click_type_var,
                            value=btn, command=self.update_settings).pack(side="left")

        # Activation Mode
        ttk.Label(main_frame, text="Activation Mode").pack(anchor="w", pady=(10,0))
        self.mode_var = tk.StringVar(value="Hold")
        mode_frame = ttk.Frame(main_frame)
        mode_frame.pack(fill="x", pady=2)
        for mode in ["Hold", "Switch"]:
            ttk.Radiobutton(mode_frame, text=mode, variable=self.mode_var,
                            value=mode, command=self.update_settings).pack(side="left")

        # Click Rate
        ttk.Label(main_frame, text="Click Rate").pack(anchor="w", pady=(10,0))
        self.variation_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(main_frame, text="Variation (Anti-Detection)",
                        variable=self.variation_var, command=self.update_settings).pack(anchor="w")

        delay_frame = ttk.Frame(main_frame)
        delay_frame.pack(fill="x", pady=2)
        ttk.Label(delay_frame, text="Min (s):").pack(side="left")
        self.delay_min_entry = ttk.Entry(delay_frame, width=8)
        self.delay_min_entry.insert(0, "0.08")
        self.delay_min_entry.pack(side="left", padx=5)
        ttk.Label(delay_frame, text="Max (s):").pack(side="left", padx=(10,0))
        self.delay_max_entry = ttk.Entry(delay_frame, width=8)
        self.delay_max_entry.insert(0, "0.12")
        self.delay_max_entry.pack(side="left", padx=5)

        # Click Limitation
        ttk.Label(main_frame, text="Click Limitation").pack(anchor="w", pady=(10,0))
        self.limit_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(main_frame, text="Active",
                        variable=self.limit_enabled_var, command=self.update_settings).pack(anchor="w")
        limit_frame = ttk.Frame(main_frame)
        limit_frame.pack(fill="x", pady=2)
        ttk.Label(limit_frame, text="Limit:").pack(side="left")
        self.limit_entry = ttk.Entry(limit_frame, width=10)
        self.limit_entry.insert(0, "500")
        self.limit_entry.pack(side="left", padx=5)
        ttk.Button(limit_frame, text="Set", width=6, command=self.set_limit).pack(side="left")

        # Currently
        ttk.Label(main_frame, text="Currently").pack(anchor="w", pady=(10,0))
        global current_label
        current_label = ttk.Label(main_frame, text="0", font=("Arial", 16, "bold"))
        current_label.pack(anchor="w", pady=2)

        # Кнопка старт/стоп
        global start_stop_btn
        start_stop_btn = ttk.Button(self.root, text="Start", command=toggle_clicking, width=15)
        start_stop_btn.pack(pady=15)

    # ==================== ГОРЯЧАЯ КЛАВИША ====================
    def setup_hotkey(self):
        """Устанавливает глобальные хуки на текущую горячую клавишу."""
        # Удаляем старые хуки
        if self.hook_press is not None:
            keyboard.unhook(self.hook_press)
            self.hook_press = None
        if self.hook_release is not None:
            keyboard.unhook(self.hook_release)
            self.hook_release = None

        # Регистрируем новые
        self.hook_press = keyboard.on_press_key(
            current_hotkey, self.on_hotkey_press, suppress=False
        )
        self.hook_release = keyboard.on_release_key(
            current_hotkey, self.on_hotkey_release, suppress=False
        )

    def on_hotkey_press(self, event):
        if self.listening_for_hotkey:
            return
        with lock:
            mode = settings['mode']
        if mode == 'hold':
            start_clicking()
        else:  # switch
            if not hasattr(self, '_switch_pressed'):
                self._switch_pressed = False
            if not self._switch_pressed:
                self._switch_pressed = True
                toggle_clicking()

    def on_hotkey_release(self, event):
        if self.listening_for_hotkey:
            return
        with lock:
            mode = settings['mode']
        if mode == 'hold':
            stop_clicking()
        else:
            self._switch_pressed = False

    def start_listening_hotkey(self):
        """Начинает прослушивание новой горячей клавиши."""
        if self.listening_for_hotkey:
            return
        self.listening_for_hotkey = True
        self.hotkey_entry.config(state="normal")
        self.hotkey_entry.delete(0, tk.END)
        self.hotkey_entry.insert(0, "Нажмите клавишу...")
        self.hotkey_entry.config(state="readonly")

        def on_key(event):
            if event.event_type == keyboard.KEY_DOWN:
                new_hotkey = event.name
                if new_hotkey:
                    # Отключаем временный хук
                    if self.temp_hook is not None:
                        keyboard.unhook(self.temp_hook)
                        self.temp_hook = None
                    # Обновляем интерфейс
                    self.hotkey_var.set(new_hotkey.upper())
                    self.hotkey_entry.config(state="normal")
                    self.hotkey_entry.delete(0, tk.END)
                    self.hotkey_entry.insert(0, new_hotkey.upper())
                    self.hotkey_entry.config(state="readonly")
                    self.listening_for_hotkey = False
                    # Меняем глобальную переменную и переустанавливаем хуки
                    global current_hotkey
                    current_hotkey = new_hotkey
                    self.setup_hotkey()
                    # Убеждаемся, что временный хук отключен (на случай, если не отключился выше)
                    if self.temp_hook is not None:
                        keyboard.unhook(self.temp_hook)
                        self.temp_hook = None

        # Сохраняем временный хук
        self.temp_hook = keyboard.hook(on_key)

    # ==================== НАСТРОЙКИ ====================
    def update_settings(self):
        with lock:
            btn_map = {'Left': 'left', 'Middle': 'middle', 'Right': 'right'}
            settings['button'] = btn_map[self.click_type_var.get()]
            settings['mode'] = self.mode_var.get().lower()
            settings['variation'] = self.variation_var.get()

            try:
                min_d = float(self.delay_min_entry.get())
                max_d = float(self.delay_max_entry.get())
                if min_d <= 0 or max_d <= 0:
                    raise ValueError
                settings['delay_min'] = min_d
                settings['delay_max'] = max_d if max_d > min_d else min_d + 0.01
            except:
                settings['delay_min'] = 0.08
                settings['delay_max'] = 0.12
                self.delay_min_entry.delete(0, tk.END)
                self.delay_min_entry.insert(0, "0.08")
                self.delay_max_entry.delete(0, tk.END)
                self.delay_max_entry.insert(0, "0.12")

            settings['limit_enabled'] = self.limit_enabled_var.get()
            try:
                lim = int(self.limit_entry.get())
                if lim > 0:
                    settings['limit_count'] = lim
            except:
                settings['limit_count'] = 500
                self.limit_entry.delete(0, tk.END)
                self.limit_entry.insert(0, "500")

    def set_limit(self):
        self.update_settings()

    def reset_all(self):
        stop_clicking()
        reset_click_counter()
        self.update_settings()
        if app_running:
            messagebox.showinfo("Сброс", "Счётчик кликов сброшен и кликер остановлен.")

    def on_close(self):
        global stop_threads, app_running
        stop_threads = True
        app_running = False

        # Отключаем все хуки
        if self.hook_press is not None:
            keyboard.unhook(self.hook_press)
            self.hook_press = None
        if self.hook_release is not None:
            keyboard.unhook(self.hook_release)
            self.hook_release = None
        if self.temp_hook is not None:
            keyboard.unhook(self.temp_hook)
            self.temp_hook = None

        self.root.destroy()

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.mainloop()