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
from ocean import ACCENTS, ANCHOR_Y, CYAN, GOLD, H, RED, W, WHITE, arena, pressure_wave, receiver, recorder, title

RESET = "\x1b[0m"
ERASE = "\x1b[K"
DIM = 0xa3b5b7
PAPER = 0x0d2129
SAFE_TEXT = str.maketrans({"—": "-", "–": "-", "−": "-", "·": ".", "›": ">", "×": "x"})


@lru_cache(maxsize=8192)
def truecolor(value, bg=False):
    return f"\x1b[{48 if bg else 38};2;{value >> 16};{(value >> 8) & 255};{value & 255}m"


@lru_cache(maxsize=4096)
def gray(value):
    return ((value >> 16) * 54 + ((value >> 8) & 255) * 183 + (value & 255) * 19) >> 8


def image_rows(canvas, width, height, color, pixels="safe"):
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
            if not color or pixels == "mono":
                text.append(ramp[min(10, (gray(a) + gray(b)) * 11 // 490)])
            elif a == b or pixels == "safe":
                if a != b:
                    a = (a & b) + (((a ^ b) & 0xfefefe) >> 1)
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
    def __init__(self, simple=False, settings=None):
        self.live = bool(not simple and sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM") != "dumb")
        self.color = self.live and "NO_COLOR" not in os.environ
        self.stack = contextlib.ExitStack()
        self.last_shape = None
        self.settings = settings
        self.window = None
        self.pixels = settings.pixels if settings else "safe"
        self.bold = settings.bold if settings else True

    def __enter__(self):
        if self.live:
            try:
                if os.name == "nt":
                    windows_modes(self.stack)
                    if self.settings:
                        from windows_console import ClassicWindow
                        self.window = ClassicWindow()
                        self.stack.callback(self.window.restore)
                        self.window.apply(self.settings.font, self.settings.fullscreen)
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
            return (line.strip().lower() or "enter") if line else "q"
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
        return max(1, actual.columns - 1), max(1, actual.lines)

    def ink(self, text, color, background=None, strong=False):
        if not self.live:
            return text
        style = "\x1b[1m" if strong and self.bold else ""
        if self.color:
            style += truecolor(color)
            if background is not None:
                style += truecolor(background, True)
        return style + text + RESET if style else text

    def show(self, rows):
        if not self.live:
            print("\n".join(rows), flush=True)
            return
        shape = self.size
        clear = "\x1b[2J" if self.last_shape != shape else ""
        self.last_shape = shape
        output = "\x1b[H" + (ERASE + "\r\n").join(rows[:shape[1]]) + ERASE + "\x1b[J"
        sys.stdout.write(clear + output)
        sys.stdout.flush()


def meter(value, maximum, length):
    lit = math.ceil(length * value / maximum)
    return "[" + "#" * lit + "." * (length - lit) + "]"


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
        self.opening = game.opening
        self.tell = game.tell
        self.final_noise = self.noise
        self.final_equipment = self.pilot.equipment

    def finish(self, game):
        self.final_noise = game.noise
        if self.index == game.index:
            self.final_equipment = game.pilot.equipment

    def apply(self, event):
        if event.kind in ("cutter", "resonate", "decoy", "breach", "brace"):
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


@dataclass(frozen=True)
class Strip:
    sections: tuple
    gap: str = "  "

    def lines(self, term, width):
        row, used = "", 0
        for label, ink, paper, strong in self.sections:
            pieces = textwrap.wrap(label.translate(SAFE_TEXT), width, replace_whitespace=False) or [""]
            for piece in pieces:
                if used and used + len(self.gap) + len(piece) > width:
                    yield row
                    row, used = "", 0
                if used:
                    row += self.gap
                    used += len(self.gap)
                row += term.ink(piece, ink, paper, strong)
                used += len(piece)
        if row:
            yield row


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
        Action("g", t("Brace"), t("Ground this beat for 4 damage and block 4." if game.crown_open and game.pulse >= 7
                                  else "Reduce the incoming hit by 4 and clear noise.")),
        Action("r", t("Repair"), t("Restore up to 12 hull. Costs 1 cell." if can_repair
                                  else "Requires hull damage and 1 cell."), can_repair),
        Action("f", t("Tune"), t("Match three notes for {amount} damage and no counterattack.",
                                amount=game.resonance_damage) if game.can_tune else t("Requires two noise marks."),
               game.can_tune),
        Action("i", t("Scan"), game.sector_hint),
    )


class Display:
    def __init__(self, terminal, language="bg"):
        self.term = terminal
        self.language = language
        self.notices = set()
        self.best = 0

    def text(self, source, **values):
        return translate(self.language, source, **values)

    def progress(self, cleared):
        total = len(SECTORS)
        return f"{self.text('Progress')}  {meter(cleared, total, total)}  {cleared}/{total} | {cleared * 100 // total}%"

    def language_menu(self, selected):
        rows = [(f"{'>' if i == selected else ' '} [{i + 1}] {name}", GOLD if i == selected else CYAN)
                for i, name in enumerate(LANGUAGES.values())]
        rows.append((f"Tab / Enter    [Esc] {self.text('Back')}", DIM))
        self._screen(f"{self.text('Language')} / {LANGUAGES[self.language]}", None, rows)

    def station_map(self, game, selected, now=0):
        t = self.text
        cleared = game.cleared if game else self.best
        rows = []
        for index, sector in enumerate(SECTORS):
            done = index < cleared
            current = index == cleared
            icon = "[x]" if done else "[>]" if current else "[.]"
            status = t("Cleared" if done else "Current" if current else "Locked")
            pointer = ">" if index == selected else " "
            rows.append((f"{pointer} {icon}  {index + 1:02}  {sector.depth:4} m  {t(sector.room)} / {status}",
                         GOLD if index == selected else CYAN if done else DIM))
        sector = SECTORS[selected]
        if selected <= cleared:
            rows.append((f"{t(sector.contact)}  /  {t('Hull')} {sector.hull}", WHITE))
            if selected < cleared:
                rows.append((t(sector.tape), DIM))
            elif game:
                rows.append((game.sector_hint, DIM))
        rows.append((f"Tab / 1-{len(SECTORS)} {t('Select')}   [K] {t('Language')}   [Esc / P] {t('Back')}", CYAN))
        canvas = arena(selected, game.pilot.name if game else "Rivet", now) if self.term.live and selected <= cleared else None
        self._screen(f"BLACK BOX / {t('Map').upper()}", canvas, rows, self.progress(cleared))

    def _screen(self, header, canvas, footer, banner=""):
        w, h = self.term.size
        header = header.translate(SAFE_TEXT)
        if self.term.live and len(header) + 8 <= w:
            header += "   " + "-" * (w - len(header) - 3)
        rows = [self.term.ink(header[:w], GOLD, strong=True)]
        if banner:
            rows.append(self.term.ink(banner[:w], WHITE))
        details = []
        notices = [(self.text(item), RED) for item in sorted(self.notices)]
        for entry in footer + notices:
            if isinstance(entry, Strip):
                details.extend(entry.lines(self.term, w))
                continue
            text, color = entry
            for line in textwrap.wrap(text.translate(SAFE_TEXT), w, break_long_words=True, replace_whitespace=True) or [""]:
                details.append(self.term.ink(line, color))
        available = h - len(rows) - len(details)
        if self.term.live and available > 0:
            if canvas is not None and available >= 3:
                height = min(available, max(3, round(w * H / (1.65 * W))))
                width = min(w, max(1, round(height * 2.5 * W / H)))
                pad = (available - height) // 2
                rows.extend([""] * pad)
                margin = " " * ((w - width) // 2)
                rows.extend(margin + line for line in image_rows(canvas, width, height, self.term.color, self.term.pixels))
                rows.extend([""] * (available - height - pad))
            else:
                rows.extend([""] * min(available, max(1, available // 3)))
        self.term.show(rows + details)

    def menu(self, now, sound, saved=None, focus="1", retry=False):
        t = self.text
        rows = [
            (f"BLACK BOX / {t('HYDROPHONE EDITION')}", GOLD),
            (t("Twelve years silent. Six minutes ago the station called you by name."), WHITE),
        ]
        choices = []
        if saved:
            label = t("Retry sector" if retry else "Continue")
            choices.append(("c", f"[C] {label} / {saved.pilot.name.upper()} / {t(saved.sector.room)} / {saved.sector.depth} m"))
        choices.extend([("1", t("[1] RIVET — Block a pulse with an anchor. Two anchors per sector.")),
                        ("2", t("[2] ECHO — Reflect a pulse. Costs one cell.")),
                        ("o", f"[O] {t('Settings')}"), ("p", f"[P] {t('Map')}")])
        rows.extend((("> " if key == focus else "  ") + label, GOLD if key == focus else CYAN) for key, label in choices)
        rows.append((f"Tab + Enter   [K] {t('Language')} ({self.language.upper()})   [M] {t(sound)}   [Q] {t('Quit')}", DIM))
        self._screen(t("PELAGIC STATION / RESCUE DIVISION"), title(now) if self.term.live else None, rows)

    def options(self, items, focus, now):
        t = self.text
        rows = [(f"{'>' if i == focus else ' '} [{i + 1}] {t(label):<20}  {value}",
                 GOLD if i == focus else WHITE) for i, (label, value) in enumerate(items)]
        rows += [(t("Tab to select / Enter to change / Esc or O to return"), CYAN),
                 (t("Window mode applies at the next Windows launch."), DIM)]
        self._screen("BLACK BOX / " + t("Settings").upper(), title(now) if self.term.live else None, rows)

    def confirm_new(self):
        self._screen("BLACK BOX", None, [(self.text("Replace the current dive?"), GOLD),
                                         (self.text("[1] Start over   [Esc / Q] Keep checkpoint"), WHITE)])

    def service(self, game, message, now, selected):
        t = self.text
        options = (("1", t("Pack a spare cell")),
                   ("2", t("Restore {amount} hull", amount=min(8, game.pilot.maximum - game.pilot.hull))))
        canvas = recorder(now) if self.term.live else None
        self._screen(f"{t('Service bay').upper()} / {t('Next')}  {t(game.sector.room)}", canvas, [
            (message, DIM),
            (f"{t('Hull')} {game.pilot.hull}/{game.pilot.maximum}    {t('Cells')} {game.pilot.cells}", CYAN),
            *((f"{'>' if i == selected else ' '} [{key}] {label}", GOLD if i == selected else WHITE)
              for i, (key, label) in enumerate(options)),
            (f"Tab / Enter    [P] {t('Map')}    [O] {t('Settings')}    [K] {t('Language')}    [Q] {t('Save and exit')}", DIM),
        ], self.progress(game.cleared))

    def battle(self, game, message, now, sound, kind="idle", phase=0., phrase=None, closed=False, actions=(), focus=0):
        t = self.text
        w, h = self.term.size
        compact = self.term.live and (w < 72 or h < 18)
        pilot, contact = game.pilot, game.contact
        hull = f"{pilot.name.upper()}  {pilot.hull:02}/{pilot.maximum}"
        target = f"{t(game.sector.contact).upper()}  {contact.hull:02}/{contact.maximum}"
        if w >= 65:
            hull += "  " + meter(pilot.hull, pilot.maximum, 10)
            target += "  " + meter(contact.hull, contact.maximum, 8)
        instruments = Strip(((hull, RED if pilot.hull <= 9 else CYAN, None, True),
                             (target, ACCENTS[game.index], None, True)), "      ")
        header = f"BLACK BOX  /  {game.index + 1:02}.{len(SECTORS):02}  /  {t(game.sector.room).upper()}  /  {game.sector.depth:04} m"
        equipment = t("decoy costs 1 cell") if pilot.skill == "Decoy" else t("{count}/2 anchors", count=pilot.equipment[0])
        sonar = f"{t('Noise')} {meter(game.noise, 3, 3)}   {t('Cells')} {pilot.cells}   {equipment}"
        if game.can_tune:
            sonar += f"   [F] {t('Tune ready')}"
        next_hit = f"{t('Next pulse')} {game.pulse if isinstance(game, CombatView) else game.response}"
        if game.noise == 2:
            next_hit += f"   ({t('+3 if you strike')})"
        footer = [instruments, (sonar, CYAN)]
        if compact:
            footer[-1] = (f"{t('Noise')} {game.noise}/3   {t('Cells')} {pilot.cells}   {equipment}", CYAN)
        if not closed:
            if actions and game.armor:
                next_hit += "   " + t("Armor −{amount} cut damage", amount=game.armor)
            if actions and not compact:
                pattern = game.pattern
                upcoming = [pattern[(game.turn + step) % len(pattern)] for step in (1, 2)]
                next_hit += f"   /   {t('Next beats')} {upcoming[0]} > {upcoming[1]}"
            footer.append((next_hit, GOLD))
            if game.tell:
                footer.append((game.tell, ACCENTS[game.index]))
        notice = textwrap.shorten(message, width=max(w, 8), placeholder="...") if compact and actions else message
        footer.append((notice, RED if kind == "counter" or game.status == "lost" else DIM))
        if phrase is not None:
            signal = "  ".join(game.sector.song)
            entered = "  ".join(list(phrase) + ["."] * (3 - len(phrase)))
            footer += [(f"{t('Hydrophone')}    {t('Call')}  {signal}      {t('Answer')}  {entered}", CYAN),
                       (t("[1] Low  [2] Mid  [3] High  [L] Replay  [X] Back") + f"  [O] {t('Settings')}  [K] {t('Language')}", WHITE)]
        elif closed:
            footer.append((f"[Enter] {t('Return to surface')}    [P] {t('Map')}    [Q] {t('Quit')}", GOLD))
        elif actions:
            row = []
            for index, action in enumerate(actions):
                marker = ">" if index == focus else " "
                name = "" if compact else " " + action.name
                label = f"{marker}[{action.key.upper()}{name}]" + ("" if action.ready else "x")
                active = index == focus
                row.append((label, PAPER if active else CYAN if action.ready else DIM, GOLD if active else None, active))
            if compact:
                navigation = f"Tab / Enter  [P] {t('Map')}  [O] {t('Settings')}  [Q]"
                detail = f"{actions[focus].name} / {actions[focus].hint}"
            else:
                navigation = f"Tab / Enter  [P] {t('Map')}  [O] {t('Settings')}  [K] {t('Language')}  [M] {t(sound)}  [Q] {t('Save and exit')}"
                detail = actions[focus].hint
            footer += [Strip(tuple(row), "" if compact else "  "), (detail, WHITE), (navigation, DIM)]
        elif not isinstance(game, CombatView):
            footer.append((f"[Q] {t('Quit')}", WHITE))
        canvas = arena(game.index, pilot.name, now, kind, phase, game.opening) if self.term.live else None
        if canvas is not None and actions and game.armor:
            pressure_wave(canvas, 105, ANCHOR_Y[game.index], 24, GOLD)
        if canvas is not None and phrase is not None:
            receiver(canvas, game.sector.song, phrase, now)
        if closed and self.term.live and game.status in ("won", "lost"):
            canvas = recorder(now, game.status == "lost")
            header = "BLACK BOX   /   " + t("Rescue complete." if game.status == "won" else "Telemetry lost.").upper()
        self._screen(header, canvas, footer, "" if compact else self.progress(game.cleared))
