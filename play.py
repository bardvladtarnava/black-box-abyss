import argparse
import sys
import time

from audio import Sound
from console import CombatView, Display, Terminal, combat_actions
from dive import Dive, Echo, Rivet, SECTORS
from locale_text import LANGUAGES

FPS = 20
IMPACT_PHASE = {"cutter": .48, "counter": .545, "resonate": .51, "decoy": .48}
CLIPS = {
    "cutter": (.65, ((0., "swing"), (IMPACT_PHASE["cutter"], "impact")), "Cutter / hydraulic thrust"),
    "counter": (.72, ((.16, "swing"), (IMPACT_PHASE["counter"], "enemy")), "Incoming / contact strikes"),
    "anchor": (.76, ((.12, "swing"), (.50, "clang")), "Anchor / shielding deployed"),
    "decoy": (.80, ((.1, "echo"), (IMPACT_PHASE["decoy"], "impact")), "Acoustic decoy / return to sender"),
    "repair": (.64, ((0., "heal"),), "Field repair / cell transfer"),
    "resonate": (.90, ((0., "chord"), (IMPACT_PHASE["resonate"], "echo")), "Standing wave / signature matched"),
    "breach": (.85, ((0., "swing"), (.48, "clang")), "Breach / armor ruptured"),
    "brace": (.43, ((.2, "clang"),), "Brace / noise vented"),
    "wreck": (.84, ((.06, "wreck"),), "Contact silent / salvaging tape"),
}


class Expedition:
    def __init__(self, term, sound, still=False, language="bg"):
        self.term = term
        self.screen = Display(term, language)
        self.sound = sound
        self.animate = term.live and not still
        self.epoch = time.monotonic()

    def clock(self):
        return time.monotonic() - self.epoch

    @property
    def audio_label(self):
        if self.sound.label == "offline":
            return "Audio offline"
        return "Muted" if self.sound.muted else "Sound"

    def wait(self, draw):
        if not self.animate:
            draw()
            return self.term.read()
        while True:
            draw()
            key = self.term.read(.14)
            if key is not None:
                return key

    def change_language(self, game=None):
        choices = dict(zip("123", LANGUAGES))
        while True:
            key = self.wait(self.screen.language_menu)
            if key in ("esc", "k", "x", "q"):
                return False
            if key in choices:
                self.screen.language = choices[key]
                if game:
                    game.language = choices[key]
                return True

    def map(self, game=None):
        selected = game.index if game else 0
        while True:
            key = self.wait(lambda: self.screen.station_map(game, selected, self.clock()))
            if key in ("esc", "p", "enter", "q"):
                return
            if key in ("up", "left"):
                selected = (selected - 1) % len(SECTORS)
            elif key in ("down", "right", "tab"):
                selected = (selected + 1) % len(SECTORS)
            elif key in ("1", "2", "3", "4"):
                selected = int(key) - 1
            elif key == "k":
                self.change_language(game)

    def menu(self):
        while True:
            key = self.wait(lambda: self.screen.menu(self.clock(), self.audio_label))
            if key in ("1", "2", "q", "d"):
                return key
            if key == "m":
                self.sound.toggle()
            elif key == "k":
                self.change_language()
            elif key == "p":
                self.map()

    def draw(self, game, message, **frame):
        if isinstance(game, Dive) and not frame:
            frame = {"actions": combat_actions(game), "focus": 0}
        self.screen.battle(game, message, self.clock(), self.audio_label, **frame)

    def sequence(self, duration, cues, draw, update=lambda phase: None):
        steps = max(2, round(duration * FPS))
        start = time.monotonic()
        event_index = 0
        for step in range(steps + 1):
            deadline = start + duration * step / steps
            time.sleep(max(0, deadline - time.monotonic()))
            phase = step / steps
            update(phase)
            while event_index < len(cues) and cues[event_index][0] <= phase:
                self.sound.cue(cues[event_index][1])
                event_index += 1
            draw(phase)

    def clip(self, before, event):
        duration, cues, label = CLIPS[event.kind]
        applied = False

        def update(phase):
            nonlocal applied
            marker = IMPACT_PHASE.get(event.kind, .48)
            if not applied and phase >= marker:
                before.apply(event)
                applied = True

        def frame(phase):
            feedback = self.screen.text(label)
            if applied and event.points:
                sign = "+" if event.kind == "repair" else "-"
                feedback += f"   {sign}{event.points} {self.screen.text('Hull').upper()}"
            pose = {"breach": "cutter", "brace": "anchor"}.get(event.kind, event.kind)
            self.draw(before, feedback, kind=pose, phase=phase)

        self.sequence(duration, cues, frame, update)

    def call(self, game, phrase=""):
        song = game.sector.song
        message = game.text("Listen to the contact, then repeat its three notes.")
        if self.term.live:
            cues = tuple((.3 * i, "note" + digit) for i, digit in enumerate(song))
            def show(phase):
                self.draw(game, message, kind="listen" if self.animate else "idle", phase=phase, phrase=phrase)
            self.sequence(.98, cues, show)
        else:
            self.draw(game, message, phrase=phrase)

    def tune(self, game):
        self.call(game)
        phrase = ""
        message = game.text("Play the signature. No time limit.")
        while True:
            key = self.wait(lambda: self.draw(game, message, phrase=phrase))
            if key == "q":
                return "q", ""
            if key in ("esc", "x"):
                return "", ""
            if key == "m":
                self.sound.toggle()
            elif key == "k":
                if self.change_language(game):
                    message = game.text("Play the signature. No time limit.")
            elif key == "l":
                self.call(game, phrase)
            elif key == "back":
                phrase = phrase[:-1]
            elif key and all(ch in "123" for ch in key) and len(phrase + key) <= 3:
                for digit in key:
                    self.sound.cue("note" + digit)
                phrase += key
                self.draw(game, message, phrase=phrase)
                if len(phrase) == 3:
                    if phrase == game.sector.song:
                        return "f", phrase
                    message = f"{phrase} / " + game.text("No harmonic match. Listen and try again.")
                    phrase = ""

    def perform(self, game, key, phrase=""):
        before = CombatView(game) if self.animate and key in ("a", "s", "r", "f", "b", "g") else None
        result = game.resolve(key, phrase)
        if result.events:
            if before:
                before.finish(game)
            for event in result.events:
                if before:
                    self.clip(before, event)
                else:
                    self.sound.cue(CLIPS[event.kind][1][-1][1])
            self.sound.scene(game.index, game.can_tune or game.pilot.hull <= 9)
            if result.events[-1].kind == "wreck":
                self.sound.cue("ending" if game.status == "won" else "reel")
            if game.status == "lost":
                self.sound.cue("lost")
        return result.message

    def salvage(self, game, message):
        tape = SECTORS[game.index - 1].tape
        selected = 0
        while True:
            key = self.wait(lambda: self.screen.service(game, message, self.clock(), selected))
            if key in ("left", "right", "up", "down", "tab"):
                selected = 1 - selected
            elif key == "m":
                self.sound.toggle()
            elif key in ("p", "k"):
                if key == "p":
                    self.map(game)
                else:
                    self.change_language(game)
                message = game.text(tape) + "  [" + game.text("+1 cell") + "]"
            elif key == "q":
                return self.perform(game, key)
            elif key in ("1", "2", "enter"):
                choice = str(selected + 1) if key == "enter" else key
                self.sound.cue("heal" if choice == "2" else "reel")
                return game.take_salvage(choice) + " " + game.sector_hint

    def game(self, selection):
        game = Dive(Rivet() if selection == "1" else Echo(), self.screen.language)
        message = game.sector_hint
        focus = 0
        while game.status == "active":
            if game.salvage:
                message = self.salvage(game, message)
                focus = 0
                continue
            actions = combat_actions(game)
            key = self.wait(lambda: self.draw(game, message, actions=actions, focus=focus))
            if key in ("left", "right", "up", "down", "tab"):
                step = -1 if key in ("left", "up") else 1
                focus = (focus + step) % len(actions)
                continue
            if key == "enter":
                key = actions[focus].key
            else:
                focus = next((i for i, action in enumerate(actions) if action.key == key), focus)
            phrase = ""
            if key == "m":
                self.sound.toggle()
                continue
            if key in ("p", "k"):
                language = game.language
                if key == "p":
                    self.map(game)
                else:
                    self.change_language(game)
                if game.language != language:
                    message = game.sector_hint
                continue
            if key == "f" and game.can_tune:
                key, phrase = self.tune(game)
                if not key:
                    message = game.text("Hydrophone closed.")
                    continue
            if key == "i":
                message = self.perform(game, key) + " " + game.sector_hint
            else:
                message = self.perform(game, key, phrase)
        self.draw(game, message, closed=game.status != "quit")
        if self.term.live and game.status != "quit":
            while True:
                key = self.wait(lambda: self.draw(game, message, closed=True))
                if key in ("q", "enter", "esc"):
                    break
                if key == "m":
                    self.sound.toggle()
                elif key == "p":
                    self.map(game)
                    message = game.text(game.sector.tape if game.status == "won" else "Telemetry lost.")
        return game.status

    def demo(self):
        game = Dive(Echo(), self.screen.language)
        message = game.text("Autonomous replay. Q returns to the surface.")
        while game.status == "active":
            self.draw(game, message)
            if self.term.live and self.term.read(.56) == "q":
                return "quit"
            if game.salvage:
                choice = "2" if game.pilot.hull <= game.pilot.maximum - 5 else "1"
                game.take_salvage(choice)
            if game.contact.hull <= game.cutter_damage:
                key = "a"
            elif game.armor and game.breach_ready:
                key = "b"
            elif game.can_tune:
                if self.term.live:
                    self.call(game)
                key = "f"
            elif game.pilot.hull <= 15 and game.pilot.cells:
                key = "r"
            elif game.response >= 5 and game.pilot.cells >= 2:
                key = "s"
            else:
                key = "a"
            message = self.perform(game, key, game.sector.song)
        self.draw(game, message, closed=True)
        if self.term.live:
            self.term.read(2.)
        return game.status


def main():
    parser = argparse.ArgumentParser(description="BLACK BOX / a terminal hydrophone adventure")
    parser.add_argument("--mute", action="store_true", help="start with music and effects muted")
    parser.add_argument("--still", action="store_true", help="use still combat scenes")
    parser.add_argument("--plain", action="store_true", help="use line input and a text-only interface")
    parser.add_argument("--demo", action="store_true", help="play a full flight-recorder run")
    parser.add_argument("--lang", choices=LANGUAGES, default="bg", help="interface language (default: bg)")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    with Terminal(args.plain) as term:
        sound = Sound(term.live, args.mute)
        try:
            expedition = Expedition(term, sound, args.still, args.lang)
            choice = "d" if args.demo else expedition.menu()
            if choice == "q":
                return
            result = expedition.demo() if choice == "d" else expedition.game(choice)
        except (EOFError, KeyboardInterrupt):
            result = "quit"
        finally:
            sound.close()
    print("BLACK BOX  /  " + expedition.screen.text({"won": "Master tape recovered.", "quit": "At the surface.",
                                                     "lost": "Telemetry lost."}[result]))


if __name__ == "__main__":
    main()
