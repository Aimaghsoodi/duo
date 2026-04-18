---
title: DuoX — Multi-Peer AI Orchestrator
emoji: 🎭
colorFrom: pink
colorTo: purple
sdk: gradio
sdk_version: 5.9.1
python_version: "3.11"
app_file: app.py
pinned: true
license: mit
short_description: Claude Code × Codex × Ollama × OpenClaw in one terminal
tags:
- agents
- multi-agent
- orchestrator
- cli
- claude
- codex
- ollama
- mcp
- tool-use
- developer-tools
- duox
---

# DuoX 🎭

[![PyPI](https://img.shields.io/pypi/v/duox.svg?color=ec5fa5)](https://pypi.org/project/duox/)
[![GitHub](https://img.shields.io/badge/github-aimaghsoodi%2Fduo-black?logo=github)](https://github.com/aimaghsoodi/duo)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/aimaghsoodi/duo/blob/main/LICENSE)

**DuoX** is a drop-in CLI alternative to Claude Code and Codex CLI that runs
them *together* — plus Ollama (local) and OpenClaw (inter-agent channels) —
under a single supervisor loop with a shared transcript.

👉 **This Space** is a live demo of the DuoX supervisor/executor loop, powered
by a Hugging Face-hosted model. Install `duox` locally to run the real thing.

## Why DuoX?

- **Multi-peer orchestration** — one supervisor, many executors, one transcript
- **Cross-validation** — supervisor checks every delegated step before the next
- **Parallel sub-agent swarms** — fan out independent work, merge results
- **Automatic credit fallback** — rate-limit/429 trips cleanly to another peer
- **`CLAUDE.md` / `AGENTS.md` / `DUO.md`** auto-loaded as context
- **`@file` mentions, `/compact`, `/remember`** — Claude-Code-grade UX
- **Headless `duox -p "…" --output-format json`** — CI- and script-ready
- **HTTP API daemon** — `duox serve` for remote control
- **MCP pass-through** — forwards `[mcp.servers.*]` to Claude Code

## Install (local CLI)

```bash
pip install duox
duox init
duox doctor      # verify peers, MCP, readline, openclaw
duox             # interactive — type /help
```

Headless / scriptable:

```bash
duox -p "review this PR and list risks" --output-format json
echo "summarise CHANGELOG.md" | duox -p
```

## Architecture

```
user ─► supervisor ─► JSON decision
                         │
                         ├─ delegate  → executor peer(s) → (parallel merge)
                         ├─ execute_self
                         ├─ validate
                         └─ done → final answer
```

## Links

- 🐙 GitHub: https://github.com/aimaghsoodi/duo
- 📦 PyPI: https://pypi.org/project/duox/  (under the AbteeX AI Labs org)
- 🤗 HF org: https://huggingface.co/AbteeXAILabs
- 🐛 Issues: https://github.com/aimaghsoodi/duo/issues

## License

MIT © AbteeX AI Labs
