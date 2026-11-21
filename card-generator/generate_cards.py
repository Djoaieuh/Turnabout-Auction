"""
Turnabout Auction card generator.

Draws one PNG per artefact, in the "5a" style (era cap, set band with emblem,
value coin, keyword ribbons, card text), in English and French.

Usage (from this folder):
    python generate_cards.py --input artefacts.json
    python generate_cards.py --input "C:/path/to/vault/Cards"

The input is either a JSON file (a list of artefacts, see artefacts.json) or a
folder of Obsidian card notes (every .md file under it, read from its
properties). Only Pillow is needed:  pip install pillow
"""
import argparse
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Layout, in design units. One unit = one pixel of a 260 x 320 card
# (twice the 130 x 160 playingcards.io size). --scale multiplies everything.
# ---------------------------------------------------------------------------
CARD_W, CARD_H, RADIUS = 260, 320, 14
PAD = 14                     # left/right padding of the text area
CAP_H = 22                   # era cap
BAND_H = 66                  # set band
COIN_D, COIN_RING = 52, 4    # value coin
COIN_RIGHT, COIN_TOP = 12, 64
NAME_TOP_GAP, NAME_RIGHT_PAD, NAME_SIZE, NAME_LH = 12, 72, 15, 1.15
BODY_GAP = 10                # between name and ribbons/text
RIBBON_SIZE, RIBBON_PAD_L, RIBBON_PAD_R, RIBBON_PAD_V, RIBBON_NOTCH, RIBBON_GAP = 9.5, 9, 16, 2, 7, 4
TEXT_SIZE, TEXT_LH, TEXT_MIN = 11, 1.4, 8.5
BOTTOM_PAD = 12
INK, TEXT_INK, WHITE = "#1B1B1B", "#2A2A2A", "#FFFFFF"
SUPERSAMPLE = 3              # draw bigger, then shrink: smooth edges

FONT_FILES = {"regular": "Inter-Regular.otf", "semibold": "Inter-SemiBold.otf",
              "bold": "Inter-Bold.otf", "extrabold": "Inter-ExtraBold.otf"}
_font_cache = {}


def font(weight, size_px):
    key = (weight, round(size_px * 4))
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(HERE / "fonts" / FONT_FILES[weight]), max(1, round(size_px)))
    return _font_cache[key]


def rgba(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), round(255 * alpha))


# ---------------------------------------------------------------------------
# Minimal SVG path support (M L H V C S Q T A Z, absolute and relative),
# flattened to polylines. Used for emblems and era patterns.
# ---------------------------------------------------------------------------
_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?")


def _arc_points(x1, y1, rx, ry, phi, fa, fs, x2, y2, steps=24):
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    phi = math.radians(phi)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    rx, ry = abs(rx), abs(ry)
    lam = (x1p ** 2) / (rx ** 2) + (y1p ** 2) / (ry ** 2)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    coef = math.sqrt(max(0, num / den)) if den else 0
    if fa == fs:
        coef = -coef
    cxp, cyp = coef * rx * y1p / ry, -coef * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = max(steps, int(abs(dt) / (math.pi / 32)))
    pts = []
    for i in range(1, n + 1):
        t = t1 + dt * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cp * x - sp * y + cx, sp * x + cp * y + cy))
    return pts


def path_to_polylines(d):
    """Return a list of (points, closed) in path units."""
    toks = _TOKEN.findall(d)
    i, cmd = 0, None
    x = y = sx = sy = 0.0
    last_ctrl = None
    polys, cur = [], []

    def num():
        nonlocal i
        v = float(toks[i]); i += 1
        return v

    while i < len(toks):
        if re.match(r"[A-Za-z]", toks[i]):
            cmd = toks[i]; i += 1
            if cmd in "Zz":
                if cur:
                    polys.append((cur, True)); cur = []
                x, y = sx, sy
                last_ctrl = None
                continue
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = (x, y) if rel else (0, 0)
        if c == "M":
            if cur:
                polys.append((cur, False))
            x, y = ox + num(), oy + num()
            sx, sy = x, y
            cur = [(x, y)]
            cmd = "l" if rel else "L"
            last_ctrl = None
        elif c == "L":
            x, y = ox + num(), oy + num(); cur.append((x, y)); last_ctrl = None
        elif c == "H":
            x = (x if rel else 0) + num(); cur.append((x, y)); last_ctrl = None
        elif c == "V":
            y = (y if rel else 0) + num(); cur.append((x, y)); last_ctrl = None
        elif c in "CS":
            if c == "C":
                x1, y1 = ox + num(), oy + num()
            else:
                x1, y1 = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1]) if last_ctrl else (x, y)
            x2, y2 = ox + num(), oy + num()
            x3, y3 = ox + num(), oy + num()
            for k in range(1, 17):
                t = k / 16
                mt = 1 - t
                cur.append((mt ** 3 * x + 3 * mt * mt * t * x1 + 3 * mt * t * t * x2 + t ** 3 * x3,
                            mt ** 3 * y + 3 * mt * mt * t * y1 + 3 * mt * t * t * y2 + t ** 3 * y3))
            last_ctrl = (x2, y2)
            x, y = x3, y3
        elif c in "QT":
            if c == "Q":
                x1, y1 = ox + num(), oy + num()
            else:
                x1, y1 = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1]) if last_ctrl else (x, y)
            x2, y2 = ox + num(), oy + num()
            for k in range(1, 13):
                t = k / 12
                mt = 1 - t
                cur.append((mt * mt * x + 2 * mt * t * x1 + t * t * x2, mt * mt * y + 2 * mt * t * y1 + t * t * y2))
            last_ctrl = (x1, y1)
            x, y = x2, y2
        elif c == "A":
            rx, ry, phi, fa, fs = num(), num(), num(), num(), num()
            x2, y2 = ox + num(), oy + num()
            cur.extend(_arc_points(x, y, rx, ry, phi, int(fa), int(fs), x2, y2))
            x, y = x2, y2
            last_ctrl = None
        else:
            raise ValueError(f"Unsupported path command {cmd!r} in {d!r}")
    if cur:
        polys.append((cur, False))
    return polys


def draw_path(draw, d, ox, oy, scale, color, width=None, fill=False):
    for pts, closed in path_to_polylines(d):
        p = [(ox + px * scale, oy + py * scale) for px, py in pts]
        if fill:
            if len(p) >= 3:
                draw.polygon(p, fill=color)
            continue
        if closed and p:
            p = p + [p[0]]
        w = max(1, round(width * scale))
        if len(p) >= 2:
            draw.line(p, fill=color, width=w, joint="curve")
        r = w / 2
        for q in (p[0], p[-1]):  # round caps
            draw.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=color)


def draw_icon(img, path, cx, cy, size, color, stroke, s):
    """Emblem on a 24 x 24 grid, centred on (cx, cy), all in design units * s."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    k = size / 24 * s
    draw_path(ImageDraw.Draw(layer), path, cx * s - size * s / 2, cy * s - size * s / 2, k, color, width=stroke)
    img.alpha_composite(layer)


def fill_pattern(img, pattern, box, alpha, s):
    """Tile an era pattern (white strokes) over box = (x, y, w, h) in design units."""
    x, y, w, h = box
    tw, th = pattern["tile"]
    tile = Image.new("RGBA", (max(1, round(tw * s)), max(1, round(th * s))), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    for p in pattern["paths"]:
        draw_path(td, p["d"], 0, 0, s, (255, 255, 255, 255), width=p.get("width", 1), fill=p.get("fill", False))
    region = Image.new("RGBA", (round(w * s), round(h * s)), (0, 0, 0, 0))
    for ty in range(0, region.height, tile.height):
        for tx in range(0, region.width, tile.width):
            region.alpha_composite(tile, (tx, ty))
    a = region.getchannel("A").point(lambda v: round(v * alpha))
    region.putalpha(a)
    img.alpha_composite(region, (round(x * s), round(y * s)))


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
def text_width(txt, f, spacing=0.0):
    if not spacing:
        return f.getlength(txt)
    return sum(f.getlength(ch) for ch in txt) + spacing * max(0, len(txt) - 1)


def draw_spaced(draw, xy, txt, f, fill, spacing=0.0):
    x, y = xy
    if not spacing:
        draw.text((x, y), txt, font=f, fill=fill)
        return
    for ch in txt:
        draw.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + spacing


def wrap(txt, f, max_w):
    lines = []
    for para in txt.split("\n"):
        words, line = para.split(), ""
        for w in words:
            trial = (line + " " + w).strip()
            if f.getlength(trial) <= max_w or not line:
                line = trial
            else:
                lines.append(line)
                line = w
        lines.append(line)
    return lines


def text_box(draw, txt, x, y, max_w, f, size, lh, fill):
    """Draw wrapped text; returns the height used."""
    step = size * lh
    lines = wrap(txt, f, max_w)
    asc, desc = f.getmetrics()
    off = (step - (asc + desc)) / 2
    for i, line in enumerate(lines):
        draw.text((x, y + off + i * step), line, font=f, fill=fill)
    return len(lines) * step


# ---------------------------------------------------------------------------
# One card
# ---------------------------------------------------------------------------
def render_card(card, lang, styles, scale):
    s = scale / 2 * SUPERSAMPLE           # design unit -> pixels while drawing
    W, H = round(CARD_W * s), round(CARD_H * s)
    era = styles["eras"][card["era"]]
    st = styles["sets"][card["set"]]
    col = st["color"]
    fr = lang == "fr"
    name = card["name_fr"] if fr else card["name"]
    text = card["text_fr"] if fr else card["text"]
    kw = (card.get("keyword_fr") if fr else card.get("keyword")) or ""
    era_label = era["label_fr" if fr else "label"].upper()
    set_label = st["label_fr" if fr else "label"].upper()
    value = "?" if card.get("base_value") in (None, "") else str(card["base_value"])

    img = Image.new("RGBA", (W, H), rgba(WHITE))
    d = ImageDraw.Draw(img)

    # era cap
    d.rectangle([0, 0, W, CAP_H * s], fill=rgba(era["color"]))
    fill_pattern(img, styles["patterns"][era["pattern"]], (0, 0, CARD_W, CAP_H), 0.30, s)
    f = font("bold", 8.5 * s)
    asc, desc = f.getmetrics()
    draw_spaced(d, (12 * s, (CAP_H * s - (asc + desc)) / 2), era_label, f, rgba(WHITE), 0.16 * 8.5 * s)

    # set band: emblem + set name, centred
    d.rectangle([0, CAP_H * s, W, (CAP_H + BAND_H) * s], fill=rgba(col))
    fill_pattern(img, styles["patterns"][era["pattern"]], (0, CAP_H, CARD_W, BAND_H), 0.16, s)
    f = font("bold", 8.5 * s)
    asc, desc = f.getmetrics()
    label_h = (asc + desc) / s
    group_h = 26 + 3 + label_h
    top = CAP_H + (BAND_H - group_h) / 2
    draw_icon(img, st["icon"], CARD_W / 2, top + 13, 26, rgba(WHITE), 1.7, s)
    d = ImageDraw.Draw(img)
    sp = 0.14 * 8.5 * s
    lw = text_width(set_label, f, sp)
    draw_spaced(d, ((W - lw) / 2, (top + 29) * s), set_label, f, rgba(WHITE), sp)

    # value coin (soft shadow, white ring, set colour)
    cx = (CARD_W - COIN_RIGHT - COIN_D / 2) * s
    cy = (COIN_TOP + COIN_D / 2) * s
    r = COIN_D / 2 * s
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([cx - r, cy - r + 1 * s, cx + r, cy + r + 1 * s], fill=(0, 0, 0, 60))
    img.alpha_composite(shadow)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgba(WHITE))
    ri = r - COIN_RING * s
    d.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=rgba(col))
    f = font("extrabold", 17 * s)
    bb = d.textbbox((0, 0), value, font=f)
    d.text((cx - (bb[0] + bb[2]) / 2, cy - (bb[1] + bb[3]) / 2), value, font=f, fill=rgba(WHITE))

    # name
    y = CAP_H + BAND_H + NAME_TOP_GAP
    f = font("bold", NAME_SIZE * s)
    y += text_box(d, name, PAD * s, y * s, (CARD_W - PAD - NAME_RIGHT_PAD) * s, f, NAME_SIZE * s, NAME_LH, rgba(INK)) / s
    y = max(y, COIN_TOP + COIN_D - 6) + BODY_GAP

    # keyword ribbons, one per keyword
    if kw:
        f = font("semibold", RIBBON_SIZE * s)
        asc, desc = f.getmetrics()
        rh = (asc + desc) / s + 2 * RIBBON_PAD_V
        for k in [p.strip() for p in kw.split(",") if p.strip()]:
            rw = f.getlength(k) / s + RIBBON_PAD_L + RIBBON_PAD_R
            x0, y0 = PAD, y
            poly = [(x0, y0), (x0 + rw, y0), (x0 + rw - RIBBON_NOTCH, y0 + rh / 2), (x0 + rw, y0 + rh), (x0, y0 + rh)]
            d.polygon([(px * s, py * s) for px, py in poly], fill=rgba(col))
            d.text(((x0 + RIBBON_PAD_L) * s, (y0 + RIBBON_PAD_V) * s), k, font=f, fill=rgba(WHITE))
            y += rh + RIBBON_GAP

    # card text, shrunk if it would not fit
    avail = CARD_H - BOTTOM_PAD - y
    size = TEXT_SIZE
    while True:
        f = font("regular", size * s)
        lines = wrap(text, f, (CARD_W - 2 * PAD) * s)
        if len(lines) * size * TEXT_LH <= avail or size <= TEXT_MIN:
            break
        size -= 0.5
    if len(lines) * size * TEXT_LH > avail:
        print(f"  ! text too long on '{name}' ({lang}): it overflows the card", file=sys.stderr)
    elif size < TEXT_SIZE:
        print(f"  - '{name}' ({lang}): text shrunk to {size}px to fit")
    text_box(d, text, PAD * s, y * s, (CARD_W - 2 * PAD) * s, f, size * s, TEXT_LH, rgba(TEXT_INK))

    # rounded corners, then shrink to the final size
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=RADIUS * s, fill=255)
    img.putalpha(mask)
    final = (round(CARD_W * scale / 2), round(CARD_H * scale / 2))
    return img.resize(final, Image.LANCZOS)


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
FIELDS = ["era", "set", "base_value", "copies", "keyword", "text", "name_fr", "keyword_fr", "text_fr", "order"]


def _parse_value(v):
    v = v.strip()
    if v == "":
        return None
    if v.startswith('"'):
        return json.loads(v)
    if v.startswith("'") and v.endswith("'"):
        return v[1:-1].replace("''", "'")
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def read_note(path):
    txt = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", txt, re.S)
    if not m:
        return None
    props = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z_]+):(.*)$", line)
        if mm:
            props[mm.group(1)] = _parse_value(mm.group(2))
    props["name"] = path.stem
    return props


def load_cards(src):
    src = Path(src)
    if src.is_dir():
        cards = [c for c in (read_note(p) for p in sorted(src.rglob("*.md"))) if c]
    else:
        cards = json.loads(src.read_text(encoding="utf-8"))
    for c in cards:
        for k in ("keyword", "keyword_fr"):
            c[k] = c.get(k) or ""
    cards.sort(key=lambda c: (c.get("order") is None, c.get("order") or 0, c["name"]))
    return cards


def slug(name):
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    n = n.replace("'", "").lower()
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_")


def check(cards, styles, langs):
    problems = []
    for c in cards:
        if c.get("era") not in styles["eras"]:
            problems.append(f"{c['name']}: era {c.get('era')!r} has no style in styles.json")
        if c.get("set") not in styles["sets"]:
            problems.append(f"{c['name']}: set {c.get('set')!r} has no style in styles.json")
        if not c.get("text"):
            problems.append(f"{c['name']}: no English text")
        if "fr" in langs and (not c.get("name_fr") or not c.get("text_fr")):
            problems.append(f"{c['name']}: missing French name or text")
        if "fr" in langs and bool(c.get("keyword")) != bool(c.get("keyword_fr")):
            problems.append(f"{c['name']}: keyword in one language only")
        cp = c.get("copies")
        if not isinstance(cp, int) or isinstance(cp, bool) or cp < 1:
            problems.append(f"{c['name']}: copies must be a whole number of 1 or more (got {cp!r})")
    seen = {}
    for c in cards:
        s = slug(c["name"])
        if s in seen:
            problems.append(f"{c['name']} and {seen[s]} would get the same image name ({s}.png)")
        seen[s] = c["name"]
    return problems


def contact_sheet(paths, out, cols=8):
    ims = [Image.open(p) for p in paths]
    if not ims:
        return
    w, h = ims[0].size
    gap = max(8, w // 20)
    rows = math.ceil(len(ims) / cols)
    sheet = Image.new("RGBA", (cols * w + (cols + 1) * gap, rows * h + (rows + 1) * gap), (233, 230, 223, 255))
    for i, im in enumerate(ims):
        sheet.alpha_composite(im, (gap + (i % cols) * (w + gap), gap + (i // cols) * (h + gap)))
    sheet.convert("RGB").save(out)


CSV_NAMES = {"en": "TurnaboutAuctionArtefactsList_EN.csv", "fr": "TurnaboutAuctionArtefactsList_FR.csv"}


def write_csv(cards, lang, url_folder, out_file):
    """One row per physical copy, a single `image` column with the card's URL."""
    rows = ["image"]
    for c in cards:
        rows += [f"{url_folder}/{slug(c['name'])}.png"] * c["copies"]
    out_file.write_text("\r\n".join(rows) + "\r\n", encoding="utf-8-sig", newline="")
    return len(rows) - 1


def main():
    settings = json.loads((HERE / "settings.json").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser(description="Generate Turnabout Auction card images.")
    ap.add_argument("--wip", action="store_true",
                    help="draw the sandbox (WIP) vault into cards-wip/ instead of the live vault into cards/")
    ap.add_argument("--input", help="override: a JSON file, or a folder of card notes")
    ap.add_argument("--styles", default=str(HERE / "styles.json"))
    ap.add_argument("--out", help="override: output folder (en/ and fr/ go inside)")
    ap.add_argument("--lang", choices=["en", "fr", "both"], default="both")
    ap.add_argument("--scale", type=float, default=4, help="1 = 130 x 160, 4 = 520 x 640 (default)")
    ap.add_argument("--only", help="only cards whose name contains this text")
    ap.add_argument("--no-sheet", action="store_true", help="skip the overview image")
    a = ap.parse_args()

    build = settings["wip" if a.wip else "live"]
    if not a.input:
        a.input = build["cards"]
        if not Path(a.input).is_dir():
            sys.exit(f"Can't find the {'WIP' if a.wip else 'live'} vault's Cards folder:\n  {a.input}\n"
                     "Fix the path in settings.json, or pass --input.")
    if not a.out:
        a.out = str((HERE / build["out"]).resolve())
    print(f"Reading {a.input}")

    # The CSV links to the images on GitHub, so it only makes sense for a full run
    # into a folder of the repo that gets pushed (the live cards/ folder).
    csv_base, csv_skip = None, None
    repo = HERE.parent.resolve()
    out_dir = Path(a.out).resolve()
    if a.only:
        csv_skip = "--only draws some cards, the CSV needs all of them"
    elif a.wip:
        csv_skip = "WIP images aren't pushed to GitHub, so their links wouldn't work"
    elif not out_dir.is_relative_to(repo):
        csv_skip = "the output folder is outside the repo, so the images won't be on GitHub"
    else:
        csv_base = settings["image_base_url"].rstrip("/") + "/" + out_dir.relative_to(repo).as_posix()

    styles = json.loads(Path(a.styles).read_text(encoding="utf-8"))
    cards = load_cards(a.input)
    if a.only:
        cards = [c for c in cards if a.only.lower() in c["name"].lower()]
    langs = ["en", "fr"] if a.lang == "both" else [a.lang]
    problems = check(cards, styles, langs)
    if problems:
        print("Can't generate, fix these first:", *problems, sep="\n  ")
        sys.exit(1)

    for lang in langs:
        out = Path(a.out) / lang
        out.mkdir(parents=True, exist_ok=True)
        made = []
        for c in cards:
            p = out / f"{slug(c['name'])}.png"
            render_card(c, lang, styles, a.scale).save(p)
            made.append(p)
        print(f"{lang}: {len(made)} cards -> {out}")
        if not a.no_sheet:
            contact_sheet(made, Path(a.out) / f"overview_{lang}.jpg")
        if csv_base:
            n = write_csv(cards, lang, f"{csv_base}/{lang}", Path(a.out) / CSV_NAMES[lang])
            print(f"{lang}: {CSV_NAMES[lang]} ({n} rows, one per copy)")
    if not csv_base:
        print(f"No CSV: {csv_skip}")


if __name__ == "__main__":
    main()
