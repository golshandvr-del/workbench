# ADR-007 — Workspace GUI technology: keep Tkinter/ttk, new shell package (2.3.0)

**Status:** accepted · **Date:** 2026-10-18 · **Scope:** `apps/desktop/src/aiwb/workspace/` · **Roadmap:** 2.3.0 stage 1
**Source:** `docs/specs/AI_Workbench_GUI_Team_Orchestration_Roadmap_FA.md` §15

## Context
The roadmap needs a project-centred workspace (sidebar, central views, collapsible inspector, timeline,
team dashboard) that stays light, works in FA RTL / EN LTR and at common Windows sizes/DPI. Candidates:
upgraded Tkinter/ttk or PySide6 (Qt Widgets).

## Spike evidence (2026-10-18, Linux sandbox, Python 3.13, 2 CPU, Xvfb — Windows numbers NOT RUN)
| Criterion | Tkinter/ttk | PySide6 |
|---|---|---|
| Extra install size | 0 (ships with python.org Python, already required by the installer probe) | PySide6-Essentials + shiboken6 win_amd64 wheels = **83.4 MB** vs current payload **1.92 MB** (×44) |
| Installer change | none | pip install or bundled wheels; offline/ARM/Python-version matrix to maintain |
| Timeline: 200 rows Treeview insert+render | 28 ms | not measured (not needed: Tk meets target) |
| 1000 / 5000 rows | 42 / 114 ms | — |
| Re-page after filter (200) | 23 ms | — |
| Canvas lanes 10×200 points | 26 ms | — |
| Main window cold build / open project (baseline) | 167 ms / 123 ms | — |
| Reuse of existing GUI tests/smokes (25 scripts) | full | rewrite |
| Docking / Model-View | manual (PanedWindow, collapsible frames) | native |

Targets from §17.2 (200 visible events < 500 ms, local interactions P95 < 100 ms) are met with Tk on the
sandbox reference; Qt does not bring a measured, documented benefit that outweighs ×44 payload and a
second packaging path.

## Decision
1. **Keep Tkinter/ttk.** Build the workspace as a new package `aiwb/workspace/` (shell, views, design tokens).
2. **Design tokens** (`aiwb/workspace/theme.py`): colours for light/dark, spacing, font sizes, severity
   and status symbols (text + symbol, never colour alone). Single source; views never hard-code colours.
3. **Responsive rules:** grid/PanedWindow weights, no fixed-only geometry; minimum size 960×600; below
   1100 px the inspector stacks under the workspace; below 900 px the sidebar shows short labels. Window
   placement clamps to the screen work area. Layout preference is stored in `ui.json` (outside project state).
4. **Separation:** views call only `WorkspaceController` (read models + actions) which delegates to
   `ProjectsController` / V2 services. No domain logic in widgets.
5. **Timeline rendering:** paginated (page = 200 events) Treeview; lane view on Canvas, drawn per page.
6. The classic main window and all existing dialogs stay; the workspace links to them (no second path).

## Consequences
* No new runtime dependency; installer and upgrade path unchanged.
* Dock/undock is not provided (collapse/expand only). Revisit only with a new ADR and measured need.
* DPI/RTL behaviour on real Windows monitors must be checked in the release gate (NOT RUN until then).
