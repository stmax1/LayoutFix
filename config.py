"""Настройки LayoutFix: %APPDATA%\\LayoutFix\\config.ini"""
import configparser
import os

APP_NAME = 'LayoutFix'
APP_VERSION = '1.0.1'

CONFIG_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.ini')

ACTIONS = {
    'word': 'Исправить последнее слово',
    'selection': 'Исправить выделенный текст',
    'phrase': 'Исправить всю фразу',
}
DEFAULT_HOTKEYS = {
    'word': 'pause',
    'selection': 'shift+pause',
    'phrase': 'scroll lock',
}


def is_first_run():
    return not os.path.exists(CONFIG_PATH)


def load_hotkeys():
    cfg = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        try:
            cfg.read(CONFIG_PATH, encoding='utf-8')
        except configparser.Error:
            pass
    section = cfg['hotkeys'] if cfg.has_section('hotkeys') else {}
    return {k: section.get(k, v).strip().lower() for k, v in DEFAULT_HOTKEYS.items()}


def save_hotkeys(hotkeys):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    cfg = configparser.ConfigParser()
    cfg['hotkeys'] = {k: hotkeys.get(k, '') for k in DEFAULT_HOTKEYS}
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.write('; Горячие клавиши LayoutFix. Удобнее менять через меню в трее -> Настройки.\n'
                '; Пустое значение — действие отключено.\n')
        cfg.write(f)
