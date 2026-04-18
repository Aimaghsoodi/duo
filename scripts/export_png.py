"""Render SVG brand assets to PNG locally.

Usage:
    pip install cairosvg
    python scripts/export_png.py
"""

from __future__ import annotations

from pathlib import Path

try:
    import cairosvg  # type: ignore
except ImportError:
    raise SystemExit("cairosvg not installed — run: pip install cairosvg")

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

EXPORTS = [
    ("logo.svg",          "logo.png",            256,  256),
    ("logo.svg",          "favicon-32.png",       32,   32),
    ("logo-linkedin.svg", "logo-linkedin.png",   512,  512),
    ("logo-linkedin.svg", "og.png",             1200, 1200),
    ("logo-wordmark.svg", "logo-wordmark.png",  1280,  400),
]

def main() -> None:
    for src, dst, w, h in EXPORTS:
        src_path = ASSETS / src
        dst_path = ASSETS / dst
        if not src_path.exists():
            print(f"skip (missing): {src_path}")
            continue
        cairosvg.svg2png(url=str(src_path), write_to=str(dst_path),
                         output_width=w, output_height=h)
        print(f"wrote {dst_path}  ({w}×{h})")

if __name__ == "__main__":
    main()
