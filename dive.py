from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple


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
    def __init__(self):
        self._cells = [Cell(), Cell()]

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
    def __init__(self, pilot):
        self.pilot = pilot
        self.index = 0
        self.status = "active"
        self.salvage = False
        self._enter()

    @property
    def sector(self):
        return SECTORS[self.index]

    def _enter(self):
        self.contact = Character(self.sector.hull)
        self.turn = self._noise = 0
        self.breach_ready = True
        self.pilot.enter()

    @property
    def noise(self):
        return self._noise

    @property
    def pulse(self):
        pattern = self.sector.pulses
        return pattern[self.turn % len(pattern)]

    @property
    def can_tune(self):
        return self.status == "active" and self.noise == 2

    @property
    def armor(self):
        if not self.breach_ready:
            return 0
        if self.index == 1 and self.pulse == 5:
            return 3
        if self.index == 3 and self.contact.hull <= self.contact.maximum // 2:
            return 2
        return 0

    @property
    def cutter_damage(self):
        return 5 - self.armor

    @property
    def response(self):
        extra = 2 if self.index == 2 and self.noise == 2 else 0
        return self.pulse + extra

    @property
    def sector_hint(self):
        if self.index == 0:
            return "Cut twice to unlock Tune. The third cut risks a sonar counter."
        if self.index == 1:
            return "The crab seals its shell on pulse 5. Breach strips its armor for the fight."
        if self.index == 2:
            return "At two noise marks the eel hits +2. Tune or Brace to clear noise."
        return "The Listener shields itself at half hull. Breach can disable the shield before it activates."

    def take_salvage(self, choice):
        if self.status != "active" or not self.salvage:
            return ""
        if choice == "1":
            self.pilot.pack.collect()
            reward = "Spare cell stored."
        elif choice == "2":
            reward = f"Service bay restored {self.pilot.heal(8)} hull."
        else:
            return ""
        self.salvage = False
        return reward

    def act(self, key):
        return self.resolve(key).message

    def resolve(self, key, phrase=""):
        if self.status != "active":
            return Turn("Dive ended.")
        if key == "q":
            self.status = "quit"
            return Turn("Ascent initiated.")
        if key == "i":
            return Turn(f"SCAN / Pulse cycle {'-'.join(map(str, self.sector.pulses))}. Acoustic signature {self.sector.song}.")
        incoming = self.response
        if key == "a":
            event = Event("cutter", self.contact.damage(self.cutter_damage))
            self._noise += 1
            message = f"Cutter hit for {event.points}."
        elif key == "s":
            event = self.pilot.ability(self.contact, incoming)
            if event is None:
                return Turn("Ability depleted. Select another action.")
            self._noise = 0
            message = "Anchor held. Pulse absorbed." if event.kind == "anchor" else f"Decoy returned {event.points} damage."
        elif key == "b":
            if not self.breach_ready:
                return Turn("Breach is spent until the next sector.")
            self.breach_ready = False
            event = Event("breach", self.contact.damage(7))
            message = f"Breach hit for {event.points}. Armor disabled."
        elif key == "g":
            self._noise = 0
            incoming = max(0, incoming - 4)
            event = Event("brace")
            message = "Brace absorbed up to 4 damage. Noise cleared."
        elif key == "r":
            restored = self.pilot.pack.repair(self.pilot)
            if not restored:
                return Turn("Repair needs hull damage and one cell.")
            event = Event("repair", restored)
            message = f"Cell fitted. Hull +{restored}."
        elif key == "f":
            if not self.can_tune:
                return Turn("Two noise marks open the hydrophone.")
            if phrase != self.sector.song:
                return Turn("No harmonic match. Listen and try again.")
            self._noise = 0
            event = Event("resonate", self.contact.damage(4))
            message = f"Signature matched. Resonance hit for {event.points}; contact silenced."
        else:
            return Turn("Unknown key. Scan with I or strike with A.")

        self.salvage = False
        if self.contact.hull == 0:
            tape = self.sector.tape
            if self.index == len(SECTORS) - 1:
                self.status = "won"
            else:
                self.index += 1
                self.pilot.pack.collect()
                self.salvage = True
                self._enter()
                tape += "  [+1 cell]"
            return Turn(tape, (event, Event("wreck")))

        events = [event]
        if event.kind in ("cutter", "repair", "breach", "brace"):
            hit = incoming
            if self.noise == 3:
                hit += 3
                self._noise = 0
                message += " SONAR LOCK."
            if hit:
                events.append(Event("counter", self.pilot.damage(hit)))
                message += f" Hull -{events[-1].points}."
        self.turn += 1
        if self.pilot.hull == 0:
            self.status = "lost"
            message += " Telemetry lost."
        return Turn(message, tuple(events))
