import array
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from audio import FRAME_BYTES, Mixer
from console import CombatView
from dive import Dive, Echo, Rivet, SECTORS
from ocean import H, W, arena
from play import CLIPS, Expedition

ROUTES = ((Rivet, "aaa2braa1aafa2asaaba2bsaafa2bfsaaa2baagrgga", 13),
          (Echo, "aaa2braa1aafa2asaba2bsaa2bfsaa2baagrgga", 19))


def console_route(rig, keys):
    game = Dive(rig())
    commands = ["1" if rig is Rivet else "2"]
    for key in keys:
        commands.append(key)
        if game.salvage:
            game.take_salvage(key)
        else:
            if key == "f":
                commands.append(game.sector.song)
            game.resolve(key, game.sector.song)
    return "\n".join(commands) + "\n"


def snapshot(game):
    return (game.index, game.turn, game.status, game.noise, game.pilot.hull,
            game.contact.hull, len(game.pilot.pack), game.pilot.equipment)


class HydrophoneRules(unittest.TestCase):
    def test_closed_receiver_and_wrong_phrase(self):
        game = Dive(Rivet())
        for key in ("f", "a", "f", "a", "f"):
            state = snapshot(game)
            report = game.resolve(key, "000")
            if key == "f":
                self.assertFalse(report.events)
                self.assertEqual(snapshot(game), state)
        self.assertTrue(game.can_tune)

    def test_finishing_resonance_salvages_one_cell(self):
        game = Dive(Echo())
        game.act("a")
        game.act("a")
        hull = game.pilot.hull
        result = game.resolve("f", "132")
        self.assertEqual([e.kind for e in result.events], ["resonate", "wreck"])
        self.assertEqual(result.events[0].points, 1)
        self.assertEqual((game.index, game.turn, game.noise, len(game.pilot.pack), game.pilot.hull),
                         (1, 0, 0, 3, hull))

    def test_nonlethal_resonance_cancels_counter(self):
        game = Dive(Rivet())
        for key in "aaaaa":
            game.act(key)
        self.assertEqual((game.index, game.contact.hull, game.noise), (1, 9, 2))
        hull = game.pilot.hull
        result = game.resolve("f", game.sector.song)
        self.assertEqual([e.kind for e in result.events], ["resonate"])
        self.assertEqual((game.contact.hull, game.pilot.hull, game.noise), (5, hull, 0))

    def test_recorded_wins_include_each_ability_and_repair(self):
        for rig, keys, remaining in ROUTES:
            pilot = rig()
            game = Dive(pilot)
            for key in keys:
                if key in "12":
                    self.assertTrue(game.take_salvage(key))
                else:
                    self.assertTrue(game.resolve(key, game.sector.song).events)
            self.assertEqual((game.status, pilot.hull), ("won", remaining))

    def test_repair_animation_has_both_effects(self):
        game = Dive(Echo())
        game.resolve("a")
        events = game.resolve("r").events
        self.assertEqual([(e.kind, e.points) for e in events], [("repair", 2), ("counter", 4)])

    def test_breach_disables_crab_shell_once(self):
        game = Dive(Rivet())
        for _ in range(3):
            game.act("a")
        self.assertEqual((game.armor, game.cutter_damage), (3, 2))
        self.assertEqual(game.resolve("b").events[0].points, 7)
        state = snapshot(game)
        self.assertFalse(game.resolve("b").events)
        self.assertEqual(snapshot(game), state)
        for _ in range(4):
            game.act("g")
        self.assertEqual((game.armor, game.cutter_damage), (0, 5))

    def test_service_reward_can_only_be_claimed_once(self):
        game = Dive(Echo())
        for _ in range(3):
            game.act("a")
        self.assertEqual(game.pilot.hull, 22)
        self.assertTrue(game.take_salvage("2"))
        self.assertFalse(game.take_salvage("1"))
        self.assertEqual((game.pilot.hull, game.pilot.cells, game.turn), (28, 3, 0))

    def test_eel_noise_counter_and_boss_half_hull_armor(self):
        game = Dive(Echo())
        for key in "aaabaa":
            game.act(key)
        self.assertEqual(game.index, 2)
        game.act("a")
        game.act("a")
        result = game.resolve("g")
        self.assertEqual([(e.kind, e.points) for e in result.events], [("brace", 0), ("counter", 4)])
        self.assertEqual(game.noise, 0)
        self.assertEqual(game.resolve("b").events[0].kind, "breach")
        game.act("a")
        self.assertEqual(game.index, 3)
        game.take_salvage("2")
        for _ in range(3):
            game.act("a")
        self.assertEqual((game.contact.hull, game.armor), (10, 2))

    def test_defeat_is_final_for_all_commands(self):
        game = Dive(Echo())
        while game.status == "active":
            game.resolve("a")
        state = snapshot(game)
        for key in "arsfiq":
            self.assertFalse(game.resolve(key, game.sector.song).events)
            self.assertEqual(snapshot(game), state)


class SoundScore(unittest.TestCase):
    def test_sound_bank_has_all_cues(self):
        bank = Mixer().bank
        names = {name for _, cues, _ in CLIPS.values() for _, name in cues}
        names.update(("reel", "ending", "lost", "note1", "note2", "note3", "pressure"))
        self.assertTrue(names.issubset(bank))
        tracks = [bank[f"depth{i}"].tobytes() for i in range(len(SECTORS))]
        self.assertEqual(len({len(track) for track in tracks}), 1)
        self.assertEqual(len(set(tracks)), len(SECTORS))

    def test_stereo_score_and_cue_onsets(self):
        for cue, side in (("impact", "right"), ("enemy", "left")):
            mixer = Mixer()
            reference = Mixer()
            mixer.cue(cue)
            output = array.array("h", mixer.render(512))
            bed = array.array("h", reference.render(512))
            if sys.byteorder == "big":
                output.byteswap()
                bed.byteswap()
            energy = [sum(abs(a - b) for a, b in zip(output[i::2], bed[i::2])) for i in (0, 1)]
            self.assertGreater(min(energy), 0)
            self.assertEqual(energy[1] > energy[0], side == "right")

    def test_mute_and_resume_do_not_rewind_music(self):
        mixer = Mixer()
        mixer.mute(True)
        mixer.cue("wreck")
        self.assertEqual(mixer.render(256), bytes(256 * FRAME_BYTES))
        self.assertFalse(mixer.voices)
        mixer.mute(False)
        self.assertTrue(any(mixer.render(256)))
        self.assertEqual(mixer.position, 512)

    def test_danger_and_sector_change_alter_score(self):
        mixer = Mixer()
        reference = Mixer()
        mixer.scene(0, True)
        self.assertNotEqual(mixer.render(1024), reference.render(1024))
        previous = mixer.position
        mixer.scene(3, False)
        mixer.render(4096)
        self.assertEqual((mixer.zone, mixer.position, mixer.transition), (3, previous + 4096, 0))

    def test_cues_share_their_visual_frame(self):
        class Probe:
            def __init__(self):
                self.pending = []

            def cue(self, name):
                self.pending.append(name)

        exp = object.__new__(Expedition)
        exp.sound = Probe()
        timeline = {}
        def draw(phase):
            for name in exp.sound.pending:
                timeline[name] = phase
            exp.sound.pending.clear()
        duration, cues, _ = CLIPS["counter"]
        with patch("play.time.sleep"):
            exp.sequence(duration, cues, draw)
        for offset, name in cues:
            self.assertGreaterEqual(timeline[name], offset)
            self.assertLessEqual(timeline[name] - offset, 1 / round(duration * 20))


class TerminalPlayback(unittest.TestCase):
    def test_presentation_replays_resolved_hits_without_touching_game(self):
        game = Dive(Echo())
        for key in ("a", "s", "r", "a", "a"):
            view = CombatView(game)
            result = game.resolve(key)
            final = snapshot(game)
            view.finish(game)
            for event in result.events:
                view.apply(event)
            self.assertEqual(view.pilot.hull, game.pilot.hull)
            self.assertEqual(view.contact.hull, game.contact.hull if view.index == game.index else 0)
            self.assertEqual(snapshot(game), final)

    def test_scene_size_and_motion(self):
        for sector in range(len(SECTORS)):
            idle = arena(sector, "Rivet", 1)
            hit = arena(sector, "Rivet", 1, "counter", .58)
            self.assertEqual(len(hit.pixels), W * H)
            self.assertGreater(sum(a != b for a, b in zip(idle.pixels, hit.pixels)), 200)

    def run_console(self, *args, keys="", root=None):
        with tempfile.TemporaryDirectory() as temporary:
            return subprocess.run([sys.executable, "play.py", "--plain", *args],
                                  cwd=os.path.dirname(os.path.abspath(__file__)), input=keys,
                                  env=dict(os.environ, BLACKBOX_DATA_DIR=root or temporary),
                                  capture_output=True, encoding="utf-8", timeout=8, check=True).stdout

    def test_keyboard_campaign_reaches_all_sectors(self):
        rig, route, _ = ROUTES[0]
        output = self.run_console("--lang", "en", keys=console_route(rig, route))
        for label in [sector.room.upper() for sector in SECTORS] + ["Rescue complete."]:
            self.assertIn(label, output)
        self.assertNotIn("\x1b", output)

    def test_bulgarian_default_and_russian_completion(self):
        rig, route, _ = ROUTES[1]
        for args, ending in (([], "Спасителната мисия завърши."), (["--lang", "ru"], "Спасательная миссия завершена.")):
            output = self.run_console(*args, keys=console_route(rig, route))
            self.assertIn(ending, output)
            for progress in [f"{i}/7" for i in range(7)] + ["7/7 | 100%"]:
                self.assertIn(progress, output)

    def test_map_and_language_switch_keep_combat_state(self):
        keys = "1\na\nk\n2\np\n2\np\nk\n3\na\np\np\na\np\n1\np\n2\nq\n"
        output = self.run_console(keys=keys)
        for text in ("Език (BG)", "Удар", "КАРТА", "Насосный зал / Закрыт", "DRONE  01/11",
                     "1/7 | 14%", "TAPE 01", "At the surface."):
            self.assertIn(text, output)

    def test_preferences_and_mid_fight_resume_across_processes(self):
        from storage import Logbook
        with tempfile.TemporaryDirectory() as root:
            self.run_console(keys="o\n1\n2\n2\n3\n4\n5\no\n1\na\ns\nb\nq\n", root=root)
            book = Logbook(root)
            self.assertEqual((book.settings.language, book.settings.sound, book.settings.motion,
                              book.settings.pixels, book.settings.fullscreen), ("ru", False, False, "fine", False))
            initial = book.resume.snapshot()
            output = self.run_console(keys="1\nesc\nc\np\n7\np\nq\n", root=root)
            self.assertIn("[C] Продолжить", output)
            self.assertIn("Колодец приливов", output)
            self.assertEqual(Logbook(root).resume.snapshot(), initial)
            self.run_console(keys="c\n2\na\nq\n", root=root)
            self.assertEqual(Logbook(root).resume.turn, 1)

    def test_reopen_during_fight_and_use_the_saved_pulse(self):
        from storage import Logbook
        with tempfile.TemporaryDirectory() as root:
            self.run_console(keys="2\na\nq\n", root=root)
            output = self.run_console("--lang", "en", keys="c\ns\nq\n", root=root)
            self.assertIn("Decoy returned 4 damage.", output)
            game = Logbook(root).resume
            self.assertEqual((game.contact.hull, game.pilot.hull, game.pilot.cells, game.turn), (2, 26, 1, 2))


if __name__ == "__main__":
    unittest.main()
