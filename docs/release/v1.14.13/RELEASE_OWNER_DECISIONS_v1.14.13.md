# Release-owner decisions — 1.14.13 RC → 1.15.0

Release owner: `golshandvr-del`. Each known gap has a decision and its effect.

| # | Gap | Decision | Effect on users |
|---|---|---|---|
| 1 | Manual checks in the Windows checklist are NOT RUN (GCM prompt, GUI network cut, real secondary rate limit, SmartScreen) | **Ship** 1.15.0; items stay NOT RUN in the checklist; logic covered by unit/E2E tests | Rare UI wording issues possible; no data-loss path (commits are never deleted, partial downloads removed) |
| 2 | Only PAT accounts (no GitHub App / OAuth device flow) | **Out of scope** for 1.15.0 (roadmap) | Users create a fine-grained PAT |
| 3 | Android toolchain bump (AGP/Gradle/Kotlin) pending | **Defer** to `0.2.x-tooling` | None — mobile builds on the pinned toolchain |
| 4 | Mobile release approval is done by the same person who tags (single-maintainer repo) | **Accept**; required reviewer is enforced by the `release` Environment, `prevent_self_review` is off because there is one maintainer | Every signed mobile release still needs an explicit approval click/API call |
| 5 | Upgrade test covers latest published release → this build; older 1.14.x → 1.15.0 not tested individually | **Accept**; settings/binding migrations are idempotent and covered by `test_github_repository_binding_v144.py` | Users on very old builds should upgrade normally; data dir is never touched by the installer |
