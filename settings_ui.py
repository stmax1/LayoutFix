"""Окно настроек: запись горячих клавиш с клавиатуры, автозапуск."""
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from config import ACTIONS, APP_NAME, APP_VERSION, DEFAULT_HOTKEYS
from layout_map import RU2EN

MODIFIERS = {'ctrl', 'alt', 'shift', 'windows', 'left ctrl', 'right ctrl', 'left alt',
             'right alt', 'left shift', 'right shift', 'left windows', 'right windows', 'alt gr'}
STRONG_MODIFIERS = {'ctrl', 'alt', 'windows'}
TYPING_KEYS = {'space', 'enter', 'tab', 'backspace', 'delete', 'left', 'right', 'up', 'down',
               'home', 'end', 'page up', 'page down', 'insert'}


def normalize_hotkey(hk):
    """'Left Ctrl+Й' -> 'ctrl+q': единые имена модификаторов и латиница вместо кириллицы."""
    parts = []
    for p in (hk or '').lower().split('+'):
        p = p.strip()
        if not p:
            continue
        for side in ('left ', 'right '):
            if p.startswith(side) and p[len(side):] in ('ctrl', 'alt', 'shift', 'windows'):
                p = p[len(side):]
        if len(p) == 1 and p in RU2EN:
            p = RU2EN[p].lower()
        if p not in parts:
            parts.append(p)
    return '+'.join(parts)


def validate_hotkey(hk):
    """Возвращает текст ошибки или None."""
    if not hk:
        return None
    parts = hk.split('+')
    keys = [p for p in parts if p not in MODIFIERS]
    mods = {p for p in parts if p in MODIFIERS}
    if not keys:
        return 'Нужна хотя бы одна обычная клавиша, а не только модификаторы.'
    if keys[-1] == 'esc':
        return 'Esc зарезервирован для отмены.'
    printable = all(len(k) == 1 or k in TYPING_KEYS for k in keys)
    if printable and not (mods & STRONG_MODIFIERS):
        return ('Такое сочетание будет мешать обычному набору и редактированию текста.\n'
                'Добавьте Ctrl, Alt или Win, либо выберите Pause, Scroll Lock, F1–F12 и т.п.')
    return None


def pretty(hk):
    if not hk:
        return '— отключено —'
    return ' + '.join(p.title() if len(p) > 1 else p.upper() for p in hk.split('+'))


class SettingsWindow:
    def __init__(self, root, hotkeys, *, on_save, suspend_hotkeys, resume_hotkeys,
                 read_hotkey, autostart_get, autostart_set):
        self.on_save = on_save
        self.suspend_hotkeys = suspend_hotkeys
        self.resume_hotkeys = resume_hotkeys
        self.read_hotkey = read_hotkey
        self.autostart_set = autostart_set
        self.values = dict(hotkeys)
        self.recording = None
        self.result_q = queue.Queue()

        self.win = w = tk.Toplevel(root)
        w.title(f'{APP_NAME} — настройки')
        w.resizable(False, False)
        w.protocol('WM_DELETE_WINDOW', self.close)

        frm = ttk.Frame(w, padding=16)
        frm.grid(sticky='nsew')
        ttk.Label(frm, text='Горячие клавиши', font=('Segoe UI', 11, 'bold')).grid(
            row=0, column=0, columnspan=4, sticky='w', pady=(0, 8))

        self.labels, self.rec_buttons = {}, {}
        for i, (action, title) in enumerate(ACTIONS.items(), start=1):
            ttk.Label(frm, text=title).grid(row=i, column=0, sticky='w', padx=(0, 12), pady=4)
            lbl = ttk.Label(frm, text=pretty(self.values[action]), width=24,
                            relief='sunken', anchor='center', padding=(6, 3))
            lbl.grid(row=i, column=1, pady=4)
            self.labels[action] = lbl
            b = ttk.Button(frm, text='Изменить', command=lambda a=action: self.start_record(a))
            b.grid(row=i, column=2, padx=(8, 4))
            self.rec_buttons[action] = b
            ttk.Button(frm, text='Отключить', command=lambda a=action: self.set_value(a, '')).grid(
                row=i, column=3)

        self.hint = ttk.Label(frm, foreground='#555', justify='left',
                              text='«Изменить» → нажмите нужное сочетание. Esc — отмена.\n'
                                   'Для ноутбука удобно: Caps Lock, Shift+Caps Lock, '
                                   'Ctrl+Alt+Space.\nF1–F12 на ноутбуке может понадобиться '
                                   'нажимать вместе с Fn.')
        self.hint.grid(row=4, column=0, columnspan=4, sticky='w', pady=(10, 6))

        self.autostart_var = tk.BooleanVar(value=autostart_get())
        ttk.Checkbutton(frm, text='Запускать вместе с Windows',
                        variable=self.autostart_var).grid(row=5, column=0, columnspan=4,
                                                          sticky='w', pady=(4, 12))

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=4, sticky='ew')
        ttk.Label(btns, text=f'v{APP_VERSION}', foreground='#888').pack(side='left')
        ttk.Button(btns, text='Отмена', command=self.close).pack(side='right')
        ttk.Button(btns, text='Сохранить', command=self.save).pack(side='right', padx=6)
        ttk.Button(btns, text='По умолчанию', command=self.reset_defaults).pack(side='right')

        w.update_idletasks()
        x = (w.winfo_screenwidth() - w.winfo_width()) // 2
        y = (w.winfo_screenheight() - w.winfo_height()) // 3
        w.geometry(f'+{x}+{y}')
        self.focus()
        self._poll()

    # --- служебное ---
    def exists(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def focus(self):
        self.win.deiconify()
        self.win.lift()
        self.win.attributes('-topmost', True)
        self.win.after(200, lambda: self.win.attributes('-topmost', False))
        self.win.focus_force()

    def set_value(self, action, hk):
        self.values[action] = hk
        self.labels[action].config(text=pretty(hk))

    def reset_defaults(self):
        for a, hk in DEFAULT_HOTKEYS.items():
            self.set_value(a, hk)

    # --- запись сочетания ---
    def start_record(self, action):
        if self.recording:
            return
        self.recording = action
        self.labels[action].config(text='Нажмите сочетание…')
        for b in self.rec_buttons.values():
            b.state(['disabled'])
        self.suspend_hotkeys()

        def worker():
            try:
                hk = self.read_hotkey()
            except Exception:
                hk = 'esc'
            self.result_q.put(hk)

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            hk = self.result_q.get_nowait()
        except queue.Empty:
            pass
        else:
            self._finish_record(hk)
        if self.exists():
            self.win.after(50, self._poll)

    def _finish_record(self, raw):
        action, self.recording = self.recording, None
        for b in self.rec_buttons.values():
            b.state(['!disabled'])
        self.resume_hotkeys()
        hk = normalize_hotkey(raw)
        if hk in ('', 'esc'):
            self.labels[action].config(text=pretty(self.values[action]))
            return
        err = validate_hotkey(hk)
        if err:
            self.labels[action].config(text=pretty(self.values[action]))
            messagebox.showwarning(APP_NAME, f'{pretty(hk)}\n\n{err}', parent=self.win)
            return
        for other, val in self.values.items():
            if other != action and val == hk:
                if not messagebox.askyesno(
                        APP_NAME, f'{pretty(hk)} уже назначено на «{ACTIONS[other]}».\n'
                                  f'Переназначить?', parent=self.win):
                    self.labels[action].config(text=pretty(self.values[action]))
                    return
                self.set_value(other, '')
        self.set_value(action, hk)
        self.win.focus_force()

    # --- сохранение ---
    def save(self):
        if self.recording:
            return
        try:
            self.on_save(dict(self.values))
            self.autostart_set(self.autostart_var.get())
        except Exception as ex:
            messagebox.showerror(APP_NAME, f'Не удалось сохранить:\n{ex}', parent=self.win)
            return
        self.close()

    def close(self):
        if self.recording:
            self.recording = None
            self.resume_hotkeys()
        self.win.destroy()
