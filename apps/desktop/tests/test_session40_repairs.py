"""Regression tests for the session-40 repairs: BF-068 (draft task wording), BF-069 (late pairing approval),
BF-070 (long Persian answer), BF-071 (clock skew), BF-072 (device permissions), BF-073 (port in use),
BF-099 / BF-100 / BF-102 (dialogs that must fit small screens)."""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))

import test_companion as tcmp  # noqa: E402
from aiwb import i18n  # noqa: E402
from aiwb.companion import crypto  # noqa: E402
from aiwb.companion.server import CompanionServer  # noqa: E402
from aiwb.companion.service import PAIRING_GRACE_SECONDS, CompanionError  # noqa: E402


def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        return None
    root.withdraw()
    return root


def pump(root: tk.Misc, seconds: float, until=None) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until() if until is not None else True


class WorkbenchWordingTests(unittest.TestCase):
    def test_bf068_draft_task_is_not_called_finished_work(self) -> None:
        en, fa = i18n.ACTION["approve_task"]
        self.assertNotIn("finish", en.lower())
        self.assertIn("new task", en)
        self.assertNotIn("تمام", fa, "the Persian text no longer says finished work either")
        self.assertIn("finished", (i18n.ACTION["review_delivery"][0] + i18n.ACTION["review_task"][0]).lower())


class CompanionRepairTests(tcmp.ServiceTests):
    def test_bf069_request_sent_before_expiry_can_still_be_decided_and_polled(self) -> None:
        ph = tcmp.Phone(self.svc, self.svc.start_pairing("127.0.0.1", 1))
        self.now[0] += 590
        self.assertEqual(ph.pair()[1]["status"], "pending")
        self.now[0] += 30   # the code ran out while the request waited for the user
        self.assertEqual(self.svc.pairing_state()["state"], "expired")
        [req] = self.svc.pending_requests()
        self.assertEqual(ph.call(ph.pid, ph.secret, {"op": "pair_status"})[1]["status"], "pending",
                         "the phone may keep polling during the grace period")
        dev = self.svc.decide(req["pairing_id"], True)
        code, st = ph.call(ph.pid, ph.secret, {"op": "pair_status"})
        self.assertEqual((code, st["status"], st["device_id"]), (200, "approved", dev["device_id"]),
                         "desktop and phone agree on the result")
        # a brand-new request is refused after expiry
        ph2 = tcmp.Phone(self.svc, self.svc.start_pairing("127.0.0.1", 1))
        self.now[0] += 601
        self.assertEqual(ph2.pair(), (403, {"error": "pairing_expired"}))

    def test_bf069_request_after_the_grace_period_is_dropped_not_registered(self) -> None:
        ph = tcmp.Phone(self.svc, self.svc.start_pairing("127.0.0.1", 1))
        ph.pair()
        self.now[0] += 600 + PAIRING_GRACE_SECONDS + 5
        self.assertEqual(self.svc.pending_requests(), [])
        with self.assertRaises(CompanionError) as cm:
            self.svc.decide(ph.pid, True)
        self.assertIn("too late", str(cm.exception))
        self.assertEqual(self.reg.list(), [], "no active device nobody can use")
        self.assertEqual(ph.call(ph.pid, ph.secret, {"op": "pair_status"}), (403, {"error": "pairing_expired"}))

    def test_bf070_long_persian_answer_is_accepted_and_oversize_gets_a_clear_code(self) -> None:
        ph = self.paired(("view_project", "submit_response"))
        persian = "سلام دنیا " * 17_500   # 175 000 characters, ~330 KB of UTF-8: refused before the repair
        self.assertEqual(len(persian), 175_000)
        code, out = ph.req("submit_response", text=persian)
        self.assertEqual(code, 200)
        self.assertEqual(out["kind"], "inbox_only", out)
        code, out = ph.req("submit_response", text="a" * 300_001)
        self.assertEqual((code, out["error"]), (200, "too_large"), "the message that explains the limit is reachable")
        code, out = ph.req("submit_response", text="ب" * 300_000)   # the documented maximum, Persian
        self.assertEqual(code, 200)
        self.assertTrue(out["ok"] or out["kind"] == "inbox_only", out)
        code, out = self.svc.handle(b"x" * (crypto.MAX_ENVELOPE_BYTES + 1))
        self.assertEqual((code, out), (413, {"error": "too_large"}))

    def test_bf070_http_server_accepts_a_long_persian_body(self) -> None:
        srv = CompanionServer(self.svc, host="127.0.0.1", port=0)
        port = srv.start()
        try:
            ph = self.paired(("view_project", "submit_response"))
            import http.client
            env = crypto.seal(ph.key, ph.device_id, {"op": "submit_response", "text": "ک" * 200_000}, ts=int(self.now[0]))
            body = json.dumps(env).encode()
            self.assertGreater(len(body), 512 * 1024)
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
            c.request("POST", "/aiwb/v1", body, {"Content-Type": "application/json"})
            r = c.getresponse()
            self.assertEqual(r.status, 200)
            r.read()
            c.close()
        finally:
            srv.stop()

    def test_bf071_valid_mac_with_wrong_clock_is_not_a_wrong_code(self) -> None:
        ph = tcmp.Phone(self.svc, self.svc.start_pairing("127.0.0.1", 1))
        for _ in range(7):   # more than PAIRING_MAX_FAILURES
            env = crypto.seal(ph.secret, ph.pid, {"op": "pair_request", "device_name": "Pixel",
                                                  "device_key": crypto.b64e(ph.key)},
                              ts=int(self.now[0]) - 420)   # the phone is 7 minutes slow
            code, out = self.svc.handle(json.dumps(env).encode())
            self.assertEqual((code, out["error"]), (401, "clock_skew"))
            self.assertEqual(out["server_time"], int(self.now[0]))
        self.assertEqual(self.svc.pairing_state()["state"], "active", "the code was NOT cancelled")
        self.assertEqual(self.svc.last_skew["seconds"], -420)
        self.assertEqual(ph.pair()[1]["status"], "pending", "the same code works once the clock is right")
        # a wrong MAC still counts and still reads as unauthenticated
        ph3 = tcmp.Phone(self.svc, self.svc.start_pairing("127.0.0.1", 1))
        forged = crypto.seal(os.urandom(32), ph3.pid, {"op": "pair_request"}, ts=int(self.now[0]))
        self.assertEqual(self.svc.handle(json.dumps(forged).encode()), (401, {"error": "unauthenticated"}))

    def test_bf071_paired_device_with_a_wrong_clock_gets_clock_skew(self) -> None:
        ph = self.paired()
        env = crypto.seal(ph.key, ph.device_id, {"op": "hello"}, ts=int(self.now[0]) + 400)
        code, out = self.svc.handle(json.dumps(env).encode())
        self.assertEqual((code, out["error"]), (401, "clock_skew"))
        self.assertEqual(self.svc.last_skew["seconds"], 400)


class CompanionWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk_root()
        if self.root is None:
            self.skipTest("no display")
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / "proj").mkdir()
        from aiwb.companion.service import CompanionService, DeviceRegistry
        from aiwb.v2.controller import ProjectsController
        self.ctl = ProjectsController(base / "proj")
        self.reg = DeviceRegistry(base / "devices.json")
        self.now = [1_792_300_000.0]
        self.svc = CompanionService(self.reg, controller=lambda: self.ctl, clock=lambda: self.now[0])
        self.server = CompanionServer(self.svc, host="127.0.0.1", port=0)
        import aiwb.companion.window as cw
        self.cw = cw
        self.errors: list[str] = []
        self._orig = cw.messagebox.showerror
        cw.messagebox.showerror = lambda *a, **k: self.errors.append(str(a[1] if len(a) > 1 else k))
        self.win = cw.CompanionWindow(self.root, self.svc, self.server, clipboard=lambda _t: None,
                                      confirm=lambda *_a: True)

    def tearDown(self) -> None:
        self.cw.messagebox.showerror = self._orig
        try:
            self.win.close()
        except tk.TclError:
            pass
        self.server.stop()
        self.root.destroy()
        self.tmp.cleanup()

    def test_bf072_selecting_a_device_loads_its_permissions_and_a_change_keeps_the_others(self) -> None:
        dev = self.reg.add("Pixel", os.urandom(32), ("view_project", "create_task", "submit_response"))
        self.win.refresh()
        self.assertEqual(str(self.win.perm_btn.cget("state")), "disabled", "nothing selected")
        self.win.tree.selection_set(dev["device_id"])
        self.root.update()
        self.assertEqual({p for p, v in self.win.perm_vars.items() if v.get()},
                         {"view_project", "create_task", "submit_response"})
        self.win.perm_vars["create_task"].set(False)
        self.win.do_permissions()
        self.assertEqual(set(self.reg.get(dev["device_id"])["permissions"]), {"view_project", "submit_response"})
        self.assertIn("removed: create task", self.win.perm_note.get())

    def test_bf072_permissions_chosen_for_one_phone_are_not_given_to_the_next(self) -> None:
        self.win.do_pair()
        ph = tcmp.Phone(self.svc, self.svc.pairing["uri"])
        ph.pair()
        self.win.refresh()
        self.win.perm_vars["submit_response"].set(True)
        self.win.do_decide(True)
        self.assertFalse(self.win.perm_vars["submit_response"].get(), "boxes go back to the defaults")

    def test_bf073_port_in_use_is_reported_not_raised(self) -> None:
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        try:
            self.server.port = blocker.getsockname()[1]
            self.assertEqual(self.win.do_pair(), "", "no exception reaches Tk's bug dialog")
            self.assertFalse(self.server.running)
            self.assertTrue(self.errors)
            self.assertIn("used by another program", self.win.pair_var.get())
        finally:
            blocker.close()

    def test_bf073_a_detected_address_is_redetected_on_start_but_a_given_one_is_kept(self) -> None:
        import aiwb.companion.server as cs
        auto = CompanionServer(self.svc, port=0)
        orig = cs.lan_address
        try:
            cs.lan_address = lambda: "127.0.0.1"
            auto._host = "10.9.9.9"
            auto.start()
            self.assertEqual(auto.host, "127.0.0.1")
        finally:
            cs.lan_address = orig
            auto.stop()
        fixed = CompanionServer(self.svc, host="127.0.0.1", port=0)
        fixed.start()
        self.assertEqual(fixed.host, "127.0.0.1")
        fixed.stop()

    def test_bf071_the_window_names_the_clock_problem(self) -> None:
        self.win.do_pair()
        ph = tcmp.Phone(self.svc, self.svc.pairing["uri"])
        env = crypto.seal(ph.secret, ph.pid, {"op": "pair_request"}, ts=int(self.now[0]) - 600)
        self.svc.handle(json.dumps(env).encode())
        self.win.refresh()
        self.assertIn("clock", self.win.pair_var.get())
        self.assertIn("10 minute", self.win.pair_var.get())


class DialogFitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk_root()
        if self.root is None:
            self.skipTest("no display")

    def tearDown(self) -> None:
        self.root.destroy()

    def _visible(self, top: tk.Toplevel, widget: tk.Misc) -> bool:
        top.update()
        sh = top.winfo_screenheight()
        return (widget.winfo_ismapped() and widget.winfo_rooty() >= 0
                and widget.winfo_rooty() + widget.winfo_height() <= sh)

    def test_bf099_proposal_dialog_keeps_its_buttons_on_screen_and_scrolls(self) -> None:
        from aiwb.v2 import projects_window as pw
        ops = [{"index": i, "operation": "create_task", "label": f"Task number {i}", "valid": i % 7 != 0,
                "problem": "bad"} for i in range(1, 61)]
        proposal = {"proposal_id": "PROP-1", "summary": "plan " * 40, "operations": ops}
        holder: dict = {}
        orig_wait = tk.Misc.wait_window
        orig_grab = tk.Toplevel.grab_set
        tk.Misc.wait_window = lambda self_, w=None: None
        tk.Toplevel.grab_set = lambda self_: None
        try:
            dlg = pw.ProposalDialog(self.root, proposal)
        finally:
            tk.Misc.wait_window, tk.Toplevel.grab_set = orig_wait, orig_grab
        dlg.top.deiconify()
        dlg.top.update()
        self.assertLessEqual(dlg.top.winfo_height(), dlg.top.winfo_screenheight())
        self.assertTrue(self._visible(dlg.top, dlg.apply_btn), "Apply selected is reachable")
        self.assertGreater(dlg.page.body.winfo_reqheight(), dlg.page.canvas.winfo_height(), "the list scrolls")
        dlg.page.canvas.yview_moveto(1.0)
        dlg.top.update()
        # Select none / all valid and keyboard defaults
        dlg._select(False)
        self.assertEqual([i for i, v in dlg.vars if v.get()], [])
        dlg._select(True)
        valid = [o["index"] for o in ops if o["valid"]]
        self.assertEqual([i for i, v in dlg.vars if v.get()], valid, "invalid operations stay unselected")
        dlg.top.event_generate("<Return>")
        dlg.top.update()
        self.assertEqual(dlg.result, valid)

    def test_bf100_long_question_keeps_ok_and_error_visible(self) -> None:
        from aiwb.ui.action_form import ActionForm
        spec = {"title": "Decision", "step_title": "Pick one",
                "question": ("The architect proposes two storage designs for the history feature. " * 22).strip(),
                "fields": [{"need": "choice", "label": "Your decision", "kind": "choice", "optional": False,
                            "default": "", "options": [f"o{i}" for i in range(6)],
                            "option_labels": {f"o{i}": f"Option {i}: store history in format {i} with sync" for i in range(6)}},
                           {"need": "rationale", "label": "Why?", "kind": "text", "optional": True, "default": ""}]}
        f = ActionForm(self.root, spec, modal=False)
        f.top.update()
        self.assertTrue(self._visible(f.top, f.ok_btn), "OK is mapped and on screen")
        self.assertTrue(self._visible(f.top, f.cancel_btn))
        f.ok()   # nothing chosen: the error appears in a place that is on screen
        f.top.update()
        self.assertTrue(f.error_var.get())
        self.assertTrue(self._visible(f.top, f.error_label), "validation feedback is visible")
        f.choose("choice", "o2")
        self.assertEqual(f.ok()["choice"], "o2")

    def test_bf102_dispatch_form_with_25_long_inputs_fits_the_screen(self) -> None:
        from aiwb.github import artifacts as ar
        from aiwb.github.actions import WorkflowInfo
        from aiwb.github.build_center_dialogs import DispatchDialog
        form = ar.DispatchForm(True, tuple(ar.DispatchInput(f"input_{i}", "string", False, "", "Description " + "x" * 250, ())
                                           for i in range(25)))

        class Svc:
            def dispatch_form(self, token, owner, repo, workflow, *, ref):
                return form

        wf = WorkflowInfo(1, "CI", ".github/workflows/ci.yml", "active", "")
        d = DispatchDialog(self.root, svc=Svc(), owner="o", repo="r", workflow=wf, ref="main", get_token=lambda: "T",
                           known_run_ids=lambda: set(), on_result=lambda _r: None)
        self.assertTrue(pump(self.root, 5, lambda: d.form is not None))
        d.win.deiconify()
        d.win.update()
        sw, sh = d.win.winfo_screenwidth(), d.win.winfo_screenheight()
        self.assertLessEqual(d.win.winfo_width(), sw)
        self.assertLessEqual(d.win.winfo_height(), sh)
        self.assertTrue(self._visible(d.win, d.btn_run), "Run workflow is on screen")
        self.assertEqual(len(d.vars), 25)
        self.assertGreater(d.inputs_body.winfo_reqheight(), d.inputs_page.canvas.winfo_height(), "inputs scroll")
        # descriptions wrap instead of widening the form to ~2000 px
        self.assertLess(d.inputs_body.winfo_reqwidth(), 1100)
        d.close()


if __name__ == "__main__":
    unittest.main()
