# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-04-18

### Added
- **Rebrand to DuoX**. New `duox` console script (`duo` kept as legacy alias);
  PyPI name becomes `duox`. Banner, welcome, slash commands, and docs all updated.
- **Ollama and OpenClaw peers** — `--peers claude,codex,ollama,openclaw`.
- **Multi-pane live TUI** (`rich.Live`) with single-scrolling transcript default.
- **30+ slash commands**: `/help /tips /examples /peers /supervisor /model
  /skills /history /save /cost /hooks /mcp /parallel /plan /review /test /swarm
  /claude /codex /ollama /openclaw /oc-health /oc-send /oc-pair /version /config
  /session /compact /remember /cd /doctor /quit`.
- **Context files** — auto-discovery of `CLAUDE.md`, `AGENTS.md`, `DUO.md`
  walking up from cwd, plus `~/.duo/DUO.md` and `~/.duo/notes.md`.
- **`@file` mentions** — inline file / dir / `@file.py:12-40` line-range
  excerpts in any prompt, with sandboxed path resolution.
- **`/compact`** — summarise transcript into one turn via supervisor.
- **`/remember <note>`** — append to `~/.duo/notes.md` (auto-loaded).
- **`/doctor` + `duox doctor`** — verify peers, MCP, readline, openclaw.
- **Headless `-p/--print`** with `--output-format text|json` — reads stdin if no arg.
- **Readline line editor** — history, `↑`/`↓`, tab-complete on slash commands.
- **Skills** — markdown prompts in `~/.duo/skills/*.md` with `always`/`match`.
- **Sessions** — JSONL event log + transcript in `~/.duo/sessions/`; `duox --resume`.
- **Hooks** — `[hooks].pre_step` / `post_step` shell commands around each step.
- **MCP pass-through** — `[mcp.servers.*]` forwarded to Claude via `--mcp-config`.
- **HTTP API daemon** — `duox serve --port 8787`.
- **Per-project config** — `.duo.toml` in repo root deep-merged over globals.
- **Hugging Face Space demo** — `app.py` (Gradio) + Space README frontmatter.
- **CI matrix** — Ubuntu × Windows × macOS × Python 3.10/3.11/3.12.
- **47 unit tests**.

### Changed
- Default interactive mode; `--once` flag for one-shot.
- Supervisor prompt references "DuoX multi-peer swarm".

## [0.1.0] — 2026-04-17

### Added
- Initial public release by AbteeX AI Labs.
- `duo` CLI: single-prompt orchestrator running Claude Code and Codex CLI as peers.
- Supervisor / executor protocol with JSON-encoded decisions
  (`delegate`, `execute_self`, `validate`, `done`).
- Continuous cross-checking: every delegated step is validated before the next move.
- **Swarm mode (default ON)**: both peers are instructed to spawn parallel sub-agents
  for independent sub-tasks.
- Automatic credit / rate-limit / quota fallback between peers.
- Live colored streaming of both CLIs in a single terminal session.
- Interactive follow-up loop via `-i` / `--interactive`.
- Windows launcher (`duo.ps1`).
- Brand assets: minimal SVG logo, horizontal wordmark, 512×512 LinkedIn card.
- One-pager site in `docs/` (GitHub Pages ready).
- GitHub Actions: CI (build + smoke test on Linux/macOS/Windows × Python 3.10–3.12),
  Pages deploy (with SVG→PNG rendering), PyPI trusted-publish on tag.

[0.2.0]: https://github.com/aimaghsoodi/duo/releases/tag/v0.2.0
[0.1.0]: https://github.com/aimaghsoodi/duo/releases/tag/v0.1.0
