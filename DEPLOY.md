# DuoX — Deployment Runbook

Ship **DuoX 0.2.0** to GitHub, PyPI (under the AbteeX AI Labs org), and the
Hugging Face Space (`AbteeXAILabs/duox`).

> ⚠️ **If you ever pasted a real token into chat, a Slack, a PR, or a screenshot,
> rotate it right now**: https://huggingface.co/settings/tokens.
> Never commit tokens or `.env` files. `.gitignore` already blocks the obvious ones.

---

## 0 · Prerequisites (one-time)

- GitHub account: `aimaghsoodi`
- PyPI org: **AbteeX AI Labs** (create at https://pypi.org/manage/organizations/)
- Hugging Face org: **AbteeXAILabs** (create at https://huggingface.co/organizations/new)

Local tools:
```bash
pip install --upgrade build twine huggingface_hub
```

---

## 1 · GitHub (source of truth)

```bash
cd S:/duo
git init                                   # if not already
git add -A
git commit -m "release: DuoX 0.2.0"
git branch -M main
git remote add origin https://github.com/aimaghsoodi/duo.git
git push -u origin main
```

Tag the release (triggers the `publish` workflow):
```bash
git tag v0.2.0
git push origin v0.2.0
```

CI does the rest: build sdist+wheel, publish to PyPI, cut a GitHub Release,
push to the HF Space.

---

## 2 · PyPI (under AbteeX AI Labs org)

**Set up PyPI trusted publishing** (one-time, no tokens required):

1. Go to https://pypi.org/manage/account/publishing/
2. Add a new pending publisher:
   - **PyPI Project Name:** `duox`
   - **Owner:** `aimaghsoodi` (your GitHub username)
   - **Repository name:** `duo`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
3. After first release, transfer the project to the **AbteeX AI Labs** org
   under https://pypi.org/manage/project/duox/collaboration/.

Manual one-shot (if you don't want to wait for CI):
```bash
cd S:/duo
python -m build
python -m twine check dist/*
python -m twine upload dist/*                # prompts for API token
```

---

## 3 · Hugging Face Space (Gradio demo)

**Files that ship to the Space** (copied by the `huggingface-space` CI job):
- `app.py`                    (root — the Gradio app)
- `huggingface/README.md`     (becomes the Space's `README.md` with SDK frontmatter)
- `huggingface/requirements.txt`

**Set the HF_TOKEN secret** (GitHub Actions side):
```
Repo → Settings → Secrets and variables → Actions → New repository secret
  Name:  HF_TOKEN
  Value: <your fresh token from https://huggingface.co/settings/tokens>
```

**Set the HF_TOKEN Space secret** (Hugging Face side, for model inference):
```
Space → Settings → Variables and secrets → New secret
  Name:  HF_TOKEN
  Value: <same token, or a scoped one>
```

Manual one-shot push (no CI):
```bash
# NEVER hard-code tokens — load from a local file gitignored as .hf_token
export HF_TOKEN=$(cat ~/.hf_token)
python -c "
from huggingface_hub import HfApi, create_repo
repo = 'AbteeXAILabs/duox'
create_repo(repo, repo_type='space', space_sdk='gradio', exist_ok=True)
api = HfApi()
import shutil, tempfile, pathlib
with tempfile.TemporaryDirectory() as t:
    r = pathlib.Path(t)
    shutil.copy('app.py', r / 'app.py')
    shutil.copy('huggingface/README.md', r / 'README.md')
    shutil.copy('huggingface/requirements.txt', r / 'requirements.txt')
    api.upload_folder(folder_path=str(r), repo_id=repo, repo_type='space',
                      commit_message='deploy DuoX 0.2.0')
"
```

---

## 4 · Verify

```bash
pip install duox                           # from PyPI
duox --version                             # DuoX 0.2.0
duox doctor                                # all peers / readline / MCP
duox -p "say hi" --output-format json      # headless smoke test
```

Visit the Space: https://huggingface.co/spaces/AbteeXAILabs/duox — run an
example prompt, confirm the orchestration trace streams.

---

## 5 · Rollback

```bash
# PyPI (yank, don't delete)
python -m twine yank duox==0.2.0 --reason "broken release"

# GitHub
gh release delete v0.2.0 -y
git push origin :refs/tags/v0.2.0

# HF Space — revert commit in the Space's git:
huggingface-cli upload AbteeXAILabs/duox . --repo-type space --commit-message "rollback"
```
