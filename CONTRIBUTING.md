# Contributing to DuoX

Thanks for your interest in **DuoX** — the multi-peer AI CLI orchestrator
(Claude Code × Codex × Ollama × OpenClaw) by AbteeX AI Labs.

## Dev setup

```bash
git clone https://github.com/aimaghsoodi/duo
cd duo
python -m venv .venv
# linux/mac: source .venv/bin/activate
# windows:   .venv\Scripts\Activate.ps1
pip install -e '.[test]'
duox --help
duox doctor
pytest -q
```

## Commit hygiene

- Keep commits focused. Separate refactor / feature / docs commits.
- Add tests for new behaviour. The suite must stay green on Linux / macOS /
  Windows × Python 3.10–3.12.
- Update `CHANGELOG.md` under an `[Unreleased]` section for any user-visible change.

## Filing issues

- Include `duox --version`, OS, and `duox doctor` output.
- If reproduction involves a peer CLI, note which one and its version.

## Releases

- Tag `vX.Y.Z` on `main`. CI builds sdist + wheel, uploads to PyPI under the
  `AbteeX AI Labs` org via trusted publishing, and cuts a GitHub release.
- For the HF Space, push `app.py` + `huggingface/README.md` +
  `huggingface/requirements.txt` to https://huggingface.co/spaces/AbteeXAILabs/duox.
  Set `HF_TOKEN` as a Space secret (Settings → Variables and secrets).

## Security

- **Never commit tokens, API keys, or `.env` files.** `.gitignore` covers the
  common ones; double-check with `git status` before committing.
- Rotate any token accidentally shared in issues / PRs / chats immediately.

## License

By contributing, you agree that your contributions are licensed under the MIT
License (see `LICENSE`).
