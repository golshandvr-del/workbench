# SESSION NOTES (agent memory — survives sandbox resets)

Purpose: the sandbox resets often. Every finding and every step done is written here and pushed
immediately, so a new session can continue without repeating work.

## Environment recovery (do this first after a reset)
- Clone: `git clone https://golshandvr-del:<TOKEN>@github.com/golshandvr-del/workbench.git /home/user/webapp`
- `git config user.name golshandvr-del; git config user.email golshandvr-del@users.noreply.github.com`
- Work directly on `main`; checkpoint rule: ONE change -> add -> commit -> push.
- Tests: `cd apps/desktop && timeout 600 python3 -m unittest discover -s tests -t .` (baseline 863 tests OK, 10 skipped)
- GUI probes need Xvfb: `sudo apt-get install -y xvfb` then `xvfb-run -a -s "-screen 0 1366x800x24" python3 ...`
- Friend's evidence: chat log of the calculator project (PM loop, revision 49..63, "the proposal has no operations").

## Baseline
- Last released: desktop-v5.15.0 (commit 73d7b50). Old roadmap 5.8 -> 5.15 complete.

## Root causes found (measured, session 1)
1. PM loop: PM's role text conflicts with the delivery format in its own prompt; doc task (TASK-0001) is
   owned by the PM, PM answers with a proposal without operations -> rejected -> re-ask loop. Each answer
   moves one tiny decision. Context requests re-send files again.
2. Slowness: every state read = full JSON parse + migrate + deepcopy. Realistic project (625 KB, 2000
   events): load ~20 ms, empty transaction ~64 ms; 2+ reads per click; status poll every 2.5 s.
3. Idle CPU: Mission map runs endless 60 fps loops (`mission:pulse`, `mission:particles`) ~42 fps idle.
4. Right-click menu: first open ~250 ms (raster shadow/panel sprite rendered in pure python); later 13 ms.
   Menu must close on page switch / focus loss / window move.
5. Tiny unclear dialogs: `simpledialog.askstring` ("Your decision") shows no question/options.
6. Freezes: heavy work on UI thread (state read/write, preview of 76 KB paste ~53 ms on every debounce);
   pasted answers without operations become dead-ends.

## Progress log
- (session 2) notes file created.
