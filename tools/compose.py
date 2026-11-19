import array
import math
import random
import sys
import wave
from pathlib import Path

RATE = 22050
BEAT = 13230
BAR = BEAT * 4
TAU = math.tau
ROOT = Path(__file__).resolve().parents[1] / "sound"


def note(key):
    return 440 * 2 ** ((key - 69) / 12)


def tone(key, duration, voice):
    length = round(duration * RATE)
    output = []
    phase = 0.0
    rng = random.Random(240 + int(key))
    smooth = 0.0
    pitch = note(key)
    for i in range(length):
        t = i / RATE
        attack = min(1.0, t * (22 if voice == "pad" else 260))
        tail = min(1.0, (length - i) / (RATE * .025))
        if voice == "kick":
            phase += TAU * (38 + 108 * math.exp(-t * 31)) / RATE
            value = math.sin(phase) * math.exp(-t * 12)
        elif voice in ("snare", "shell"):
            noise = rng.uniform(-1, 1)
            smooth += .17 * (noise - smooth)
            value = (smooth * 1.9 + .12 * math.sin(TAU * 171 * t)) * math.exp(-t * 19)
        elif voice == "pad":
            phase = TAU * pitch * t
            value = (.56 * math.sin(phase) + .24 * math.sin(phase * 1.003) +
                     .16 * math.sin(2 * phase + .4 * math.sin(t * 3))) * math.sin(math.pi * i / length) ** .8
        elif voice == "bass":
            phase = TAU * pitch * t
            value = (.72 * math.sin(phase) + .20 * math.sin(2 * phase) +
                     .1 * math.sin(3 * phase)) * math.exp(-t * 3.8)
        else:
            phase = TAU * pitch * t
            value = (.66 * math.sin(phase + .9 * math.exp(-t * 9) * math.sin(phase * 2)) +
                     .18 * math.sin(phase * 3.01) + .09 * math.sin(phase * 4.98)) * math.exp(-t * 4.3)
        output.append(attack * tail * value)
    return output


def paste(track, sample, offset, gain, wrap=False):
    for i, val in enumerate(sample):
        index = offset + i
        if index >= len(track):
            if not wrap:
                break
            index %= len(track)
        track[index] += val * gain


def save(name, values):
    out = array.array("h", (int(32767 * max(-.98, min(.98, v))) for v in values))
    if sys.byteorder == "big":
        out.byteswap()
    with wave.open(str(ROOT / (name + ".wav")), "wb") as f:
        f.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        f.writeframes(out.tobytes())


def compose_zone(zone):
    loop = [0.] * (BAR * 4)
    roots = ((38, 34, 41, 36), (38, 41, 36, 33), (38, 46, 41, 36), (38, 35, 34, 33))[zone]
    for bar, root in enumerate(roots):
        start = bar * BAR
        for chord_note in (root + 12, root + 19, root + 22):
            paste(loop, tone(chord_note, 2.8, "pad"), start, .086, True)
        for pos in (0, 1.5, 2.75):
            paste(loop, tone(root, .75, "bass"), start + int(BEAT * pos), .23, True)
        for beat in ((0, 2), (0, 1.75, 3), (0, 2.5), (0, 1.5, 2.75))[zone]:
            paste(loop, tone(38, .34, "kick"), start + round(BEAT * beat), .27, True)
        for beat in (1, 3, 3.5):
            paste(loop, tone(57, .18, "shell"), start + round(BEAT * beat), .15, True)
        for step, offset in enumerate(((0, 7, 3), (0, 3, 10), (7, 3, 0), (0, 12, 7))[bar]):
            pitch = root + 24 + offset + (12 if zone == 2 else 0)
            glass = tone(pitch, .85, "glass")
            place = start + round(BEAT * (.5 + step * .95 + .25 * (zone == 3)))
            paste(loop, glass, place, .13, True)
            paste(loop, glass, place + round(.27 * RATE), .041, True)
    save(f"depth{zone}", loop)


def effect(name, duration, freq, sweep=0, grit=0, decay=6, ring=0):
    rng = random.Random(25)
    length = round(RATE * duration)
    phase = smooth = 0.
    output = []
    for i in range(length):
        t = i / RATE
        phase += TAU * (freq + sweep * math.exp(-t * 15)) / RATE
        smooth += .23 * (rng.uniform(-1, 1) - smooth)
        envelope = min(1, t * 180) * math.exp(-decay * t) * min(1, (length - i) / (RATE * .055))
        value = math.sin(phase + ring * math.sin(phase * 2.4)) * (1 - grit) + smooth * 2.4 * grit
        output.append(.64 * envelope * value)
    save(name, output)


def main():
    ROOT.mkdir(exist_ok=True)
    for i in range(4):
        compose_zone(i)
    pressure = [0.] * BAR
    for pos in (0, .32, 2, 2.32):
        paste(pressure, tone(35, .30, "kick"), round(BEAT * pos), .32, True)
    save("pressure", pressure)
    for i, key in enumerate((62, 65, 69), 1):
        save(f"note{i}", [v * .52 for v in tone(key + 12, .63, "glass")])
    effect("swing", .22, 98, 440, .61, 13)
    effect("impact", .54, 52, 170, .52, 8, .8)
    effect("enemy", .52, 63, 119, .26, 8, 1.6)
    effect("clang", .7, 202, 40, .25, 7, 2.7)
    effect("echo", .66, 245, 100, .08, 4, 1.6)
    effect("wreck", .95, 41, 140, .79, 4, .6)
    for name, keys in (("heal", (62, 69, 74)), ("chord", (62, 65, 69, 74)),
                       ("reel", (69, 65, 62)), ("ending", (62, 65, 69, 74, 77)),
                       ("lost", (50, 45, 38))):
        out = [0.] * round(RATE * (1.0 + len(keys) * .16))
        for i, key in enumerate(keys):
            paste(out, tone(key, 1., "glass"), round(RATE * .16 * i), .39)
        save(name, out)


if __name__ == "__main__":
    main()
