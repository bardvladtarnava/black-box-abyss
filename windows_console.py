import ctypes
import shutil
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path


def open_terminal(fullscreen, arguments):
    executable = shutil.which("wt.exe")
    if not executable:
        return False
    game = Path(__file__).resolve().with_name("play.py")
    options = ["--fullscreen"] if fullscreen else []
    command = [executable, "-w", "new", *options, "new-tab", "--title", "BLACK BOX",
               "--startingDirectory", str(game.parent), sys.executable, "-X", "utf8",
               str(game), "--in-window", *arguments]
    try:
        return subprocess.run(command, check=False).returncode == 0
    except OSError:
        return False


class Coord(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short)]


class FontInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.ULONG), ("index", wintypes.DWORD), ("cell", Coord),
                ("family", wintypes.UINT), ("weight", wintypes.UINT), ("face", ctypes.c_wchar * 32)]


class ClassicWindow:
    def __init__(self):
        import msvcrt
        self.kernel = ctypes.WinDLL("kernel32")
        self.user = ctypes.WinDLL("user32")
        self.kernel.GetConsoleWindow.restype = wintypes.HWND
        self.hwnd = wintypes.HWND(self.kernel.GetConsoleWindow())
        self.handle = wintypes.HANDLE(msvcrt.get_osfhandle(sys.stdout.fileno()))
        self.visible = bool(self.hwnd and self.user.IsWindowVisible(self.hwnd))
        self.original = FontInfo()
        self.original.size = ctypes.sizeof(self.original)
        self.has_font = self.visible and self.kernel.GetCurrentConsoleFontEx(
            self.handle, False, ctypes.byref(self.original))
        self.mode = wintypes.DWORD()
        self.has_mode = self.visible and self.kernel.GetConsoleDisplayMode(ctypes.byref(self.mode))
        self.maximized = self.visible and self.user.IsZoomed(self.hwnd)
        self.changed_mode = False
        self.expanded = False
        self.changed_font = False

    def set_font(self, face):
        if not self.has_font:
            return
        chosen = FontInfo.from_buffer_copy(self.original)
        if face != "Host":
            chosen.face = face
            chosen.index = 0
            chosen.cell.x = 0
        if self.kernel.SetCurrentConsoleFontEx(self.handle, False, ctypes.byref(chosen)):
            self.changed_font = True

    def apply(self, font, fullscreen):
        if not self.visible:
            return
        self.set_font(font)
        if fullscreen and self.has_mode and not self.mode.value & 1:
            self.changed_mode = bool(self.kernel.SetConsoleDisplayMode(self.handle, 1, ctypes.byref(Coord())))
        if fullscreen and not self.changed_mode and not self.mode.value & 1 and not self.maximized:
            self.user.ShowWindow(self.hwnd, 3)
            self.expanded = True

    def restore(self):
        if self.changed_mode:
            self.kernel.SetConsoleDisplayMode(self.handle, 2, ctypes.byref(Coord()))
        if self.changed_font:
            self.kernel.SetCurrentConsoleFontEx(self.handle, False, ctypes.byref(self.original))
        if self.expanded:
            self.user.ShowWindow(self.hwnd, 9)
