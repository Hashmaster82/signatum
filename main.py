import os
import json
import csv
import shutil
from datetime import datetime
from tkinter import *
from tkinter import ttk, messagebox, filedialog
from fpdf import FPDF
import logging

# === Глобальный конфиг ===
CONFIG_FILE = "config.json"


def get_or_ask_data_directory():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            data_dir = cfg.get("data_directory")
            if data_dir and os.path.isdir(data_dir):
                return data_dir
    root = Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="Выберите папку для хранения данных программы Signatum")
    root.destroy()
    if not folder:
        messagebox.showerror("Ошибка", "Папка не выбрана. Программа завершится.")
        exit()
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({"data_directory": folder}, f, ensure_ascii=False, indent=2)
    return folder


DATA_DIR = get_or_ask_data_directory()
PRINTERS_FILE = os.path.join(DATA_DIR, "printers.json")
CARTRIDGES_FILE = os.path.join(DATA_DIR, "cartridges.json")
CARTRIDGE_MODELS_FILE = os.path.join(DATA_DIR, "cartridge_models.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)
LOG_FILE = os.path.join(DATA_DIR, "app_log.txt")

# Создаем папку assets/font если её нет
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "font")
os.makedirs(ASSETS_DIR, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)


def backup_files():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for file in [PRINTERS_FILE, CARTRIDGES_FILE, CARTRIDGE_MODELS_FILE, HISTORY_FILE, SETTINGS_FILE]:
        if os.path.exists(file):
            shutil.copy(file, os.path.join(BACKUP_DIR, f"backup_{timestamp}_{os.path.basename(file)}"))


backup_files()


def load_json(file_path, default):
    if not os.path.exists(file_path):
        save_json(file_path, default)
        logging.info(f"Создан новый файл: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


printers_data = load_json(PRINTERS_FILE, {"принтеры": []})
cartridges_data = load_json(CARTRIDGES_FILE, {"картриджи": []})
cartridge_models_data = load_json(CARTRIDGE_MODELS_FILE, {"модели_картриджей": []})
history_data = load_json(HISTORY_FILE, {"записи": []})
settings_data = load_json(SETTINGS_FILE, {"критические_уровни": {}})


# === Вспомогательные функции ===

def get_cartridge_models_from_registry_only():
    """Возвращает только модели из cartridge_models.json"""
    models = set()
    for model_data in cartridge_models_data["модели_картриджей"]:
        models.add(model_data["модель"])
    return sorted(models)


def get_warehouse_stock():
    """Возвращает количество картриджей на складе, только для моделей, которые реально есть на складе"""
    stock = {}
    for c in cartridges_data["картриджи"]:
        if c["статус"] == "на складе":
            model = c["модель"]
            stock[model] = stock.get(model, 0) + 1
    return stock


def is_color_printer(printer):
    """Определяет, является ли принтер цветным"""
    color_models = ["Cyan", "Magenta", "Yellow", "Color", "Цветной"]
    for i in range(1, 5):
        cart_model = printer.get(f"картридж_{i}", "")
        if any(color_model.lower() in cart_model.lower() for color_model in color_models):
            return True
    return False


def get_critical_level(model):
    return settings_data["критические_уровни"].get(model, 5)


# ✅ ИСПРАВЛЕНА ЭТА ФУНКЦИЯ — теперь отображаются ВСЕ модели из реестра, даже с количеством 0
def get_stock_with_status():
    """Возвращает данные о запасах для ВСЕХ моделей из реестра, включая нулевые остатки."""
    actual_stock = get_warehouse_stock()
    result = []
    for model_data in cartridge_models_data["модели_картриджей"]:
        model = model_data["модель"]
        qty = actual_stock.get(model, 0)  # 0, если нет на складе
        crit = get_critical_level(model)

        if qty == 0:
            status = "Отсутствует"
            color = "red"
            priority = 1
        elif qty < crit:
            status = "Низкий"
            color = "orange"
            priority = 2
        else:
            status = "Норма"
            color = "green"
            priority = 3

        result.append({
            "модель": model,
            "количество": qty,
            "критический_уровень": crit,
            "статус": status,
            "цвет": color,
            "приоритет": priority
        })

    # Сортируем: сначала отсутствующие и низкие
    result.sort(key=lambda x: x["приоритет"])
    return result


def update_stock_display(tree, search_query=""):
    for row in tree.get_children():
        tree.delete(row)
    stock_data = get_stock_with_status()
    for item in stock_data:
        if search_query and search_query.lower() not in item["модель"].lower():
            continue
        tree.insert("", "end", values=(
            item["модель"],
            item["количество"],
            item["критический_уровень"],
            item["статус"]
        ), tags=(item["цвет"],))
    tree.tag_configure("red", background="#ffcccc")
    tree.tag_configure("orange", background="#ffebcc")
    tree.tag_configure("green", background="#d4edda")


def show_critical_alerts():
    stock_data = get_stock_with_status()
    alerts = []
    for item in stock_data:
        if item["приоритет"] in [1, 2]:  # Отсутствует или низкий уровень
            alerts.append(f"{item['модель']} (осталось {item['количество']} шт.)")
    if alerts:
        msg = "Срочно закажите:\n" + "\n".join(alerts)
        messagebox.showwarning("Критический уровень запаса!", msg)
        logging.warning("Показано уведомление: " + "; ".join(alerts))


def get_printer_cartridge_status(printer):
    """Возвращает статус по каждому картриджу и общий статус принтера."""
    stock = get_warehouse_stock()
    cartridges_needed = []
    has_at_least_one_ready = False
    has_zero_stock = False
    is_color = is_color_printer(printer)
    for i in range(1, 5):
        model = printer.get(f"картридж_{i}")
        if not model:
            continue
        qty = stock.get(model, 0)  # Если модели нет на складе, количество = 0
        crit = get_critical_level(model)
        if qty == 0:
            status = "❌ Отсутствует"
            color = "red"
            has_zero_stock = True
        elif qty >= crit:
            status = f"✅ Есть ({qty})"
            color = "green"
            has_at_least_one_ready = True
        else:
            status = f"⚠️ Низкий ({qty})"
            color = "orange"
            if is_color:
                has_zero_stock = True  # Для цветных принтеров низкий уровень = не готов
        cartridges_needed.append({
            "модель": model,
            "статус": status,
            "цвет": color
        })
    if not cartridges_needed:
        overall = "⚪ Не настроен"
        overall_color = "gray"
    elif is_color and has_zero_stock:
        overall = "❌ Не готов"
        overall_color = "red"
    elif not is_color and has_at_least_one_ready:
        overall = "✅ Готов"
        overall_color = "green"
    elif has_zero_stock:
        overall = "❌ Не готов"
        overall_color = "red"
    else:
        overall = "✅ Готов"
        overall_color = "green"
    return cartridges_needed, overall, overall_color


# === Основной класс приложения ===
class CartridgeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Signatum — Учёт картриджей")
        self.root.geometry("1200x750")
        self.create_main_view()

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def create_main_view(self):
        self.clear_window()
        left_frame = Frame(self.root, padx=10, pady=10, width=400)
        left_frame.pack(side=LEFT, fill=Y, expand=False)
        Label(left_frame, text="Какой картридж только что был установлен?", font=("Arial", 12, "bold")).pack(anchor=W,
                                                                                                             pady=(0,
                                                                                                                   10))
        self.model_var = StringVar()
        Label(left_frame, text="Модель картриджа:").pack(anchor=W)
        model_combo = ttk.Combobox(left_frame, textvariable=self.model_var,
                                   values=get_cartridge_models_from_registry_only(), state="readonly")
        model_combo.pack(fill=X, pady=(0, 10))
        Label(left_frame, text="Серийный номер (опционально):").pack(anchor=W)
        self.sn_entry = Entry(left_frame)
        self.sn_entry.pack(fill=X, pady=(0, 10))
        Button(left_frame, text="Подтвердить установку", command=self.confirm_installation, bg="#4CAF50",
               fg="white").pack(pady=(0, 20))
        Button(left_frame, text="Добавить картридж на склад", command=self.add_cartridge_to_warehouse).pack(fill=X,
                                                                                                            pady=5)
        Button(left_frame, text="Список моделей картриджей", command=self.show_cartridge_models_list).pack(fill=X,
                                                                                                           pady=5)
        Button(left_frame, text="Управление принтерами", command=self.show_printer_list).pack(fill=X, pady=5)
        Button(left_frame, text="История установок", command=self.show_history).pack(fill=X, pady=5)
        Button(left_frame, text="Настройки запасов", command=self.open_settings).pack(fill=X, pady=5)
        Button(
            left_frame,
            text="📊 Статус принтеров",
            command=self.show_printer_status_report,
            bg="#2196F3",
            fg="white",
            font=("Arial", 10, "bold"),
            height=2
        ).pack(fill=X, pady=(15, 5))

        right_frame = Frame(self.root, padx=10, pady=10)
        right_frame.pack(side=RIGHT, fill=BOTH, expand=True)
        Label(right_frame, text="Картриджи на складе", font=("Arial", 12, "bold")).pack(anchor=W, pady=(0, 10))

        search_frame = Frame(right_frame)
        search_frame.pack(fill=X, pady=(0, 5))
        Label(search_frame, text="Поиск по модели:", anchor=W).pack(side=LEFT)
        self.search_var = StringVar()
        search_entry = Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=LEFT, fill=X, expand=True, padx=(5, 0))
        self.search_var.trace("w", lambda *args: self.on_search_change())

        columns = ("Модель", "Остаток", "Крит. уровень", "Статус")
        self.stock_tree = ttk.Treeview(right_frame, columns=columns, show="headings", height=15)
        for col in columns:
            self.stock_tree.heading(col, text=col)
            self.stock_tree.column(col, width=150)
        self.stock_tree.pack(fill=BOTH, expand=True, pady=(0, 10))

        self.stock_context_menu = Menu(self.root, tearoff=0)
        self.stock_context_menu.add_command(label="Изменить количество", command=self.edit_stock_quantity)
        self.stock_context_menu.add_command(label="Редактировать запись", command=self.edit_stock_record)
        self.stock_context_menu.add_command(label="Удалить запись", command=self.delete_stock_record)

        def on_stock_right_click(event):
            item = self.stock_tree.identify_row(event.y)
            if item:
                self.stock_tree.selection_set(item)
                self.stock_context_menu.post(event.x_root, event.y_root)

        self.stock_tree.bind("<Button-3>", on_stock_right_click)

        btn_frame = Frame(right_frame)
        btn_frame.pack(side=BOTTOM, anchor=SE, pady=10)
        Button(btn_frame, text="Обновить данные",
               command=lambda: update_stock_display(self.stock_tree, self.search_var.get())).pack(side=LEFT, padx=5)
        Button(btn_frame, text="Экспорт в CSV", command=self.export_csv).pack(side=LEFT, padx=5)
        Button(btn_frame, text="Экспорт в PDF", command=self.export_pdf).pack(side=LEFT, padx=5)
        Button(btn_frame, text="Настройки", command=self.open_global_settings).pack(side=LEFT, padx=5)

        update_stock_display(self.stock_tree)
        show_critical_alerts()

    def on_search_change(self):
        query = self.search_var.get()
        update_stock_display(self.stock_tree, query)

    # === Список моделей картриджей с контекстным меню ===
    def show_cartridge_models_list(self):
        win = Toplevel(self.root)
        win.title("Список моделей картриджей")
        win.geometry("800x500")
        columns = ("Модель", "Принтеры", "Тип", "Описание")
        tree = ttk.Treeview(win, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=180)
        tree.pack(fill=BOTH, expand=True, padx=10, pady=10)
        for idx, model in enumerate(cartridge_models_data["модели_картриджей"]):
            printers_display = ", ".join(model.get("принтеры", [])) if isinstance(model.get("принтеры"),
                                                                                  list) else model.get("принтер", "")
            tree.insert("", "end", iid=idx, values=(
                model.get("модель", ""),
                printers_display,
                model.get("тип", ""),
                model.get("описание", "")
            ))
        context_menu = Menu(win, tearoff=0)
        context_menu.add_command(label="Редактировать", command=lambda: self.edit_cartridge_model(tree, context_menu))
        context_menu.add_command(label="Удалить", command=lambda: self.delete_cartridge_model(tree, context_menu))

        def on_right_click(event):
            item = tree.identify_row(event.y)
            if item:
                tree.selection_set(item)
                context_menu.post(event.x_root, event.y_root)

        tree.bind("<Button-3>", on_right_click)
        btn_frame = Frame(win)
        btn_frame.pack(pady=10)
        Button(btn_frame, text="Добавить модель картриджа",
               command=lambda: [win.destroy(), self.add_cartridge_model()]).pack(side=LEFT, padx=5)
        Button(btn_frame, text="Закрыть", command=win.destroy).pack(side=LEFT, padx=5)

    def edit_cartridge_model(self, tree, menu):
        selection = tree.selection()
        if not selection:
            return
        idx = int(selection[0])
        model_data = cartridge_models_data["модели_картриджей"][idx]
        menu.unpost()
        self._open_cartridge_model_form(model_data, idx)

    def delete_cartridge_model(self, tree, menu):
        selection = tree.selection()
        if not selection:
            return
        idx = int(selection[0])
        model_name = cartridge_models_data["модели_картриджей"][idx]["модель"]
        if messagebox.askyesno("Удаление", f"Удалить модель картриджа '{model_name}'?"):
            del cartridge_models_data["модели_картриджей"][idx]
            save_json(CARTRIDGE_MODELS_FILE, cartridge_models_data)
            menu.unpost()
            self.show_cartridge_models_list()

    def _open_cartridge_model_form(self, model_data=None, index=None):
        win = Toplevel(self.root)
        win.title("Редактирование модели картриджа" if model_data else "Добавление новой модели картриджа")
        win.geometry("500x550")
        printer_list = [p.get("модель", "") for p in printers_data["принтеры"]]
        Label(win, text="Совместимые принтеры (до 3):", font=("Arial", 10)).pack(anchor=W, padx=20, pady=(10, 0))
        printer_vars = []
        for i in range(3):
            frame = Frame(win)
            frame.pack(fill=X, padx=20, pady=2)
            Label(frame, text=f"Принтер {i + 1}:", width=10, anchor=W).pack(side=LEFT)
            var = StringVar()
            combo = ttk.Combobox(frame, textvariable=var, values=printer_list, width=40)
            combo.pack(side=LEFT, padx=(5, 0))
            printer_vars.append(var)
        if model_data:
            printers = model_data.get("принтеры", [])
            if isinstance(printers, str):
                printers = [printers]  # обратная совместимость
            for i in range(min(3, len(printers))):
                printer_vars[i].set(printers[i])
        Label(win, text="Название модели картриджа:", font=("Arial", 10)).pack(anchor=W, padx=20)
        model_entry = Entry(win)
        model_entry.pack(fill=X, padx=20, pady=(0, 10))
        if model_data:
            model_entry.insert(0, model_data.get("модель", ""))
        Label(win, text="Описание (опционально):", font=("Arial", 10)).pack(anchor=W, padx=20)
        desc_text = Text(win, height=4)
        desc_text.pack(fill=X, padx=20, pady=(0, 10))
        if model_data:
            desc_text.insert("1.0", model_data.get("описание", ""))
        Label(win, text="Тип картриджа:", font=("Arial", 10)).pack(anchor=W, padx=20)
        type_var = StringVar(value=model_data.get("тип", "") if model_data else "")
        type_combo = ttk.Combobox(win, textvariable=type_var,
                                  values=["Черный", "Цветной", "Cyan", "Magenta", "Yellow", "Другое"])
        type_combo.pack(fill=X, padx=20, pady=(0, 10))

        def save_model():
            model = model_entry.get().strip()
            if not model:
                messagebox.showerror("Ошибка", "Введите название модели картриджа!")
                return
            for i, existing in enumerate(cartridge_models_data["модели_картриджей"]):
                if existing["модель"].lower() == model.lower() and (index is None or i != index):
                    messagebox.showerror("Ошибка", f"Модель '{model}' уже существует!")
                    return
            printers_selected = [var.get().strip() for var in printer_vars if var.get().strip()]
            new_model = {
                "модель": model,
                "принтеры": printers_selected,
                "описание": desc_text.get("1.0", END).strip(),
                "тип": type_var.get().strip(),
                "дата_добавления": model_data.get("дата_добавления",
                                                  datetime.now().isoformat()) if model_data else datetime.now().isoformat()
            }
            if index is not None:
                cartridge_models_data["модели_картриджей"][index] = new_model
            else:
                cartridge_models_data["модели_картриджей"].append(new_model)
            save_json(CARTRIDGE_MODELS_FILE, cartridge_models_data)
            logging.info(f"{'Обновлена' if model_data else 'Добавлена'} модель картриджа: {model}")
            win.destroy()
            messagebox.showinfo("Успех",
                                f"Модель картриджа '{model}' успешно {'обновлена' if model_data else 'добавлена'}!")

        Button(win, text="Сохранить", command=save_model, bg="#4CAF50", fg="white").pack(pady=10)

    # === Отчёт "Статус принтеров" ===
    def show_printer_status_report(self):
        self.clear_window()
        Label(self.root, text="Статус принтеров", font=("Arial", 16, "bold")).pack(pady=10)
        columns = ("Модель принтера", "Тип", "Картридж 1", "Картридж 2", "Картридж 3", "Картридж 4", "Общий статус")
        tree = ttk.Treeview(self.root, columns=columns, show="headings", height=20)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=140)
        tree.pack(fill=BOTH, expand=True, padx=20, pady=10)
        tree.tag_configure("green", background="#d4edda")
        tree.tag_configure("red", background="#ffcccc")
        tree.tag_configure("orange", background="#ffebcc")
        tree.tag_configure("gray", background="#f0f0f0")
        for p in printers_data["принтеры"]:
            model = p.get("модель", "Без названия")
            is_color = is_color_printer(p)
            printer_type = "Цветной" if is_color else "Черно-белый"
            cartridges_needed, overall, overall_color = get_printer_cartridge_status(p)
            cart_statuses = ["—"] * 4
            for i, cart in enumerate(cartridges_needed[:4]):
                cart_statuses[i] = cart["статус"]
            tree.insert("", "end", values=(
                model,
                printer_type,
                cart_statuses[0],
                cart_statuses[1],
                cart_statuses[2],
                cart_statuses[3],
                overall
            ), tags=(overall_color,))
        btn_frame = Frame(self.root)
        btn_frame.pack(pady=10)
        Button(btn_frame, text="Назад", command=self.create_main_view).pack()

    # === Настройки запасов с переключателем фильтра ===
    def open_settings(self):
        win = Toplevel(self.root)
        win.title("Настройки запасов")
        win.state('zoomed')
        main_frame = Frame(win)
        main_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)
        filter_var = BooleanVar(value=True)  # ✅ По умолчанию — только из реестра
        filter_frame = Frame(main_frame)
        filter_frame.pack(anchor=W, pady=(0, 10))
        Checkbutton(
            filter_frame,
            text="Показывать только модели из реестра картриджей",
            variable=filter_var
        ).pack(side=LEFT)
        canvas = Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient=VERTICAL, command=canvas.yview)
        scrollable_frame = Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        Label(scrollable_frame, text="Критические уровни запасов", font=("Arial", 14, "bold")).pack(pady=(0, 15))
        cart_to_printers = {}
        for p in printers_data["принтеры"]:
            for i in range(1, 5):
                cart_model = p.get(f"картридж_{i}")
                if cart_model:
                    cart_to_printers.setdefault(cart_model, set()).add(p.get("модель", "Без названия"))
        entries = {}

        def refresh_settings_list():
            for widget in scrollable_frame.winfo_children():
                if widget != filter_frame and isinstance(widget, Frame):
                    widget.destroy()
            if filter_var.get():
                models = get_cartridge_models_from_registry_only()
            else:
                models = sorted(set(c["модель"] for c in cartridges_data["картриджи"]))
            for model in models:
                row = Frame(scrollable_frame)
                row.pack(fill=X, pady=4)
                model_label = Label(row, text=model, width=30, anchor=W, font=("Arial", 10))
                model_label.pack(side=LEFT)
                printers_list = ", ".join(sorted(cart_to_printers.get(model, []))) or "—"
                printer_label = Label(row, text=printers_list, width=40, anchor=W, fg="gray", font=("Arial", 9))
                printer_label.pack(side=LEFT, padx=(10, 20))
                var = StringVar(value=str(get_critical_level(model)))
                entry = Entry(row, textvariable=var, width=8, justify='center')
                entry.pack(side=RIGHT)
                entries[model] = var

        filter_var.trace("w", lambda *args: refresh_settings_list())
        refresh_settings_list()

        def apply():
            for model, var in entries.items():
                try:
                    val = int(var.get())
                    if val < 0:
                        raise ValueError
                    settings_data["критические_уровни"][model] = val
                except ValueError:
                    messagebox.showerror("Ошибка", f"Некорректное значение для {model}")
                    return
            save_json(SETTINGS_FILE, settings_data)
            logging.info("Обновлены критические уровни")
            update_stock_display(self.stock_tree, self.search_var.get())
            win.destroy()
            messagebox.showinfo("Успех", "Настройки сохранены!")

        btn_frame = Frame(win)
        btn_frame.pack(pady=15)
        Button(btn_frame, text="Применить", command=apply, bg="#4CAF50", fg="white", font=("Arial", 12),
               width=15).pack()

    # === Остальные методы (без изменений) ===
    def edit_stock_quantity(self):
        selection = self.stock_tree.selection()
        if not selection:
            return
        item = self.stock_tree.item(selection[0])
        model = item['values'][0]
        current_qty = item['values'][1]
        win = Toplevel(self.root)
        win.title(f"Изменение количества: {model}")
        win.geometry("300x200")
        Label(win, text=f"Модель: {model}", font=("Arial", 10, "bold")).pack(pady=10)
        Label(win, text=f"Текущее количество: {current_qty} шт.").pack(pady=5)
        Label(win, text="Новое количество:").pack(pady=5)
        qty_var = StringVar(value=str(current_qty))
        qty_entry = Entry(win, textvariable=qty_var, font=("Arial", 12), justify='center')
        qty_entry.pack(pady=5)
        qty_entry.select_range(0, END)
        qty_entry.focus()

        def apply_quantity():
            try:
                new_qty = int(qty_var.get())
                if new_qty < 0:
                    raise ValueError
                current_cartridges = [c for c in cartridges_data["картриджи"] if
                                      c["модель"] == model and c["статус"] == "на складе"]
                current_count = len(current_cartridges)
                if new_qty > current_count:
                    to_add = new_qty - current_count
                    for i in range(to_add):
                        new_cartridge = {
                            "модель": model,
                            "серийный_номер": f"AUTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}",
                            "статус": "на складе",
                            "дата_поступления": datetime.now().isoformat(),
                            "остаточный_ресурс": 100,
                            "принтер": "",
                            "комментарий": "Добавлено автоматически"
                        }
                        cartridges_data["картриджи"].append(new_cartridge)
                elif new_qty < current_count:
                    to_remove = current_count - new_qty
                    removed = 0
                    for i in range(len(cartridges_data["картриджи"]) - 1, -1, -1):
                        if removed >= to_remove:
                            break
                        c = cartridges_data["картриджи"][i]
                        if c["модель"] == model and c["статус"] == "на складе":
                            del cartridges_data["картриджи"][i]
                            removed += 1
                save_json(CARTRIDGES_FILE, cartridges_data)
                update_stock_display(self.stock_tree, self.search_var.get())
                win.destroy()
                messagebox.showinfo("Успех", f"Количество картриджей '{model}' изменено на {new_qty}")
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное число (0 или больше)")

        Button(win, text="Применить", command=apply_quantity, bg="#4CAF50", fg="white", width=15).pack(pady=10)
        win.bind('<Return>', lambda e: apply_quantity())

    def edit_stock_record(self):
        selection = self.stock_tree.selection()
        if not selection:
            return
        item = self.stock_tree.item(selection[0])
        model = item['values'][0]
        cartridges_on_stock = [c for c in cartridges_data["картриджи"] if
                               c["модель"] == model and c["статус"] == "на складе"]
        if not cartridges_on_stock:
            messagebox.showwarning("Внимание", f"Не найдены картриджи модели '{model}' на складе")
            return
        self.show_edit_stock_window(model, cartridges_on_stock)

    def show_edit_stock_window(self, model, cartridges):
        win = Toplevel(self.root)
        win.title(f"Редактирование картриджей: {model}")
        win.geometry("800x500")
        Label(win, text=f"Картриджи модели '{model}' на складе", font=("Arial", 12, "bold")).pack(pady=10)
        columns = ("Серийный номер", "Остаточный ресурс", "Дата поступления", "Комментарий")
        tree = ttk.Treeview(win, columns=columns, show="headings", height=15)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150)
        tree.pack(fill=BOTH, expand=True, padx=20, pady=10)
        for idx, cart in enumerate(cartridges):
            tree.insert("", "end", iid=idx, values=(
                cart.get("серийный_номер", "N/A"),
                cart.get("остаточный_ресурс", 100),
                cart.get("дата_поступления", ""),
                cart.get("комментарий", "")
            ))
        context_menu = Menu(win, tearoff=0)
        context_menu.add_command(label="Редактировать картридж",
                                 command=lambda: self.edit_single_cartridge(tree, cartridges, context_menu))
        context_menu.add_command(label="Удалить картридж",
                                 command=lambda: self.delete_single_cartridge(tree, cartridges, context_menu))

        def on_right_click(event):
            item = tree.identify_row(event.y)
            if item:
                tree.selection_set(item)
                context_menu.post(event.x_root, event.y_root)

        tree.bind("<Button-3>", on_right_click)
        btn_frame = Frame(win)
        btn_frame.pack(pady=10)
        Button(btn_frame, text="Добавить картридж этой модели",
               command=lambda: self.add_cartridge_of_model(model, win)).pack(side=LEFT, padx=5)
        Button(btn_frame, text="Закрыть", command=win.destroy).pack(side=LEFT, padx=5)

    def edit_single_cartridge(self, tree, cartridges, menu):
        selection = tree.selection()
        if not selection:
            return
        idx = int(selection[0])
        cartridge = cartridges[idx]
        menu.unpost()
        self.show_edit_cartridge_window(cartridge, tree, cartridges)

    def show_edit_cartridge_window(self, cartridge, tree, cartridges):
        win = Toplevel(self.root)
        win.title("Редактирование картриджа")
        win.geometry("400x300")
        Label(win, text="Редактирование картриджа", font=("Arial", 12, "bold")).pack(pady=10)
        fields = ["серийный_номер", "остаточный_ресурс", "дата_поступления", "комментарий"]
        labels = ["Серийный номер:", "Остаточный ресурс (%):", "Дата поступления:", "Комментарий:"]
        entries = {}
        for i, (field, label) in enumerate(zip(fields, labels)):
            Label(win, text=label).pack(anchor=W, padx=20)
            entry = Entry(win, width=50)
            entry.pack(fill=X, padx=20, pady=(0, 10))
            entry.insert(0, str(cartridge.get(field, "")))
            entries[field] = entry

        def save_changes():
            for field, entry in entries.items():
                if field == "остаточный_ресурс":
                    try:
                        cartridge[field] = int(entry.get())
                    except ValueError:
                        messagebox.showerror("Ошибка", "Остаточный ресурс должен быть числом")
                        return
                else:
                    cartridge[field] = entry.get().strip()
            save_json(CARTRIDGES_FILE, cartridges_data)
            update_stock_display(self.stock_tree, self.search_var.get())
            win.destroy()
            messagebox.showinfo("Успех", "Картридж успешно обновлен!")

        Button(win, text="Сохранить", command=save_changes, bg="#4CAF50", fg="white").pack(pady=10)

    def delete_single_cartridge(self, tree, cartridges, menu):
        selection = tree.selection()
        if not selection:
            return
        idx = int(selection[0])
        cartridge = cartridges[idx]
        sn = cartridge.get("серийный_номер", "N/A")
        if messagebox.askyesno("Удаление", f"Удалить картридж с серийным номером {sn}?"):
            for i, c in enumerate(cartridges_data["картриджи"]):
                if (c["модель"] == cartridge["модель"] and c.get("серийный_номер") == cartridge.get("серийный_номер")):
                    del cartridges_data["картриджи"][i]
                    break
            save_json(CARTRIDGES_FILE, cartridges_data)
            menu.unpost()
            update_stock_display(self.stock_tree, self.search_var.get())
            messagebox.showinfo("Успех", "Картридж удален!")

    def delete_stock_record(self):
        selection = self.stock_tree.selection()
        if not selection:
            return
        item = self.stock_tree.item(selection[0])
        model = item['values'][0]
        if messagebox.askyesno("Удаление", f"Удалить ВСЕ картриджи модели '{model}' со склада?"):
            cartridges_data["картриджи"] = [
                c for c in cartridges_data["картриджи"]
                if not (c["модель"] == model and c["статус"] == "на складе")
            ]
            save_json(CARTRIDGES_FILE, cartridges_data)
            update_stock_display(self.stock_tree, self.search_var.get())
            messagebox.showinfo("Успех", f"Все картриджи модели '{model}' удалены со склада!")

    def add_cartridge_of_model(self, model, parent_win):
        win = Toplevel(parent_win)
        win.title(f"Добавить картридж модели {model}")
        win.geometry("400x250")
        Label(win, text=f"Добавление картриджа модели '{model}'", font=("Arial", 12, "bold")).pack(pady=10)
        Label(win, text="Серийный номер:").pack(anchor=W, padx=20)
        sn_entry = Entry(win, width=50)
        sn_entry.pack(fill=X, padx=20, pady=(0, 10))
        Label(win, text="Остаточный ресурс (%):").pack(anchor=W, padx=20)
        resource_entry = Entry(win, width=50)
        resource_entry.insert(0, "100")
        resource_entry.pack(fill=X, padx=20, pady=(0, 10))
        Label(win, text="Комментарий:").pack(anchor=W, padx=20)
        comment_entry = Entry(win, width=50)
        comment_entry.pack(fill=X, padx=20, pady=(0, 10))

        def save_cartridge():
            sn = sn_entry.get().strip()
            resource = resource_entry.get().strip()
            comment = comment_entry.get().strip()
            if not resource:
                resource = "100"
            try:
                resource_int = int(resource)
                if resource_int < 0 or resource_int > 100:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Ошибка", "Остаточный ресурс должен быть числом от 0 до 100")
                return
            if sn:
                for c in cartridges_data["картриджи"]:
                    if c.get("серийный_номер") == sn:
                        messagebox.showerror("Ошибка", f"Картридж с серийным номером {sn} уже существует!")
                        return
            new_cartridge = {
                "модель": model,
                "серийный_номер": sn or "N/A",
                "статус": "на складе",
                "дата_поступления": datetime.now().isoformat(),
                "остаточный_ресурс": resource_int,
                "комментарий": comment,
                "принтер": ""
            }
            cartridges_data["картриджи"].append(new_cartridge)
            save_json(CARTRIDGES_FILE, cartridges_data)
            update_stock_display(self.stock_tree, self.search_var.get())
            win.destroy()
            parent_win.destroy()
            messagebox.showinfo("Успех", "Картридж добавлен на склад!")

        Button(win, text="Сохранить", command=save_cartridge, bg="#4CAF50", fg="white").pack(pady=10)

    def show_printer_list(self):
        self.clear_window()
        Label(self.root, text="Список принтеров", font=("Arial", 16, "bold")).pack(pady=10)
        columns = ("Модель", "Серийный", "IP", "Закреплён за", "Картридж 1", "Картридж 2", "Картридж 3", "Картридж 4",
                   "Комментарий")
        tree = ttk.Treeview(self.root, columns=columns, show="headings", height=20)
        column_widths = {
            "Модель": 150, "Серийный": 120, "IP": 100, "Закреплён за": 120,
            "Картридж 1": 120, "Картридж 2": 120, "Картридж 3": 120, "Картридж 4": 120, "Комментарий": 200
        }
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=column_widths[col])
        scroll_x = ttk.Scrollbar(self.root, orient=HORIZONTAL, command=tree.xview)
        tree.configure(xscrollcommand=scroll_x.set)
        scroll_x.pack(side=BOTTOM, fill=X)
        tree.pack(fill=BOTH, expand=True, padx=20, pady=10)
        for idx, p in enumerate(printers_data["принтеры"]):
            tree.insert("", "end", iid=idx, values=(
                p.get("модель", ""),
                p.get("серийный_номер", ""),
                p.get("ip_адрес", ""),
                p.get("закреплён_за", ""),
                p.get("картридж_1", ""),
                p.get("картридж_2", ""),
                p.get("картридж_3", ""),
                p.get("картридж_4", ""),
                p.get("комментарий", "")
            ))
        context_menu = Menu(self.root, tearoff=0)
        context_menu.add_command(label="Редактировать", command=lambda: self.edit_selected_printer(tree, context_menu))
        context_menu.add_command(label="Удалить", command=lambda: self.delete_selected_printer(tree, context_menu))

        def on_right_click(event):
            item = tree.identify_row(event.y)
            if item:
                tree.selection_set(item)
                context_menu.post(event.x_root, event.y_root)

        tree.bind("<Button-3>", on_right_click)
        btn_frame = Frame(self.root)
        btn_frame.pack(pady=10)
        Button(btn_frame, text="Добавить принтер", command=self.show_printer_form).pack(side=LEFT, padx=5)
        Button(btn_frame, text="Назад", command=self.create_main_view).pack(side=LEFT, padx=5)
        self.printer_tree = tree
        self.context_menu = context_menu

    def edit_selected_printer(self, tree, menu):
        selection = tree.selection()
        if not selection:
            return
        idx = int(selection[0])
        printer = printers_data["принтеры"][idx]
        menu.unpost()
        self.show_printer_form(printer_data=printer, index=idx)

    def delete_selected_printer(self, tree, menu):
        selection = tree.selection()
        if not selection:
            return
        idx = int(selection[0])
        model = printers_data["принтеры"][idx].get("модель", "Без названия")
        if messagebox.askyesno("Удаление", f"Удалить принтер {model}?"):
            del printers_data["принтеры"][idx]
            save_json(PRINTERS_FILE, printers_data)
            menu.unpost()
            self.show_printer_list()

    def show_printer_form(self, printer_data=None, index=None):
        self.clear_window()
        self.editing_printer_index = index
        self.root.state('zoomed')
        title = "Редактирование принтера" if printer_data else "Добавление нового принтера"
        Label(self.root, text=title, font=("Arial", 16, "bold")).pack(pady=10)
        fields = ["модель", "серийный_номер", "ip_адрес", "закреплён_за", "картридж_1", "картридж_2", "картридж_3",
                  "картридж_4", "комментарий"]
        labels = ["Модель", "Серийный номер", "IP-адрес", "Закреплён за", "Картридж 1", "Картридж 2", "Картридж 3",
                  "Картридж 4", "Комментарий"]
        self.printer_entries = {}
        form_frame = Frame(self.root)
        form_frame.pack(pady=20, padx=50, fill=BOTH, expand=True)
        for f, lbl in zip(fields, labels):
            row = Frame(form_frame)
            Label(row, text=lbl + ":", width=20, anchor=W, font=("Arial", 12)).pack(side=LEFT)
            if f.startswith("картридж_"):
                entry = ttk.Combobox(row, font=("Arial", 12), width=47,
                                     values=get_cartridge_models_from_registry_only())
            else:
                entry = Entry(row, font=("Arial", 12), width=50)
            entry.pack(side=LEFT, padx=10, fill=X, expand=True)
            row.pack(fill=X, pady=8)
            self.printer_entries[f] = entry
        if printer_data:
            for f in fields:
                if f in printer_data:
                    self.printer_entries[f].insert(0, printer_data.get(f, ""))
        btn_frame = Frame(self.root)
        btn_frame.pack(pady=20)
        Button(btn_frame, text="Сохранить", command=self.save_printer, bg="#4CAF50", fg="white", font=("Arial", 12),
               width=15).pack(side=LEFT, padx=10)
        Button(btn_frame, text="Назад", command=self.create_main_view, bg="#ccc", font=("Arial", 12), width=15).pack(
            side=LEFT, padx=10)

    def save_printer(self):
        data = {}
        for f, entry in self.printer_entries.items():
            data[f] = entry.get().strip()
        if not data.get("модель") or not data.get("серийный_номер"):
            messagebox.showerror("Ошибка", "Модель и серийный номер обязательны!")
            return
        if self.editing_printer_index is not None:
            printers_data["принтеры"][self.editing_printer_index] = data
            action = "обновлён"
        else:
            printers_data["принтеры"].append(data)
            action = "добавлен"
        save_json(PRINTERS_FILE, printers_data)
        logging.info(f"Принтер {action}: {data['модель']} ({data.get('серийный_номер', 'N/A')})")
        messagebox.showinfo("Успех", f"Принтер успешно {action}!")
        self.create_main_view()

    def add_cartridge_model(self):
        self._open_cartridge_model_form()

    def confirm_installation(self):
        model = self.model_var.get().strip()
        sn = self.sn_entry.get().strip()
        if not model:
            messagebox.showerror("Ошибка", "Выберите модель картриджа!")
            return
        available_cartridges = [c for c in cartridges_data["картриджи"] if
                                c["модель"] == model and c["статус"] == "на складе"]
        if not available_cartridges:
            messagebox.showerror("Ошибка", f"На складе нет картриджей модели '{model}'!")
            return
        cartridge_to_install = None
        if sn:
            for c in available_cartridges:
                if c.get("серийный_номер") == sn:
                    cartridge_to_install = c
                    break
            if not cartridge_to_install:
                messagebox.showerror("Ошибка", f"Картридж с серийным номером {sn} не найден на складе!")
                return
        else:
            cartridge_to_install = available_cartridges[0]
            sn = cartridge_to_install.get("серийный_номер", "N/A")
        now = datetime.now().isoformat()
        cartridge_to_install["статус"] = "в использовании"
        cartridge_to_install["дата_установки"] = now
        cartridge_to_install["принтер"] = "N/A"
        history_data["записи"].append({
            "модель_картриджа": model,
            "серийный_номер": sn,
            "принтер": "N/A",
            "дата_установки": now,
            "остаток_при_установке": cartridge_to_install.get("остаточный_ресурс", 100)
        })
        save_json(CARTRIDGES_FILE, cartridges_data)
        save_json(HISTORY_FILE, history_data)
        logging.info(f"Установлен картридж: {model}, SN: {sn}")
        self.model_var.set("")
        self.sn_entry.delete(0, END)
        update_stock_display(self.stock_tree, self.search_var.get())
        show_critical_alerts()
        messagebox.showinfo("Успех",
                            f"Картридж {model} (SN: {sn}) успешно установлен!\nКоличество на складе уменьшено.")

    def add_cartridge_to_warehouse(self):
        win = Toplevel(self.root)
        win.title("Добавить картридж на склад")
        win.geometry("500x200")
        Label(win, text="Модель:").pack(anchor=W, padx=20)
        model_var = StringVar()
        combo = ttk.Combobox(win, textvariable=model_var, values=get_cartridge_models_from_registry_only(), width=50)
        combo.pack(fill=X, padx=20, pady=(0, 10))
        Label(win, text="Серийный номер (опционально):").pack(anchor=W, padx=20)
        sn_entry = Entry(win, width=50)
        sn_entry.pack(fill=X, padx=20, pady=(0, 10))

        def save():
            model = model_var.get().strip()
            sn = sn_entry.get().strip()
            if not model:
                messagebox.showerror("Ошибка", "Укажите модель!")
                return
            new = {
                "модель": model,
                "серийный_номер": sn or "N/A",
                "статус": "на складе",
                "дата_поступления": datetime.now().isoformat(),
                "остаточный_ресурс": 100,
                "принтер": ""
            }
            cartridges_data["картриджи"].append(new)
            save_json(CARTRIDGES_FILE, cartridges_data)
            logging.info(f"Добавлен на склад: {model}, SN: {sn}")
            update_stock_display(self.stock_tree, self.search_var.get())
            win.destroy()
            messagebox.showinfo("Успех", "Картридж добавлен на склад!")

        Button(win, text="Сохранить", command=save).pack(pady=10)

    def show_history(self):
        win = Toplevel(self.root)
        win.title("История установок")
        win.geometry("800x500")
        columns = ("Модель", "Серийный", "Принтер", "Дата", "Остаток")
        tree = ttk.Treeview(win, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col)
        tree.pack(fill=BOTH, expand=True)
        for rec in history_data["записи"]:
            tree.insert("", "end", values=(
                rec["модель_картриджа"],
                rec["серийный_номер"],
                rec["принтер"],
                rec["дата_установки"][:16],
                rec["остаток_при_установке"]
            ))

    def export_csv(self):
        path = filedialog.asksaveasfilename(initialdir=DATA_DIR, defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        stock_data = get_stock_with_status()
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Модель", "Остаток", "Критический уровень", "Статус"])
            for item in stock_data:
                if self.search_var.get() and self.search_var.get().lower() not in item["модель"].lower():
                    continue
                writer.writerow([item["модель"], item["количество"], item["критический_уровень"], item["статус"]])
        messagebox.showinfo("Экспорт", "Данные экспортированы в CSV!")

    def export_pdf(self):
        path = filedialog.asksaveasfilename(initialdir=DATA_DIR, defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        pdf = FPDF()
        pdf.add_page()
        font_path = os.path.join(ASSETS_DIR, "ChakraPetch-Regular.ttf")
        if os.path.exists(font_path):
            pdf.add_font("ChakraPetch", "", font_path, uni=True)
            pdf.set_font("ChakraPetch", size=16)
        else:
            pdf.set_font("Arial", size=16)
            logging.warning("Шрифт ChakraPetch-Regular.ttf не найден, используется стандартный шрифт")
        pdf.cell(200, 10, txt="Signatum — Список картриджей к закупке", ln=True, align='C')
        if os.path.exists(font_path):
            pdf.set_font("ChakraPetch", size=12)
        else:
            pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}", ln=True, align='C')
        if self.search_var.get():
            pdf.cell(200, 10, txt=f"Фильтр: {self.search_var.get()}", ln=True, align='C')
        pdf.ln(10)
        stock_data = get_stock_with_status()
        if os.path.exists(font_path):
            pdf.set_font("ChakraPetch", size=10)
        else:
            pdf.set_font("Arial", size=10)
        col_width = 45
        pdf.cell(col_width, 10, "Модель", border=1)
        pdf.cell(col_width, 10, "Остаток", border=1)
        pdf.cell(col_width, 10, "Крит. уровень", border=1)
        pdf.cell(col_width, 10, "Статус", border=1)
        pdf.ln()
        for item in stock_data:
            if self.search_var.get() and self.search_var.get().lower() not in item["модель"].lower():
                continue
            pdf.cell(col_width, 10, item["модель"], border=1)
            pdf.cell(col_width, 10, str(item["количество"]), border=1)
            pdf.cell(col_width, 10, str(item["критический_уровень"]), border=1)
            pdf.cell(col_width, 10, item["статус"], border=1)
            pdf.ln()
        pdf.output(path)
        messagebox.showinfo("Экспорт", "Данные экспортированы в PDF!")

    def open_global_settings(self):
        win = Toplevel(self.root)
        win.title("Глобальные настройки")
        win.geometry("500x150")
        Label(win, text=f"Текущая папка данных:\n{DATA_DIR}", wraplength=480, justify=LEFT).pack(pady=10)

        def change_folder():
            new_folder = filedialog.askdirectory(title="Выберите новую папку для данных Signatum")
            if not new_folder:
                return
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({"data_directory": new_folder}, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Перезапуск", "Изменения вступят в силу после перезапуска программы.")
            win.destroy()

        Button(win, text="Изменить папку данных", command=change_folder).pack(pady=10)


# === Запуск ===
if __name__ == "__main__":
    root = Tk()
    app = CartridgeApp(root)
    root.mainloop()