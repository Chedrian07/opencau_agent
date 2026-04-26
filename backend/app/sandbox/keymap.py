from __future__ import annotations

KEY_MAP: dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "option": "alt",
    "meta": "super",
    "cmd": "super",
    "command": "super",
    "win": "super",
    "windows": "super",
    "super": "super",
    "enter": "Return",
    "return": "Return",
    "esc": "Escape",
    "escape": "Escape",
    "tab": "Tab",
    "space": "space",
    "spacebar": "space",
    "backspace": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "home": "Home",
    "end": "End",
    "pageup": "Page_Up",
    "pgup": "Page_Up",
    "pagedown": "Page_Down",
    "pgdn": "Page_Down",
    "arrowup": "Up",
    "up": "Up",
    "arrowdown": "Down",
    "down": "Down",
    "arrowleft": "Left",
    "left": "Left",
    "arrowright": "Right",
    "right": "Right",
    "insert": "Insert",
    "ins": "Insert",
    "capslock": "Caps_Lock",
    "printscreen": "Print",
    "scrolllock": "Scroll_Lock",
    "pause": "Pause",
    "menu": "Menu",
    "f1": "F1",
    "f2": "F2",
    "f3": "F3",
    "f4": "F4",
    "f5": "F5",
    "f6": "F6",
    "f7": "F7",
    "f8": "F8",
    "f9": "F9",
    "f10": "F10",
    "f11": "F11",
    "f12": "F12",
    "/": "slash",
    "\\": "backslash",
    "+": "plus",
    "-": "minus",
    "=": "equal",
    "[": "bracketleft",
    "]": "bracketright",
    "{": "braceleft",
    "}": "braceright",
    "(": "parenleft",
    ")": "parenright",
    ".": "period",
    ",": "comma",
    ";": "semicolon",
    "'": "apostrophe",
    "`": "grave",
    "~": "asciitilde",
    "!": "exclam",
    "@": "at",
    "#": "numbersign",
    "$": "dollar",
    "%": "percent",
    "^": "asciicircum",
    "&": "ampersand",
    "*": "asterisk",
    "?": "question",
    ":": "colon",
    "\"": "quotedbl",
    "<": "less",
    ">": "greater",
    "|": "bar",
    "_": "underscore",
}


def normalize_key(key: str) -> str:
    cleaned = key.strip()
    if not cleaned:
        raise ValueError("empty key in keypress")
    lower = cleaned.lower()
    if lower in KEY_MAP:
        return KEY_MAP[lower]
    if len(cleaned) == 1 and cleaned.isprintable():
        return cleaned
    return cleaned


def normalize_chord(keys: list[str]) -> str:
    if not keys:
        raise ValueError("keypress requires at least one key")
    return "+".join(normalize_key(key) for key in keys)
