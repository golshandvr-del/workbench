"""Roadmap 5.15.0 scenario S7: the chat (ChatGPT) gives a ZIP instead of text — Load ZIP… → Accept → files on disk.

Guided project, Home only, REAL widgets. Charter → Accept → Prepare (the task prompt is copied) → ChatGPT answers
with a downloadable ZIP in its usual shape (corpus F14): one top folder named after the project, the files under it,
``AIWB_HANDOFF.json`` next to them, plus the ``__MACOSX`` / ``.DS_Store`` noise of a Mac → the card's **Load ZIP…**
button (only the operating system's file picker is replaced: it returns the downloaded file) → the live check says ✓
→ Use this answer → Accept → the files are on disk under the project root (the top folder is not kept), the noise is
not written anywhere. (A file outside the task's paths
turns the card into "Problems found" — covered by the answer corpus, not here.)
"""
from __future__ import annotations

import json
import tkinter as tk
import zipfile
from pathlib import Path

from aiwb.ui import paste_box
from scenario_driver import (Driver, charter_to_first_prompt, digest, handoff_manifest, new_guided_project, run,
                             scenario_home)

FILES = {"src/core/model.py": "class Todo:\n    title = ''\n",
         "src/core/store.py": "import json\n\n\ndef load(path):\n    return json.load(open(path))\n",
         }


def gpt_zip(target: Path, h: dict) -> Path:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for p, c in FILES.items():
            z.writestr("todo/" + p, c)
        z.writestr("todo/AIWB_HANDOFF.json", json.dumps(handoff_manifest(h, "core done"), indent=2))
        z.writestr("__MACOSX/todo/src/core/._model.py", "x")
        z.writestr("todo/.DS_Store", "x")
    return target


def main() -> None:
    with scenario_home("s7") as home:
        d = Driver(tk.Tk(), "s7")
        try:
            app = d.start()
            card = new_guided_project(d, app, "Todo", "A command-line todo app", ["Core dev", "CLI dev", "QA"])
            h = charter_to_first_prompt(d, app, card)
            folder = Path(app.workspace)
            before = digest(folder)
            downloaded = gpt_zip(home / "Downloads.zip", h)

            # Load ZIP…: the real button; only the OS file picker is replaced by "the user picks the download"
            picked: list[str] = []
            paste_box.filedialog.askopenfilename = lambda **k: (picked.append(k.get("title", "")), str(downloaded))[1]
            d.click(card.paste.zip_btn, "Load ZIP…")
            assert picked == ["Load the ZIP the chat gave you"], picked
            line = d.wait_line(card.paste, "✓")
            text = card.paste.box.get("1.0", "end-1c")
            assert all(f'path="{p}"' in text for p in FILES), text[:400]
            assert "__MACOSX" not in text and ".DS_Store" not in text, "ZIP noise reached the answer"
            d.shot("01_zip_loaded")
            d.click(card.paste.ok_btn, "Use this answer")
            d.pump(500)
            ho = app.workspace_window.wc.ctl.state()["handoffs"][h["handoff_id"]]
            staged = sorted(f["path"] for f in ho.get("staged_files") or [])
            assert staged == sorted(FILES), f"staged from the ZIP: {staged}"
            accept = next((lbl for lbl in card.labels() if lbl.startswith("Accept")), None)
            assert accept, f"no Accept after the ZIP: {card.title_var.get()!r} {card.labels()}"
            d.step(card, accept)
            for p, c in FILES.items():
                assert (folder / p).read_text(encoding="utf-8") == c, f"{p} on disk"
            new = set(digest(folder)) - set(before)
            assert new == set(FILES), f"files written by the ZIP: {sorted(new)}"
            assert not (folder / "todo").exists(), "the ZIP's top folder was kept"
            d.shot("02_zip_applied")
            assert app.shell.current == "home", f"the path left Home for {app.shell.current!r}"
            d.finish()
        finally:
            d.destroy()
    d.say(f"S7 GPT ZIP (top folder, AIWB_HANDOFF.json, Mac noise) -> Load ZIP... -> {line[:40]} -> Accept -> "
          f"{len(FILES)} files on disk, nothing else; {len(d.clicks)} clicks + {d.pastes} pastes: PASS")


if __name__ == "__main__":
    run(main)
