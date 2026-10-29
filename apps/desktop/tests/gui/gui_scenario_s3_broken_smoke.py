"""Roadmap 5.15.0 scenario S3: a broken GPT answer is fixed automatically, or the user gets a fix prompt to send back.

Guided project, Home only, REAL widgets and the real clipboard:

1. the chat's charter points a task at a task that does not exist (``t99``) → refused, nothing imported, the card
   says so and the **fix prompt** for the same chat is on the clipboard (it names the problem);
2. the chat answers again in the DeepSeek/Gemini habit — ``//`` comments, trailing commas, smart quotes, the markers
   in bold → **fixed automatically** → Charter ✓ … auto-fixes → Accept → the tasks exist;
3. the first task's answer comes as Markdown (``**path**`` + code fence, no AIWB blocks, no manifest) → converted
   → Accept → the file is on disk.
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path

from scenario_driver import CHARTER, Driver, new_guided_project, open_handoff, run, scenario_home


def charter_data(app) -> dict:
    data = json.loads(CHARTER.read_text(encoding="utf-8"))
    data["base_state_revision"] = app.workspace_window.wc.ctl.state()["state_revision"]
    return data


def messy(data: dict) -> str:
    """The same charter as a sloppy chat writes it: comments, trailing commas, smart quotes, bold markers."""
    body = json.dumps(data, indent=2, ensure_ascii=False)
    body = body.replace("\n  \"project\":", "\n  // the project\n  \"project\":", 1)
    body = body.replace("\n  ]", ",\n  ]").replace("\n  }\n}", ",\n  },\n}")
    body = body.replace('"schema_version"', "\u201cschema_version\u201d", 1)
    return ("Sure — here is the corrected plan.\n\n**<<<AIWB_PROJECT_CHARTER>>>**\n```json\n" + body
            + "\n```\n**<<<AIWB_END_PROJECT_CHARTER>>>**\n\nLet me know if you want changes!")


def main() -> None:
    with scenario_home("s3"):
        d = Driver(tk.Tk(), "s3")
        try:
            app = d.start()
            card = new_guided_project(d, app, "Todo", "A command-line todo app", ["Core dev", "CLI dev", "QA"])
            ctl = app.workspace_window.wc.ctl

            # 1) a charter the app cannot repair → fix prompt on the clipboard, nothing imported
            bad = charter_data(app)
            bad["tasks"][1]["depends_on_refs"] = ["t99"]
            d.paste(card.paste.box, "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(bad) + "\n<<<AIWB_END_PROJECT_CHARTER>>>")
            d.pump(400)
            d.click(card.paste.ok_btn)
            d.pump(500)
            msg = card.message_var.get()
            assert "fix prompt" in msg and "copied" in msg, msg
            fix = d.clipboard()
            assert fix.startswith("# AI Workbench — please fix your Project Charter") and "t99" in fix, fix[:400]
            assert not ctl.state()["tasks"], "a refused charter imported tasks"
            d.shot("01_fix_prompt")

            # 2) the chat answers again, sloppily → repaired automatically → Accept
            d.use_answer(card, messy(charter_data(app)), "Charter ✓")
            msg = card.message_var.get()
            assert "auto-fix" in msg and "Imported as PROP-" in msg, msg
            d.shot("02_auto_fixed")
            d.step(card, "Accept")
            assert ctl.state()["tasks"], "the repaired charter made no tasks"

            # 3) the task answer as Markdown (no AIWB blocks, no manifest) → converted → Accept → on disk
            d.step(card, "Prepare")
            h = open_handoff(app)
            md = (f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n\nHere is the core store.\n\n**src/core/store.py**\n"
                  "```python\nITEMS: list[str] = []\n\n\ndef add(item: str) -> None:\n    ITEMS.append(item)\n```\n")
            d.use_answer(card, md, "✓")
            accept = next((lbl for lbl in card.labels() if lbl.startswith("Accept")), None)
            assert accept, f"no Accept after the Markdown answer: {card.title_var.get()!r} {card.labels()}"
            d.step(card, accept)
            target = Path(app.workspace) / "src/core/store.py"
            assert target.is_file() and "def add" in target.read_text(encoding="utf-8"), "the Markdown file is on disk"
            d.shot("03_markdown_applied")
            d.finish()
        finally:
            d.destroy()
    d.say(f"S3 broken answers: unknown dependency -> fix prompt copied, nothing imported; sloppy charter -> auto-fixed "
          f"-> accepted; Markdown files -> converted -> on disk; {len(d.clicks)} clicks + {d.pastes} pastes: PASS")


if __name__ == "__main__":
    run(main)
