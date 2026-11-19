# SPDX-License-Identifier: GPL-2.0-or-later
"""Model for input.ini (shadPS4 syntax: output = input, one input per line)."""
import shutil
from pathlib import Path

ACTIONS: list[tuple[str, str]] = [
    ("cross", "Cross"),
    ("circle", "Circle"),
    ("square", "Square"),
    ("triangle", "Triangle"),
    ("l1", "L1"),
    ("r1", "R1"),
    ("l2", "L2"),
    ("r2", "R2"),
    ("l3", "L3"),
    ("r3", "R3"),
    ("options", "OPTIONS (pause menu)"),
    ("pad_up", "D-pad up"),
    ("pad_down", "D-pad down"),
    ("pad_left", "D-pad left"),
    ("pad_right", "D-pad right"),
    ("touchpad_left", "Touchpad left"),
    ("touchpad_center", "Touchpad center"),
    ("touchpad_right", "Touchpad right"),
    ("axis_left_x_minus", "Left stick left"),
    ("axis_left_x_plus", "Left stick right"),
    ("axis_left_y_minus", "Left stick up"),
    ("axis_left_y_plus", "Left stick down"),
    ("axis_right_x_minus", "Right stick left"),
    ("axis_right_x_plus", "Right stick right"),
    ("axis_right_y_minus", "Right stick up"),
    ("axis_right_y_plus", "Right stick down"),
]

_OUTPUTS = frozenset(o for o, _ in ACTIONS)

CONTROLLER_INPUTS = frozenset({
    "cross", "circle", "square", "triangle", "l1", "r1", "l2", "r2", "l3", "r3",
    "options", "back", "pad_up", "pad_down", "pad_left", "pad_right",
    "axis_left_x", "axis_left_y", "axis_right_x", "axis_right_y",
})

MOUSE_INPUTS = frozenset({
    "leftbutton", "rightbutton", "middlebutton", "sidebuttonback", "sidebuttonforward",
    "mousewheelup", "mousewheeldown", "mousewheelleft", "mousewheelright",
})

_KB, _CTRL, _MOUSE = "keyboard", "controller", "mouse"


def _parse(line: str):
    """(output, input) for a binding of an ACTIONS output, else None."""
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    out, inp = (p.strip() for p in s.split("=", 1))
    if out not in _OUTPUTS or not inp:
        return None
    return out, inp


def _kind(inp: str) -> str:
    if inp in MOUSE_INPUTS:
        return _MOUSE
    if inp in CONTROLLER_INPUTS:
        return _CTRL
    return _KB


class InputConfig:
    def __init__(self, lines: list[str]):
        self.lines = lines

    @classmethod
    def load(cls, path: Path) -> "InputConfig":
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            text = ""
        return cls(text.splitlines())

    def _values(self, output: str, kind: str) -> list[str]:
        res = []
        for line in self.lines:
            p = _parse(line)
            if p and p[0] == output and _kind(p[1]) == kind:
                res.append(p[1])
        return res

    def keyboard(self, output: str) -> list[str]:
        return self._values(output, _KB)

    def controller(self, output: str) -> list[str]:
        return self._values(output, _CTRL)

    def mouse(self, output: str) -> list[str]:
        return self._values(output, _MOUSE)

    def _set(self, output: str, value: str, kind: str) -> None:
        new = f"{output} = {value}"
        mine = []
        last_of_kind = -1
        for i, line in enumerate(self.lines):
            p = _parse(line)
            if p and _kind(p[1]) == kind:
                last_of_kind = i
                if p[0] == output:
                    mine.append(i)
        if mine:
            self.lines[mine[0]] = new
            for i in reversed(mine[1:]):
                del self.lines[i]
        elif last_of_kind >= 0:
            self.lines.insert(last_of_kind + 1, new)
        else:
            self.lines.append(new)

    def set_keyboard(self, output: str, key: str) -> None:
        self._set(output, key, _KB)

    def set_controller(self, output: str, button: str) -> None:
        self._set(output, button, _CTRL)

    def set_mouse(self, output: str, button: str) -> list[str]:
        """Binds a mouse button or wheel direction to output, moving it off the other actions
        (a mouse has few buttons; one doing two actions is never wanted). Returns those actions."""
        moved = [p[0] for p in map(_parse, self.lines) if p and p[0] != output and p[1] == button]
        self._set(output, button, _MOUSE)
        self.lines = [l for l in self.lines
                      if not ((p := _parse(l)) and p[0] != output and p[1] == button)]
        return moved

    def remove_mouse(self, output: str, button: str) -> None:
        self.lines = [l for l in self.lines if _parse(l) != (output, button)]

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(self.lines) + "\n")

    @staticmethod
    def reset(path: Path, default: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(default, path)


_TK_SPECIAL = {
    "space": "space", "Return": "enter", "KP_Enter": "enter", "BackSpace": "backspace",
    "Tab": "tab", "Escape": "escape", "Up": "up", "Down": "down", "Left": "left",
    "Right": "right", "Shift_L": "lshift", "Shift_R": "rshift", "Control_L": "lctrl",
    "Control_R": "rctrl", "Alt_L": "lalt", "Alt_R": "ralt", "Home": "home", "End": "end",
    "Prior": "pgup", "Next": "pgdown", "Delete": "delete", "Insert": "insert",
    "Caps_Lock": "capslock",
}


def _number_row_digit(keycode: int, windowing: str) -> str | None:
    """Digit of a number-row key from its key code, whatever character the layout gives it.
    Windows sends the virtual key ('0'-'9' on every layout), X11 the physical key (10-19)."""
    if windowing == "win32" and 0x30 <= keycode <= 0x39:
        return chr(keycode)
    if windowing == "x11" and 10 <= keycode <= 19:
        return str((keycode - 9) % 10)
    return None


def tk_key_name(keysym: str, keycode: int | None = None, windowing: str = "") -> str | None:
    """Tk keysym -> input.ini key name, None when unsupported.

    Names follow what the key types (the runtime resolves them through the active layout),
    except the number row: on AZERTY it types & é " ... unshifted, yet the runtime (SDL)
    still calls it 1 2 3, so those keys are named by keycode (tk windowingsystem)."""
    if keysym in _TK_SPECIAL:
        return _TK_SPECIAL[keysym]
    if len(keysym) == 1 and keysym.isascii() and keysym.isalnum():
        return keysym.lower()
    if keysym.startswith("F") and keysym[1:].isdigit() and 1 <= int(keysym[1:]) <= 12:
        return keysym.lower()
    if keycode is not None:
        return _number_row_digit(keycode, windowing)
    return None
