import contextlib
import ctypes
import math
import os
import select
import shutil
import sys
import textwrap
import time
from functools import lru_cache
from dataclasses import dataclass

from ocean import CYAN, GOLD, H, RED, W, WHITE, arena, receiver, recorder, title

RESET = "\x1b[0m"
ERASE = "\x1b[K"
DIM = 0xa3b5b7


@lru_cache(maxsize=8192)
def truecolor(value, bg=False):
    return f"\x1b[{48 if bg else 38};2;{value >> 16};{(value >> 8) & 255};{value & 255}m"


@lru_cache(maxsize=4096)
def gray(value):
    return ((value >> 16) * 54 + ((value >> 8) & 255) * 183 + (value & 255) * 19) >> 8


def image_rows(canvas, width, height, color):
    output = []
    xs = [min(W - 1, (2 * x + 1) * W // (2 * width)) for x in range(width)]
    ramp = " .,:;+*x%#@"
    for row in range(height):
        top = min(H - 1, (4 * row + 1) * H // (height * 4)) * W
        low = min(H - 1, (4 * row + 3) * H // (height * 4)) * W
        text = []
        fg = bg = -1
        for x in xs:
            a, b = canvas.pixels[top + x], canvas.pixels[low + x]
            if not color:
                text.append(ramp[min(10, (gray(a) + gray(b)) * 11 // 490)])
            elif a == b:
                if bg != a:
                    text.append(truecolor(a, True))
                    bg = a
                text.append(" ")
            else:
                if fg != a:
                    text.append(truecolor(a))
                    fg = a
                if bg != b:
                    text.append(truecolor(b, True))
                    bg = b
                text.append("▀")
        output.append("".join(text) + (RESET if color else ""))
    return output


def windows_modes(stack):
    import msvcrt
    kernel = ctypes.WinDLL("kernel32")
    for stream, flags in ((sys.stdout, 0x0004), (sys.stdin, None)):
        handle = ctypes.c_void_p(msvcrt.get_osfhandle(stream.fileno()))
        mode = ctypes.c_uint32()
        if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            raise OSError("VT terminal unavailable")
        updated = mode.value | flags if flags else mode.value & ~0x0006
        if not kernel.SetConsoleMode(handle, updated):
            raise OSError("Console mode unavailable")
        stack.callback(kernel.SetConsoleMode, handle, mode.value)


class Terminal:
    def __init__(self, simple=False):
        self.live = bool(not simple and sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM") != "dumb")
        self.color = self.live and "NO_COLOR" not in os.environ
        self.stack = contextlib.ExitStack()
        self.last_shape = None

    def __enter__(self):
        if self.live:
            try:
                if os.name == "nt":
                    windows_modes(self.stack)
                else:
                    import termios
                    import tty
                    fd = sys.stdin.fileno()
                    previous = termios.tcgetattr(fd)
                    tty.setcbreak(fd)
                    self.stack.callback(termios.tcsetattr, fd, termios.TCSADRAIN, previous)
            except (OSError, ValueError):
                self.stack.close()
                self.live = self.color = False
        if self.live:
            sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")
            sys.stdout.flush()
        return self

    def __exit__(self, *exc):
        try:
            if self.live:
                sys.stdout.write(RESET + "\x1b[?25h\x1b[?1049l")
                sys.stdout.flush()
        finally:
            self.stack.close()

    def read(self, timeout=None):
        if not self.live:
            line = sys.stdin.readline()
            return line.strip().lower() if line else "q"
        if os.name == "nt":
            import msvcrt
            end = time.monotonic() + timeout if timeout is not None else None
            while not msvcrt.kbhit():
                if end is not None and time.monotonic() >= end:
                    return None
                time.sleep(.008)
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                msvcrt.getwch()
                return ""
        else:
            if not select.select([sys.stdin], [], [], timeout)[0]:
                return None
            raw = os.read(sys.stdin.fileno(), 1)
            if not raw:
                return "q"
            if raw == b"\x1b" and select.select([sys.stdin], [], [], .002)[0]:
                more = os.read(sys.stdin.fileno(), 1)
                if more in (b"[", b"O"):
                    while select.select([sys.stdin], [], [], .002)[0]:
                        if 0x40 <= os.read(sys.stdin.fileno(), 1)[0] <= 0x7e:
                            break
                    return ""
                return "esc"
            key = raw.decode("ascii", "ignore")
        if key in ("\x03", "\x04", "\x1a"):
            return "q"
        if key in ("\x08", "\x7f"):
            return "back"
        if key in ("\r", "\n"):
            return "enter"
        if key == "\x1b":
            return "esc"
        return key.lower()

    @property
    def size(self):
        actual = shutil.get_terminal_size((100, 32))
        return min(118, max(16, actual.columns - 1)), max(7, actual.lines)

    def ink(self, text, color):
        return truecolor(color) + text + RESET if self.color else text

    def show(self, rows):
        if not self.live:
            print("\n".join(rows), flush=True)
            return
        shape = self.size
        clear = "\x1b[2J" if self.last_shape != shape else ""
        self.last_shape = shape
        output = "\x1b[H" + (ERASE + "\r\n").join(rows[:shape[1] - 1]) + ERASE + "\x1b[J"
        sys.stdout.write(clear + output)
        sys.stdout.flush()


def meter(value, maximum, length):
    lit = math.ceil(length * value / maximum)
    return "▰" * lit + "▱" * (length - lit)


@dataclass
class HullReading:
    hull: int
    maximum: int


@dataclass
class RigReading(HullReading):
    name: str
    skill: str
    equipment: str
    cells: int


class CombatView:
    def __init__(self, game):
        pilot = game.pilot
        self.pilot = RigReading(pilot.hull, pilot.maximum, pilot.name, pilot.skill,
                                pilot.equipment, len(pilot.pack))
        self.contact = HullReading(game.contact.hull, game.contact.maximum)
        self.sector, self.index = game.sector, game.index
        self.pulse, self.noise = game.pulse, game.noise
        self.can_tune, self.status = game.can_tune, game.status
        self.final_noise = self.noise
        self.final_equipment = self.pilot.equipment

    def finish(self, game):
        self.final_noise = game.noise
        if self.index == game.index:
            self.final_equipment = game.pilot.equipment

    def apply(self, event):
        if event.kind in ("cutter", "resonate", "decoy"):
            self.contact.hull -= event.points
        elif event.kind == "counter":
            self.pilot.hull -= event.points
        elif event.kind == "repair":
            self.pilot.hull += event.points
            self.pilot.cells -= 1
        if event.kind == "decoy":
            self.pilot.cells -= 1
        if event.kind in ("cutter", "anchor", "decoy", "resonate"):
            self.noise = self.final_noise
            self.can_tune = self.noise == 2
            self.pilot.equipment = self.final_equipment


class Display:
    def __init__(self, terminal):
        self.term = terminal

    def _screen(self, header, canvas, footer, banner=""):
        w, h = self.term.size
        rows = [self.term.ink(header[:w], GOLD)]
        if banner:
            rows.append(self.term.ink(banner[:w], WHITE))
        details = []
        for text, color in footer:
            for line in textwrap.wrap(text, w, break_long_words=True, replace_whitespace=True) or [""]:
                details.append(self.term.ink(line, color))
        available = h - len(rows) - len(details) - 1
        if canvas is not None and available >= 3 and self.term.live:
            height = min(26, round(w * H / (2 * W)), available)
            width = min(w, max(20, round(height * 2 * W / H)))
            margin = " " * max(0, (w - width) // 2)
            rows.extend(margin + line for line in image_rows(canvas, width, height, self.term.color))
        self.term.show(rows + details)

    def menu(self, now, sound):
        self._screen("PELAGIC STATION   /   AUTONOMOUS RESCUE DIVISION", title(now) if self.term.live else None, [
            ("BLACK BOX   /   HYDROPHONE EDITION", GOLD),
            ("Twelve years silent. Six minutes ago the station called you by name.", WHITE),
            ("[1] RIVET   Brass salvage rig. Anchor twice per sector to block a pulse.", CYAN),
            ("[2] ECHO    Acoustic rig. Spend one cell to send a pulse back.", CYAN),
            (f"[D] Watch a dive     [M] Audio {sound}     [Q] Surface", DIM),
        ])

    def battle(self, game, message, now, sound, kind="idle", phase=0., phrase=None, closed=False):
        w, _ = self.term.size
        pilot, contact = game.pilot, game.contact
        hull = f"{pilot.name.upper()}  {pilot.hull:02}/{pilot.maximum}"
        target = f"{game.sector.contact.upper()}  {contact.hull:02}/{contact.maximum}"
        if w >= 65:
            hull += "  " + meter(pilot.hull, pilot.maximum, 10)
            target += "  " + meter(contact.hull, contact.maximum, 8)
        gap = " " * max(3, min(w - len(hull) - len(target), 10))
        header = f"BLACK BOX    /    {game.sector.room.upper()}    /    {game.sector.depth:04} m"
        if w > 74:
            header += f"     REEL {game.index + 1:02} / 04"
        sonar = f"NOISE {'●' * game.noise}{'○' * (3 - game.noise)}   CELLS {pilot.cells}   {pilot.equipment.upper()}"
        if game.can_tune:
            sonar += "   •   F: MATCH OPEN"
        next_hit = f"NEXT PULSE {game.pulse}" + ("   (+3 if you strike)" if game.noise == 2 else "")
        footer = [(hull + gap + target, WHITE), (sonar, CYAN)]
        if not closed:
            footer.append((next_hit, GOLD))
        footer.append((message, RED if kind == "counter" or game.status == "lost" else DIM))
        if phrase is not None:
            signal = "  ".join(game.sector.song)
            entered = "  ".join(list(phrase) + ["·"] * (3 - len(phrase)))
            footer += [(f"HYDROPHONE    CALL  {signal}      ANSWER  {entered}", CYAN),
                       ("[1] Low  [2] Mid  [3] High    [L] Replay    [X] Cancel", WHITE)]
        elif closed:
            footer.append(("[Enter / Q] Return to surface", GOLD))
        else:
            footer.append((f"[A] Cut  [S] {pilot.skill}  [R] Repair  [F] Tune  [I] Scan  [M] {sound}  [Q] Quit", WHITE))
        canvas = arena(game.index, pilot.name, now, kind, phase) if self.term.live else None
        if canvas is not None and phrase is not None:
            receiver(canvas, game.sector.song, phrase, now)
        if closed and self.term.live and game.status in ("won", "lost"):
            canvas = recorder(now, game.status == "lost")
            header = "BLACK BOX   /   " + ("MASTER TAPE RECOVERED" if game.status == "won" else "SIGNAL LOST")
        self._screen(header, canvas, footer)
