"""The App Map (roadmap 5.5.0): every place and every command of the running application, as one tree.

``docs/UI_TREE.md`` is the *design* tree (rail destinations, sections, menus — :mod:`structure5`). The App Map is the
*live* tree: :func:`extract` walks the real widgets of a running :class:`WorkbenchApp` and returns

    app → area (Toolbar · Rail · Status bar) → page → section / tab → button / menu → menu item / option

``docs/UI_MAP.md`` holds the same tree as Markdown (:func:`to_markdown` / :func:`parse_markdown`) and
``docs/design/ui_map.svg`` draws it (:func:`to_svg`). Tests keep the three equal, so changing any tab, section,
button or menu without updating the map turns CI red — the contract the owner asked for on 2026-10-21.

:func:`audit` applies the balance rules (no empty page, no overloaded section or menu, no command with two homes,
destinations of similar weight); the rules and their numbers live in :data:`RULES`.

Section detection (pure widget conventions, no per-page code):

* a ``TLabelframe`` with text, a ``TNotebook`` tab, or a frame whose first child is a title label
  (``SectionTitle`` / ``CardTitle`` style) is a section named by that text;
* a widget with ``_aiwb_section = "Name"`` is a section of that name (``""`` = a header, not a section) and may add
  ``_aiwb_menu = (title, labels)`` for a canvas right-click menu;
* a button with ``_aiwb_link = page_key`` is a *link* to another page, not a command of its own.
"""
from __future__ import annotations

import html
import re
from typing import Any, Iterable

KINDS = ("app", "area", "page", "section", "tab", "link", "button", "menu", "item", "option")
CONTROL_KINDS = ("button", "menu", "option", "link")
COMMAND_KINDS = ("button", "item", "option")

RULES = {
    "page_min_commands": 3,       # a page with fewer own commands is "almost empty"
    "section_max_controls": 7,    # Miller: a section shows at most 7 direct controls
    "page_max_visible": 10,       # a page shows at most 10 buttons/menus/options at once (3.3.0 rule)
    "menu_max_items": 12,         # a More menu holds at most 12 commands
    "weight_ratio_max": 4.0,      # heaviest rail destination ≤ 4 × the lightest (commands incl. their tools)
}
# Labels that may appear in several places because they mean "this place's" variant of a generic verb.
GENERIC = {"More", "Refresh", "Clear", "Search", "Browse…", "Copy prompt"}

TITLE_STYLES = ("SectionTitle", "CardTitle")


def node(label: str, kind: str, children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(kind)
    return {"label": label, "kind": kind, "children": children or []}


# -- extraction from live widgets --------------------------------------------------------------------
def _cls(w: Any) -> str:
    try:
        return str(w.winfo_class())
    except Exception:  # noqa: BLE001
        return ""


def _mapped(w: Any) -> bool:
    try:
        return bool(w.winfo_manager())
    except Exception:  # noqa: BLE001
        return False


def _text(w: Any) -> str:
    try:
        return str(w.cget("text")).strip()
    except Exception:  # noqa: BLE001
        return ""


def _style(w: Any) -> str:
    try:
        return str(w.cget("style"))
    except Exception:  # noqa: BLE001
        return ""


def _ordered(w: Any) -> list[Any]:
    """Children in reading order: rows by vertical centre (12 px tolerance — fonts differ per machine), then x."""
    kids = list(w.winfo_children())
    try:
        pos = [(c.winfo_rooty() + c.winfo_height() / 2, c.winfo_rootx(), i) for i, c in enumerate(kids)]
    except Exception:  # noqa: BLE001
        return kids
    try:  # a frame whose children are all packed side by side is ONE row, whatever the heights (Windows fonts)
        packed = w.pack_slaves()
        sides = {str(c.pack_info().get("side")) for c in packed}
        if packed and len(sides) == 1 and sides <= {"left", "right"}:
            # pack order, not geometry: squeezed widgets (narrow window, Windows fonts) keep their place
            row = list(packed) if sides == {"left"} else list(reversed(packed))
            rest = [kids[i] for _y, _x, i in sorted(pos) if kids[i] not in row]
            return row + rest
    except Exception:  # noqa: BLE001
        pass
    rows: list[list[tuple[float, int, int]]] = []
    for p in sorted(pos):
        if rows and abs(p[0] - rows[-1][0][0]) <= 12:
            rows[-1].append(p)
        else:
            rows.append([p])
    return [kids[i] for row in rows for _y, _x, i in sorted(row, key=lambda q: (q[1], q[2]))]


def menu_items(menu: Any) -> list[str]:
    """Command labels of a Tk menu (group headers — disabled ALL-CAPS rows — and separators skipped)."""
    out: list[str] = []
    try:
        end = menu.index("end")
    except Exception:  # noqa: BLE001
        return out
    if end is None:
        return out
    for i in range(int(end) + 1):
        if menu.type(i) not in ("command", "checkbutton", "radiobutton", "cascade"):
            continue
        label = str(menu.entrycget(i, "label"))
        if str(menu.entrycget(i, "state")) == "disabled" and label.isupper():
            continue
        out.append(label)
    return out


def _is_nav(w: Any) -> bool:
    st = _style(w)
    return "Nav." in st or "Rail." in st or "NavActive" in st or len(_text(w)) <= 1


def _title_of(frame: Any) -> str | None:
    """Section name of a card-like frame: its first child is a title label."""
    kids = [k for k in _ordered(frame) if _mapped(k)]
    if kids and _cls(kids[0]) == "TLabel" and any(t in _style(kids[0]) for t in TITLE_STYLES):
        return _text(kids[0]) or None
    return None


def walk(w: Any, into: list[dict[str, Any]]) -> None:
    """Append the map nodes found under widget ``w`` (not ``w`` itself) to ``into``."""
    import tkinter as tk
    for ch in _ordered(w):
        if isinstance(ch, tk.Toplevel) or not _mapped(ch):
            continue
        _visit(ch, into)


def _visit(ch: Any, into: list[dict[str, Any]]) -> None:
    cls = _cls(ch)
    explicit = getattr(ch, "_aiwb_section", None)
    if explicit is not None:
        if explicit == "":
            return  # a header: shown, but not a section of its own
        sec = node(explicit, "section")
        extra = getattr(ch, "_aiwb_menu", None)
        if extra:
            sec["children"].append(node(extra[0], "menu", [node(x, "item") for x in extra[1]]))
        walk(ch, sec["children"])
        into.append(sec)
        return
    if cls in ("TButton", "Button"):
        if _is_nav(ch):
            return
        link = getattr(ch, "_aiwb_link", None)
        into.append(node(_text(ch), "link" if link else "button"))
        return
    if cls in ("TMenubutton", "Menubutton"):
        items: list[str] = []
        try:
            items = menu_items(ch.nametowidget(ch.cget("menu")))
        except Exception:  # noqa: BLE001
            pass
        into.append(node(_text(ch), "menu", [node(x, "item") for x in items]))
        return
    if cls in ("TCheckbutton", "TRadiobutton", "Checkbutton", "Radiobutton"):
        if _text(ch):
            into.append(node(_text(ch), "option"))
        return
    if cls in ("TLabelframe", "Labelframe") and _text(ch):
        sec = node(_text(ch), "section")
        walk(ch, sec["children"])
        into.append(sec)
        return
    if cls == "TNotebook":
        for tab in ch.tabs():
            t = node(str(ch.tab(tab, "text")), "tab")
            walk(ch.nametowidget(tab), t["children"])
            into.append(t)
        return
    if cls in ("TFrame", "Frame"):
        title = _title_of(ch)
        if title:
            sec = node(title, "section")
            walk(ch, sec["children"])
            into.append(sec)
            return
    walk(ch, into)


def extract(app: Any) -> dict[str, Any]:
    """The whole live map of a running application (Advanced mode shows every page).

    Pages are visited in rail order; every visit only *shows* a page, it never writes project state.
    """
    from . import structure5
    from .shell import RAIL_PAGE
    sh = app.shell
    root = node("AI Workbench", "app")
    tb = node("Toolbar", "area")
    for _id, label, _icon, kids in structure5.TOOLBAR:
        tb["children"].append(node(label, "menu", [node(c[1], "item") for c in kids]) if kids
                              else node(label, "button"))
    root["children"].append(tb)
    rail = node("Rail", "area")
    before = sh.current
    for key, label, _icon, _sections in structure5.RAIL:
        page = node(label, "page")
        pkey = RAIL_PAGE[key]
        sh.show(pkey)
        app.root.update_idletasks()
        app.root.update()
        if pkey == "workbench" and getattr(app, "workspace_window", None) is not None:
            page["children"] = _workbench(app)
        else:
            walk(sh.pages[pkey], page["children"])
        homed = [(k, lab) for k, lab in structure5.TOOLS if structure5.TOOL_HOME[k] == key]
        if homed:  # the expert pages of this destination, each mapped as a sub-page under its "Tools" section
            tools = next((c for c in page["children"] if c["label"] == "Tools" and c["kind"] == "section"), None)
            if tools is None:
                tools = node("Tools", "section")
                page["children"].append(tools)
            tools["children"] = [c for c in tools["children"] if c["kind"] != "link"]  # each link becomes its page
            for tkey, tlabel in homed:
                sub = node(tlabel, "page")
                sh.show(tkey)
                app.root.update_idletasks()
                app.root.update()
                walk(sh.pages[tkey], sub["children"])
                tools["children"].append(sub)
        rail["children"].append(page)
    sh.show(before)
    root["children"].append(rail)
    root["children"].append(node("Status bar", "area", [node(s, "item") for s in structure5.STATUS_BAR]))
    return root


def _workbench(app: Any) -> list[dict[str, Any]]:
    """The Project Workbench: its guide bar, then one tab per sidebar section (each visited once)."""
    ws = app.workspace_window
    out: list[dict[str, Any]] = []
    guide = node("Next step", "section")
    walk(ws.next_frame, guide["children"])
    out.append(guide)
    current = ws.wc.section
    from ..workspace.controller import SECTIONS
    for key in SECTIONS:
        ws.show(key)
        app.root.update_idletasks()
        t = node(ws.wc.section_label(key), "tab")
        holder = ws.center
        walk(holder, t["children"])
        out.append(t)
    ws.show(current)
    card = getattr(app, "tool_cards", {}).get("projects")
    if card is not None and _mapped(card):
        _visit(card, out)
    return out


# -- Markdown -------------------------------------------------------------------------------------------
LINE = re.compile(r"^(?P<pad>(?:  )*)- (?P<label>.*?) \[(?P<kind>[a-z]+)\]$")


def to_markdown(tree: dict[str, Any]) -> str:
    """Two spaces per level, ``- Label [kind]`` per node (the root itself is not written)."""
    lines: list[str] = []

    def rec(n: dict[str, Any], d: int) -> None:
        for c in n["children"]:
            lines.append(f"{'  ' * d}- {c['label']} [{c['kind']}]")
            rec(c, d + 1)
    rec(tree, 0)
    return "\n".join(lines) + "\n"


def parse_markdown(text: str, label: str = "AI Workbench") -> dict[str, Any]:
    """Inverse of :func:`to_markdown`; only the lines between ``<!-- ui-map:start -->`` / ``end`` if present."""
    if "<!-- ui-map:start -->" in text:
        text = text.split("<!-- ui-map:start -->", 1)[1].split("<!-- ui-map:end -->", 1)[0]
    root = node(label, "app")
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = LINE.match(raw)
        if not m:
            raise ValueError(f"bad map line: {raw!r}")
        level = len(m["pad"]) // 2
        while stack[-1][0] >= level:
            stack.pop()
        if level != stack[-1][0] + 1:
            raise ValueError(f"map skips a level: {raw!r}")
        n = node(m["label"], m["kind"])
        stack[-1][1]["children"].append(n)
        stack.append((level, n))
    return root


# -- counting and audit -----------------------------------------------------------------------------------
def iter_nodes(n: dict[str, Any], path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], dict[str, Any]]]:
    for c in n["children"]:
        p = path + (c["label"],)
        yield p, c
        yield from iter_nodes(c, p)


def commands(n: dict[str, Any], *, into_pages: bool = False) -> int:
    """Commands under ``n``: buttons, menu items, options (sub-pages only when ``into_pages``)."""
    total = 0
    for c in n["children"]:
        if c["kind"] == "page" and not into_pages:
            continue
        total += 1 if c["kind"] in COMMAND_KINDS else 0
        total += commands(c, into_pages=into_pages)
    return total


def visible_controls(n: dict[str, Any]) -> int:
    """Controls drawn at once on a page: everything but menu items, notebook tabs count one at a time (max)."""
    own = 0
    tab_max = 0
    for c in n["children"]:
        if c["kind"] == "page":
            continue
        if c["kind"] == "tab":
            tab_max = max(tab_max, visible_controls(c))
            continue
        own += 1 if c["kind"] in CONTROL_KINDS else 0
        if c["kind"] not in ("menu",):
            own += visible_controls(c)
    return own + tab_max


def pages(tree: dict[str, Any]) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    return [(p, n) for p, n in iter_nodes(tree) if n["kind"] == "page"]


def stats(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per page: path, sections, tabs, own commands, visible controls, links."""
    rows = []
    for path, pg in pages(tree):
        rows.append({"page": " › ".join(path[1:]), "sections": sum(1 for _p, n in iter_nodes(pg) if n["kind"] == "section"),
                     "tabs": sum(1 for _p, n in iter_nodes(pg) if n["kind"] == "tab"),
                     "commands": commands(pg), "visible": visible_controls(pg),
                     "links": sum(1 for _p, n in iter_nodes(pg) if n["kind"] == "link")})
    return rows


def audit(tree: dict[str, Any], rules: dict[str, Any] | None = None) -> list[str]:
    """Every balance-rule break of the map (empty list = balanced)."""
    r = {**RULES, **(rules or {})}
    out: list[str] = []
    for path, pg in pages(tree):
        name = " › ".join(path[1:])
        own = commands(pg)
        if own < r["page_min_commands"]:
            out.append(f"{name}: only {own} command(s) — almost empty (min {r['page_min_commands']})")
        vis = visible_controls(pg)
        if vis > r["page_max_visible"]:
            out.append(f"{name}: {vis} controls at once (max {r['page_max_visible']})")
    for path, n in iter_nodes(tree):
        if n["kind"] in ("section", "tab", "page"):
            direct = [c for c in n["children"] if c["kind"] in CONTROL_KINDS]
            if len(direct) > r["section_max_controls"]:
                out.append(f"{' › '.join(path[1:])}: {len(direct)} direct controls (max {r['section_max_controls']})")
        if n["kind"] == "menu":
            items = [c for c in n["children"] if c["kind"] == "item"]
            if len(items) > r["menu_max_items"]:
                out.append(f"{' › '.join(path[1:])}: menu of {len(items)} items (max {r['menu_max_items']})")
        if n["kind"] in KINDS and n["children"]:
            labels = [c["label"] for c in n["children"]]
            dup = sorted({x for x in labels if labels.count(x) > 1 and x not in GENERIC})
            if dup:
                out.append(f"{' › '.join(path[1:]) or '/'}: duplicate sibling labels {dup}")
    out += [f"command with two homes: {x}" for x in two_homes(tree)]
    rail = next((c for c in tree["children"] if c["label"] == "Rail"), None)
    if rail is not None and rail["children"]:
        weights = {pg["label"]: commands(pg, into_pages=True) for pg in rail["children"]}
        lo, hi = min(weights.values()), max(weights.values())
        if lo == 0 or hi / lo > r["weight_ratio_max"]:
            out.append(f"rail destinations unbalanced: {weights} (max ratio {r['weight_ratio_max']})")
    return out


def two_homes(tree: dict[str, Any]) -> list[str]:
    """Command labels found on more than one page (generic verbs excepted). The Toolbar counts as a home."""
    homes: dict[str, set[str]] = {}

    def rec(n: dict[str, Any], owner: str) -> None:
        for c in n["children"]:
            o = c["label"] if c["kind"] in ("page", "area") else owner
            if c["kind"] in COMMAND_KINDS and c["label"] not in GENERIC:
                homes.setdefault(_norm(c["label"]), set()).add(owner)
            rec(c, o)
    rec(tree, "")
    return sorted(f"{k} ({', '.join(sorted(v))})" for k, v in homes.items() if len(v) > 1)


def _norm(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", label.lower().replace("+", "")).strip()


# -- drawing (SVG for the docs; the same layout feeds the in-app viewer) -----------------------------------
KIND_ROLE = {"app": "source", "area": "text_dim", "page": "active", "section": "go", "tab": "version",
             "link": "active_hi", "button": "text", "menu": "text", "item": "text_faint", "option": "text_dim"}


def layout(tree: dict[str, Any], *, col_w: int = 210, row_h: int = 22, max_depth: int = 99) -> dict[str, Any]:
    """Left-to-right tidy tree: one column per depth, one row per leaf; parents centred on their children."""
    boxes: list[dict[str, Any]] = []
    edges: list[tuple[int, int]] = []
    row = [0]

    def rec(n: dict[str, Any], d: int) -> int:
        kids = n["children"] if d < max_depth else []
        idx = len(boxes)
        boxes.append({"label": n["label"], "kind": n["kind"], "depth": d, "x": 16 + d * col_w, "y": 0.0})
        if not kids:
            boxes[idx]["y"] = 16 + row[0] * row_h
            row[0] += 1
            return idx
        ys = []
        for c in kids:
            ci = rec(c, d + 1)
            edges.append((idx, ci))
            ys.append(boxes[ci]["y"])
        boxes[idx]["y"] = (min(ys) + max(ys)) / 2
        return idx
    rec(tree, 0)
    depth = max(b["depth"] for b in boxes)
    return {"boxes": boxes, "edges": edges, "width": 32 + (depth + 1) * col_w, "height": 32 + row[0] * row_h,
            "col_w": col_w, "row_h": row_h}


def to_svg(tree: dict[str, Any], theme: str = "midnight") -> str:
    """The App Map as a standalone SVG (Midnight colours, curved connectors, kind-coloured pills)."""
    from .tokens5 import palette5
    p = palette5(theme)
    g = layout(tree)
    w, h, cw = g["width"], g["height"], g["col_w"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
           f'font-family="Segoe UI, Inter, Arial, sans-serif" font-size="11">',
           f'<rect width="{w}" height="{h}" fill="{p["field"]}"/>']
    for a, b in g["edges"]:
        pa, pb = g["boxes"][a], g["boxes"][b]
        x0, y0 = pa["x"] + cw - 28, pa["y"]
        x1, y1 = pb["x"], pb["y"]
        mx = (x0 + x1) / 2
        out.append(f'<path d="M{x0:.1f},{y0:.1f} C{mx:.1f},{y0:.1f} {mx:.1f},{y1:.1f} {x1:.1f},{y1:.1f}" '
                   f'fill="none" stroke="{p["text_faint"]}" stroke-opacity="0.7" stroke-width="1.1"/>')
    for bx in g["boxes"]:
        col = p[KIND_ROLE[bx["kind"]]]
        label = bx["label"] if len(bx["label"]) <= 28 else bx["label"][:27] + "…"
        bw = cw - 28
        strong = bx["kind"] in ("app", "area", "page", "section", "tab")
        out.append(f'<rect x="{bx["x"]}" y="{bx["y"] - 9:.1f}" width="{bw}" height="18" rx="9" '
                   f'fill="{p["raised"] if strong else p["field"]}" stroke="{col}" '
                   f'stroke-width="{1.4 if strong else 0.8}" stroke-opacity="{1 if strong else 0.55}"/>')
        weight = ' font-weight="600"' if strong else ""  # no backslash inside f-strings (Python 3.10)
        out.append(f'<text x="{bx["x"] + 10}" y="{bx["y"] + 4:.1f}" fill="{col if strong else p["text"]}"'
                   f'{weight}>{html.escape(label)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"
