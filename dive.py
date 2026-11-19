from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple

from locale_text import translate


@dataclass(frozen=True)
class Sector:
    depth: int
    room: str
    contact: str
    hull: int
    pulses: Tuple[int, ...]
    song: str
    tape: str


SECTORS = (
    Sector(180, "Flood lock", "Lantern drone", 11, (2, 4), "132",
           "TAPE 01 / Three taps on the glass. Someone knows the rescue signal."),
    Sector(460, "Pump cathedral", "Piston crab", 16, (5, 1, 2), "211",
           "TAPE 02 / Beneath the pumps, a voice is practising your callsign."),
    Sector(790, "Tape archive", "Spindle eel", 19, (1, 3, 6), "312",
           "TAPE 03 / The oldest reel is labelled RESCUE DRILL. It is in your handwriting."),
    Sector(1200, "Recorder vault", "The Listener", 25, (2, 6, 3), "123",
           "MASTER / It learned your voice from a training tape. You tap the glass three times. Something taps back."),
    Sector(1680, "Glass reef", "Kiln Nautilus", 26, (4, 6, 1), "231",
           "TAPE 05 / The nautilus opens. Inside its shell, an air gauge is still ticking."),
    Sector(2240, "Choir trench", "Wire Siren", 29, (3, 0, 7, 2), "322",
           "TAPE 06 / Between two notes you hear breathing. The distress call came from below the station."),
    Sector(3100, "Tidal well", "The Tide Crown", 34, (2, 5, 3), "213",
           "LAST REEL / Three taps. The hatch opens from inside. This time a hand takes yours."),
)


@dataclass(frozen=True)
class Event:
    kind: str
    points: int = 0


@dataclass(frozen=True)
class Turn:
    message: str
    events: Tuple[Event, ...] = ()


class Character:
    def __init__(self, hull):
        if hull <= 0:
            raise ValueError("Maximum hull must be positive")
        self._maximum = self._hull = hull

    @property
    def maximum(self):
        return self._maximum

    @property
    def hull(self):
        return self._hull

    def damage(self, amount):
        if amount < 0:
            raise ValueError("Negative damage")
        taken = min(self.hull, amount)
        self._hull -= taken
        return taken

    def heal(self, amount):
        if amount < 0:
            raise ValueError("Negative repair")
        restored = min(self.maximum - self.hull, amount)
        self._hull += restored
        return restored


class Cell:
    def repair(self, pilot):
        return pilot.heal(12)


class Inventory:
    def __init__(self, count=2):
        self._cells = [Cell() for _ in range(count)]

    def __len__(self):
        return len(self._cells)

    def collect(self):
        self._cells.append(Cell())

    def spend(self):
        if not self._cells:
            return False
        self._cells.pop()
        return True

    def repair(self, pilot):
        if not self._cells:
            return 0
        restored = self._cells[-1].repair(pilot)
        if restored:
            self._cells.pop()
        return restored


class Hero(Character, ABC):
    def __init__(self):
        super().__init__(28)
        self.pack = Inventory()

    @property
    def cells(self):
        return len(self.pack)

    def enter(self):
        pass

    @abstractmethod
    def ability(self, contact, pulse):
        pass


class Rivet(Hero):
    name = "Rivet"
    skill = "Anchor"

    def __init__(self):
        super().__init__()
        self.enter()

    def enter(self):
        self._charges = 2

    @property
    def equipment(self):
        return f"{self._charges}/2 anchors"

    @property
    def ability_ready(self):
        return self._charges > 0

    @property
    def anchors(self):
        return self._charges

    def load_anchors(self, count):
        self._charges = count

    def ability(self, contact, pulse):
        if not self._charges:
            return None
        self._charges -= 1
        return Event("anchor")


class Echo(Hero):
    name = "Echo"
    skill = "Decoy"
    equipment = "decoy costs 1 cell"

    @property
    def ability_ready(self):
        return self.cells > 0

    def ability(self, contact, pulse):
        if self.pack.spend():
            return Event("decoy", contact.damage(pulse))
        return None


class Dive:
    def __init__(self, pilot, language="en"):
        self.language = language
        self.pilot = pilot
        self.index = 0
        self.status = "active"
        self.salvage = False
        self._enter()

    def text(self, source, **values):
        return translate(self.language, source, **values)

    @property
    def cleared(self):
        return self.index + int(self.status == "won")

    @property
    def sector(self):
        return SECTORS[self.index]

    def _enter(self):
        self.contact = Character(self.sector.hull)
        self.turn = self._noise = 0
        self.breach_ready = True
        self.pilot.enter()

    def snapshot(self):
        if self.status != "active":
            raise ValueError("Only a live dive can be suspended")
        return {
            "rig": self.pilot.name, "sector": self.index, "turn": self.turn,
            "hull": self.pilot.hull, "contact": self.contact.hull, "cells": self.pilot.cells,
            "noise": self.noise, "breach": self.breach_ready, "service": self.salvage,
            "anchors": self.pilot.anchors if isinstance(self.pilot, Rivet) else 0,
        }

    @classmethod
    def from_snapshot(cls, data, language="bg"):
        if not isinstance(data, dict) or data.get("rig") not in ("Rivet", "Echo"):
            raise ValueError("Unknown rig")

        def number(key, low, high):
            value = data.get(key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(key)
            return value

        pilot = Rivet() if data["rig"] == "Rivet" else Echo()
        game = cls(pilot, language)
        game.index = number("sector", 0, len(SECTORS) - 1)
        game._enter()
        game.turn = number("turn", 0, 2**53)
        pilot.damage(pilot.maximum - number("hull", 1, pilot.maximum))
        game.contact.damage(game.sector.hull - number("contact", 1, game.sector.hull))
        pilot.pack = Inventory(number("cells", 0, 2 + 2 * game.index))
        game._noise = number("noise", 0, 2)
        anchors = number("anchors", 0, 2 if isinstance(pilot, Rivet) else 0)
        if isinstance(pilot, Rivet):
            pilot.load_anchors(anchors)
        if type(data.get("breach")) is not bool or type(data.get("service")) is not bool:
            raise ValueError("Invalid equipment or service flag")
        game.breach_ready, game.salvage = data["breach"], data["service"]
        if game.salvage and (not game.index or game.turn or game.contact.hull != game.sector.hull
                             or game.noise or not game.breach_ready):
            raise ValueError("Invalid service stop")
        return game

    @property
    def noise(self):
        return self._noise

    @property
    def crown_open(self):
        return self.index == 6 and self.contact.hull <= self.sector.hull // 2

    @property
    def pattern(self):
        return (8, 0, 7) if self.crown_open else self.sector.pulses

    @property
    def pulse(self):
        pattern = self.pattern
        return pattern[self.turn % len(pattern)]

    @property
    def can_tune(self):
        return self.status == "active" and (self.noise == 2 or self.siren_rest)

    @property
    def siren_rest(self):
        return self.index == 5 and self.pulse == 0

    @property
    def resonance_damage(self):
        return 8 if self.siren_rest else 4

    @property
    def opening(self):
        return (self.index == 4 and self.pulse == 1) or self.siren_rest or self.crown_open

    @property
    def armor(self):
        if not self.breach_ready:
            return 0
        if self.index == 1 and self.pulse == 5:
            return 3
        if self.index == 3 and self.contact.hull <= self.contact.maximum // 2:
            return 2
        if self.index == 4 and self.pulse != 1:
            return 3
        return 0

    @property
    def cutter_damage(self):
        return (8 if self.index == 4 and self.pulse == 1 else 5) - self.armor

    @property
    def tell(self):
        if self.index == 4:
            return self.text("VENT OPEN / Cut for 8" if self.pulse == 1 else "SHELL TURNING")
        if self.index == 5:
            return self.text("REST / Answer for 8" if self.siren_rest else "STRINGS UNDER TENSION")
        if self.index == 6:
            return self.text("INNER TIDE / Brace returns 4 on a heavy beat" if self.crown_open else "OUTER TIDE")
        return ""

    @property
    def response(self):
        extra = 2 if self.index == 2 and self.noise == 2 else 0
        return self.pulse + extra

    @property
    def sector_hint(self):
        if self.index == 0:
            return self.text("Cut twice to unlock Tune. The third cut risks a sonar counter.")
        if self.index == 1:
            return self.text("The crab seals its shell on pulse 5. Breach strips its armor for the fight.")
        if self.index == 2:
            return self.text("At two noise marks the eel hits +2. Tune or Brace to clear noise.")
        hints = (
            "The Listener shields itself at half hull. Breach can disable the shield before it activates.",
            "The shell opens on pulse 1. Cut for 8 while it vents. Breach strips the closed shell.",
            "On a silent beat, Tune works at any noise and hits for 8. Save your cells for the next beat.",
            "At half hull the tide changes to 8 / 0 / 7. Brace on 7 or 8 to return 4 damage.",
        )
        return self.text(hints[self.index - 3])

    def take_salvage(self, choice):
        if self.status != "active" or not self.salvage:
            return ""
        if choice == "1":
            self.pilot.pack.collect()
            reward = self.text("Spare cell stored.")
        elif choice == "2":
            reward = self.text("Service bay restored {amount} hull.", amount=self.pilot.heal(8))
        else:
            return ""
        self.salvage = False
        return reward

    def act(self, key):
        return self.resolve(key).message

    def resolve(self, key, phrase=""):
        if self.status != "active":
            return Turn(self.text("Dive ended."))
        if key == "q":
            self.status = "quit"
            return Turn(self.text("Ascent initiated."))
        if key == "i":
            return Turn(self.text("Scan / Pulse cycle {pattern}. Acoustic signature {song}.",
                                  pattern="-".join(map(str, self.pattern)), song=self.sector.song))
        incoming = self.response
        if key == "a":
            event = Event("cutter", self.contact.damage(self.cutter_damage))
            self._noise += 1
            message = self.text("Cutter hit for {amount}.", amount=event.points)
        elif key == "s":
            event = self.pilot.ability(self.contact, incoming)
            if event is None:
                return Turn(self.text("Ability depleted. Select another action."))
            self._noise = 0
            message = self.text("Anchor held. Pulse absorbed.") if event.kind == "anchor" else self.text("Decoy returned {amount} damage.", amount=event.points)
        elif key == "b":
            if not self.breach_ready:
                return Turn(self.text("Breach is spent until the next sector."))
            self.breach_ready = False
            event = Event("breach", self.contact.damage(7))
            message = self.text("Breach hit for {amount}. Armor disabled.", amount=event.points)
        elif key == "g":
            self._noise = 0
            returned = self.contact.damage(4) if self.crown_open and incoming >= 7 else 0
            incoming = max(0, incoming - 4)
            event = Event("brace", returned)
            message = self.text("Grounded the tide. Returned 4 damage." if returned else
                                "Brace absorbed up to 4 damage. Noise cleared.")
        elif key == "r":
            restored = self.pilot.pack.repair(self.pilot)
            if not restored:
                return Turn(self.text("Repair needs hull damage and one cell."))
            event = Event("repair", restored)
            message = self.text("Cell fitted. Hull +{amount}.", amount=restored)
        elif key == "f":
            if not self.can_tune:
                return Turn(self.text("Two noise marks open the hydrophone."))
            if phrase != self.sector.song:
                return Turn(self.text("No harmonic match. Listen and try again."))
            self._noise = 0
            event = Event("resonate", self.contact.damage(self.resonance_damage))
            message = self.text("Signature matched. Resonance hit for {amount}.", amount=event.points)
        else:
            return Turn(self.text("Unknown key. Scan with I or strike with A."))

        self.salvage = False
        if self.contact.hull == 0:
            tape = self.text(self.sector.tape)
            if self.index == len(SECTORS) - 1:
                self.status = "won"
            else:
                self.index += 1
                self.pilot.pack.collect()
                self.salvage = True
                self._enter()
                tape += "  [" + self.text("+1 cell") + "]"
            return Turn(tape, (event, Event("wreck")))

        events = [event]
        if event.kind in ("cutter", "repair", "breach", "brace"):
            hit = incoming
            if self.noise == 3:
                hit += 3
                self._noise = 0
                message += " " + self.text("Sonar lock.")
            if hit:
                events.append(Event("counter", self.pilot.damage(hit)))
                message += " " + self.text("Hull −{amount}.", amount=events[-1].points)
        self.turn += 1
        if self.pilot.hull == 0:
            self.status = "lost"
            message += " " + self.text("Telemetry lost.")
        return Turn(message, tuple(events))
