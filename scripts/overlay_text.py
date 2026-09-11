#!/usr/bin/env python3
"""PIL 后叠 SVG 文字到 NO TEXT 底图上。"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def pick_font(size, bold=False):
    candidates = [
        "/System/Library/Fonts/SFNSDisplay.ttf" if not bold else "/System/Library/Fonts/SFNSText.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()


def main():
    if len(sys.argv) != 6:
        print(__doc__)
        sys.exit(1)
    bg_path, out_path, title, subtitle, caption = sys.argv[1:6]
    img = Image.open(bg_path).convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    WHITE = (255, 255, 255, 255)
    GREY = (180, 185, 200, 230)
    PINK = (236, 72, 153, 255)
    title_font = pick_font(int(h * 0.07), bold=True)
    draw.text((int(w * 0.05), int(h * 0.05)), title, fill=WHITE, font=title_font)
    sub_font = pick_font(int(h * 0.028), bold=False)
    draw.text((int(w * 0.05), int(h * 0.16)), subtitle, fill=GREY, font=sub_font)
    cap_font = pick_font(int(h * 0.022), bold=False)
    draw.text((int(w * 0.05), int(h * 0.92)), caption, fill=PINK, font=cap_font)
    composite = Image.alpha_composite(img, overlay)
    composite.convert("RGB").save(out_path, quality=95)
    print(f"OK overlay -> {out_path}")


if __name__ == "__main__":
    main()
