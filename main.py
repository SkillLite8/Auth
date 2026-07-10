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

# Разделяем нажатие и отпускание для фикса в Minecraft
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


# ==================== ЛОГИКА КЛИКЕРА ====================
class ClickerCore:
    def __init__(self, ui_update_callback, state_change_callback):
        self.lock = threading.Lock()
        self.ui_callback = ui_update_callback
        self.state_callback = state_change_callback
        
        self.clicking = False
        self.click_count = 0
        self.limit_reached = False
        
        self.button = 'left'
        self.limit_enabled = False
        self.limit_count = 500
        self.cps = 16
        
        self.stop_event = threading.Event()
        self.trigger_event = threading.Event()
        
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
            self.trigger_event.wait(timeout=0.2)
            
            with self.lock:
                if not self.clicking or self.limit_reached:
                    continue
                
                if self.limit_enabled and self.click_count >= self.limit_count:
                    self.limit_reached = True
                    self.clicking = False
                    self.trigger_event.clear()
                    self.state_callback(False, msg="Лимит достигнут.")
                    continue
                
                self.click_count += 1
                current_count = self.click_count
                current_button = self.button

            # ФИКС ДЛЯ МАЙНКРАФТА:
            # Нажимаем кнопку мыши
            send_mouse_event('down', current_button)
            # Ждем 18 миллисекунд (чтобы игра успела зафиксировать нажатие в кадре)
            time.sleep(0.018)
            # Отпускаем кнопку мыши
            send_mouse_event('up', current_button)
            
            self.ui_callback(current_count)
            
            # Рассчитываем оставшееся время до следующего CPS (16 CPS = ~0.0625с всего цикла)
            total_delay = 1.0 / self.cps
            remaining_delay = max(0.001, total_delay - 0.018)
            time.sleep(remaining_delay)


# ==================== ТЕМНЫЙ ИНТЕРФЕЙС GUI ====================
class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SpeedAutoClicker")
        self.root.geometry("450x500")
        self.root.resizable(False, False)
        self.root.configure(bg="#20262E") # Темно-серый фон как на скрине
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.current_hotkey = 'r'
        self.hotkey_hook = None
        self.listening_for_hotkey = False

        # Настройка стилей
        self.style = ttk.Style()
        self.style.theme_use('default')
        
        # Перекрашиваем все элементы под игровой стиль
        self.style.configure('.', background='#20262E', foreground='white', font=('Segoe UI', 10))
        self.style.configure('TLabelframe', background='#20262E', bordercolor='#2D3748')
        self.style.configure('TLabelframe.Label', background='#20262E', foreground='#A0AEC0', font=('Segoe UI', 10, 'bold'))
        self.style.configure('TLabel', background='#20262E', foreground='white')
        
        # Кастомные кнопки (Зеленые, как на скрине)
        self.style.configure('Game.TButton', background='#2F855A', foreground='white', borderwidth=0, focuscolor='none')
        self.style.map('Game.TButton', background=[('active', '#22543D'), ('disabled', '#4A5568')])
        
        # Радиокнопки
        self.style.configure('TRadiobutton', background='#20262E', foreground='white', focuscolor='none')
        self.style.map('TRadiobutton', foreground=[('selected', '#48BB78')])
        
        # Инпуты
        self.style.configure('TEntry', fieldbackground='#2D3748', foreground='white', borderwidth=1)

        self.clicker = ClickerCore(
            ui_update_callback=self.async_update_counter,
            state_change_callback=self.async_state_change
        )

        self.create_widgets()
        self.setup_hotkey_listener()
        
        # Автоматический запрос прав админа (для игр обязательно)
        self.check_admin_rights()

    def create_widgets(self):
        # Левый сайдбар (как на картинке)
        sidebar = tk.Frame(self.root, bg="#1A202C", width=130)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Логотип/Иконка в сайдбаре
        logo_lbl = tk.Label(sidebar, text="🎯", font=("Segoe UI", 28), bg="#1A202C", fg="#48BB78")
        logo_lbl.pack(pady=(20, 10))

        # Кнопки меню слева
        menu_buttons = ["Auto Clicker", "Updates", "FAQ/Help"]
        for btn_txt in menu_buttons:
            b = tk.Button(sidebar, text=btn_txt, bg="#1A202C", fg="white", bd=0, 
                          activebackground="#2D3748", activeforeground="white", anchor="w", padx=15, pady=8)
            b.pack(fill="x")
        
        # Кнопка сброса
        reset_btn = tk.Button(sidebar, text="Reset All", bg="#9B2C2C", fg="white", bd=0, 
                              activebackground="#742A2A", command=self.reset_all, pady=5)
        reset_btn.pack(fill="x", side="bottom", pady=20, padx=10)

        # Главная правая панель
        main_container = tk.Frame(self.root, bg="#20262E", padx=15, pady=15)
        main_container.pack(side="right", fill="both", expand=True)

        # Горячая клавиша верхняя плашка
        hk_frame = tk.Frame(main_container, bg="#2D3748", height=40)
        hk_frame.pack(fill="x", pady=(0, 15))
        hk_frame.pack_propagate(False)
        
        self.hotkey_var = tk.StringVar(value=f"КЛАВИША: {self.current_hotkey.upper()}")
        self.hk_label = tk.Label(hk_frame, textvariable=self.hotkey_var, bg="#2D3748", fg="#63B3ED", font=("Segoe UI", 10, "bold"))
        self.hk_label.pack(side="left", padx=10)
        
        self.change_hk_btn = ttk.Button(hk_frame, text="Изменить", style="Game.TButton", command=self.start_listening_hotkey, width=10)
        self.change_hk_btn.pack(side="right", padx=5, pady=5)

        # Основной блок настроек
        config_frame = ttk.LabelFrame(main_container, text=" НАСТРОЙКИ КЛИКЕРА ", padding=10)
        config_frame.pack(fill="both", expand=True)

        # 1. Выбор кнопки мыши
        ttk.Label(config_frame, text="Тип клика (Mouse Click Type):").pack(anchor="w", pady=(5,2))
        self.click_type_var = tk.StringVar(value="Left")
        type_grid = tk.Frame(config_frame, bg="#20262E")
        type_grid.pack(fill="x", pady=(0, 10))
        for btn in ["Left", "Middle", "Right"]:
            ttk.Radiobutton(type_grid, text=btn, variable=self.click_type_var,
                            value=btn, command=self.sync_settings).pack(side="left", padx=10)

        # 2. Режим активации
        ttk.Label(config_frame, text="Режим работы (Activation Mode):").pack(anchor="w", pady=(5,2))
        mode_grid = tk.Frame(config_frame, bg="#20262E")
        mode_grid.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(mode_grid, text="Hold (Зажатие)", value="Hold", state="disabled").pack(side="left", padx=10)
        rb_switch = ttk.Radiobutton(mode_grid, text="Switch (Переключатель)", value="Switch")
        rb_switch.pack(side="left", padx=10)
        rb_switch.configure(state="normal")
        rb_switch.invoke()

        # 3. Скорость клика
        ttk.Label(config_frame, text="Скорость клика (Click Rate):").pack(anchor="w", pady=(5,2))
        rate_info = tk.Label(config_frame, text="Фиксировано: 16 CPS (Майнкрафт фикс включен)", bg="#20262E", fg="#48BB78", font=("Segoe UI", 9, "italic"))
        rate_info.pack(anchor="w", padx=5, pady=(0,10))

        # 4. Ограничения по кликам
        ttk.Label(config_frame, text="Лимит кликов (Click Limitation):").pack(anchor="w", pady=(5,2))
        self.limit_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(config_frame, text="Активировать лимит",
                        variable=self.limit_enabled_var, command=self.sync_settings).pack(anchor="w", padx=5)
        
        limit_input_frame = tk.Frame(config_frame, bg="#20262E")
        limit_input_frame.pack(fill="x", pady=5, padx=5)
        ttk.Label(limit_input_frame, text="Макс кликов:").pack(side="left")
        
        vcmd = (self.root.register(self.validate_number), '%P')
        self.limit_entry = ttk.Entry(limit_input_frame, width=12, validate="key", validatecommand=vcmd)
        self.limit_entry.insert(0, "500")
        self.limit_entry.pack(side="left", padx=10)
        self.limit_entry.bind("<KeyRelease>", lambda e: self.sync_settings())

        # 5. Счетчик кликов (Крупный игровой счетчик внизу)
        counter_frame = tk.Frame(main_container, bg="#1A202C", bd=1, relief="solid")
        counter_frame.pack(fill="x", pady=15)
        
        tk.Label(counter_frame, text="ВСЕГО КЛИКОВ:", bg="#1A202C", fg="#A0AEC0", font=("Segoe UI", 9, "bold")).pack(side="left", padx=15, pady=10)
        self.current_label = tk.Label(counter_frame, text="0", bg="#1A202C", fg="#48BB78", font=("Consolas", 22, "bold"))
        self.current_label.pack(side="right", padx=20)

        # Основная кнопка запуска
        self.start_stop_btn = ttk.Button(main_container, text="START (Клавиша R)", style="Game.TButton", command=self.on_toggle_action)
        self.start_stop_btn.pack(fill="x", ipady=8)

        self.sync_settings()

    def validate_number(self, text):
        return text.isdigit() or text == ""

    def sync_settings(self):
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
        if is_clicking:
            self.start_stop_btn.config(text=f"STOP (Клавиша {self.current_hotkey.upper()})")
            self.style.configure('Game.TButton', background='#E53E3E') # Красный цвет при работе
        else:
            self.start_stop_btn.config(text=f"START (Клавиша {self.current_hotkey.upper()})")
            self.style.configure('Game.TButton', background='#2F855A') # Возвращаем зеленый

    def async_update_counter(self, count):
        if self.root.winfo_exists():
            self.root.after(0, lambda: self.current_label.config(text=str(count)))

    def async_state_change(self, is_clicking, msg=None):
        if self.root.winfo_exists():
            self.root.after(0, lambda: self.update_btn_ui(is_clicking))
            if msg:
                self.root.after(0, lambda: messagebox.showwarning("Информация", msg))

    # ==================== УПРАВЛЕНИЕ ХОТКЕЕМ ====================
    def setup_hotkey_listener(self):
        if self.hotkey_hook:
            keyboard.unhook(self.hotkey_hook)
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
        self.hotkey_var.set("НАЖМИТЕ КЛАВИШУ...")
        
        threading.Thread(target=self._capture_next_key, daemon=True).start()

    def _capture_next_key(self):
        event = keyboard.read_event(suppress=True)
        if event.event_type == keyboard.KEY_DOWN:
            new_key = event.name
            self.root.after(0, lambda: self.finalize_new_hotkey(new_key))

    def finalize_new_hotkey(self, new_key):
        self.current_hotkey = new_key
        self.hotkey_var.set(f"КЛАВИША: {new_key.upper()}")
        self.setup_hotkey_listener()
        self.listening_for_hotkey = False
        self.change_hk_btn.config(state="normal")
        self.update_btn_ui(self.clicker.clicking)

    def reset_all(self):
        self.clicker.reset_counter()
        self.current_label.config(text="0")
        self.update_btn_ui(False)
        messagebox.showinfo("Сброс", "Все счетчики сброшены, кликер остановлен.")

    def check_admin_rights(self):
        try:
            if not ctypes.windll.shell32.IsUserAnAdmin():
                messagebox.showwarning(
                    "Запуск от Администратора", 
                    "ВНИМАНИЕ: Minecraft Bedrock блокирует сторонний ввод! Обязательно перезапустите этот кликер ОТ ИМЕНИ АДМИНИСТРАТОРА, иначе клики в игре работать не будут."
                )
        except:
            pass

    def on_close(self):
        self.clicker.stop_event.set()
        self.clicker.trigger_event.set()
        if self.hotkey_hook:
            keyboard.unhook(self.hotkey_hook)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.mainloop()
