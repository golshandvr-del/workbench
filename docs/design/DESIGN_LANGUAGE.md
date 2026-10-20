# AI Workbench 5.x — Design language "Mission Map"

The owner's reference images (`docs/design/reference/`) define the target. This file turns them into rules that
code can follow and tests can check. Tokens live in `apps/desktop/src/aiwb/ui/tokens5.py`; nothing else may
hard-code a colour.

## 1. Mood

A night-time mission control: a deep blue-black field, thin quiet lines, and a few points of light that mean
something. The eye should land, in order, on: the golden source → the active (blue) tasks → the assistant's
latest message. Everything else stays in the background.

## 2. Colour (Midnight — the default theme)

| Token | Hex | Use |
|---|---|---|
| `window` | `#0f131a` | window / chrome |
| `field` | `#10151c` | Mission Map canvas |
| `panel` | `#151a23` | rail, toolbar, status bar, assistant panel |
| `raised` | `#1b2130` | bubbles, inputs, menus, buttons |
| `raised_hi` | `#232a3b` | hover |
| `line` | `#2a3142` | hairlines, lane rails, borders |
| `line_soft` | `#1d2331` | grid, version dashes (dim part) |
| `text` | `#e6eaf2` | primary text |
| `text_dim` | `#9aa3b5` | secondary text |
| `text_faint` | `#5f687b` | captions, timestamps |
| `active` | `#2f7bff` | the ONE accent: active task, selection, primary button |
| `active_glow` | `#1d5fe0` | halo around active nodes |
| `version` | `#5aa9ff` | version labels + dashed columns |
| `go` | `#22c55e` | start capsule, lane hexagons, "online", success |
| `go_deep` | `#0f5132` | fills behind green outlines |
| `source` | `#f5c542` | the golden source node only |
| `idle` | `#2c313d` | future task disc |
| `idle_ring` | `#4a5263` | future task ring |
| `warn` | `#f59e0b` | needs attention |
| `danger` | `#f43f5e` | blocked / failed |

A Light theme ("Daylight") mirrors every token; Midnight is the default because it is what the owner drew.

## 3. Type

Segoe UI Variable / Segoe UI for text (9–10 pt body, 11 pt titles, 8 pt captions; titles semibold, never bold
caps except menu items and the start capsule, which the reference sets in tracked caps). Version labels,
IDs and counters use Cascadia Mono → Consolas.

## 4. Geometry

4 px grid. Rail 64 px; toolbar 44 px; status bar 30 px; assistant panel 340 px (collapses under 1100 px window
width). Lanes are 68 px apart; version columns 66 px apart; task disc 22 px with a 2 px ring; lane hexagon 22 px;
source node 16 px. Corners: 6 px for buttons/inputs, 10 px for bubbles and menus, full round for capsules.

## 5. Light & depth

No drop shadows on flat surfaces. Glow is reserved for *live* things: the source node, active tasks, the
selected rail item. Menus get one soft 12 px shadow so they float.

## 6. Motion (5.3.0)

One animation clock (`aiwb/ui/motion.py`) at up to 60 fps that sleeps when nothing moves. Durations: 120 ms
hover, 180 ms menus, 240 ms page change, 600 ms branch growth. Easing: cubic-out for entering, cubic-in-out for
moving. Live loops (active pulse, light particles on active branches) are slow (1.6 s) and subtle. "Reduce
motion" turns every animation into its end state.

## 7. Why it will not look "AI-made"

* No purple/indigo gradients, no glassmorphism, no emoji, no oversized rounded cards.
* Asymmetry where it carries meaning (the source on the left, flow to the right).
* Real data density: many small precise things instead of a few big vague ones.
* Hand-tuned optical details: hexagon numbers nudged 1 px up, chevrons on the lane baseline, version labels on
  the dash axis, the golden node slightly smaller than task discs so it reads as a point of origin.

## 8. Rendering

Shapes are drawn by `tools/gen_ui_assets.py` with Pillow at 4× and downsampled (anti-aliased), for scales
1.0 / 1.25 / 1.5 / 2.0, and committed as PNG under `apps/desktop/src/aiwb/ui/assets/`. At run time Tk only
places images (fast, crisp); Pillow is not needed on the user's machine.
