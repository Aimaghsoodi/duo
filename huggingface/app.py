# The DuoX Space entry point lives at the repo root (../app.py).
# HF Spaces uses this file only if present; copy the contents from ../app.py
# when uploading, or keep app.py at the root of the Space repo.
from __future__ import annotations
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from app import build_demo  # noqa: E402

if __name__ == "__main__":
    build_demo().launch()
