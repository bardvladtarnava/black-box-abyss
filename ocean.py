import math
import random
from functools import lru_cache

W, H = 140, 48
WHITE = 0xe3f8e5
CYAN = 0x7bf9dd
GOLD = 0xf9bd66
MINT = 0x64ccae
INK = 0x101e2c
METAL = 0x445969
STEEL = 0x81969a
PLATE = 0xca8447
BRASS = 0xf3b85b
PALE = 0xffdf99
RED = 0xe1746b
DEEP = (0x132f41, 0x173530, 0x262d46, 0x1e2035, 0x12374a, 0x251d42, 0x12232d)
LIGHT = (0x377477, 0x59745f, 0x525672, 0x594356, 0x427f91, 0x70547f, 0x4e605f)
ACCENTS = (CYAN, 0xeeb176, 0xb4b7ff, 0xf59b99, 0x8fe9ff, 0xf5b0ed, 0xffbf78)
ANCHOR_Y = (25, 30, 25, 23, 25, 23, 24)
TAU = 2 * math.pi


def mix(left, right, amount):
    t = max(0, min(256, int(amount * 256)))
    s = 256 - t
    rb = (((left & 0xff00ff) * s + (right & 0xff00ff) * t) >> 8) & 0xff00ff
    g = (((left & 0x00ff00) * s + (right & 0x00ff00) * t) >> 8) & 0x00ff00
    return rb | g


class Raster:
    def __init__(self, pixels=None):
        self.pixels = pixels if pixels is not None else [0] * (W * H)

    def dot(self, x, y, color):
        x, y = round(x), round(y)
        if 0 <= x < W and 0 <= y < H:
            self.pixels[y * W + x] = color

    def rect(self, x, y, w, h, color):
        x, y, w, h = map(round, (x, y, w, h))
        lo, hi = max(0, x), min(W, x + w)
        if lo >= hi:
            return
        run = [color] * (hi - lo)
        for row in range(max(0, y), min(H, y + h)):
            self.pixels[row * W + lo:row * W + hi] = run

    def line(self, x, y, u, v, color, size=1):
        dx, dy = u - x, v - y
        count = max(1, math.ceil(max(abs(dx), abs(dy))))
        for i in range(count + 1):
            a, b = x + dx * i / count, y + dy * i / count
            if size == 1:
                self.dot(a, b, color)
            else:
                self.rect(a, b, size, size, color)

    def path(self, points, color, size=1):
        for (x, y), (u, v) in zip(points, points[1:]):
            self.line(x, y, u, v, color, size)

    def disk(self, x, y, rx, ry, color):
        x, y = round(x), round(y)
        rx, ry = max(1, round(rx)), max(1, round(ry))
        for delta in range(-ry, ry + 1):
            span = round(rx * math.sqrt(max(0, 1 - (delta / ry) ** 2)))
            self.rect(x - span, y + delta, span * 2 + 1, 1, color)

    def ring(self, x, y, rx, ry, color):
        points = [(x + rx * math.cos(i * TAU / 48), y + ry * math.sin(i * TAU / 48)) for i in range(49)]
        self.path(points, color)

    def poly(self, points, color):
        for y in range(max(0, math.ceil(min(v for _, v in points))), min(H, math.ceil(max(v for _, v in points)))):
            cross = []
            for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
                if min(y0, y1) <= y < max(y0, y1):
                    cross.append(x0 + (x1 - x0) * (y - y0) / (y1 - y0))
            cross.sort()
            for a, b in zip(cross[::2], cross[1::2]):
                self.rect(math.ceil(a), y, math.floor(b) - math.ceil(a) + 1, 1, color)


@lru_cache(maxsize=len(DEEP))
def backdrop(zone):
    rng = random.Random(937 + zone)
    c = Raster()
    base, light = DEEP[zone], LIGHT[zone]
    for y in range(H):
        for x in range(W):
            shaft = max(0, math.cos((x + y * .55 - 62) * .11)) ** 8
            level = (.32 + .28 * math.cos((x - 60) / 58) + shaft * .25) * (1 - .68 * y / H)
            c.dot(x, y, mix(base, light, round(level * 17) / 17))
    shadow, steel, rim = mix(base, INK, .6), mix(base, light, .26), mix(base, light, .63)
    if zone == 0:
        for x, radius in ((8, 27), (71, 22), (135, 27)):
            for r in (radius, radius - 2, radius - 6):
                c.ring(x, 27, r, r, steel if r != radius - 2 else rim)
            c.line(x - radius, 28, x - radius, 43, shadow, 2)
        for x in range(0, W, 9):
            c.rect(x, 6, 5, 1, rim)
    elif zone == 1:
        for x in (8, 24, 61, 84, 126, 135):
            c.rect(x, 0, 5, 43, shadow)
            c.rect(x + 1, 0, 1, 43, rim)
            for y in (6, 20, 34):
                c.rect(x - 1, y, 7, 2, steel)
        for x, y in ((63, 15), (124, 8)):
            c.ring(x, y, 11, 11, rim)
            for i in range(6):
                a = i * TAU / 6
                c.line(x, y, x + 9 * math.cos(a), y + 9 * math.sin(a), steel, 2)
    elif zone == 2:
        for x in range(-8, W, 24):
            c.rect(x, 3, 19, 29, shadow)
            for y in range(6, 30, 5):
                c.rect(x + 2, y, 15, 3, steel)
                c.rect(x + 4, y, 1, 2, rim)
                c.dot(x + 14, y + 1, mix(rim, CYAN, .37))
        for x in (9, 52, 81):
            c.path([(x, 0), (x + 7, 5), (x + 20, 7), (x + 28, 0)], shadow)
    elif zone == 3:
        for r in (11, 15, 22, 24):
            c.ring(73, 17, r * 1.32, r, rim if r == 22 else steel)
        for i in range(12):
            a = i * TAU / 12
            c.line(73 + 16 * math.cos(a), 17 + 13 * math.sin(a),
                   73 + 28 * math.cos(a), 17 + 21 * math.sin(a), steel)
        for x in (9, 13, 130, 134):
            c.rect(x, 0, 2, H, shadow)
    elif zone == 4:
        for x in range(-8, W, 13):
            end = rng.randrange(7, 24)
            c.poly([(x, 0), (x + 10, 0), (x + 4, end)], steel)
            c.line(x + 9, 0, x + 4, end, rim)
        for x in (0, 14, 48, 68, 118, 136):
            tip = rng.randrange(18, 33)
            c.poly([(x - 8, 43), (x + 3, tip), (x + 10, 42)], shadow)
            c.line(x + 3, tip, x - 2, 42, rim)
    elif zone == 5:
        for x in (5, 22, 48, 79, 118, 138):
            c.path([(x - 15, 0), (x - 8, 8), (x, 12), (x + 8, 8), (x + 15, 0)], steel, 2)
            length = rng.randrange(15, 36)
            c.line(x, 12, x, length, rim)
            c.disk(x, length, 2, 1, rim)
        for x in range(-8, W, 19):
            c.poly([(x, 43), (x + 6, 29), (x + 10, 37), (x + 16, 31), (x + 19, 43)], shadow)
    else:
        for r in (11, 17, 24, 34, 45):
            c.ring(70, 13, r, r * .56, rim if r == 24 else steel)
        c.disk(70, 13, 10, 5, shadow)
        for x in (-6, 11, 46, 82, 121, 142):
            c.poly([(x - 3, 0), (x + 3, 0), (x, 8), (x - 1, 24)], shadow)
            c.path([(x - 6, 42), (x + 2, 35), (x + 7, 23)], steel, 2)
    for x in range(W):
        floor = 40 + round(1.7 * math.sin(x * .09) + .7 * math.cos(x * .25))
        c.rect(x, floor, 1, H - floor, shadow)
        if x % 3 == 0:
            c.dot(x, floor, rim)
    for _ in range(110):
        x, y = rng.randrange(W), rng.randrange(43, H)
        c.rect(x, y, rng.randrange(1, 4), 1, steel)
    return tuple(c.pixels)


def joint(c, x, y, size=2):
    c.disk(x, y, size, size, INK)
    c.dot(x, y, STEEL)


def stride(surge, side):
    return math.sin(surge * math.pi * 2 + side * math.pi / 2) * math.sin(surge * math.pi)


def rig(c, name, x, y, clock, extension, guard, surge=0):
    echo = name == "Echo"
    plate, shine = (0x568f9c, 0xb7f1df) if echo else (PLATE, BRASS)
    dark = mix(plate, INK, .52)
    sway = round(.75 * math.sin(clock * 2.2))
    y += sway
    for side, shade in ((-1, dark), (1, plate)):
        step = stride(surge, side)
        lift = max(0, step) * 3
        hip = (x + side * 3, y + 6)
        knee = (x + side * 5 + extension // 4 + step * 3, y + 11 - lift)
        foot = (x + side * 7 - extension // 4 + step * 6, y + 15 - sway - lift)
        c.line(*hip, *knee, METAL, 4)
        c.line(*knee, *foot, INK, 3)
        c.line(knee[0] + 1, knee[1] + 2, foot[0] + 1, foot[1], STEEL)
        c.rect(knee[0] - 1, knee[1] - 1, 5, 3, shade)
        c.rect(foot[0] - 1, foot[1], 8, 3, dark)
        c.rect(foot[0], foot[1], 6, 1, shine)
    c.rect(x - 10, y - 7, 5, 12, INK)
    c.rect(x - 10, y - 6, 3, 8, STEEL)
    for k in range(3):
        c.rect(x - 10, y - 5 + k * 3, 4, 1, METAL)
    c.poly([(x - 7, y - 7), (x + 5, y - 8), (x + 8, y - 3),
            (x + 5, y + 6), (x - 2, y + 9), (x - 7, y + 5)], dark)
    c.poly([(x - 6, y - 6), (x + 5, y - 7), (x + 7, y - 3),
            (x + 4, y + 2), (x - 4, y + 3)], plate)
    c.line(x - 5, y - 6, x + 5, y - 7, shine)
    c.rect(x - 2, y + 4, 7, 2, INK)
    c.rect(x - 2, y + 4, 3, 1, CYAN)
    if echo:
        c.path([(x - 8, y - 8), (x - 13, y - 12), (x - 13, y - 15)], shine)
        c.path([(x - 5, y - 9), (x - 8, y - 14), (x - 4, y - 13)], plate)
    c.disk(x, y - 8, 6, 5, dark)
    c.disk(x + 1, y - 9, 5, 4, plate)
    c.rect(x, y - 10, 7, 3, INK)
    c.rect(x + 2, y - 10, 5, 1, CYAN)
    c.dot(x + 6, y - 10, WHITE)
    elbow = (x + 7 + extension // 2, y + 3 - guard)
    hand = (x + 12 + extension, y + 1 - guard)
    c.line(x + 3, y - 3, *elbow, INK, 4)
    c.line(*elbow, *hand, STEEL, 3)
    joint(c, *elbow)
    c.disk(x + 3, y - 3, 4, 3, shine)
    c.disk(x + 3, y - 2, 4, 2, plate)
    c.rect(hand[0] - 2, hand[1] - 2, 7, 4, METAL)
    c.poly([(hand[0] + 3, hand[1] - 2), (hand[0] + 12, hand[1] - 4),
            (hand[0] + 8, hand[1]), (hand[0] + 3, hand[1] + 1)], shine)
    c.line(hand[0] + 4, hand[1], hand[0] + 12, hand[1] - 4, CYAN)


def lantern(c, x, y, t, snap):
    swing = math.sin(t * 3) * 2
    for side in (-1, 1):
        c.poly([(x + side * 5, y), (x + side * 15, y - 4 + swing),
                (x + side * 12, y + 3), (x + side * 6, y + 5)], 0x417c85)
        c.line(x + side * 6, y, x + side * 15, y - 4 + swing, 0x8ac3af)
    for side in (-1, 0, 1):
        c.path([(x + side * 4, y + 4), (x + side * 6, y + 8),
                (x + side * 6 - 2 + swing, y + 11)], 0x699998)
    c.disk(x, y, 9, 7, 0x234653)
    c.disk(x, y - 1, 8, 6, 0x567e7e)
    c.disk(x - 3, y - 1, 5, 4, INK)
    c.disk(x - 4, y - 1, 3, 2, GOLD)
    c.dot(x - 5, y - 2, WHITE)
    c.path([(x, y - 6), (x - 2, y - 12), (x - 7, y - 14), (x - 10 - snap, y - 10)], STEEL)
    c.disk(x - 10 - snap, y - 9, 2, 2, PALE)


def crab(c, x, y, t, snap):
    for side in (-1, 1):
        for i in range(3):
            sway = math.sin(t * 3 + i) * 1.7
            c.path([(x + side * 5, y + 2), (x + side * (9 + i * 3), y + i),
                    (x + side * (14 + i * 3) + sway, y + 10 - i)], 0x775a54, 2)
        claw = x + side * (15 + snap)
        c.line(x + side * 7, y - 1, claw, y - 6, 0xbe7958, 3)
        c.disk(claw, y - 7, 5, 4, 0xc17d56)
        c.poly([(claw - 4, y - 8), (claw - 5 - snap, y - 14), (claw, y - 9)], PALE)
        c.poly([(claw + 1, y - 8), (claw + 4 + snap, y - 13), (claw + 4, y - 7)], BRASS)
    c.disk(x, y + 1, 11, 6, 0x633b3c)
    c.disk(x - 1, y - 1, 10, 5, 0xb76c50)
    c.line(x - 7, y - 4, x + 3, y - 5, 0xe3a56e)
    for i in (-5, 3):
        c.rect(x + i, y - 6, 3, 4, INK)
        c.rect(x + i, y - 6, 2, 1, CYAN)


def eel(c, x, y, t, snap):
    for i in range(30, -1, -1):
        px = x - 9 + i * .96
        py = y + math.sin(t * 2.7 + i * .16) * (2 + i * .15) - i * .10
        radius = max(1, 5 - i * .13)
        c.disk(px, py, radius + 1, radius, 0x314d68)
        c.dot(px, py - radius, 0x839caf)
        if i % 4 == 0:
            c.line(px, py - radius, px + 2, py - radius - 3, 0x84dac7)
            c.dot(px, py + 1, CYAN)
    hy = y + math.sin(t * 2.7) * 2
    c.poly([(x - 6, hy - 5), (x - 15, hy - 4), (x - 20 - snap, hy),
            (x - 12, hy + 1), (x - 7, hy + 4)], 0x7997a0)
    c.line(x - 18, hy + 3 + snap, x - 9, hy + 4, CYAN)
    c.dot(x - 14, hy - 2, PALE)


def listener(c, x, y, t, snap):
    for arm in range(7):
        root = x - 10 + arm * 3
        chain = [(root + math.sin(t * 1.7 + arm + i * .38) * (i * .65),
                  y + 3 + i) for i in range(13)]
        c.path(chain, 0x925a68 if arm % 2 else 0x536d79, 2)
        c.dot(*chain[-1], PALE)
    c.disk(x, y - 3, 14, 11, 0x332e43)
    c.disk(x - 1, y - 4, 13, 10, 0x94616e)
    c.ring(x - 1, y - 4, 12, 9, 0xd99b85)
    for i in range(10):
        a = i * TAU / 10 + t * .25
        c.line(x + 7 * math.cos(a), y - 4 + 6 * math.sin(a),
               x + 11 * math.cos(a), y - 4 + 9 * math.sin(a), 0x594355)
    c.disk(x - 4, y - 4, 7, 6, INK)
    c.ring(x - 4, y - 4, 5 + snap, 4, GOLD)
    c.disk(x - 5, y - 4, 2, 3, WHITE)


def nautilus(c, x, y, t, snap):
    for i in range(5):
        tip = y + 4 + i * 2 + math.sin(t * 3 + i) * 2
        c.path([(x - 6, y + 1), (x - 14, y + i), (x - 20 - snap, tip)], 0xefad73 if i % 2 else PALE)
    c.disk(x + 2, y - 2, 13, 12, 0x284356)
    c.disk(x + 2, y - 3, 12, 11, 0xa9d8d8)
    c.ring(x + 2, y - 3, 12, 11, 0xdef4da)
    spiral = []
    for step in range(89):
        a = step / 7.7 + t * .15
        r = 1 + step * .118
        spiral.append((x + 2 + math.cos(a) * r, y - 3 + math.sin(a) * r * .90))
        if step > 52 and step % 5 == 0:
            c.line(*spiral[-1], x + 2 + math.cos(a + .28) * 12, y - 3 + math.sin(a + .28) * 11, 0x507d83)
    c.path(spiral, 0x315a66, 2)
    c.disk(x - 9, y + 2, 3, 2, INK)
    c.dot(x - 10, y + 1, GOLD)


def siren(c, x, y, t, snap):
    for side in (-1, 1):
        outer = x + side * (20 + snap)
        c.poly([(x, y - 5), (outer, y - 13), (outer - side * 4, y + 3),
                (x + side * 6, y + 10)], 0x584362)
        c.path([(x, y - 3), (outer, y - 13), (outer - side * 4, y + 2),
                (x + side * 5, y + 11)], 0xd68aca, 2)
        for i in range(3, 17, 3):
            u = x + side * i
            c.line(u, y - 4 - i * .42, u + math.sin(t * 5 + i) * 2, y + 9 - i * .32, 0xf2c3dd)
    for i in range(3):
        c.path([(x + i, y + 5), (x - 3 + i, y + 12),
                (x + i + math.sin(t * 2 + i) * 4, y + 17)], 0xb782b4)
    c.disk(x, y - 2, 5, 7, 0x43394d)
    c.poly([(x - 4, y - 4), (x, y - 11), (x + 4, y - 4), (x, y + 3)], 0xe4b1d3)
    c.line(x - 2, y - 3, x + 2, y - 3, INK)
    c.dot(x - 1, y - 3, WHITE)


def crown(c, x, y, t, snap):
    for i in range(8):
        a = i * TAU / 8 + t * .32
        rx, ry = math.cos(a), math.sin(a)
        base = x + rx * 13, y + ry * 10
        elbow = x + rx * (18 + snap), y + ry * 14
        tip = elbow[0] - ry * 6, elbow[1] + rx * 4
        c.path([base, elbow, tip], 0xb17d52, 2)
        c.line(tip[0], tip[1], tip[0] + rx * 3, tip[1] + ry * 3, PALE)
    c.disk(x, y, 13, 10, 0x26383c)
    c.ring(x, y, 12, 9, BRASS)
    c.ring(x, y, 9, 7, 0x879e87)
    for i in range(6):
        a = i * TAU / 6 - t * .65
        points = [(x + 9 * math.cos(a), y + 7 * math.sin(a)),
                  (x + 8 * math.cos(a + .7), y + 6 * math.sin(a + .7)),
                  (x + 3 * math.cos(a + 1.3), y + 2 * math.sin(a + 1.3))]
        c.poly(points, 0x68988d if i % 2 else 0xb9af7e)
    c.disk(x, y, 3, 2, CYAN)
    c.dot(x, y, WHITE)


CREATURES = (lantern, crab, eel, listener, nautilus, siren, crown)


def burst(c, x, y, age, color, count=19):
    for i in range(count):
        angle = i * 2.39996
        speed = 6 + (i * 7 % 15)
        dx, dy = math.cos(angle) * speed, math.sin(angle) * speed * .7
        tail = max(0, age - .13)
        c.line(x + dx * tail, y + dy * tail + tail * tail * 4,
               x + dx * age, y + dy * age + age * age * 4, WHITE if i % 5 == 0 else color)


def pressure_wave(c, x, y, radius, color):
    c.ring(x, y, radius, radius * .53, color)
    if radius > 5:
        c.ring(x, y, radius - 3, (radius - 3) * .53, mix(color, INK, .52))


def water(c, clock):
    for i in range(28):
        x = (i * 43 + math.sin(clock * .5 + i) * 2) % W
        y = (i * 19 - clock * (1.1 + (i % 3) * .4)) % H
        c.dot(x, y, 0x48676b if i % 4 else 0x80968d)


def ease(a, b, p):
    u = min(1, max(0, (p - a) / (b - a)))
    return u * u * (3 - 2 * u)


def contact_pose(zone, kind, p):
    if kind != "counter":
        return 0, 0, 0
    lunge = ease(.12, .55, p) - ease(.61, 1, p)
    if zone == 1:
        return -37 * lunge, -7 * math.sin(math.pi * lunge), round(3 * lunge)
    if zone == 2:
        return -45 * lunge, -3 * lunge, round(2 * lunge)
    return 4 * math.sin(p * math.pi), 0, round(2 * lunge)


def arena(zone, hero, clock, kind="idle", p=0, opening=False):
    c = Raster(list(backdrop(zone)))
    water(c, clock)
    base_y = 25
    surge = ease(.16, .48, p) - ease(.58, 1, p)
    lunge = 48 * surge if kind == "cutter" else 0
    player_x = 26 + lunge
    player_y = base_y - math.sin(surge * math.pi) * 2 if kind == "cutter" else base_y
    extension = round(8 * surge) if kind == "cutter" else 0
    guard = round(5 * (ease(0, .25, p) - ease(.75, 1, p))) if kind == "anchor" else 0
    dx, dy, snap = contact_pose(zone, kind, p)
    if kind in ("cutter", "decoy", "resonate"):
        dx += (ease(.47, .53, p) - ease(.61, .9, p)) * 4
    enemy_x = 105 + dx
    enemy_y = ANCHOR_Y[zone] + dy
    if zone != 1:
        enemy_y += math.sin(clock * 1.9) * 1.6
    if kind == "counter":
        player_x -= (ease(.54, .60, p) - ease(.68, .96, p)) * 5
    c.disk(player_x, 43, 13, 1, INK)
    c.disk(enemy_x, 43, 16, 1, INK)
    if kind == "cutter" and .20 < p < .54:
        for i in range(3):
            c.line(player_x - 22 + i, player_y - 4 + i * 3,
                   player_x - 8, player_y - 5 + i * 3, 0x65a797)
    rig(c, hero, player_x, player_y, clock, extension, guard, surge if kind == "cutter" else 0)
    if kind != "wreck" or p < .55 and int(p * 18) % 2 == 0:
        CREATURES[zone](c, enemy_x, enemy_y, clock, snap)
        if opening:
            if zone == 4:
                c.disk(enemy_x + 2, enemy_y - 3, 5, 4, INK)
                c.ring(enemy_x + 2, enemy_y - 3, 5, 4, GOLD)
                c.disk(enemy_x + 2, enemy_y - 3, 2, 2, PALE)
            elif zone == 5:
                for r in (5, 9):
                    c.ring(enemy_x, enemy_y - 15, r, r * .36, ACCENTS[5])
            elif zone == 6:
                c.disk(enemy_x, enemy_y, 7, 5, INK)
                c.ring(enemy_x, enemy_y, 7, 5, RED)
                c.disk(enemy_x, enemy_y, 3, 2, PALE)
    if kind == "cutter" and .38 < p < .8:
        c.path([(player_x + 13, 32), (player_x + 26, 27), (enemy_x - 6, 20)],
               WHITE if p < .52 else CYAN, 2 if p < .55 else 1)
    contact_at = .51 if kind == "resonate" else .48
    if kind in ("cutter", "resonate", "decoy") and p >= contact_at:
        burst(c, enemy_x - 6, enemy_y, (p - contact_at) * 2, GOLD)
    if kind == "anchor":
        c.line(player_x + 2, 31, player_x + 10, 42, BRASS, 2)
        if .18 < p < .88:
            pressure_wave(c, player_x + 5, 26, 18, CYAN)
            cx = 93 - 49 * ease(.12, .53, p)
            c.line(cx, 25, cx + 9, 24, GOLD, 2)
            if p >= .49:
                burst(c, 47, 25, (p - .49) * 2, CYAN)
    if kind == "decoy":
        target = 54 + 43 * ease(.40, .54, p)
        c.ring(54, 23, 6, 8, mix(CYAN, INK, .35))
        if .12 < p < .55:
            cx = 95 - 41 * ease(.12, .4, p) if p < .4 else target
            c.disk(cx, 22, 4, 1, PALE)
            c.dot(cx, 22, WHITE)
    if kind == "resonate":
        for i in range(3):
            radius = (p * 105 - i * 13)
            if 0 < radius < 86:
                pressure_wave(c, player_x + 4, 25, radius, CYAN if i % 2 else WHITE)
    if kind == "repair":
        for i in range(6):
            x = player_x - 10 + i * 4
            y = 36 - (p * 22 + i * 3) % 18
            c.line(x - 1, y, x + 1, y, CYAN)
            c.line(x, y - 1, x, y + 1, CYAN)
    if kind == "counter":
        if .13 <= p <= .64:
            travel = ease(.16, .55, p)
            front = 96 - travel * 62
            if zone == 0:
                c.line(front, 24, front + 11, 22, GOLD, 2)
                c.line(front + 2, 24, front + 11, 23, WHITE)
            elif zone == 3:
                for r in (0, 5, 10):
                    pressure_wave(c, front + r, 24, 5 + r, RED)
            elif zone == 4:
                for i in range(3):
                    u, v = front + i * 5, 24 + (i - 1) * 4
                    c.poly([(u - 4, v), (u + 5, v - 2), (u + 2, v + 2)], ACCENTS[4])
            elif zone == 5:
                for i in (-1, 0, 1):
                    c.path([(u, 25 + i * 3 + math.sin((u - front) * .32 + p * 10) * 2)
                            for u in range(round(front), 102, 2)], ACCENTS[5] if i else WHITE)
            elif zone == 6:
                for i in (-1, 1):
                    c.path([(enemy_x - 9, enemy_y + i * 4), (front + 12, 24 + i * 7),
                            (front, 24 + i), (front + 5, 24 + i * 5)], BRASS, 2)
            elif travel > .85:
                c.path([(32, 29), (40, 22), (enemy_x - 10, 24)], PALE, 2)
        if p > .54:
            burst(c, player_x + 4, 25, (p - .54) * 2, RED)
    if kind == "wreck":
        burst(c, enemy_x, enemy_y, p * 1.3, GOLD, 34)
        if .12 < p < .75:
            pressure_wave(c, enemy_x, enemy_y, 2 + p * 24, 0xd2b48b)
    if kind == "listen":
        pressure_wave(c, enemy_x, enemy_y, 3 + (p * 3 % 1) * 25, MINT)
    if kind == "cutter" and .47 < p < .57 or kind == "counter" and .54 < p < .63:
        for y in (0, H - 1):
            c.rect(0, y, W, 1, PALE if kind == "cutter" else RED)
    return c


LETTERS = {
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "A": ("01110", "11011", "10001", "11111", "10001", "10001", "10001"),
    "C": ("01111", "11000", "10000", "10000", "10000", "11000", "01111"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "O": ("01110", "11011", "10001", "10001", "10001", "11011", "01110"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
}


def title(clock):
    c = Raster(list(backdrop(0)))
    c.rect(0, 0, 80, H, 0x0d242f)
    for j, word in enumerate(("BLACK", "BOX")):
        for i, char in enumerate(word):
            for y, row in enumerate(LETTERS[char]):
                for x, bit in enumerate(row):
                    if bit == "1":
                        c.rect(6 + i * 13 + x * 2, 5 + j * 18 + y * 2, 2, 2, WHITE if j == 0 else GOLD)
    for r in (4, 11, 18, 22):
        c.ring(108, 24, r, r, 0x44736f)
    angle = clock * 1.3
    for i in range(4):
        a = angle - i * .10
        c.line(108, 24, 108 + 21 * math.cos(a), 24 + 21 * math.sin(a), mix(CYAN, DEEP[0], i * .21))
    for i in range(3):
        c.disk(96 + i * 6, 24 - i * 3, 1, 1, GOLD)
    for i in range(53):
        wave = math.sin(i * .9 - clock * 3) * (1 + 2 * (i % 17 < 4))
        c.dot(7 + i, 42 + wave, MINT)
    water(c, clock)
    return c


def receiver(canvas, song, entered, clock):
    canvas.rect(49, 3, 39, 12, INK)
    canvas.line(49, 3, 87, 3, MINT)
    canvas.line(49, 15, 87, 15, 0x405e66)
    for i, digit in enumerate(song):
        x = 55 + i * 11
        height = int(digit) * 2
        c = GOLD if i < len(entered) and entered[i] != digit else CYAN
        canvas.rect(x, 13 - height, 4, height, c if i < len(entered) else METAL)
        canvas.dot(x + 2, 12 - height, WHITE)
    scan = 50 + int(clock * 18 % 37)
    canvas.dot(scan, 4, CYAN)


def recorder(clock, lost=False):
    c = Raster(list(backdrop(3)))
    c.rect(37, 6, 68, 37, INK)
    c.rect(39, 7, 64, 33, 0x955f43 if not lost else 0x68464b)
    c.rect(41, 9, 60, 22, 0xddad77 if not lost else 0x8a6360)
    c.rect(43, 11, 56, 3, 0x3e424d)
    for x in (55, 87):
        c.disk(x, 23, 7, 6, INK)
        c.ring(x, 23, 5, 4, GOLD)
        for i in range(3):
            a = clock * (0 if lost else 2) + i * TAU / 3
            c.line(x, 23, x + 4 * math.cos(a), 23 + 3 * math.sin(a), WHITE)
    c.rect(63, 20, 16, 6, INK)
    for i in range(13):
        c.dot(65 + i, 23 + math.sin(i + clock * 3) * (1.5 if not lost else 0), CYAN)
    c.poly([(48, 39), (52, 33), (89, 33), (94, 39)], METAL)
    for x in (53, 89):
        c.disk(x, 37, 1, 1, INK)
    water(c, clock)
    return c
