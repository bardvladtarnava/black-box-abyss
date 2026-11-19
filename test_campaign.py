import os
import ctypes
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from audio import Mixer
from console import Display, Terminal, image_rows, meter
from dive import Dive, Echo, Rivet, SECTORS
from locale_text import TEXT
from ocean import H, W, arena
from storage import Logbook
from windows_console import ClassicWindow, FontInfo, open_terminal


class LateContacts(unittest.TestCase):
    def sector(self, index):
        game = Dive(Rivet())
        game.index = index
        game._enter()
        return game

    def test_shell_opens_on_vent_even_after_breach(self):
        game = self.sector(4)
        self.assertEqual(game.cutter_damage, 2)
        game.act("b")
        self.assertEqual(game.cutter_damage, 5)
        game.act("s")
        self.assertEqual((game.pulse, game.cutter_damage), (1, 8))
        self.assertEqual(game.resolve("a").events[0].points, 8)

    def test_silent_beat_at_zero_noise(self):
        game = self.sector(5)
        game.act("s")
        self.assertEqual((game.noise, game.pulse), (0, 0))
        game.resolve("f", "111")
        self.assertTrue(game.can_tune)
        answer = game.resolve("f", game.sector.song)
        self.assertEqual([(e.kind, e.points) for e in answer.events], [("resonate", 8)])
        self.assertFalse(game.can_tune)

    def test_crown_announces_new_cycle_and_can_die_to_brace(self):
        game = self.sector(6)
        self.assertFalse(game.crown_open)
        game.contact.damage(17)
        self.assertEqual((game.pulse, game.response), (8, 8))
        self.assertIn("8-0-7", game.act("i"))
        result = game.resolve("g")
        self.assertEqual([(e.kind, e.points) for e in result.events], [("brace", 4), ("counter", 4)])
        self.assertEqual(game.pulse, 0)
        self.assertEqual(game.resolve("g").events[0].points, 0)
        game.contact.damage(12)
        hull = game.pilot.hull
        game.act("g")
        self.assertEqual((game.status, game.pilot.hull), ("won", hull))

    def test_every_contact_has_distinct_art_score_and_translated_recording(self):
        mixer = Mixer()
        scenes = set()
        for i, sector in enumerate(SECTORS):
            mixer.scene(i, True)
            self.assertTrue(any(mixer.render(4096)))
            frame = arena(i, "Echo", 1.3)
            self.assertEqual(len(frame.pixels), W * H)
            scenes.add(tuple(frame.pixels))
            for key in (sector.room, sector.contact, sector.tape):
                self.assertIn(key, TEXT)
        self.assertEqual(len(scenes), len(SECTORS))


class Checkpoints(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.book = Logbook(self.root)

    def test_exact_midfight_resume_and_next_turn_for_both_rigs(self):
        for rig in (Rivet, Echo):
            game = Dive(rig())
            self.book.checkpoint(game, new=True)
            for key in "aas":
                game.resolve(key)
                self.book.checkpoint(game)
            resumed = Logbook(self.root).resume
            self.assertEqual(game.snapshot(), resumed.snapshot())
            self.assertEqual(game.resolve("b").events, resumed.resolve("b").events)
            self.assertEqual(game.snapshot(), resumed.snapshot())

    def test_service_choice_once_and_loss_rewinds_only_one_sector(self):
        game = Dive(Echo())
        self.book.checkpoint(game, new=True)
        for key in "aaa":
            game.act(key)
            self.book.checkpoint(game)
        expected = game.snapshot()
        self.assertTrue(expected["service"])
        game = Logbook(self.root).resume
        game.take_salvage("1")
        self.book.checkpoint(game)
        self.assertFalse(Logbook(self.root).resume.take_salvage("1"))
        game.pilot.damage(game.pilot.hull - 1)
        game.act("a")
        self.assertEqual(game.status, "lost")
        self.book.checkpoint(game)
        loaded = Logbook(self.root)
        self.assertTrue(loaded.retry)
        self.assertEqual((loaded.best, loaded.resume.snapshot()), (1, expected))
        loaded.checkpoint(Dive(Rivet()), new=True)
        self.assertEqual(Logbook(self.root).best, 1)

    def test_completion_keeps_all_tapes_without_an_active_slot(self):
        game = Dive(Rivet())
        game.index = len(SECTORS) - 1
        game._enter()
        game.contact.damage(game.contact.hull - 1)
        game.act("a")
        self.book.checkpoint(game)
        loaded = Logbook(self.root)
        self.assertEqual((loaded.best, loaded.resume, loaded.entry), (len(SECTORS), None, None))

    def test_corruption_and_partial_writes_are_recoverable(self):
        game = Dive(Rivet())
        self.book.checkpoint(game, new=True)
        original = (self.root / "campaign.json").read_bytes()
        game.act("a")
        with patch("storage.os.replace", side_effect=PermissionError):
            self.assertFalse(self.book.checkpoint(game))
        self.assertEqual((self.root / "campaign.json").read_bytes(), original)
        self.assertEqual(list(self.root.glob("*.tmp")), [])
        self.assertTrue(self.book.checkpoint(game))
        self.assertFalse(self.book.notices)
        (self.root / "campaign.json").write_bytes(b"{")
        (self.root / "settings.json").write_bytes(b"[]")
        loaded = Logbook(self.root)
        self.assertIsNone(loaded.resume)
        self.assertEqual(loaded.settings.language, "bg")
        self.assertEqual(loaded.notices, {"Checkpoint unreadable.", "Settings unreadable."})

    def test_reject_inconsistent_or_unbounded_game_fields(self):
        state = Dive(Echo()).snapshot()
        for key, value in (("cells", 10**9), ("contact", -1), ("noise", True), ("sector", 100),
                           ("rig", "X"), ("breach", "false"), ("service", True), ("anchors", 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                Dive.from_snapshot(dict(state, **{key: value}))

    def test_stale_window_cannot_overwrite_newer_combat(self):
        game = Dive(Rivet())
        self.book.checkpoint(game, new=True)
        second = Logbook(self.root)
        game.act("a")
        self.assertTrue(self.book.checkpoint(game))
        second.resume.act("s")
        self.assertFalse(second.checkpoint(second.resume))
        self.assertEqual(Logbook(self.root).resume.snapshot(), game.snapshot())


class ConsolePresentation(unittest.TestCase):
    def test_safe_health_bars_and_terrain(self):
        self.assertEqual(meter(28, 28, 10), "[##########]")
        self.assertEqual(meter(0, 11, 8), "[........]")
        self.assertEqual(meter(1, 11, 8), "[#.......]")
        scene = arena(5, "Echo", .2)
        for pixels in ("safe", "mono"):
            self.assertTrue(all(row.isascii() for row in image_rows(scene, 95, 21, True, pixels)))
        self.assertIn("▀", "".join(image_rows(scene, 95, 21, True, "fine")))

    def test_large_windows_use_more_than_previous_limits(self):
        term = Terminal(True)
        term.live = True
        display = Display(term, "en")
        with patch("console.shutil.get_terminal_size", return_value=os.terminal_size((202, 54))), \
                patch.object(term, "show") as output:
            display.menu(0, "Sound")
        rows = output.call_args.args[0]
        self.assertEqual(len(rows), 54)
        self.assertGreater(sum(len(row.strip()) > 140 for row in rows), 26)

    def test_windows_launcher_requests_separate_window_and_forwards_argv(self):
        with patch("windows_console.shutil.which", return_value="wt.exe"), \
                patch("windows_console.subprocess.run") as process:
            process.return_value.returncode = 0
            self.assertTrue(open_terminal(True, ["--lang", "ru"]))
            args = process.call_args.args[0]
            self.assertEqual(args[:5], ["wt.exe", "-w", "new", "--fullscreen", "new-tab"])
            self.assertEqual(args[-3:], ["--in-window", "--lang", "ru"])
            self.assertTrue(open_terminal(False, []))
            self.assertNotIn("--fullscreen", process.call_args.args[0])
        with patch("windows_console.shutil.which", return_value=None):
            self.assertFalse(open_terminal(True, []))

    def test_classic_host_fullscreen_fallback_and_font_restoration(self):
        for native in (False, True):
            with self.subTest(native=native):
                window = object.__new__(ClassicWindow)
                window.kernel, window.user = Mock(), Mock()
                window.kernel.SetConsoleDisplayMode.return_value = native
                window.kernel.SetCurrentConsoleFontEx.return_value = True
                window.hwnd, window.handle = 123, 15
                window.mode = ctypes.c_uint32()
                window.original = FontInfo()
                window.original.face = "Original"
                window.visible = window.has_font = window.has_mode = True
                window.maximized = window.expanded = window.changed_mode = window.changed_font = False
                window.apply("Consolas", True)
                chosen_font = window.kernel.SetCurrentConsoleFontEx.call_args.args[-1]._obj.face
                self.assertEqual(chosen_font, "Consolas")
                self.assertEqual(window.changed_mode, native)
                self.assertEqual(window.expanded, not native)
                window.restore()
                restored = window.kernel.SetCurrentConsoleFontEx.call_args.args[-1]._obj.face
                self.assertEqual(restored, "Original")
                if native:
                    self.assertEqual(window.kernel.SetConsoleDisplayMode.call_args.args[1], 2)
                else:
                    self.assertEqual([c.args[1] for c in window.user.ShowWindow.call_args_list], [3, 9])


if __name__ == "__main__":
    unittest.main()
