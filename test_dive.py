import unittest

from dive import Character, Dive, Echo, Rivet


class Rules(unittest.TestCase):
    def test_bounds(self):
        c = Character(10)
        c.damage(99)
        self.assertEqual(c.hull, 0)
        c.heal(99)
        self.assertEqual(c.hull, 10)
        for method in (c.damage, c.heal):
            with self.assertRaises(ValueError):
                method(-1)
            self.assertEqual(c.hull, 10)

    def test_free_actions(self):
        g = Dive(Rivet())
        for key in ("?", "i", "r"):
            g.act(key)
        self.assertEqual((g.turn, g.pilot.hull, len(g.pilot.pack)), (0, 28, 2))
        g.act("s")
        g.act("s")
        g.act("s")
        self.assertEqual((g.turn, g.pilot.hull), (2, 28))

    def test_cells(self):
        g = Dive(Echo())
        g.act("a")
        g.act("r")
        self.assertEqual(len(g.pilot.pack), 1)
        g.act("s")
        turn = g.turn
        g.act("s")
        self.assertEqual((g.turn, len(g.pilot.pack)), (turn, 0))
        self.assertEqual(len(Echo().pack), 2)

    def test_sonar(self):
        g = Dive(Rivet())
        g.contact = Character(40)
        for _ in range(3):
            g.act("a")
        self.assertEqual((g.noise, g.pilot.hull), (0, 17))

    def test_victory(self):
        for pilot in (Echo(), Rivet()):
            g = Dive(pilot)
            for _ in range(100):
                if g.status != "active":
                    break
                if g.contact.hull <= 5:
                    hull = pilot.hull
                    g.act("a")
                    self.assertEqual(pilot.hull, hull)
                elif pilot.hull <= 15 and len(pilot.pack):
                    g.act("r")
                else:
                    g.act("a")
            self.assertEqual(g.status, "won")

    def test_endings(self):
        for key, expected in (("q", "quit"), ("a", "lost")):
            g = Dive(Echo())
            while g.status == "active":
                g.act(key)
            g.act("a")
            self.assertEqual(g.status, expected)
