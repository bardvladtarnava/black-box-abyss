import json
import os
import sys
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from dive import Dive, SECTORS
from locale_text import LANGUAGES


@dataclass
class Settings:
    language: str = "bg"
    sound: bool = True
    motion: bool = True
    pixels: str = "safe"
    fullscreen: bool = True
    font: str = "Consolas"
    bold: bool = True

    @classmethod
    def read(cls, data):
        defaults = cls()
        options = {"language": LANGUAGES, "pixels": ("safe", "fine", "mono"),
                   "font": ("Consolas", "Lucida Console", "Host")}
        for field in fields(cls):
            key = field.name
            value = data.get(key)
            if key in options:
                if isinstance(value, str) and value in options[key]:
                    setattr(defaults, key, value)
            elif type(value) is bool:
                setattr(defaults, key, value)
        return defaults


def data_directory():
    if os.environ.get("BLACKBOX_DATA_DIR"):
        return Path(os.environ["BLACKBOX_DATA_DIR"])
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "BlackBoxAbyss"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BlackBoxAbyss"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "black-box-abyss"


@contextmanager
def campaign_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / "campaign.lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


class Logbook:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else data_directory()
        self.notices = set()
        self.settings = Settings.read(self._read("settings"))
        campaign = self._read("campaign")
        self.revision = campaign.get("revision")
        best = campaign.get("best", 0)
        self.best = best if type(best) is int and 0 <= best <= len(SECTORS) else 0
        self.resume = None
        self.entry = None
        self.retry = False
        if campaign.get("active") is not None:
            try:
                self.resume = Dive.from_snapshot(campaign["active"], self.settings.language)
                self.best = max(self.best, self.resume.cleared)
                self.retry = campaign.get("retry") is True
            except ValueError:
                self.notices.add("Checkpoint unreadable.")
        if self.resume and campaign.get("entry") is not None:
            try:
                entry = Dive.from_snapshot(campaign["entry"])
                if entry.index == self.resume.index and entry.pilot.name == self.resume.pilot.name and not entry.turn:
                    self.entry = entry.snapshot()
            except ValueError:
                self.notices.add("Checkpoint unreadable.")

    def _read(self, name):
        try:
            data = json.loads((self.root / (name + ".json")).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
                raise ValueError("Unsupported format")
            return data
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, RecursionError):
            self.notices.add("Checkpoint unreadable." if name == "campaign" else "Settings unreadable.")
            return {}

    def _write(self, name, data):
        tmp = None
        warning = "Checkpoint could not be saved." if name == "campaign" else "Settings could not be saved."
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=str(self.root), encoding="utf-8",
                                             prefix=name + "-", suffix=".tmp", delete=False) as stream:
                tmp = Path(stream.name)
                json.dump(dict(data, version=1), stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, self.root / (name + ".json"))
            self.notices.discard(warning)
            return True
        except OSError:
            self.notices.add(warning)
            return False
        finally:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass

    def preferences(self):
        saved = self._write("settings", asdict(self.settings))
        if saved:
            self.notices.discard("Settings unreadable.")
        return saved

    def checkpoint(self, game, new=False):
        best = max(self.best, game.cleared)
        entry = self.entry
        if game.status == "active":
            active = game.snapshot()
            if new or (game.salvage and not game.turn) or (entry is None and not game.turn):
                entry = active
        elif game.status == "lost":
            active = entry
        else:
            active = entry = None
        retry = game.status == "lost" and active is not None
        self.best, self.entry, self.retry = best, entry, retry
        self.resume = Dive.from_snapshot(active, game.language) if active is not None else None
        try:
            with campaign_lock(self.root):
                if self._read("campaign").get("revision") != self.revision:
                    self.notices.add("Another window saved a newer checkpoint. Reopen to continue it.")
                    return False
                revision = uuid.uuid4().hex
                saved = self._write("campaign", {"best": best, "active": active, "entry": entry,
                                                 "retry": retry, "revision": revision})
                if saved:
                    self.revision = revision
                    self.notices.discard("Checkpoint unreadable.")
                return saved
        except OSError:
            self.notices.add("Checkpoint could not be saved.")
            return False
