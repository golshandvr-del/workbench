"""Tk window "Mobile Companion": start/stop the LAN endpoint, show a one-time pairing code, approve or deny
a phone, list paired devices, change permissions and revoke. Behaviour lives in CompanionService."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from .server import CompanionServer
from .service import DEFAULT_PERMISSIONS, PERMISSIONS, CompanionService


class CompanionWindow:
    def __init__(self, parent: tk.Misc, service: CompanionService, server: CompanionServer, *,
                 clipboard: Callable[[str], None], confirm: Callable[[str, str], bool] | None = None) -> None:
        self.svc, self.server, self.clipboard = service, server, clipboard
        self.confirm = confirm or (lambda title, msg: messagebox.askyesno(title, msg, parent=self.win, default="no"))
        self.win = tk.Toplevel(parent)
        self.win.title("Mobile Companion")
        self.win.geometry("760x520")
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
        self.code = tk.Text(pf, height=2, wrap="char")
        self.code.pack(fill="x")
        self.pair_var = tk.StringVar(value="No pairing in progress.")
        ttk.Label(pf, textvariable=self.pair_var, wraplength=700).pack(anchor="w", pady=(4, 0))
        row = ttk.Frame(pf)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="Copy code", command=self.do_copy).pack(side="left")
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
        ttk.Button(row2, text="Set permissions", command=self.do_permissions).pack(side="left", padx=6)
        ttk.Button(row2, text="Revoke", command=self.do_revoke).pack(side="left")
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
        self.approve_btn.configure(state=st)
        self.deny_btn.configure(state=st)
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for d in self.svc.registry.list():
            self.tree.insert("", "end", iid=d["device_id"], values=(d["name"], d["status"], ", ".join(d["permissions"]) or "—",
                                                                    d.get("last_seen") or "never"))
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])

    def toggle(self) -> None:
        try:
            self.server.stop() if self.server.running else self.server.start()
        except OSError as exc:
            messagebox.showerror("Mobile Companion", f"Could not start the endpoint: {exc}", parent=self.win)
        self.refresh()

    def do_pair(self) -> str:
        if not self.server.running:
            self.server.start()
        uri = self.svc.start_pairing(self.server.host, self.server.port)
        self.code.delete("1.0", "end")
        self.code.insert("1.0", uri)
        self.pair_var.set("Enter this one-time code in the AI Workbench app on your phone (valid 10 minutes).")
        self.refresh()
        return uri

    def do_copy(self) -> None:
        self.clipboard(self.code.get("1.0", "end-1c"))

    def do_decide(self, approve: bool) -> None:
        pend = self.svc.pending_requests()
        if not pend:
            return
        perms = tuple(p for p, v in self.perm_vars.items() if v.get()) or DEFAULT_PERMISSIONS
        self.svc.decide(pend[0]["pairing_id"], approve, perms)
        self.pair_var.set("Device approved." if approve else "Pairing denied.")
        self.refresh()

    def _selected(self) -> str:
        sel = self.tree.selection()
        return sel[0] if sel else ""

    def do_permissions(self) -> None:
        did = self._selected()
        if did:
            self.svc.registry.set_permissions(did, [p for p, v in self.perm_vars.items() if v.get()])
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
