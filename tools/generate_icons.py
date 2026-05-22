#!/usr/bin/env python3
"""Generate WhisperClip application icon (ICO + PNG previews)."""
from __future__ import annotations
import io, struct
from pathlib import Path
try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("pip install pillow")

SIZES = [16, 24, 32, 48, 64, 128, 256]
SCALE = 4

BG_TOP     = (20,  30,  58, 255)
BG_BOT     = ( 9,  16,  36, 255)
MIC_COL    = (245, 251, 255, 255)
WAVE_1_COL = (100, 178, 255, 185)
WAVE_2_COL = (100, 178, 255, 100)
REC_COL    = (255,  68,  68, 230)
BORDER_COL = (255, 255, 255,  20)

def _lerp(a, b, t): return int(a + (b - a) * t)

def make_icon(size):
    ws = size * SCALE
    bg = Image.new("RGBA", (ws, ws), (0, 0, 0, 0))
    bg_d = ImageDraw.Draw(bg)
    for y in range(ws):
        t = y / max(1, ws - 1)
        bg_d.line([(0, y), (ws, y)], fill=(
            _lerp(BG_TOP[0], BG_BOT[0], t),
            _lerp(BG_TOP[1], BG_BOT[1], t),
            _lerp(BG_TOP[2], BG_BOT[2], t), 255))
    cr = max(2, int(ws * 0.22))
    mask = Image.new("L", (ws, ws), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, ws-1, ws-1], radius=cr, fill=255)
    img = Image.new("RGBA", (ws, ws), (0, 0, 0, 0))
    img.paste(bg, mask=mask)
    d = ImageDraw.Draw(img)
    if size >= 20:
        d.rounded_rectangle([0, 0, ws-1, ws-1], radius=cr, outline=BORDER_COL, width=SCALE)
    cx = ws / 2.0
    mw = ws * 0.24; mh = ws * 0.34; mr = mw / 2.0
    mcy = ws * 0.40; mt = mcy - mh/2; mb = mcy + mh/2
    d.rounded_rectangle([cx-mr, mt, cx+mr, mb], radius=int(mr), fill=MIC_COL)
    lw = max(SCALE, int(ws/17))
    ahw = ws * 0.195; ah = ws * 0.165
    at_ = mb - ws*0.04; ab = at_ + ah
    d.arc([cx-ahw, at_, cx+ahw, ab], start=0, end=180, fill=MIC_COL, width=lw)
    pt = ab - ws*0.01; pb = pt + ws*0.10
    d.line([(cx, pt), (cx, pb)], fill=MIC_COL, width=lw)
    bhw = ws * 0.14
    d.line([(cx-bhw, pb), (cx+bhw, pb)], fill=MIC_COL, width=lw)
    if size >= 32:
        wlw = max(SCALE, int(ws/24))
        for r_frac, col in [(0.29, WAVE_1_COL), (0.41, WAVE_2_COL)]:
            wr = ws * r_frac; wh = wr * 0.68
            d.arc([cx-wr, mcy-wh, cx, mcy+wh], start=143, end=217, fill=col, width=wlw)
            d.arc([cx, mcy-wh, cx+wr, mcy+wh], start=-37, end=37, fill=col, width=wlw)
    if size >= 48:
        dr = ws*0.075; dcx = ws*0.775; dcy = ws*0.185
        if size >= 64:
            dgr = dr*1.55
            d.ellipse([dcx-dgr, dcy-dgr, dcx+dgr, dcy+dgr], outline=(255,68,68,70), width=SCALE)
        d.ellipse([dcx-dr, dcy-dr, dcx+dr, dcy+dr], fill=REC_COL)
    return img.resize((size, size), Image.LANCZOS)


def save_ico(images_dict, path):
    """Write a proper multi-resolution ICO using embedded PNG frames."""
    sizes = sorted(images_dict.keys())
    frames_png = []
    for s in sizes:
        buf = io.BytesIO()
        images_dict[s].save(buf, format="PNG")
        frames_png.append(buf.getvalue())

    # ICO ICONDIR header: Reserved=0, Type=1 (icon), Count=N
    ico = struct.pack("<HHH", 0, 1, len(sizes))

    # Directory entries (each 16 bytes)
    data_offset = 6 + 16 * len(sizes)
    for s, png_data in zip(sizes, frames_png):
        w = h = s if s < 256 else 0   # 0 encodes 256 in ICO format
        ico += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png_data), data_offset)
        data_offset += len(png_data)

    # Image data
    for png_data in frames_png:
        ico += png_data

    path.write_bytes(ico)


def main():
    out_dir = Path(__file__).resolve().parent.parent / "assets" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)
    print("Generating icons …")
    images = {s: make_icon(s) for s in SIZES}

    ico_path = out_dir / "whisperclip.ico"
    save_ico(images, ico_path)
    print(f"  ICO  {ico_path}  ({ico_path.stat().st_size:,} bytes, {len(SIZES)} sizes)")

    for s in (32, 64, 256):
        p = out_dir / f"whisperclip_{s}.png"
        images[s].save(str(p))
        print(f"  PNG  {p}")

if __name__ == "__main__":
    main()
