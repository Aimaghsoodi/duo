"""Push DuoX Space files to Hugging Face.

Usage:
    set HF_TOKEN=hf_...your_fresh_token...   # Windows
    export HF_TOKEN=hf_...your_fresh_token... # Linux/mac
    py -3 scripts/push_to_hf.py

Uploads app.py + huggingface/README.md + huggingface/requirements.txt to the
Space at AbteeX-AI-Labs/duox. Creates the Space if it doesn't exist.

DO NOT hard-code the token. DO NOT commit the token. If a token leaks:
    https://huggingface.co/settings/tokens → revoke.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile


def main() -> int:
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("error: set HF_TOKEN env var with a FRESH token "
              "(https://huggingface.co/settings/tokens). Do NOT reuse a "
              "token that has been pasted anywhere.", file=sys.stderr)
        return 2

    from huggingface_hub import HfApi, create_repo

    repo_id = "AbteeX-AI-Labs/duox"
    print(f"→ ensuring Space {repo_id} exists…")
    create_repo(repo_id, repo_type="space", space_sdk="gradio",
                token=token, exist_ok=True)

    root = pathlib.Path(__file__).resolve().parent.parent
    staging = pathlib.Path(tempfile.mkdtemp(prefix="duox-space-"))
    try:
        shutil.copy(root / "app.py",                     staging / "app.py")
        shutil.copy(root / "huggingface" / "README.md",  staging / "README.md")
        shutil.copy(root / "huggingface" / "requirements.txt", staging / "requirements.txt")

        api = HfApi(token=token)
        print(f"→ uploading to {repo_id}…")
        api.upload_folder(
            folder_path=str(staging),
            repo_id=repo_id,
            repo_type="space",
            commit_message="deploy DuoX 0.2.0",
        )
        print(f"✓ https://huggingface.co/spaces/{repo_id}")
        return 0
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
