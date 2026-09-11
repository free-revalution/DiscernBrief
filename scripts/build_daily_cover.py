#!/usr/bin/env python3
"""端到端封面图工作流。"""
import argparse
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

PROJ = Path(__file__).resolve().parent.parent
DAILY_DIR = PROJ / "cache" / "daily-content"


def detect_date(args):
    if args.date:
        return args.date
    tz = ZoneInfo("Asia/Shanghai") if ZoneInfo else None
    now = datetime.now(tz) if tz else datetime.now()
    return (now - timedelta(days=1)).strftime("%Y-%m-%d")


def extract_prompt(zsxq1_path):
    md = zsxq1_path.read_text(encoding="utf-8")
    m = re.search(r'EN prompt template:\s*"([^"]+)"', md, re.DOTALL)
    if not m:
        raise ValueError(f"EN prompt template not found in {zsxq1_path}")
    return m.group(1).replace('\\"', '"').replace('40%%', '40%')


def derive_title_subtitle(zsxq1_path, md=None):
    if md is None:
        md = zsxq1_path.read_text(encoding="utf-8")
    tldr = re.search(r'## TL;DR\s*\n+(.+?)(?:\n\n|\Z)', md, re.DOTALL)
    title = tldr.group(1).strip()[:60] if tldr else zsxq1_path.parent.name
    subtitle = zsxq1_path.parent.name.replace("-", " ").title()
    return title, subtitle


def update_frontmatter(zsxq1_path, cover_rel):
    md = zsxq1_path.read_text(encoding="utf-8")
    if "cover_image:" in md:
        return False
    new_md = md.replace("language: zh\n", f"language: zh\ncover_image: {cover_rel}\n", 1)
    if new_md != md:
        zsxq1_path.write_text(new_md, encoding="utf-8")
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="日期 YYYY-MM-DD")
    ap.add_argument("--yesterday", action="store_true")
    ap.add_argument("--slug", help="只跑某个 topic")
    ap.add_argument("--skip-image", action="store_true", help="只跑 overlay")
    ap.add_argument("--no-overlay", action="store_true", help="只跑 image_generate")
    args = ap.parse_args()

    date_str = detect_date(args)
    daily_date_dir = DAILY_DIR / date_str
    if not daily_date_dir.exists():
        print(f"ERROR: {daily_date_dir} 不存在 - 先跑 daily-content", file=sys.stderr)
        sys.exit(1)

    topics = sorted([d for d in daily_date_dir.iterdir() if d.is_dir()])
    if args.slug:
        topics = [t for t in topics if t.name == args.slug or t.name.endswith(args.slug)]
        if not topics:
            print(f"ERROR: slug={args.slug!r} 没找到", file=sys.stderr)
            sys.exit(1)

    print(f"=== build_daily_cover ({date_str}, {len(topics)} topic) ===")

    for topic_dir in topics:
        zsxq1 = topic_dir / "zsxq-1.md"
        if not zsxq1.exists():
            print(f"  ! {topic_dir.name}/zsxq-1.md 不存在")
            continue
        md = zsxq1.read_text(encoding="utf-8")
        prompt = extract_prompt(zsxq1)
        title, subtitle = derive_title_subtitle(zsxq1, md)

        (topic_dir / "cover-prompt.txt").write_text(prompt, encoding="utf-8")
        print(f"  > {topic_dir.name}")
        print(f"    prompt: {topic_dir}/cover-prompt.txt ({len(prompt)} chars)")

        cover_png = topic_dir / "cover.png"
        if not args.skip_image and not cover_png.exists():
            print(f"    image_generate: 请用 cover-prompt.txt 的 prompt 调 image_generate")
            print(f"                   保存为 {cover_png}")
            print(f"                   然后再跑此脚本（不需要 --skip-image）")

        overlay_png = topic_dir / "cover-final.png"
        if cover_png.exists() and not args.no_overlay:
            overlay_script = PROJ / "scripts" / "overlay_text.py"
            if overlay_script.exists():
                cmd = ["python3", str(overlay_script), str(cover_png), str(overlay_png),
                       title, subtitle, f"DiscernBrief · {date_str}"]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if r.returncode == 0:
                    print(f"    overlay: OK {overlay_png.name}")
                else:
                    print(f"    overlay: ! {r.stderr[:200]}")

        cover_rel = "cover-final.png" if overlay_png.exists() else "cover.png"
        if update_frontmatter(zsxq1, cover_rel):
            print(f"    frontmatter: 加了 cover_image: {cover_rel}")
        print()

    print("OK 跑完。Cover image 全部就绪。")


if __name__ == "__main__":
    main()
