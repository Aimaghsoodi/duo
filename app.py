"""DuoX — Hugging Face Space demo.

A single-pane terminal-style Gradio UI for the DuoX supervisor/executor
orchestration loop. One model plays both supervisor and executor via the HF
Inference API (on Spaces, real peer CLIs like claude/codex aren't available).

Run locally:
    pip install "gradio>=5" huggingface_hub
    python app.py
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

import gradio as gr


DEFAULT_MODEL = os.environ.get("DUOX_DEMO_MODEL", "meta-llama/Llama-3.1-8B-Instruct")


def _hf_chat(messages: list[dict], model: str = DEFAULT_MODEL) -> str:
    try:
        from huggingface_hub import InferenceClient
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        client = InferenceClient(model=model, token=token)
        resp = client.chat_completion(messages=messages, max_tokens=600, temperature=0.4)
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"[inference unavailable: {type(e).__name__}: {e}]"


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


def _transcript(s: DemoState) -> str:
    return "\n\n".join(f"[{t.role}] {t.text}" for t in s.transcript) or "(empty)"


def _decide(state: DemoState, goal: str, model: str) -> dict:
    raw = _hf_chat([
        {"role": "system", "content": SUPERVISOR_SYS},
        {"role": "user",
         "content": f"User goal:\n{goal}\n\nShared transcript:\n{_transcript(state)}"
                    "\n\nRespond with the JSON decision now."},
    ], model)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {"action": "done", "final_answer": raw, "reason": "no-json"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"action": "done", "final_answer": raw, "reason": "bad-json"}


def _execute(state: DemoState, instructions: str, model: str) -> str:
    return _hf_chat([
        {"role": "system", "content": EXECUTOR_SYS},
        {"role": "user",
         "content": f"Transcript so far:\n{_transcript(state)}\n\n"
                    f"Instructions:\n{instructions}"},
    ], model)


def run_goal(goal: str, model: str, max_steps: int = 3):
    """Yield a single growing terminal string (Claude-CLI style)."""
    goal = (goal or "").strip()
    model = (model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    if not goal:
        yield "› type a goal and press enter."
        return

    state = DemoState()
    state.transcript.append(Turn("user", goal))

    lines: list[str] = []
    lines.append(f"› {goal}")
    lines.append("")
    yield "\n".join(lines)

    for step in range(1, max_steps + 1):
        lines.append(f"  supervisor · step {step} · deciding…")
        yield "\n".join(lines)

        d = _decide(state, goal, model)
        action = d.get("action", "done")
        reason = (d.get("reason") or "").strip()
        instr = (d.get("instructions") or "").strip()
        lines[-1] = f"  supervisor · step {step} · {action}" + (f"  — {reason}" if reason else "")
        if instr:
            lines.append(f"    └─ {instr}")
        state.transcript.append(Turn("supervisor", json.dumps(d)))
        yield "\n".join(lines)

        if action == "done":
            final = (d.get("final_answer") or "").strip() or "(no final answer)"
            lines.append("")
            lines.append(final)
            yield "\n".join(lines)
            return

        if action == "delegate":
            lines.append("  executor · running…")
            yield "\n".join(lines)
            out = _execute(state, instr, model).strip()
            state.transcript.append(Turn("executor", out))
            lines[-1] = "  executor ·"
            for ln in out.splitlines() or [""]:
                lines.append(f"    {ln}")
            yield "\n".join(lines)
            time.sleep(0.1)
            continue

        # execute_self
        out = _execute(state, instr or goal, model).strip()
        state.transcript.append(Turn("supervisor", out))
        lines.append("  supervisor ·")
        for ln in out.splitlines() or [""]:
            lines.append(f"    {ln}")
        yield "\n".join(lines)

    lines.append("")
    lines.append(f"  (hit max_steps={max_steps})")
    yield "\n".join(lines)


EXAMPLES = [
    "outline a multi-agent orchestrator architecture for a coding assistant",
    "draft release notes for a v0.2 Python CLI that added parallel execution",
    "explain when to prefer supervisor/executor over a single-agent ReAct loop",
    "review this pseudocode for race conditions: lock=False; if not lock: lock=True; do_work(); lock=False",
]


CSS = """
:root { --bg:#0b0e14; --fg:#eef1f7; --muted:#7a869a; --pink:#ec5fa5; --purple:#a259ff; }
html, body, .gradio-container { background:var(--bg) !important; color:var(--fg); }
.gradio-container { max-width: 900px !important; margin: 0 auto !important; padding: 32px 20px 48px !important; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
footer { display:none !important; }

/* Kill default borders/backgrounds on every block so it looks like plain terminal. */
.gradio-container .block, .gradio-container .form, .gradio-container .wrap,
.gradio-container .container { background: transparent !important; border: none !important; box-shadow: none !important; }

/* Header */
.duox-header { display:flex; align-items:baseline; gap:10px; margin-bottom: 6px; }
.duox-header .brand { font-weight: 700; background: linear-gradient(135deg,#ec5fa5,#a259ff); -webkit-background-clip:text; background-clip:text; color:transparent; font-size:18px; letter-spacing:.5px; }
.duox-header .tag { color: var(--muted); font-size: 12px; }
.duox-sub { color: var(--muted); font-size: 13px; margin: 0 0 22px 0; }
.duox-sub a { color: var(--pink); text-decoration: none; }

/* Input: a single line that looks like a shell prompt. */
.duox-input textarea {
  background: transparent !important;
  border: none !important;
  border-bottom: 1px solid #1e2430 !important;
  border-radius: 0 !important;
  color: var(--fg) !important;
  font-family: inherit !important;
  font-size: 14.5px !important;
  padding: 10px 0 12px 22px !important;
  box-shadow: none !important;
  resize: none !important;
}
.duox-input { position: relative; }
.duox-input::before {
  content: "›";
  position: absolute;
  left: 2px; top: 10px;
  color: var(--pink);
  font-size: 16px;
  font-weight: 700;
  z-index: 2;
  pointer-events: none;
}
.duox-input label, .duox-input .label-wrap { display:none !important; }

/* Output: plain pre, no panel. */
.duox-output { margin-top: 14px; }
.duox-output .prose, .duox-output pre, .duox-output code {
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
  margin: 0 !important;
  color: var(--fg) !important;
  font-family: inherit !important;
  font-size: 13.5px !important;
  line-height: 1.65 !important;
  white-space: pre-wrap;
}
.duox-output label, .duox-output .label-wrap { display:none !important; }

/* Run button — a small pill, top-right of input */
.duox-run { min-width: 80px !important; }
.duox-run button {
  background: linear-gradient(135deg,#ec5fa5,#a259ff) !important;
  color: white !important;
  border: none !important;
  border-radius: 8px !important;
  font-family: inherit !important;
  font-size: 13px !important;
  font-weight: 600 !important;
  padding: 8px 14px !important;
}

/* Model row: barely visible */
.duox-model input {
  background: transparent !important;
  border: none !important;
  border-bottom: 1px dashed #1e2430 !important;
  border-radius: 0 !important;
  color: var(--muted) !important;
  font-family: inherit !important;
  font-size: 12px !important;
  padding: 6px 0 !important;
}
.duox-model label, .duox-model .label-wrap { display:none !important; }
.duox-model::before { content: "model: "; color: var(--muted); font-size: 12px; }

/* Examples */
.duox-examples { margin-top: 18px; }
.duox-examples button {
  background: transparent !important;
  border: 1px solid #1e2430 !important;
  color: var(--muted) !important;
  font-family: inherit !important;
  font-size: 12px !important;
  border-radius: 999px !important;
  padding: 4px 12px !important;
}
.duox-examples button:hover { color: var(--fg) !important; border-color: var(--pink) !important; }
.duox-examples label, .duox-examples .label-wrap { display:none !important; }
"""


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="DuoX — multi-peer orchestrator demo",
                   theme=gr.themes.Base(), css=CSS) as demo:
        gr.HTML(
            '<div class="duox-header">'
            '<span class="brand">DuoX</span>'
            '<span class="tag">· multi-peer AI CLI orchestrator</span>'
            '</div>'
            '<p class="duox-sub">supervisor · executor · one transcript · '
            '<a href="https://pypi.org/project/duox/">pip install duox</a> · '
            '<a href="https://github.com/aimaghsoodi/duo">github</a></p>'
        )

        with gr.Row():
            goal = gr.Textbox(
                placeholder="type a goal and press enter…",
                lines=1, max_lines=3, show_label=False, container=False,
                elem_classes=["duox-input"], scale=5,
            )
            run_btn = gr.Button("run ↵", elem_classes=["duox-run"], scale=1)

        out = gr.Markdown(elem_classes=["duox-output"])

        model = gr.Textbox(
            value=DEFAULT_MODEL, show_label=False, container=False,
            elem_classes=["duox-model"],
        )

        gr.Examples(
            EXAMPLES, inputs=[goal], label="",
            elem_id="duox-examples",
        )

        goal.submit(run_goal, inputs=[goal, model], outputs=[out])
        run_btn.click(run_goal, inputs=[goal, model], outputs=[out])

    return demo


if __name__ == "__main__":
    build_demo().launch()
