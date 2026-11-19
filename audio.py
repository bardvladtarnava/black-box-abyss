import array
import ctypes
import ctypes.util
import os
import queue
import shutil
import struct
import subprocess
import sys
import threading
import wave
from pathlib import Path

RATE = 22050
BLOCK = 512
FRAME_BYTES = 4
PANS = {
    "swing": (-.65, .45), "impact": (.68, .22), "enemy": (-.65, -.3),
    "clang": (-.55, -.12), "echo": (.55, -.58), "heal": (-.45, -.1),
    "wreck": (.68, .05), "chord": (-.5, .6),
    "note1": (-.38, -.38), "note2": (0, 0), "note3": (.38, .38),
}
ASSETS = Path(__file__).with_name("sound")


class Mixer:
    def __init__(self):
        self.bank = {}
        for path in ASSETS.glob("*.wav"):
            with wave.open(str(path), "rb") as stream:
                if (stream.getframerate(), stream.getsampwidth(), stream.getnchannels()) != (RATE, 2, 1):
                    raise ValueError(f"Invalid audio format in {path.name}")
                samples = array.array("h")
                samples.frombytes(stream.readframes(stream.getnframes()))
                if sys.byteorder == "big":
                    samples.byteswap()
                self.bank[path.stem] = samples
        self.zone = self.previous = 0
        self.position = 0
        self.transition = 0
        self.pressure = False
        self.pressure_gain = 0.
        self.voices = []
        self.muted = False

    def scene(self, zone, danger=False):
        if zone != self.zone:
            self.previous, self.zone = self.zone, zone
            self.transition = 3072
        self.pressure = danger

    def cue(self, name):
        if name in self.bank and not self.muted:
            start, end = PANS.get(name, (0., 0.))
            self.voices.append((self.bank[name], 0, start, end))
            self.voices = self.voices[-12:]

    def mute(self, muted):
        self.muted = muted
        if muted:
            self.voices.clear()

    def render(self, count):
        lead = self.bank[f"depth{self.zone}"]
        old = self.bank[f"depth{self.previous}"]
        layer = self.bank["pressure"]
        output = array.array("h")
        pressure_target = .72 if self.pressure else 0.
        for i in range(count):
            pos = self.position + i
            value = lead[pos % len(lead)]
            reflection = lead[(pos - 249) % len(lead)]
            if self.transition:
                fade = self.transition / 3072
                value = old[pos % len(old)] * fade + value * (1 - fade)
                reflection = old[(pos - 249) % len(old)] * fade + reflection * (1 - fade)
                self.transition -= 1
            self.pressure_gain += .00045 * (pressure_target - self.pressure_gain)
            pulse = layer[pos % len(layer)] * self.pressure_gain
            left = value * .63 + reflection * .05 + pulse
            right = value * .52 + reflection * .16 + pulse
            for sample, offset, start, end in self.voices:
                point = offset + i
                if point < len(sample):
                    pan = start + (end - start) * point / len(sample)
                    voice = sample[point] * .66
                    left += voice * (1 - pan)
                    right += voice * (1 + pan)
            if self.muted:
                output.extend((0, 0))
            else:
                output.append(max(-32767, min(32767, round(left))))
                output.append(max(-32767, min(32767, round(right))))
        self.position += count
        self.voices = [(s, n + count, a, b) for s, n, a, b in self.voices if n + count < len(s)]
        if sys.byteorder == "big":
            output.byteswap()
        return output.tobytes()


class WaveFormat(ctypes.Structure):
    _fields_ = [("tag", ctypes.c_uint16), ("channels", ctypes.c_uint16),
                ("rate", ctypes.c_uint32), ("bytes_sec", ctypes.c_uint32),
                ("align", ctypes.c_uint16), ("bits", ctypes.c_uint16), ("extra", ctypes.c_uint16)]


class WaveHeader(ctypes.Structure):
    _fields_ = [("data", ctypes.c_void_p), ("size", ctypes.c_uint32),
                ("recorded", ctypes.c_uint32), ("user", ctypes.c_size_t),
                ("flags", ctypes.c_uint32), ("loops", ctypes.c_uint32),
                ("next", ctypes.c_void_p), ("reserved", ctypes.c_size_t)]


class WindowsAudio:
    label = "WaveOut"

    def __init__(self):
        self.dll = ctypes.WinDLL("winmm")
        self.handle = ctypes.c_void_p()
        fmt = WaveFormat(1, 2, RATE, RATE * FRAME_BYTES, FRAME_BYTES, 16, 0)
        self._check(self.dll.waveOutOpen(ctypes.byref(self.handle), 0xffffffff, ctypes.byref(fmt), 0, 0, 0))
        self.slots = []
        self.index = 0
        try:
            for _ in range(2):
                buf = ctypes.create_string_buffer(BLOCK * FRAME_BYTES)
                header = WaveHeader(data=ctypes.addressof(buf), size=BLOCK * FRAME_BYTES)
                self._check(self.dll.waveOutPrepareHeader(self.handle, ctypes.byref(header), ctypes.sizeof(header)))
                self.slots.append((buf, header))
        except OSError:
            self.close()
            raise

    @staticmethod
    def _check(result):
        if result:
            raise OSError(f"WaveOut error {result}")

    def write(self, data, stop):
        buf, hdr = self.slots[self.index]
        while hdr.flags & 16:
            if stop.wait(.002):
                return
        ctypes.memmove(buf, data, len(data))
        self._check(self.dll.waveOutWrite(self.handle, ctypes.byref(hdr), ctypes.sizeof(hdr)))
        self.index = 1 - self.index

    def close(self):
        self.dll.waveOutReset(self.handle)
        for _, h in self.slots:
            self.dll.waveOutUnprepareHeader(self.handle, ctypes.byref(h), ctypes.sizeof(h))
        self.dll.waveOutClose(self.handle)


class MacAudio:
    label = "CoreAudio"

    def __init__(self):
        self.api = ctypes.CDLL(ctypes.util.find_library("AudioToolbox") or "AudioToolbox")
        self.guard = threading.Condition()
        self.free = []
        self.closing = False
        self.handle = ctypes.c_void_p()
        callback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        self.callback = callback(self._returned)
        fmt = ctypes.create_string_buffer(struct.pack("=d8I", RATE, 0x6c70636d, 12, FRAME_BYTES, 1, FRAME_BYTES, 2, 16, 0))
        self._check(self.api.AudioQueueNewOutput(ctypes.byref(fmt), self.callback, None, None, None, 0, ctypes.byref(self.handle)))
        try:
            for _ in range(3):
                buf = ctypes.c_void_p()
                self._check(self.api.AudioQueueAllocateBuffer(self.handle, BLOCK * FRAME_BYTES, ctypes.byref(buf)))
                self.free.append(buf.value)
        except OSError:
            self.close()
            raise
        self.primed = 0

    class Buffer(ctypes.Structure):
        _fields_ = [("capacity", ctypes.c_uint32), ("data", ctypes.c_void_p), ("size", ctypes.c_uint32)]

    @staticmethod
    def _check(result):
        if result:
            raise OSError(f"AudioQueue error {result}")

    def _returned(self, user, handle, address):
        with self.guard:
            if not self.closing:
                self.free.append(address)
                self.guard.notify()

    def write(self, data, stop):
        with self.guard:
            while not self.free:
                if stop.is_set():
                    return
                self.guard.wait(.05)
            address = self.free.pop()
        buf = self.Buffer.from_address(address)
        ctypes.memmove(buf.data, data, len(data))
        buf.size = len(data)
        self._check(self.api.AudioQueueEnqueueBuffer(self.handle, ctypes.c_void_p(address), 0, None))
        self.primed += 1
        if self.primed == 2:
            self._check(self.api.AudioQueueStart(self.handle, None))

    def close(self):
        self.closing = True
        self.api.AudioQueueDispose(self.handle, True)


class PulseAudio:
    label = "PulseAudio"

    def __init__(self):
        filename = ctypes.util.find_library("pulse-simple")
        if not filename:
            raise OSError("PulseAudio unavailable")
        self.lib = ctypes.CDLL(filename)
        self.lib.pa_simple_new.restype = ctypes.c_void_p
        spec = ctypes.create_string_buffer(struct.pack("=IIB3x", 3, RATE, 2))
        attributes = ctypes.create_string_buffer(struct.pack("=5I", 0xffffffff, BLOCK * FRAME_BYTES * 3, 0, BLOCK * FRAME_BYTES, 0xffffffff))
        handle = self.lib.pa_simple_new(None, b"Black Box", 1, None, b"Hydrophone", spec, None, attributes, None)
        if not handle:
            raise OSError("No PulseAudio output")
        self.handle = ctypes.c_void_p(handle)

    def write(self, data, stop):
        if self.lib.pa_simple_write(self.handle, data, ctypes.c_size_t(len(data)), None) < 0:
            raise OSError("PulseAudio output disconnected")

    def close(self):
        self.lib.pa_simple_free(self.handle)


class SDLSpec(ctypes.Structure):
    _fields_ = [("frequency", ctypes.c_int), ("format", ctypes.c_uint16),
                ("channels", ctypes.c_uint8), ("silence", ctypes.c_uint8),
                ("samples", ctypes.c_uint16), ("padding", ctypes.c_uint16),
                ("size", ctypes.c_uint32), ("callback", ctypes.c_void_p),
                ("userdata", ctypes.c_void_p)]


class LinuxAudio:
    label = "SDL audio"

    def __init__(self):
        path = ctypes.util.find_library("SDL2-2.0")
        if not path:
            raise OSError("SDL audio unavailable")
        self.api = ctypes.CDLL(path)
        if self.api.SDL_InitSubSystem(0x10) < 0:
            raise OSError("Audio driver unavailable")
        spec = SDLSpec(RATE, 0x8010, 2, 0, BLOCK, 0, 0, None, None)
        self.api.SDL_OpenAudioDevice.restype = ctypes.c_uint32
        self.id = self.api.SDL_OpenAudioDevice(None, 0, ctypes.byref(spec), None, 0)
        if not self.id:
            self.api.SDL_QuitSubSystem(0x10)
            raise OSError("No SDL output device")
        self.api.SDL_PauseAudioDevice(self.id, 0)

    def write(self, data, stop):
        while self.api.SDL_GetQueuedAudioSize(self.id) >= BLOCK * FRAME_BYTES * 2:
            if stop.wait(.003):
                return
        if self.api.SDL_QueueAudio(self.id, data, len(data)) < 0:
            raise OSError("SDL audio disconnected")

    def close(self):
        self.api.SDL_CloseAudioDevice(self.id)
        self.api.SDL_QuitSubSystem(0x10)


class AlsaPlayer:
    label = "ALSA"

    def __init__(self):
        path = shutil.which("aplay")
        if not path:
            raise OSError("No aplay output")
        self.process = subprocess.Popen([path, "-q", "-t", "raw", "-f", "S16_LE", "-c", "2",
                                         "-r", str(RATE), "--buffer-time=50000"],
                                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def write(self, data, stop):
        self.process.stdin.write(data)
        self.process.stdin.flush()

    def close(self):
        try:
            self.process.stdin.close()
        except BrokenPipeError:
            pass
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait()


def output_device():
    if os.name == "nt":
        return WindowsAudio()
    if sys.platform == "darwin":
        return MacAudio()
    try:
        return LinuxAudio()
    except OSError:
        try:
            return PulseAudio()
        except OSError:
            return AlsaPlayer()


class Sound:
    def __init__(self, active=True, muted=False):
        self.commands = queue.SimpleQueue()
        self.stop = threading.Event()
        self.muted = muted
        self.label = "starting" if active else "offline"
        self.thread = None
        if active:
            self.thread = threading.Thread(target=self._play, daemon=True)
            self.thread.start()

    def _play(self):
        device = None
        try:
            device = output_device()
            mixer = Mixer()
            mixer.mute(self.muted)
            self.label = device.label
            while not self.stop.is_set():
                while True:
                    try:
                        method, args = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    getattr(mixer, method)(*args)
                device.write(mixer.render(BLOCK), self.stop)
        except (OSError, ValueError, KeyError):
            self.label = "offline"
        finally:
            if device:
                device.close()

    def command(self, method, *args):
        if self.thread and self.thread.is_alive():
            self.commands.put((method, args))

    def cue(self, name):
        self.command("cue", name)

    def scene(self, zone, danger=False):
        self.command("scene", zone, danger)

    def toggle(self):
        self.muted = not self.muted
        self.command("mute", self.muted)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=1)
