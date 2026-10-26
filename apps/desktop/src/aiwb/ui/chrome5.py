"""Window chrome of the 5.x look (roadmap 5.1.0): toolbar, icon rail, live status bar.

Matches the owner's reference image: a flat toolbar (New Project ▾ · Open · Save · Run), a 64 px icon rail
(Home · Projects · Agents · History · Settings) with a sliding accent marker and the user's avatar, and a status
bar ("● 5 agents running · Milestone V0.1.0" … "Autosaved").

Built from plain Tk frames/labels so every colour comes from :mod:`tokens5` (no theme engine in the way), with
anti-aliased icons from :mod:`assets`. The structure (which commands, which destinations) is read from
:mod:`structure5`, the same tables ``docs/UI_TREE.md`` is checked against. Nothing here touches project data.
"""
from __future__ import annotations

import getpass
import tkinter as tk
from typing import Any, Callable

from . import structure5
from .assets import Assets
from .tokens5 import GEOMETRY, MOTION, font5, palette5, theme5


def ease_out(t: float) -> float:
    """Cubic ease-out (fast start, soft landing) on 0..1."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return 1 - (1 - t) ** 3


def _bind_all(widget: tk.Misc, seq: str, fn: Callable[[Any], Any]) -> None:
    widget.bind(seq, fn, add="+")
    for ch in widget.winfo_children():
        _bind_all(ch, seq, fn)


class Pad(tk.Frame):
    """A flat clickable surface (icon + text) with hover / pressed / selected colours from the palette."""

    def __init__(self, master: tk.Misc, assets: Assets, *, icon: str, text: str, command: Callable[[], Any],
                 vertical: bool = False, chevron: bool = False, icon_size: int = 16, framed: bool = True,
                 name: str = "") -> None:
        super().__init__(master, highlightthickness=1 if framed else 0, bd=0, cursor="hand2")
        self._aiwb_keep_colours = True
        self.assets, self.icon_name, self.icon_size = assets, icon, icon_size
        self.command, self.vertical, self.framed, self.key = command, vertical, framed, name or icon
        self.hover = self.selected = self.pressed = False
        sc = assets.scale
        self.icon_lbl = tk.Label(self, bd=0)
        self.text_lbl = tk.Label(self, text=text, bd=0, font=font5("caption" if vertical else "small", sc))
        self.chev_lbl = tk.Label(self, bd=0) if chevron else None
        for w in (self.icon_lbl, self.text_lbl) + ((self.chev_lbl,) if self.chev_lbl else ()):
            w._aiwb_keep_colours = True  # type: ignore[attr-defined]
        if vertical:
            self.icon_lbl.pack(side="top", pady=(round(9 * sc), round(3 * sc)))
            self.text_lbl.pack(side="top", pady=(0, round(8 * sc)))
        else:
            self.icon_lbl.pack(side="left", padx=(round(10 * sc), round(6 * sc)), pady=round(5 * sc))
            self.text_lbl.pack(side="left", padx=(0, round(10 * sc) if not chevron else round(4 * sc)))
            if self.chev_lbl is not None:
                self.chev_lbl.pack(side="left", padx=(0, round(8 * sc)))
        _bind_all(self, "<Enter>", lambda _e: self._set(hover=True))
        _bind_all(self, "<Leave>", lambda _e: self._leave())
        _bind_all(self, "<ButtonPress-1>", lambda _e: self._set(pressed=True))
        _bind_all(self, "<ButtonRelease-1>", self._release)
        self.recolor()

    @property
    def text(self) -> str:
        return str(self.text_lbl.cget("text"))

    def _leave(self) -> None:
        # <Leave> also fires when the pointer moves onto a child label; only reset when it really left
        try:
            x, y = self.winfo_pointerxy()
            inside = self.winfo_containing(x, y)
        except (tk.TclError, KeyError):
            inside = None
        w = inside
        while w is not None and w is not self:
            w = getattr(w, "master", None)
        if w is None:
            self._set(hover=False, pressed=False)

    def _release(self, _e: Any) -> None:
        was = self.pressed
        self._set(pressed=False)
        if was:
            self.invoke()

    def invoke(self) -> Any:
        return self.command()

    def _set(self, **kw: bool) -> None:
        for k, v in kw.items():
            setattr(self, k, v)
        self.recolor()

    def recolor(self) -> None:
        p = palette5(self.assets.theme)
        base = p["panel"] if not self.framed else p["raised"]
        bg = p["raised_hi"] if (self.hover or self.pressed) else base
        if self.selected:
            bg = p["raised"] if not self.framed else p["selection"]
        fg_role = "active_hi" if self.selected else ("text" if self.hover or self.framed else "text_dim")
        if self.vertical and not self.selected and not self.hover:
            fg_role = "text_dim"
        fg = p[fg_role]
        self.configure(background=bg, highlightbackground=p["line"], highlightcolor=p["line"])
        self.icon_lbl.configure(background=bg, image=self.assets.icon(self.icon_name, self.icon_size, color=fg))
        self.text_lbl.configure(background=bg, foreground=fg if self.selected else p["text" if not self.vertical
                                                                                       else fg_role])
        if self.chev_lbl is not None:
            self.chev_lbl.configure(background=bg, image=self.assets.icon("chevron_down", 12, color=p["text_dim"]))


NO_PROJECT = "No project open"


class Toolbar(tk.Frame):
    """New Project ▾ · Open · Save · Run (from :data:`structure5.TOOLBAR`) and the project switcher "<name> ▾"."""

    def __init__(self, master: tk.Misc, assets: Assets, commands: dict[str, Callable[[], Any]]) -> None:
        super().__init__(master, bd=0, highlightthickness=0)
        self._aiwb_keep_colours = True
        self.assets, self.commands = assets, commands
        sc = assets.scale
        self.configure(height=round(GEOMETRY["toolbar_h"] * sc))
        self.pack_propagate(False)
        self.buttons: dict[str, Pad] = {}
        self.menus: dict[str, tk.Menu] = {}
        for tid, label, icon, kids in structure5.TOOLBAR:
            if kids:
                menu = tk.Menu(self, tearoff=False)
                for cid, clabel in kids:
                    menu.add_command(label=clabel, command=lambda c=cid: self._run(c))
                self.menus[tid] = menu
                cmd: Callable[[], Any] = lambda t=tid: self.post_menu(t)
            else:
                cmd = lambda t=tid: self._run(t)
            b = Pad(self, assets, icon=icon, text=label, command=cmd, chevron=bool(kids), name=tid)
            b.pack(side="left", padx=(round(8 * sc), 0), pady=round(6 * sc))
            self.buttons[tid] = b
        # 5.13.0 (B3/B4): the open project's name is the project switcher "<name> ▾" (Projects left the rail)
        self.project_var = tk.StringVar(value="")
        self.project_btn = Pad(self, assets, icon="projects", text=NO_PROJECT, command=self.post_project_menu,
                               chevron=True, name="project")
        self.project_btn.pack(side="right", padx=(0, round(10 * sc)), pady=round(6 * sc))
        self.project_lbl = self.project_btn.text_lbl  # 5.1.0 name, kept for callers
        self.project_menu = tk.Menu(self, tearoff=False)
        self.menus["project"] = self.project_menu
        self.recolor()

    def set_project(self, name: str) -> None:
        """Show the open project's name on the switcher (``""`` = no project)."""
        name = (name or "").strip()
        self.project_var.set(name)
        short = name if len(name) <= 28 else name[:27] + "…"
        self.project_btn.text_lbl.configure(text=short or NO_PROJECT)

    def fill_project_menu(self) -> list[str]:
        """Recent projects (``commands["project_items"]`` → ``[(label, callable, is_open)]``), then PROJECT_MENU."""
        m = self.project_menu
        m.delete(0, "end")
        rows = []
        items = self.commands.get("project_items")
        for label, fn, is_open in (items() if items is not None else [])[:8]:
            m.add_command(label=("● " if is_open else "    ") + label, command=fn)
            rows.append(label)
        if rows:
            m.add_separator()
        for cid, label in structure5.PROJECT_MENU:
            m.add_command(label=label, command=lambda c=cid: self._run(c))
            rows.append(label)
        return rows

    def post_project_menu(self) -> None:
        self.fill_project_menu()
        self.post_menu("project")

    def _run(self, cid: str) -> Any:
        fn = self.commands.get(cid)
        return fn() if fn is not None else None

    def post_menu(self, tid: str) -> None:
        b = self.buttons[tid] if tid in self.buttons else self.project_btn
        try:
            self.menus[tid].tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height() + 2)
        finally:
            self.menus[tid].grab_release()

    def recolor(self) -> None:
        p = palette5(self.assets.theme)
        self.configure(background=p["panel"])
        self.project_btn.recolor()
        for m in self.menus.values():
            m.configure(background=p["menu"], foreground=p["text"], activebackground=p["active"],
                        activeforeground=p["active_text"], relief="flat", bd=1)
        for b in self.buttons.values():
            b.recolor()


class IconRail(tk.Frame):
    """The destinations of :data:`structure5.RAIL` (5.13.0: four), a sliding selection marker and the avatar."""

    def __init__(self, master: tk.Misc, assets: Assets, on_select: Callable[[str], Any]) -> None:
        super().__init__(master, bd=0, highlightthickness=0)
        self._aiwb_keep_colours = True
        self.assets, self.on_select = assets, on_select
        sc = assets.scale
        self.width_px = round(GEOMETRY["rail_w"] * sc)
        self.configure(width=self.width_px)
        self.pack_propagate(False)
        self.items: dict[str, Pad] = {}
        self.current = ""
        for key, label, icon, _sections in structure5.RAIL:
            b = Pad(self, assets, icon=icon, text=label, command=lambda k=key: self.on_select(k), vertical=True,
                    framed=False, icon_size=20, name=key)
            if key == "settings":
                continue_pack = False
            else:
                continue_pack = True
            if continue_pack:
                b.pack(side="top", fill="x", padx=round(4 * sc), pady=(round(4 * sc), 0))
            self.items[key] = b
        self.user = getpass.getuser() if hasattr(getpass, "getuser") else "You"
        self.user_box = tk.Frame(self, bd=0)
        self.avatar = tk.Label(self.user_box, bd=0)
        self.user_lbl = tk.Label(self.user_box, text=self._short(self.user), bd=0, font=font5("caption", sc))
        self.avatar.pack(side="top", pady=(round(6 * sc), round(2 * sc)))
        self.user_lbl.pack(side="top", pady=(0, round(8 * sc)))
        for w in (self.user_box, self.avatar, self.user_lbl):
            w._aiwb_keep_colours = True  # type: ignore[attr-defined]
        self.user_box.pack(side="bottom", fill="x")
        self.items["settings"].pack(side="top", fill="x", padx=round(4 * sc), pady=(round(4 * sc), 0))
        self.marker = tk.Frame(self, bd=0, width=max(2, round(3 * sc)))
        self.marker._aiwb_keep_colours = True  # type: ignore[attr-defined]
        self._anim: str | None = None
        self.marker_y = 0.0
        self.motion: Any = None  # set by AppShell (5.3.0)
        self.recolor()

    @staticmethod
    def _short(name: str) -> str:
        name = (name or "You").strip() or "You"
        return name if len(name) <= 9 else name[:8] + "…"

    def select(self, key: str, animate: bool = True) -> None:
        if key not in self.items:
            return
        old = self.current
        self.current = key
        for k, b in self.items.items():
            b.selected = k == key
            b.recolor()
        self.update_idletasks()
        target = self.items[key]
        y1, h = float(target.winfo_y()), max(1, target.winfo_height())
        if not old or not animate or not self.winfo_ismapped():
            self._place_marker(y1, h)
            return
        y0 = self.marker_y
        self._slide(y0, y1, h, MOTION["menu_ms"])

    def _place_marker(self, y: float, h: int) -> None:
        self.marker_y = y
        inset = round(h * 0.22)
        self.marker.place(x=0, y=round(y) + inset, height=max(4, h - 2 * inset))
        self.marker.lift()

    def _slide(self, y0: float, y1: float, h: int, ms: int) -> None:
        mo = getattr(self, "motion", None)
        if mo is not None:  # 5.3.0: the shared animation clock (Reduce motion = jump)
            mo.tween("rail:marker", y0, y1, ms, lambda y: self._place_marker(y, h), ease="in_out",
                     alive=self.winfo_exists)
            return
        if self._anim is not None:
            try:
                self.after_cancel(self._anim)
            except tk.TclError:
                pass
        steps = max(1, round(ms / (1000 / MOTION["fps"])))

        def step(i: int) -> None:
            self._place_marker(y0 + (y1 - y0) * ease_out(i / steps), h)
            self._anim = self.after(16, step, i + 1) if i < steps else None

        step(1)

    def recolor(self) -> None:
        p = palette5(self.assets.theme)
        self.configure(background=p["panel"])
        self.user_box.configure(background=p["panel"])
        self.avatar.configure(background=p["panel"], image=self.assets.sprite("avatar"))
        self.user_lbl.configure(background=p["panel"], foreground=p["text_dim"])
        self.marker.configure(background=p["active"])
        for b in self.items.values():
            b.recolor()


class StatusBar(tk.Frame):
    """``● N agents running · Milestone …`` · last message … ``Autosaved`` · version."""

    def __init__(self, master: tk.Misc, assets: Assets, *, message: tk.StringVar, version: str) -> None:
        super().__init__(master, bd=0, highlightthickness=0)
        self._aiwb_keep_colours = True
        self.assets = assets
        sc = assets.scale
        self.configure(height=round(GEOMETRY["status_h"] * sc))
        self.pack_propagate(False)
        self.live = False
        self.dot = tk.Label(self, bd=0)
        self.facts_var = tk.StringVar(value="No project open")
        self.facts = tk.Label(self, textvariable=self.facts_var, bd=0, font=font5("small", sc))
        self.sep = tk.Label(self, text="·", bd=0, font=font5("small", sc))
        self.message = tk.Label(self, textvariable=message, bd=0, font=font5("small", sc), anchor="w")
        self.version = tk.Label(self, text=f"v{version}", bd=0, font=font5("mono_small", sc))
        self.saved_var = tk.StringVar(value="")
        self.saved_icon = tk.Label(self, bd=0)
        self.saved = tk.Label(self, textvariable=self.saved_var, bd=0, font=font5("small", sc))
        self.slot = tk.Frame(self, bd=0)  # the application's progress bar goes here
        pad = round(12 * sc)
        self.dot.pack(side="left", padx=(pad, round(4 * sc)))
        self.facts.pack(side="left")
        self.sep.pack(side="left", padx=round(8 * sc))
        self.version.pack(side="right", padx=(round(10 * sc), pad))
        self.saved.pack(side="right")
        self.saved_icon.pack(side="right", padx=(0, round(4 * sc)))
        self.slot.pack(side="right", padx=round(8 * sc))
        self.message.pack(side="left", fill="x", expand=True)
        for w in (self.dot, self.facts, self.sep, self.message, self.version, self.saved, self.saved_icon, self.slot):
            w._aiwb_keep_colours = True  # type: ignore[attr-defined]
        self.recolor()

    def show_facts(self, facts: dict[str, Any]) -> None:
        self.facts_var.set(str(facts.get("text", "")))
        if bool(facts.get("live")) != self.live:
            self.live = bool(facts.get("live"))
            self.recolor()

    def show_saved(self, text: str) -> None:
        self.saved_var.set(text)
        self.recolor()

    def recolor(self) -> None:
        p = palette5(self.assets.theme)
        bg = p["panel"]
        self.configure(background=bg)
        self.slot.configure(background=bg)
        self.dot.configure(background=bg, image=self.assets.sprite("dot", role="go" if self.live else "text_faint"))
        for w, role in ((self.facts, "text_dim"), (self.sep, "text_faint"), (self.message, "text_faint"),
                        (self.version, "text_faint"), (self.saved, "text_dim")):
            w.configure(background=bg, foreground=p[role])
        icon = "check" if self.saved_var.get() else ""
        if icon:
            self.saved_icon.configure(background=bg, image=self.assets.icon(icon, 12, color=p["text_dim"]))
        else:
            self.saved_icon.configure(background=bg, image="")


def chrome_theme(pref_theme: str) -> str:
    """5.x chrome theme for the application preference (``light`` → Daylight, ``dark`` → Midnight)."""
    return theme5(pref_theme)
