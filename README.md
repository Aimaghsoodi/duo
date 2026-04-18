<p align="center">
  <img src="https://raw.githubusercontent.com/aimaghsoodi/duo/main/assets/logo-wordmark.svg" alt="DuoX — by AbteeX AI Labs" width="420">
</p>

<p align="center">
  <strong>Claude Code · Codex · Ollama · OpenClaw — one terminal, one transcript.</strong><br>
  A multi-peer AI CLI orchestrator with shared memory, cross-checking, parallel
  swarms, MCP passthrough, and automatic credit fallback.
</p>
 
<p align="center">
  <em>an <a href="https://www.abteex.com">AbteeX AI Labs</a> release</em> ·
  <a href="https://aimaghsoodi.github.io/duo/">site</a> ·
  <a href="https://github.com/aimaghsoodi/duo">github</a> ·
  <a href="https://huggingface.co/spaces/AbteeXAILabs/duox">huggingface space</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/duox/"><img alt="PyPI" src="https://img.shields.io/pypi/v/duox.svg?color=ec5fa5"></a>
  <a href="https://pypi.org/project/duox/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/duox.svg"></a>
  <a href="https://github.com/aimaghsoodi/duo/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/aimaghsoodi/duo/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/aimaghsoodi/duo/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
</p>

---

**DuoX** is a drop-in CLI alternative to Claude Code / Codex CLI that runs them
*together* — plus Ollama (local) and OpenClaw (inter-agent channels) — under
one supervisor loop. One prompt, many peers, a shared transcript, a single
scrolling interface.

## Why DuoX?

| | Claude Code | Codex CLI | **DuoX** |
|---|---|---|---|
| Single-agent chat | ✓ | ✓ | ✓ |
| Multiple agents in one transcript | ✗ | ✗ | ✓ |
| Cross-validation (planner ↔ executor) | ✗ | ✗ | ✓ |
| Parallel sub-agent fan-out | ✗ | ✗ | ✓ |
| Automatic credit/rate-limit fallback | ✗ | ✗ | ✓ |
| Local Ollama fallback | ✗ | ✗ | ✓ |
| MCP pass-through | ✓ | ✗ | ✓ |
| `CLAUDE.md` / `AGENTS.md` auto-context | ✓ | ✓ | ✓ |
| `@file` mentions, `/compact`, `/remember` | ✓ | partial | ✓ |
| Headless `-p` + JSON output | ✓ | ✓ | ✓ |
| HTTP API daemon | ✗ | ✗ | ✓ |

## Install

```bash
pip install duox
```

From source:

```bash
git clone https://github.com/aimaghsoodi/duo && cd duo
pip install -e .
```

Requires Python 3.10+. After install:

```bash
duox init      # write ~/.duo/config.toml + sample skill
duox doctor    # verify peers, MCP, readline, openclaw
```

`duox doctor` tells you exactly what's missing and how to fix it.

## Quick start

**Interactive** (default — Claude-Code-like loop):
```bash
duox
# then type your goal, or any of:
#   /help  /tips  /examples  /peers  /cost  /compact  /remember  /doctor
#   @src/main.py                  (inline file excerpt)
#   @src/main.py:40-80            (line range)
#   /cd ../other-repo             (switch working dir mid-session)
```

**Headless** (for scripts / CI / git hooks):
```bash
duox -p "summarise the last 10 commits"
duox -p "run the test suite and fix any failures" --output-format json
echo "review my changes" | duox -p
```

**With specific peers / supervisor:**
```bash
duox --peers claude,codex,ollama --supervisor claude "refactor the auth module"
duox --parallel "run these three benchmarks"
duox --resume abc123   # resume a previous session
```

## Try it live

A Gradio demo of the orchestration loop is hosted on Hugging Face:

👉 https://huggingface.co/spaces/AbteeXAILabs/duox

## Features

- **Shared transcript** — every peer sees every message.
- **Supervisor / executor loop** — one peer plans & validates, others execute.
- **Parallel swarm mode** — fan the same task across peers, supervisor merges.
- **Credit fallback** — rate-limit/429/"out of credits" auto-fails over.
- **Context files** — `CLAUDE.md`, `AGENTS.md`, `DUO.md` auto-loaded (walks up from cwd).
- **`@file` mentions** — inline file/dir/line-range excerpts in any prompt.
- **Skills** — markdown prompts in `~/.duo/skills/` auto-injected by keyword match.
- **Sessions** — JSONL event log + transcript under `~/.duo/sessions/`; `duox --resume`.
- **Hooks** — run commands on `pre_step`/`post_step` (tests, linters, formatters).
- **MCP pass-through** — `[mcp.servers.*]` in your config is forwarded to Claude.
- **HTTP API** — `duox serve --port 8787` exposes goals/sessions over JSON.
- **Per-project config** — drop a `.duo.toml` in any repo to override globals.
- **Line editor** — history, `↑`/`↓`, tab-complete on slash commands + peer names.
- **30+ slash commands** — `/help` lists them all.

## Configuration

`~/.duo/config.toml`:

```toml
peers        = ["claude", "codex", "ollama"]
supervisor   = "claude"
ollama_model = "llama3.1"
max_steps    = 30
parallel_default = false

[hooks]
pre_step  = []
post_step = ["pytest -q"]

[mcp.servers.context7]
command = "npx"
args    = ["-y", "@upstash/context7-mcp"]

[openclaw]
thinking = "high"
```

Project-level `.duo.toml` in your repo root is deep-merged on top.

## Headless / scripting

```bash
# Plain text (stdout = final answer)
duox -p "give me a release-notes draft"

# JSON envelope with per-peer stats
duox -p "audit this PR" --output-format json | jq '.final'
```

JSON output shape:
```json
{
  "ok": true,
  "final": "…final answer…",
  "session_id": "20260418-abc",
  "turns": 14,
  "peers": {"claude": {"calls": 4, "seconds": 12.3, "tokens_in": 4280, "tokens_out": 910}}
}
```

## Architecture

```
user prompt
    ↓
 supervisor ──► JSON decision {action, to, instructions}
    │
    ├── delegate ─► executor peer(s) ─► output
    │                     │
    │                     └── (parallel) ─► merge
    ├── execute_self
    ├── validate
    └── done  ─► final answer
```

Under the hood: `claude -p --dangerously-skip-permissions`,
`codex exec --dangerously-bypass-approvals-and-sandbox`, `ollama run`, and
`openclaw agent`, streamed through a small Python orchestrator.

> **Note:** the internal Python package is still named `duo` for backwards
> compatibility — `from duo import …` continues to work. The user-facing CLI
> is `duox`, with `duo` kept as a legacy alias.

## Safety

DuoX runs peer CLIs with permissive flags so they can actually do work. Run it
in a directory you trust — ideally a scratch repo, container, or VM. The
transcript shows every action; read it.

## Develop

```bash
pip install -e '.[test]'
pytest -q          # 47 tests, 3 OS × 3 Python versions in CI
```

## Links

- PyPI: https://pypi.org/project/duox/
- GitHub: https://github.com/aimaghsoodi/duo
- HF Space (demo): https://huggingface.co/spaces/AbteeXAILabs/duox
- HF model card: https://huggingface.co/AbteeXAILabs/duox
- Issues: https://github.com/aimaghsoodi/duo/issues

## License

MIT © 2026 [AbteeX AI Labs](https://www.abteex.com).
