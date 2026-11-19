import array
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from audio import FRAME_BYTES, Mixer
from console import CombatView
from dive import Dive, Echo, Rivet
from ocean import H, W, arena
from play import CLIPS, Expedition


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
        self.assertEqual((game.index, game.contact.hull, game.noise), (1, 6, 2))
        hull = game.pilot.hull
        result = game.resolve("f", game.sector.song)
        self.assertEqual([e.kind for e in result.events], ["resonate"])
        self.assertEqual((game.contact.hull, game.pilot.hull, game.noise), (2, hull, 0))

    def test_recorded_wins_include_each_ability_and_repair(self):
        routes = ((Rivet(), "aaasaafaaafarsaafaaa", 15),
                  (Echo(), "aaasaaaaafarsaafa", 20))
        for pilot, keys, remaining in routes:
            game = Dive(pilot)
            for key in keys:
                self.assertTrue(game.resolve(key, game.sector.song).events)
            self.assertEqual((game.status, pilot.hull), ("won", remaining))

    def test_repair_animation_has_both_effects(self):
        game = Dive(Echo())
        game.resolve("a")
        events = game.resolve("r").events
        self.assertEqual([(e.kind, e.points) for e in events], [("repair", 2), ("counter", 4)])

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
        self.assertEqual(len({len(bank[f"depth{i}"]) for i in range(4)}), 1)

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
        for sector in range(4):
            idle = arena(sector, "Rivet", 1)
            hit = arena(sector, "Rivet", 1, "counter", .58)
            self.assertEqual(len(hit.pixels), W * H)
            self.assertGreater(sum(a != b for a, b in zip(idle.pixels, hit.pixels)), 200)

    def test_console_replays_all_sectors(self):
        result = subprocess.run([sys.executable, "play.py", "--plain", "--demo"],
                                cwd=os.path.dirname(os.path.abspath(__file__)),
                                capture_output=True, encoding="utf-8", timeout=6, check=True)
        for label in ("FLOOD LOCK", "PUMP CATHEDRAL", "TAPE ARCHIVE", "RECORDER VAULT", "Master tape recovered."):
            self.assertIn(label, result.stdout)
        self.assertNotIn("\x1b", result.stdout)


if __name__ == "__main__":
    unittest.main()
