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

from dive import SECTORS
from locale_text import LANGUAGES, translate
from ocean import CYAN, GOLD, H, RED, W, WHITE, arena, pressure_wave, receiver, recorder, title

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
                return {"K": "left", "M": "right", "H": "up", "P": "down"}.get(msvcrt.getwch(), "")
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
                        part = os.read(sys.stdin.fileno(), 1)
                        if not part:
                            return "q"
                        if 0x40 <= part[0] <= 0x7e:
                            return {b"A": "up", b"B": "down", b"C": "right", b"D": "left"}.get(part, "")
                    return ""
                return "esc"
            key = raw.decode("ascii", "ignore")
        if key in ("\x03", "\x04", "\x1a"):
            return "q"
        if key in ("\x08", "\x7f"):
            return "back"
        if key in ("\r", "\n"):
            return "enter"
        if key == "\t":
            return "tab"
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
        self.pulse, self.noise = game.response, game.noise
        self.can_tune, self.status = game.can_tune, game.status
        self.cleared = game.cleared
        self.final_noise = self.noise
        self.final_equipment = self.pilot.equipment

    def finish(self, game):
        self.final_noise = game.noise
        if self.index == game.index:
            self.final_equipment = game.pilot.equipment

    def apply(self, event):
        if event.kind in ("cutter", "resonate", "decoy", "breach"):
            self.contact.hull -= event.points
        elif event.kind == "counter":
            self.pilot.hull -= event.points
        elif event.kind == "repair":
            self.pilot.hull += event.points
            self.pilot.cells -= 1
        if event.kind == "decoy":
            self.pilot.cells -= 1
        if event.kind in ("cutter", "anchor", "decoy", "resonate", "brace"):
            self.noise = self.final_noise
            self.can_tune = self.noise == 2
            self.pilot.equipment = self.final_equipment


@dataclass(frozen=True)
class Action:
    key: str
    name: str
    hint: str
    ready: bool = True


def combat_actions(game):
    t = game.text
    pilot = game.pilot
    rig = t("Block the pulse and clear noise. Costs 1 anchor.") if pilot.skill == "Anchor" else (
        t("Reflect the incoming {amount} damage. Costs 1 cell.", amount=game.response)
    )
    can_repair = pilot.hull < pilot.maximum and pilot.cells > 0
    return (
        Action("a", t("Cut"), t("{amount} damage, +1 noise. Contact can respond.", amount=game.cutter_damage)),
        Action("s", t(pilot.skill), rig if pilot.ability_ready else t("No charges left."), pilot.ability_ready),
        Action("b", t("Breach"), t("7 damage and disables armor. Once per sector." if game.breach_ready
                                  else "Spent. Reloads in the next sector."), game.breach_ready),
        Action("g", t("Brace"), t("Reduce the incoming hit by 4 and clear noise.")),
        Action("r", t("Repair"), t("Restore up to 12 hull. Costs 1 cell." if can_repair
                                  else "Requires hull damage and 1 cell."), can_repair),
        Action("f", t("Tune"), t("Match three notes for 4 damage and no counterattack." if game.can_tune
                                else "Requires two noise marks."), game.can_tune),
        Action("i", t("Scan"), game.sector_hint),
    )


class Display:
    def __init__(self, terminal, language="bg"):
        self.term = terminal
        self.language = language

    def text(self, source, **values):
        return translate(self.language, source, **values)

    def progress(self, cleared):
        total = len(SECTORS)
        return f"{self.text('Progress')}  {meter(cleared, total, total)}  {cleared}/{total} · {cleared * 100 // total}%"

    def language_menu(self):
        self._screen(f"{self.text('Language')} / {LANGUAGES[self.language]}", None, [
            (self.text("[1] Български   [2] Русский   [3] English   [Esc] Back"), CYAN),
        ])

    def station_map(self, game, selected, now=0):
        t = self.text
        cleared = game.cleared if game else 0
        rows = []
        for index, sector in enumerate(SECTORS):
            done = index < cleared
            current = index == cleared
            icon = "✓" if done else "◆" if current else "○"
            status = t("Cleared" if done else "Current" if current else "Locked")
            pointer = "›" if index == selected else " "
            rows.append((f"{pointer} {icon}  {index + 1:02}  {sector.depth:4} m  {t(sector.room)} · {status}",
                         GOLD if index == selected else CYAN if done else DIM))
        sector = SECTORS[selected]
        if selected <= cleared:
            rows.append((f"{t(sector.contact)}  ·  {t('Hull')} {sector.hull}", WHITE))
            if selected < cleared:
                rows.append((t(sector.tape), DIM))
            elif game:
                rows.append((game.sector_hint, DIM))
        rows.append((f"↑ ↓ / Tab / 1–4 {t('Select')}   [K] {t('Language')}   [Esc / P] {t('Back')}", CYAN))
        canvas = arena(selected, game.pilot.name if game else "Rivet", now) if self.term.live and selected <= cleared else None
        self._screen(f"BLACK BOX / {t('Map').upper()}", canvas, rows, self.progress(cleared))

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
        t = self.text
        self._screen(t("PELAGIC STATION / RESCUE DIVISION"), title(now) if self.term.live else None, [
            (f"BLACK BOX / {t('HYDROPHONE EDITION')}", GOLD),
            (t("Twelve years silent. Six minutes ago the station called you by name."), WHITE),
            (t("[1] RIVET — Block a pulse with an anchor. Two anchors per sector."), CYAN),
            (t("[2] ECHO — Reflect a pulse. Costs one cell."), CYAN),
            (f"[D] {t('Demo')}   [P] {t('Map')}   [K] {t('Language')} ({self.language.upper()})   "
             f"[M] {t(sound)}   [Q] {t('Quit')}", DIM),
        ])

    def service(self, game, message, now, selected):
        t = self.text
        options = (("1", t("Pack a spare cell")),
                   ("2", t("Restore {amount} hull", amount=min(8, game.pilot.maximum - game.pilot.hull))))
        canvas = recorder(now) if self.term.live else None
        self._screen(f"{t('Service bay').upper()} / {t('Next')}  {t(game.sector.room)}", canvas, [
            (message, DIM),
            (f"{t('Hull')} {game.pilot.hull}/{game.pilot.maximum}    {t('Cells')} {game.pilot.cells}", CYAN),
            *((f"{'›' if i == selected else ' '} [{key}] {label}", GOLD if i == selected else WHITE)
              for i, (key, label) in enumerate(options)),
            (f"← → / Tab  {t('Select')}    Enter  {t('Use')}    [P] {t('Map')}    [K] {t('Language')}    [Q] {t('Quit')}", DIM),
        ], self.progress(game.cleared))

    def battle(self, game, message, now, sound, kind="idle", phase=0., phrase=None, closed=False, actions=(), focus=0):
        t = self.text
        w, _ = self.term.size
        pilot, contact = game.pilot, game.contact
        hull = f"{pilot.name.upper()}  {pilot.hull:02}/{pilot.maximum}"
        target = f"{t(game.sector.contact).upper()}  {contact.hull:02}/{contact.maximum}"
        if w >= 65:
            hull += "  " + meter(pilot.hull, pilot.maximum, 10)
            target += "  " + meter(contact.hull, contact.maximum, 8)
        gap = " " * max(3, min(w - len(hull) - len(target), 10))
        header = f"BLACK BOX    /    {t(game.sector.room).upper()}    /    {game.sector.depth:04} m"
        equipment = t("decoy costs 1 cell") if pilot.skill == "Decoy" else t("{count}/2 anchors", count=pilot.equipment[0])
        sonar = f"{t('Noise')} {'●' * game.noise}{'○' * (3 - game.noise)}   {t('Cells')} {pilot.cells}   {equipment}"
        if game.can_tune:
            sonar += f"   •   F: {t('Tune ready')}"
        next_hit = f"{t('Next pulse')} {game.pulse if isinstance(game, CombatView) else game.response}"
        if game.noise == 2:
            next_hit += f"   ({t('+3 if you strike')})"
        footer = [(hull + gap + target, WHITE), (sonar, CYAN)]
        if not closed:
            if actions and game.armor:
                next_hit += "   " + t("Armor −{amount} cut damage", amount=game.armor)
            footer.append((next_hit, GOLD))
        footer.append((message, RED if kind == "counter" or game.status == "lost" else DIM))
        if phrase is not None:
            signal = "  ".join(game.sector.song)
            entered = "  ".join(list(phrase) + ["·"] * (3 - len(phrase)))
            footer += [(f"{t('Hydrophone')}    {t('Call')}  {signal}      {t('Answer')}  {entered}", CYAN),
                       (t("[1] Low  [2] Mid  [3] High  [L] Replay  [X] Back") + f"  [K] {t('Language')}", WHITE)]
        elif closed:
            footer.append((f"[Enter / Q] {t('Return to surface')}    [P] {t('Map')}", GOLD))
        elif actions:
            row = []
            for index, action in enumerate(actions):
                marker = "›" if index == focus else " "
                label = f"{marker}[{action.key.upper()} {action.name}]" + ("" if action.ready else "×")
                row.append(label)
            footer += [("  ".join(row), CYAN), (actions[focus].hint, WHITE),
                       (f"← → / Tab {t('Select')}  Enter {t('Use')}  [P] {t('Map')}  [K] {t('Language')}  [M] {t(sound)}  [Q] {t('Quit')}", DIM)]
        elif not isinstance(game, CombatView):
            footer.append((f"[Q] {t('Quit')}", WHITE))
        canvas = arena(game.index, pilot.name, now, kind, phase) if self.term.live else None
        if canvas is not None and actions and game.armor:
            y = 30 if game.index == 1 else 23
            pressure_wave(canvas, 105, y, 24, GOLD)
        if canvas is not None and phrase is not None:
            receiver(canvas, game.sector.song, phrase, now)
        if closed and self.term.live and game.status in ("won", "lost"):
            canvas = recorder(now, game.status == "lost")
            header = "BLACK BOX   /   " + t("Master tape recovered." if game.status == "won" else "Telemetry lost.").upper()
        self._screen(header, canvas, footer, self.progress(game.cleared))
