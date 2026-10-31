"""Таблица соответствия физических клавиш раскладкам EN (QWERTY) и RU (ЙЦУКЕН).

Ключ — scan code клавиши (set 1), значение — (en, EN_shift, ru, RU_shift).
"""

KEYS = {
    0x29: ('`', '~', 'ё', 'Ё'),
    0x02: ('1', '!', '1', '!'),
    0x03: ('2', '@', '2', '"'),
    0x04: ('3', '#', '3', '№'),
    0x05: ('4', '$', '4', ';'),
    0x06: ('5', '%', '5', '%'),
    0x07: ('6', '^', '6', ':'),
    0x08: ('7', '&', '7', '?'),
    0x09: ('8', '*', '8', '*'),
    0x0A: ('9', '(', '9', '('),
    0x0B: ('0', ')', '0', ')'),
    0x0C: ('-', '_', '-', '_'),
    0x0D: ('=', '+', '=', '+'),
    0x1A: ('[', '{', 'х', 'Х'),
    0x1B: (']', '}', 'ъ', 'Ъ'),
    0x27: (';', ':', 'ж', 'Ж'),
    0x28: ("'", '"', 'э', 'Э'),
    0x2B: ('\\', '|', '\\', '/'),
    0x33: (',', '<', 'б', 'Б'),
    0x34: ('.', '>', 'ю', 'Ю'),
    0x35: ('/', '?', '.', ','),
    0x39: (' ', ' ', ' ', ' '),
}

# Буквенные ряды
for start, en, ru in (
    (0x10, 'qwertyuiop', 'йцукенгшщз'),
    (0x1E, 'asdfghjkl', 'фывапролд'),
    (0x2C, 'zxcvbnm', 'ячсмить'),
):
    for i, (e, r) in enumerate(zip(en, ru)):
        KEYS[start + i] = (e, e.upper(), r, r.upper())

SPACE_SC = 0x39


def char_for(sc, shift, caps, ru):
    """Символ, который даёт клавиша в указанной раскладке."""
    en_l, en_s, ru_l, ru_s = KEYS[sc]
    lower, upper = (ru_l, ru_s) if ru else (en_l, en_s)
    ch = upper if shift else lower
    if caps and lower.isalpha():  # CapsLock влияет только на буквы
        ch = lower if shift else lower.upper()
    return ch


def render(entries, ru):
    """entries: список (scan_code, shift, caps) -> строка в нужной раскладке."""
    return ''.join(char_for(sc, sh, cp, ru) for sc, sh, cp in entries)


# Посимвольные словари для конвертации готового (выделенного) текста
EN2RU, RU2EN = {}, {}
for en_l, en_s, ru_l, ru_s in KEYS.values():
    for e, r in ((en_l, ru_l), (en_s, ru_s)):
        if e != r:
            EN2RU.setdefault(e, r)
            RU2EN.setdefault(r, e)
            # заглавные буквы через CapsLock/Shift
            if e.isalpha() and r.isalpha():
                EN2RU.setdefault(e.swapcase(), r.swapcase())
                RU2EN.setdefault(r.swapcase(), e.swapcase())


def text_is_russian(text):
    """True, если в тексте больше кириллицы, чем латиницы."""
    cyr = sum(1 for c in text if c in RU2EN and c.isalpha())
    lat = sum(1 for c in text if c in EN2RU and c.isalpha())
    return cyr > lat


def convert_text(text):
    """Конвертирует текст в противоположную раскладку.
    Возвращает (новый_текст, целевая_раскладка_ru: bool)."""
    if text_is_russian(text):
        return ''.join(RU2EN.get(c, c) for c in text), False
    return ''.join(EN2RU.get(c, c) for c in text), True
