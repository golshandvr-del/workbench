"""Tk window "Mobile Companion": start/stop the LAN endpoint, show a one-time pairing code, approve or deny
a phone, list paired devices, change permissions and revoke. Behaviour lives in CompanionService."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from ..ui import qr
from .server import CompanionServer
from .service import DEFAULT_PERMISSIONS, PERMISSIONS, CompanionError, CompanionService


class CompanionWindow:
    def __init__(self, parent: tk.Misc, service: CompanionService, server: CompanionServer, *,
                 clipboard: Callable[[str], None], confirm: Callable[[str, str], bool] | None = None) -> None:
        self.svc, self.server, self.clipboard = service, server, clipboard
        self.confirm = confirm or (lambda title, msg: messagebox.askyesno(title, msg, parent=self.win, default="no"))
        self.win = tk.Toplevel(parent)
        self.win.title("Mobile Companion")
        self.win.geometry("760x680")
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        top = ttk.Frame(self.win, padding=8)
        top.pack(fill="x")
        self.state_var = tk.StringVar()
        ttk.Label(top, textvariable=self.state_var).pack(side="left")
        self.toggle_btn = ttk.Button(top, command=self.toggle)
        self.toggle_btn.pack(side="right")
        ttk.Button(top, text="Pair new device…", command=self.do_pair).pack(side="right", padx=6)
        note = ("Local network only: the phone and this PC must be on the same Wi-Fi. Messages are encrypted and "
                "authenticated; GitHub tokens never leave this PC. The phone can view the project and builds, and — "
                "only if you allow it — create tasks and submit answers. Preview/Apply/Run stay on this PC.")
        ttk.Label(self.win, text=note, wraplength=720, padding=(8, 0)).pack(anchor="w")
        pf = ttk.LabelFrame(self.win, text="Pairing", padding=8)
        pf.pack(fill="x", padx=8, pady=6)
        body = ttk.Frame(pf)
        body.pack(fill="x")
        # The QR code is always black on white (also in the dark theme) so phone cameras can read it.
        self.qr_canvas = tk.Canvas(body, width=240, height=240, highlightthickness=0, background="#ffffff")
        self.qr_canvas.pack(side="left")
        side = ttk.Frame(body, padding=(12, 0))
        side.pack(side="left", fill="both", expand=True)
        ttk.Label(side, text="Scan with the phone camera or the AI Workbench app, or type this code:",
                  wraplength=420).pack(anchor="w")
        self.code_var = tk.StringVar(value="")
        ttk.Label(side, textvariable=self.code_var, font=("Consolas", 20, "bold")).pack(anchor="w", pady=(6, 6))
        self.timer_var = tk.StringVar(value="")
        ttk.Label(side, textvariable=self.timer_var).pack(anchor="w")
        self.uri = ""
        self.pair_var = tk.StringVar(value="No pairing in progress.")
        ttk.Label(pf, textvariable=self.pair_var, wraplength=700).pack(anchor="w", pady=(4, 0))
        row = ttk.Frame(pf)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="Copy link", command=self.do_copy).pack(side="left")
        self.approve_btn = ttk.Button(row, text="Approve device", command=lambda: self.do_decide(True), state="disabled")
        self.approve_btn.pack(side="left", padx=6)
        self.deny_btn = ttk.Button(row, text="Deny", command=lambda: self.do_decide(False), state="disabled")
        self.deny_btn.pack(side="left")
        df = ttk.LabelFrame(self.win, text="Paired devices", padding=8)
        df.pack(fill="both", expand=True, padx=8, pady=6)
        self.tree = ttk.Treeview(df, columns=("name", "status", "perms", "seen"), show="headings", height=6)
        for c, w in (("name", 180), ("status", 80), ("perms", 300), ("seen", 120)):
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True)
        row2 = ttk.Frame(df)
        row2.pack(fill="x", pady=(4, 0))
        self.perm_vars = {p: tk.BooleanVar(value=p in DEFAULT_PERMISSIONS) for p in PERMISSIONS}
        for p, v in self.perm_vars.items():
            ttk.Checkbutton(row2, text=p.replace("_", " "), variable=v).pack(side="left")
        self.perm_btn = ttk.Button(row2, text="Set permissions", command=self.do_permissions, state="disabled")
        self.perm_btn.pack(side="left", padx=6)
        self.revoke_btn = ttk.Button(row2, text="Revoke", command=self.do_revoke, state="disabled")
        self.revoke_btn.pack(side="left")
        self.perm_note = tk.StringVar(value="")
        ttk.Label(df, textvariable=self.perm_note, wraplength=700).pack(anchor="w")
        # BF-072: selecting a device shows ITS permissions in the boxes (they are not the next pairing's choice)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())
        # on_change is called from the network thread: never touch Tk there, the timer refreshes the UI
        self.svc.on_change = lambda: None
        self.refresh()
        self._timer = self.win.after(1500, self._tick)

    def _tick(self) -> None:
        try:
            self.refresh()
            self._timer = self.win.after(1500, self._tick)
        except tk.TclError:
            pass

    def refresh(self) -> None:
        running = self.server.running
        self.state_var.set(f"Companion endpoint: {'ON at ' + self.server.host + ':' + str(self.server.port) if running else 'off'}")
        self.toggle_btn.configure(text="Stop" if running else "Start")
        pend = self.svc.pending_requests()
        if pend:
            self.pair_var.set(f"Device '{pend[0]['device_name']}' asks to pair. Approve only if this is your phone.")
        st = "normal" if pend else "disabled"
        ps = self.svc.pairing_state()
        if ps["state"] == "active":
            m, sec = divmod(ps["seconds_left"], 60)
            self.timer_var.set("Code used - waiting for your approval." if ps.get("used")
                               else f"Valid for {m}:{sec:02d} - single use, 5 attempts.")
        elif ps["state"] == "expired":
            self.timer_var.set("Code expired. Click 'Pair new device…' for a new one.")
            self._clear_code()
        elif ps["state"] == "locked":
            self.timer_var.set("Too many wrong attempts - the code was cancelled. Create a new one.")
            self._clear_code()
        self.approve_btn.configure(state=st)
        self.deny_btn.configure(state=st)
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for d in self.svc.registry.list():
            self.tree.insert("", "end", iid=d["device_id"], values=(d["name"], d["status"], ", ".join(d["permissions"]) or "—",
                                                                    d.get("last_seen") or "never"))
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])
        self._update_device_buttons()
        skew = self.svc.last_skew   # BF-071: say it when a phone's clock is the reason it cannot connect
        if skew and self.svc.clock() - skew["at"] < 120 and not pend:
            mins = max(1, round(abs(skew["seconds"]) / 60))
            self.pair_var.set(f"A phone tried to connect but its clock is {mins} minute(s) "
                              f"{'ahead' if skew['seconds'] > 0 else 'behind'}. Set the phone and this PC to automatic time.")

    def _selected_device(self) -> dict | None:
        did = self._selected()
        return next((d for d in self.svc.registry.list() if d["device_id"] == did), None) if did else None

    def _update_device_buttons(self) -> None:
        dev = self._selected_device()
        live = bool(dev) and dev.get("status") == "active"
        self.perm_btn.configure(state="normal" if live else "disabled")
        self.revoke_btn.configure(state="normal" if live else "disabled")

    def _on_select(self) -> None:
        dev = self._selected_device()
        if dev:
            for p, v in self.perm_vars.items():
                v.set(p in dev.get("permissions", []))
            self.perm_note.set(f"{dev['name']}: {', '.join(p.replace('_', ' ') for p in dev['permissions']) or 'no permissions'}")
        self._update_device_buttons()

    def toggle(self) -> None:
        try:
            self.server.stop() if self.server.running else self.server.start()
        except OSError as exc:
            self._start_failed(exc)
        self.refresh()

    def _start_failed(self, exc: OSError) -> None:
        text = (f"Port {self.server.port} is used by another program (maybe a second AI Workbench). Close it and try "
                f"again. ({exc})") if getattr(exc, "errno", None) in (98, 10048, 48) else \
            f"Could not start the endpoint: {exc}"
        self.pair_var.set(text)
        messagebox.showerror("Mobile Companion", text, parent=self.win)

    def do_pair(self) -> str:
        if not self.server.running:
            try:
                self.server.start()
            except OSError as exc:   # BF-073: a taken port is a normal situation, not an application bug
                self._start_failed(exc)
                return ""
        uri = self.svc.start_pairing(self.server.host, self.server.port)
        self.uri = uri
        self.code_var.set(self.svc.pairing_code())
        matrix = qr.encode(uri, "M")
        module = max(2, 240 // (len(matrix) + 8))
        qr.draw(self.qr_canvas, matrix, module=module)
        self.pair_var.set(f"Scan the QR code, or in the AI Workbench app type the desktop address "
                          f"{self.server.host}:{self.server.port} and the 16-character code (valid 10 minutes).")
        self.refresh()
        return uri

    def _clear_code(self) -> None:
        if self.uri:
            self.uri = ""
            self.code_var.set("")
            self.qr_canvas.delete("qr")

    def do_copy(self) -> None:
        if self.uri:
            self.clipboard(self.uri)

    def do_decide(self, approve: bool) -> None:
        pend = self.svc.pending_requests()
        if not pend:
            return
        perms = tuple(p for p, v in self.perm_vars.items() if v.get()) or DEFAULT_PERMISSIONS
        try:
            self.svc.decide(pend[0]["pairing_id"], approve, perms)
        except CompanionError as exc:   # BF-069: a request that came too late is refused with a reason
            self.pair_var.set(str(exc))
            self.refresh()
            return
        self.pair_var.set("Device approved." if approve else "Pairing denied.")
        self._reset_permission_boxes()   # BF-072: the choice made for this phone is not carried to the next one
        self.refresh()

    def _selected(self) -> str:
        sel = self.tree.selection()
        return sel[0] if sel else ""

    def _reset_permission_boxes(self) -> None:
        for p, v in self.perm_vars.items():
            v.set(p in DEFAULT_PERMISSIONS)

    def do_permissions(self) -> None:
        dev = self._selected_device()
        if not dev or dev.get("status") != "active":
            return
        new = [p for p, v in self.perm_vars.items() if v.get()]
        old = list(dev.get("permissions", []))
        self.svc.registry.set_permissions(dev["device_id"], new)
        removed = [p for p in old if p not in new]
        added = [p for p in new if p not in old]
        txt = ", ".join(p.replace("_", " ") for p in new) or "no permissions"
        note = f"{dev['name']}: {txt}"
        if removed:
            note += f" (removed: {', '.join(p.replace('_', ' ') for p in removed)})"
        if added:
            note += f" (added: {', '.join(p.replace('_', ' ') for p in added)})"
        self.perm_note.set(note)
        self.refresh()

    def do_revoke(self) -> None:
        did = self._selected()
        if did and self.confirm("Revoke device", "Revoke this device? It will be refused immediately."):
            self.svc.registry.revoke(did)
            self.refresh()

    def close(self) -> None:
        try:
            self.win.after_cancel(self._timer)
        except (tk.TclError, ValueError):
            pass
        self.svc.on_change = lambda: None
        self.win.destroy()
