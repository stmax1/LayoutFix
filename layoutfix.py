"""LayoutFix — переключатель раскладки по запросу (аналог Punto Switcher без автозамены).

Горячие клавиши по умолчанию (меняются в трее -> Настройки):
  Pause         — исправить последнее набранное слово (повторное нажатие — вернуть обратно)
  Shift+Pause   — исправить выделенный текст
  Scroll Lock   — исправить всю набранную фразу (с момента последнего Enter/клика)
"""
import ctypes
import ctypes.wintypes as wt
import os
import queue
import sys
import threading
import time
import tkinter as tk
import winreg

import keyboard
import mouse
import pyperclip
import pystray
from PIL import Image

from config import APP_NAME, APP_VERSION, is_first_run, load_hotkeys, save_hotkeys
from layout_map import KEYS, SPACE_SC, convert_text, render
from settings_ui import SettingsWindow, normalize_hotkey, pretty, validate_hotkey

LANG_RU, LANG_EN = 0x19, 0x09
WM_INPUTLANGCHANGEREQUEST = 0x0050
VK_CAPITAL = 0x14
MAX_BUFFER = 300

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetKeyboardLayout.argtypes = [wt.DWORD]
user32.GetKeyboardLayout.restype = ctypes.c_void_p
user32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.c_void_p]
user32.GetKeyboardLayoutList.restype = ctypes.c_int
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
kernel32.CreateEventW.restype = wt.HANDLE
kernel32.OpenEventW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
kernel32.OpenEventW.restype = wt.HANDLE
kernel32.SetEvent.argtypes = [wt.HANDLE]
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
kernel32.WaitForSingleObject.restype = wt.DWORD
EVENT_MODIFY_STATE = 0x0002
SHOW_EVENT = 'Local\\LayoutFixShowSettings'


def resource(name):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# ---------- раскладки Windows ----------

def foreground_layout():
    hwnd = user32.GetForegroundWindow()
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    return user32.GetKeyboardLayout(tid) or 0


def is_ru_now():
    return (foreground_layout() & 0x3FF) == LANG_RU


def find_layout(primary_lang):
    n = user32.GetKeyboardLayoutList(0, None)
    arr = (ctypes.c_void_p * n)()
    user32.GetKeyboardLayoutList(n, arr)
    for hkl in arr:
        if hkl and (hkl & 0x3FF) == primary_lang:
            return hkl
    return None


def switch_layout(ru):
    hkl = find_layout(LANG_RU if ru else LANG_EN)
    if hkl:
        user32.PostMessageW(user32.GetForegroundWindow(), WM_INPUTLANGCHANGEREQUEST, 0, hkl)


# ---------- автозапуск ----------

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def autostart_command():
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    pyw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    return f'"{pyw}" "{os.path.abspath(__file__)}"'


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(on):
    if on == autostart_enabled():
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


# ---------- основная логика ----------

class Switcher:
    MODIFIER_NAMES = {'shift', 'left shift', 'right shift', 'caps lock'}

    def __init__(self):
        self.hotkeys = {}
        self.hotkey_keys = set()
        self.handles = []
        self.buf = []           # [(scan_code, shift, caps), ...]
        self.hwnd = None
        self.lock = threading.Lock()
        self.busy = False
        self.enabled = True
        self.q = queue.Queue()

    # --- горячие клавиши ---
    def _register(self, hotkeys):
        for action, hk in hotkeys.items():
            if hk:
                self.handles.append(
                    keyboard.add_hotkey(hk, self.request, args=(action,), suppress=True))

    def clear_hotkeys(self):
        for h in self.handles:
            try:
                keyboard.remove_hotkey(h)
            except (KeyError, ValueError):
                pass
        self.handles = []

    def set_hotkeys(self, hotkeys):
        old = dict(self.hotkeys)
        self.clear_hotkeys()
        try:
            self._register(hotkeys)
        except Exception:
            self.clear_hotkeys()
            self._register(old)
            raise
        self.hotkeys = dict(hotkeys)
        self.hotkey_keys = {hk.split('+')[-1] for hk in hotkeys.values() if hk}

    def suspend_hotkeys(self):
        self.clear_hotkeys()

    def resume_hotkeys(self):
        if not self.handles:
            self._register(self.hotkeys)

    # --- отслеживание набора ---
    def reset(self, *_):
        with self.lock:
            self.buf.clear()

    def on_key(self, e):
        if e.event_type != 'down' or self.busy:
            return
        name = (e.name or '').lower()
        if name in self.MODIFIER_NAMES or name in self.hotkey_keys:
            return
        hwnd = user32.GetForegroundWindow()
        with self.lock:
            if hwnd != self.hwnd:
                self.buf.clear()
                self.hwnd = hwnd
            if name == 'backspace':
                if self.buf:
                    self.buf.pop()
                return
            if (keyboard.is_pressed('ctrl') or keyboard.is_pressed('alt')
                    or keyboard.is_pressed('windows')):
                self.buf.clear()
                return
            sc = e.scan_code
            if sc in KEYS and not e.is_keypad:
                shift = keyboard.is_pressed('shift')
                caps = bool(user32.GetKeyState(VK_CAPITAL) & 1)
                self.buf.append((sc, shift, caps))
                if len(self.buf) > MAX_BUFFER:
                    del self.buf[:-MAX_BUFFER]
            else:
                # Enter, Tab, стрелки, Home/End, Delete и т.п. — начинаем заново
                self.buf.clear()

    def on_mouse(self, e):
        if isinstance(e, mouse.ButtonEvent) and e.event_type == 'down':
            self.reset()

    # --- выполнение команд ---
    def request(self, action):
        if self.enabled:
            self.q.put(action)

    def worker(self):
        while True:
            action = self.q.get()
            try:
                self._wait_modifiers_released()
                getattr(self, 'do_' + action)()
            except Exception as ex:  # не роняем программу из-за одного сбоя
                print('Ошибка:', ex, file=sys.stderr)

    @staticmethod
    def _wait_modifiers_released(timeout=1.5):
        end = time.time() + timeout
        while time.time() < end and any(
                keyboard.is_pressed(m) for m in ('shift', 'ctrl', 'alt', 'windows')):
            time.sleep(0.01)

    def _retype(self, segment):
        target_ru = not is_ru_now()
        text = render(segment, target_ru)
        self.busy = True
        try:
            for _ in segment:
                keyboard.send('backspace')
            keyboard.write(text, exact=True)
            switch_layout(target_ru)
        finally:
            time.sleep(0.1)  # даём хуку «пропустить» наши собственные нажатия
            self.busy = False

    def do_word(self):
        with self.lock:
            buf = list(self.buf)
        i = len(buf)
        while i > 0 and buf[i - 1][0] == SPACE_SC:   # хвостовые пробелы
            i -= 1
        while i > 0 and buf[i - 1][0] != SPACE_SC:   # само слово
            i -= 1
        segment = buf[i:]
        if any(sc != SPACE_SC for sc, _, _ in segment):
            self._retype(segment)

    def do_phrase(self):
        with self.lock:
            segment = list(self.buf)
        if segment:
            self._retype(segment)

    def do_selection(self):
        try:
            saved = pyperclip.paste()
        except Exception:
            saved = None
        self.busy = True
        try:
            pyperclip.copy('')
            keyboard.send('ctrl+c')
            text = ''
            end = time.time() + 0.6
            while time.time() < end:
                time.sleep(0.03)
                text = pyperclip.paste()
                if text:
                    break
            if not text:
                return
            text = text.replace('\r\n', '\n')
            new_text, target_ru = convert_text(text)
            keyboard.write(new_text, exact=True)
            # снова выделяем вставленное, чтобы повторное нажатие вернуло как было
            if len(new_text) <= 500:
                for _ in new_text:
                    keyboard.send('shift+left')
            switch_layout(target_ru)
        finally:
            time.sleep(0.15)
            if saved is not None:
                try:
                    pyperclip.copy(saved)
                except Exception:
                    pass
            self.busy = False
            self.reset()

    def start(self, hotkeys):
        keyboard.hook(self.on_key)
        mouse.hook(self.on_mouse)
        threading.Thread(target=self.worker, daemon=True).start()
        bad = {}
        for action, hk in hotkeys.items():   # битые значения из config.ini не роняют запуск
            try:
                self.set_hotkeys({**self.hotkeys, action: hk})
            except Exception:
                bad[action] = hk
                self.hotkeys[action] = ''
        return bad


# ---------- приложение ----------

def main():
    kernel32.CreateMutexW(None, False, 'Local\\LayoutFixSingleInstance')
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        # уже запущено — просим ту копию открыть настройки
        ev = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, SHOW_EVENT)
        if ev:
            kernel32.SetEvent(ev)
        return
    show_event = kernel32.CreateEventW(None, False, False, SHOW_EVENT)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    first_run = is_first_run()
    hotkeys = {a: normalize_hotkey(hk) for a, hk in load_hotkeys().items()}
    hotkeys = {a: ('' if validate_hotkey(hk) else hk) for a, hk in hotkeys.items()}
    if first_run:
        save_hotkeys(hotkeys)

    sw = Switcher()
    bad = sw.start(hotkeys)

    root = tk.Tk()
    root.withdraw()
    try:
        root.iconbitmap(default=resource('icon.ico'))
    except tk.TclError:
        pass

    ui_q = queue.Queue()
    settings = {'win': None}
    icon_img = Image.open(resource('icon.ico'))
    off_img = icon_img.convert('LA').convert('RGBA')

    def hint():
        h = sw.hotkeys
        return (f"Слово: {pretty(h.get('word'))}\nВыделение: {pretty(h.get('selection'))}\n"
                f"Фраза: {pretty(h.get('phrase'))}")

    def apply_hotkeys(new):
        sw.set_hotkeys(new)
        save_hotkeys(new)
        icon.title = f'{APP_NAME}\n{hint()}'[:127]
        icon.update_menu()

    def open_settings():
        w = settings['win']
        if w and w.exists():
            w.focus()
            return
        settings['win'] = SettingsWindow(
            root, sw.hotkeys,
            on_save=apply_hotkeys,
            suspend_hotkeys=sw.suspend_hotkeys,
            resume_hotkeys=sw.resume_hotkeys,
            read_hotkey=lambda: keyboard.read_hotkey(suppress=False),
            autostart_get=autostart_enabled,
            autostart_set=set_autostart,
        )

    def toggle_enabled(icon_, _):
        sw.enabled = not sw.enabled
        sw.reset()
        icon_.icon = icon_img if sw.enabled else off_img

    def quit_app(icon_, _):
        keyboard.unhook_all()
        mouse.unhook_all()
        icon_.stop()
        ui_q.put(root.quit)

    menu = pystray.Menu(
        pystray.MenuItem(lambda _: f'Слово: {pretty(sw.hotkeys.get("word"))}', None, enabled=False),
        pystray.MenuItem(lambda _: f'Выделение: {pretty(sw.hotkeys.get("selection"))}', None,
                         enabled=False),
        pystray.MenuItem(lambda _: f'Фраза: {pretty(sw.hotkeys.get("phrase"))}', None,
                         enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Включено', toggle_enabled, checked=lambda _: sw.enabled),
        pystray.MenuItem('Настройки…', lambda *_: ui_q.put(open_settings), default=True),
        pystray.MenuItem('Выход', quit_app),
    )
    icon = pystray.Icon(APP_NAME, icon_img, f'{APP_NAME}\n{hint()}'[:127], menu)

    def on_ready(icon_):
        icon_.visible = True
        if bad:
            icon_.notify('Некоторые сочетания не удалось назначить — проверьте настройки.',
                         APP_NAME)
            ui_q.put(open_settings)
        elif first_run:
            icon_.notify(f'Pause — исправить слово, Shift+Pause — выделение.\n'
                         f'Настройки — клик по значку в трее.', f'{APP_NAME} {APP_VERSION}')

    threading.Thread(target=icon.run, kwargs={'setup': on_ready}, daemon=True).start()

    def poll():
        while not ui_q.empty():
            ui_q.get_nowait()()
        root.after(100, poll)

    def wait_show_requests():
        while True:
            if kernel32.WaitForSingleObject(show_event, 0xFFFFFFFF) == 0:
                ui_q.put(open_settings)

    threading.Thread(target=wait_show_requests, daemon=True).start()
    if '--settings' in sys.argv:
        ui_q.put(open_settings)
    root.after(100, poll)
    root.mainloop()


if __name__ == '__main__':
    main()
