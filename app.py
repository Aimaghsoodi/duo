"""DuoX — Hugging Face Space demo.

A Gradio UI that demonstrates the DuoX supervisor/executor orchestration loop.
On HF Spaces, real peer CLIs (claude, codex) aren't available, so this demo
simulates the orchestration with a single model acting as both supervisor and
executor via the Hugging Face Inference API.

Run locally:
    pip install gradio huggingface_hub
    python app.py

Deploy on HF Spaces: push this repo with `sdk: gradio` in README frontmatter.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

import gradio as gr


# ── Model backend ────────────────────────────────────────────────────────────

DEFAULT_MODEL = os.environ.get("DUOX_DEMO_MODEL", "meta-llama/Llama-3.1-8B-Instruct")


def _hf_chat(messages: list[dict], model: str = DEFAULT_MODEL) -> str:
    """Call HF Inference API. Falls back to canned response if unavailable."""
    try:
        from huggingface_hub import InferenceClient
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        client = InferenceClient(model=model, token=token)
        resp = client.chat_completion(messages=messages, max_tokens=600, temperature=0.4)
        return resp.choices[0].message.content or ""
    except Exception as e:
        return (
            "[demo fallback — HF Inference unavailable: "
            f"{type(e).__name__}]\nConfigure HF_TOKEN in Space secrets to enable "
            "live model responses. The orchestration loop below is still real."
        )


# ── DuoX orchestration loop (demo edition) ───────────────────────────────────

SUPERVISOR_SYS = (
    "You are the SUPERVISOR in the DuoX multi-peer swarm.\n"
    "Each turn, respond with ONE JSON object only:\n"
    '  {"action": "delegate"|"execute_self"|"done",\n'
    '   "to": "executor"|null,\n'
    '   "instructions": "<concrete scope>",\n'
    '   "reason": "<one sentence>",\n'
    '   "final_answer": "<only if action=done>"}\n'
    "Rules: delegate heavy work to 'executor'; use execute_self for small "
    "reasoning; stop with action=done when the goal is met (max 3 steps)."
)

EXECUTOR_SYS = (
    "You are the EXECUTOR peer in the DuoX swarm. Carry out the supervisor's "
    "instruction concretely. Be terse and useful."
)


@dataclass
class Turn:
    role: str
    text: str


@dataclass
class DemoState:
    transcript: list[Turn] = field(default_factory=list)


def _render_transcript(state: DemoState) -> str:
    return "\n\n".join(f"[{t.role}]\n{t.text}" for t in state.transcript) or "(empty)"


def _decide(state: DemoState, goal: str, model: str) -> dict:
    messages = [
        {"role": "system", "content": SUPERVISOR_SYS},
        {"role": "user",
         "content": f"User goal:\n{goal}\n\nShared transcript:\n{_render_transcript(state)}"
                    "\n\nRespond with the JSON decision now."},
    ]
    raw = _hf_chat(messages, model)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {"action": "done", "final_answer": raw, "reason": "no-json"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"action": "done", "final_answer": raw, "reason": "bad-json"}


def _execute(state: DemoState, instructions: str, model: str) -> str:
    messages = [
        {"role": "system", "content": EXECUTOR_SYS},
        {"role": "user",
         "content": f"Transcript so far:\n{_render_transcript(state)}\n\n"
                    f"Instructions:\n{instructions}"},
    ]
    return _hf_chat(messages, model)


def run_goal(goal: str, model: str, max_steps: int = 3):
    """Generator that yields (markdown_log, final) tuples so the UI streams."""
    state = DemoState()
    state.transcript.append(Turn("user", goal))
    log: list[str] = [f"### ▸ user goal\n{goal}"]
    yield "\n\n".join(log), ""
    final = ""

    for step in range(1, max_steps + 1):
        log.append(f"\n### · step {step} — supervisor deciding…")
        yield "\n\n".join(log), ""
        d = _decide(state, goal, model)
        action = d.get("action", "done")
        reason = d.get("reason", "")
        instr = (d.get("instructions") or "").strip()
        log.append(f"**decision:** `{action}` — _{reason}_")
        if instr:
            log.append(f"> {instr}")
        state.transcript.append(Turn("supervisor", json.dumps(d)))
        yield "\n\n".join(log), ""

        if action == "done":
            final = d.get("final_answer") or "(no final answer)"
            log.append(f"\n### ✓ done\n{final}")
            yield "\n\n".join(log), final
            return

        if action == "delegate":
            log.append(f"\n### → executor running…")
            yield "\n\n".join(log), ""
            out = _execute(state, instr, model)
            state.transcript.append(Turn("executor", out))
            log.append(f"**executor:**\n\n{out}")
            yield "\n\n".join(log), ""
            time.sleep(0.2)
            continue

        # execute_self
        out = _execute(state, instr or goal, model)
        state.transcript.append(Turn("supervisor", out))
        log.append(f"**supervisor (execute_self):**\n\n{out}")
        yield "\n\n".join(log), ""

    log.append(f"\n_hit max_steps={max_steps}; stopping._")
    yield "\n\n".join(log), final


# ── Gradio UI ────────────────────────────────────────────────────────────────

EXAMPLES = [
    "Outline a multi-agent orchestrator architecture for a coding assistant",
    "Draft release notes for a v0.2 Python CLI that added parallel execution",
    "Explain when to prefer supervisor/executor over a single-agent ReAct loop",
    "Review this pseudocode for race conditions: lock = False; if not lock: lock=True; do_work(); lock=False",
]

HEADER = """
# DuoX — multi-peer AI CLI orchestrator

A live demo of the **DuoX supervisor/executor loop**. Enter a goal; a supervisor
LLM emits a JSON decision each turn (`delegate` / `execute_self` / `done`),
routes to the executor, and stops when the goal is met.

> 🖥️ **Full CLI**: `pip install duox`  ·  `duox`  (Claude + Codex + Ollama + OpenClaw)
> 📦 **GitHub**: [aimaghsoodi/duo](https://github.com/aimaghsoodi/duo)  ·  **PyPI**: [duox](https://pypi.org/project/duox/)  ·  **HF org**: [AbteeX-AI-Labs](https://huggingface.co/AbteeX-AI-Labs)
"""


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="DuoX — multi-peer orchestrator demo",
                   theme=gr.themes.Soft(primary_hue="pink")) as demo:
        gr.Markdown(HEADER)
        with gr.Row():
            with gr.Column(scale=2):
                goal = gr.Textbox(label="Your goal",
                                  placeholder="e.g. outline a plan for shipping a CLI tool",
                                  lines=3)
                with gr.Row():
                    model = gr.Textbox(label="HF model",
                                       value=DEFAULT_MODEL, scale=3)
                    run_btn = gr.Button("▶ Run", variant="primary", scale=1)
                gr.Examples(EXAMPLES, inputs=[goal], label="Try one")
            with gr.Column(scale=3):
                log = gr.Markdown(label="Orchestration trace")
                final = gr.Textbox(label="Final answer", lines=6, show_copy_button=True)

        run_btn.click(run_goal, inputs=[goal, model], outputs=[log, final])

        gr.Markdown(
            "---\n"
            "**What you're seeing:** this is the same supervisor/executor loop DuoX "
            "runs locally, just backed by one HF-hosted model instead of real peer "
            "CLIs. Install `duox` to run it with Claude Code, Codex, Ollama, and "
            "OpenClaw for real.\n\n"
            "_MIT © AbteeX AI Labs_"
        )
    return demo


if __name__ == "__main__":
    build_demo().launch()
