"""Roadmap 5.12.0 gate (owner audit B1, B2, B8): a real chat answer, pasted from the real clipboard, moves the card.

The owner's 5.11.0 test: GPT answered the task prompt with a context request; copied from the rendered chat on
Windows every line ended with ``\\``; after fixing that by hand the paste box said "Context request ✓" and **nothing
happened**. Earlier smokes inserted text straight into the Text widget, never through the clipboard (B8).

This smoke only uses real widgets on Home and the real clipboard (``clipboard_append`` → ``<<Paste>>``, what Ctrl+V
does):

New Project wizard → charter → Accept → Prepare (prompt copied; it shows the exact context-request block and the
whole-answer rule) → the owner's GPT answer, damaged like a Windows rendered copy, pasted from the clipboard → live
diagnosis "Context request ✓ · 4 files" → Use this answer → **the card changes** to "<AI> asked for 4 files" →
Copy the files for the chat (clipboard has the files, the folder expanded, ``.env`` refused) → I sent them → the
delivery pasted from the clipboard → Accept → the file is on disk. No popup, no callback error.

Rule checked on the way: every answer the preview marks ✓ changes the card.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_owner_path_smoke import Owner, do_step, menu_labels, walk
from gui_smoke_helpers import wait_for_project_ready

REPO = Path(__file__).resolve().parents[4]
CHARTER = REPO / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"
OWNER = REPO / "docs/audit/owner-5.11/HO-0006_gpt_answer_context_request.txt"
F4 = "````"


def windows_copy(text: str) -> str:
    """Selecting the rendered answer in a chat on Windows and pressing Ctrl+C (owner audit B1)."""
    return "\n".join(line.replace("_", "\\_") + "\\" if line.strip() else line for line in text.split("\n"))


def clipboard_paste(o: Owner, box: tk.Text, value: str) -> None:
    """Put ``value`` on the system clipboard and paste it into ``box`` the way Ctrl+V does."""
    o.pastes += 1
    o.root.clipboard_clear()
    o.root.clipboard_append(value)
    o.pump(50)
    box.delete("1.0", "end")
    box.focus_force()
    box.event_generate("<<Paste>>")
    o.pump(100)
    got = box.get("1.0", "end-1c")
    assert got.replace("\r", "") == value.replace("\r", ""), f"the clipboard paste changed the text ({len(got)} chars)"


def use_clipboard_answer(o: Owner, card, text: str, needle: str) -> str:
    panel = card.paste
    assert panel.winfo_manager(), f"no paste panel on Home: {card.title_var.get()!r} {card.labels()}"
    before = card.title_var.get()
    clipboard_paste(o, panel.box, text)
    end, line = time.monotonic() + 5, ""
    while time.monotonic() < end and needle not in line:
        o.pump(50)
        line = panel.status_var.get()
    assert needle in line, f"live diagnosis never showed {needle!r}: {line!r}"
    o.click(panel.ok_btn)
    o.pump(600)
    if "✓" in line:   # 5.12.0 rule: an answer the preview marks ✓ must change the card
        assert card.title_var.get() != before or card.message_var.get(), f"✓ but the card did not move: {before!r}"
    return line


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-context-") as temp:
        home = Path(temp)
        os.environ["LOCALAPPDATA"] = str(home / "appdata")
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)
        (home / "Documents").mkdir()
        root = tk.Tk()
        root.geometry("1366x800+0+0")
        o = Owner(root)
        boxes: list[tuple[str, tuple]] = []
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(wb.messagebox, name, (lambda n: lambda *a, **k: boxes.append((n, a)))(name))
        try:
            app = wb.WorkbenchApp(root)
            o.pump(600)
            o.click_menu(app.shell.toolbar.menus["new"], menu_labels(app.shell.toolbar.menus["new"])[0])
            o.pump(400)
            wiz = app.project_wizard
            [c for c in walk(wiz.pages[0]) if c.winfo_class() == "TEntry"][0].insert(0, "Bridge")
            wiz.goal_text.insert("1.0", "A CATIA bridge with shared contracts")
            o.click(wiz.next_btn)
            o.pump(200)
            o.click(wiz.next_btn)
            o.pump(200)
            o.click(wiz.next_btn)
            assert app.workspace is not None, "Create made no project: " + wiz.error_var.get()
            wait_for_project_ready(app, root, app.workspace)
            o.pump(1000)
            ws_root = Path(app.workspace)
            # the files GPT will ask for (owner audit B2: three files and a folder) — and a secret it must never get
            (ws_root / "src" / "contracts").mkdir(parents=True)
            (ws_root / "src" / "contracts" / "models.py").write_text("class Part:\n    pass\n", encoding="utf-8")
            (ws_root / "src" / "contracts" / "__init__.py").write_text("from .models import Part\n", encoding="utf-8")
            (ws_root / "docs" / "contracts").mkdir(parents=True)
            (ws_root / "docs" / "contracts" / "catia-bridge-spec.md").write_text("# Spec\nOpen, read.\n", encoding="utf-8")
            (ws_root / "src" / "catia_bridge").mkdir(parents=True)
            (ws_root / "src" / "catia_bridge" / "session.py").write_text("SESSION = None\n", encoding="utf-8")
            (ws_root / ".env").write_text("TOKEN=do-not-send\n", encoding="utf-8")
            ws = app.workspace_window
            card = app.home_card
            card.refresh()
            o.click(card.next_btn)          # Copy the charter prompt
            o.pump(300)
            charter_prompt = root.clipboard_get()
            assert "five backticks" in charter_prompt, "the charter prompt asks for one code block (B1)"
            data = json.loads(CHARTER.read_text(encoding="utf-8"))
            data["base_state_revision"] = ws.wc.ctl.state()["state_revision"]
            charter = "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(data, indent=1) + "\n<<<AIWB_END_PROJECT_CHARTER>>>"
            use_clipboard_answer(o, card, windows_copy("Here is the plan.\n" + charter), "Charter ✓")
            do_step(o, card, "Accept")
            o.pump(500)
            do_step(o, card, "Prepare")
            o.pump(300)
            prompt = root.clipboard_get()
            assert prompt.startswith("AIWB_ATTEMPT_ID:"), prompt[:80]
            assert '"type": "AIWB_CONTEXT_REQUEST"' in prompt, "the task prompt shows the exact request (B2)"
            assert "five backticks" in prompt, "the task prompt asks for one code block (B1)"
            h = next(h for h in ws.wc.ctl.state()["handoffs"].values() if h["status"] in ("prepared", "prompt_exported"))
            att = h["attempt_id"]
            # the owner's real GPT answer, as the Windows rendered copy delivers it, through the clipboard
            real = OWNER.read_text(encoding="utf-8").replace("\r", "").replace("att-20261023-192855-0ba9959e", att)
            line = use_clipboard_answer(o, card, windows_copy(real), "Context request ✓")
            assert "4 files" in line, line
            title = card.title_var.get()
            assert "asked for 4 files" in title, f"the card did not turn into the files step: {title!r} {card.labels()}"
            assert card.next_btn.cget("text") == "Copy the files for the chat", card.labels()
            # Copy the files → clipboard
            o.click(card.next_btn)
            o.pump(300)
            pack = root.clipboard_get()
            assert pack.startswith(f"AIWB_ATTEMPT_ID: {att}"), pack[:80]
            for needle in ("class Part:", "from .models import Part", "# Spec", "src/catia_bridge/session.py"):
                assert needle in pack, f"{needle!r} not in the copied context"
            assert "do-not-send" not in pack
            assert card.next_btn.cget("text") == "I sent them", card.labels()
            o.click(card.next_btn)
            o.pump(300)
            # the delivery, pasted from the clipboard (whole answer in one five-backtick block, as the rule asks)
            h = ws.wc.ctl.state()["handoffs"][h["handoff_id"]]
            t = ws.wc.ctl.state()["tasks"][h["task_id"]]
            scope = ((t.get("scope") or {}).get("include") or ["src/**"])[0].rstrip("*").rstrip("/") or "src"
            man = {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": h["task_id"],
                   "task_revision": h["task_revision"], "attempt_id": att, "outcome": "complete", "summary": "bridge",
                   "completed_items": ["bridge"], "unresolved_items": [], "validation_claims": []}
            answer = ("`````text\n" + f"AIWB_ATTEMPT_ID: {att}\n"
                      f'<<<AIWB_FILE path="{scope}/bridge.py" action="write">>>\n{F4}\nfrom contracts import Part\n{F4}\n'
                      "<<<AIWB_END_FILE>>>\n<<<AIWB_HANDOFF>>>\n" + json.dumps(man) + "\n<<<AIWB_END_HANDOFF>>>\n`````")
            use_clipboard_answer(o, card, answer, "✓")
            labels = card.labels()
            assert any(lbl.startswith("Accept") for lbl in labels), f"no Accept after the answer: {labels}"
            do_step(o, card, next(lbl for lbl in labels if lbl.startswith("Accept")))
            o.pump(600)
            target = ws_root / scope / "bridge.py"
            assert target.is_file() and "from contracts import Part" in target.read_text(encoding="utf-8"), target
            assert "context_request" not in ws.wc.ctl.state()["handoffs"][h["handoff_id"]], "request closed"
            assert app.shell.current == "home", app.shell.current
            assert not o.dialogs, f"modal dialogs opened on the way: {o.dialogs}"
            assert not o.errors, "UI callback errors:\n" + "\n".join(o.errors)
            assert not [b for b in boxes if b[0] == "showerror"], f"error boxes: {boxes}"
        finally:
            root.destroy()
    msg = (f"Context smoke passed: charter and owner's GPT context request pasted from the clipboard as a Windows "
           f"rendered copy -> card 'asked for 4 files' -> files copied (folder expanded, .env refused) -> sent -> "
           f"delivery -> file on disk; {len(o.clicks)} clicks + {o.pastes} clipboard pastes")
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(msg.encode(enc, "replace").decode(enc, "replace"))


if __name__ == "__main__":
    main()
