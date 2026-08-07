# Feature: Web deployment — publish-to-cloud feedback loop

## Status
Designed 2026-08-07 (owner + Claude, brainstormed with Gemini + Codex).
Not commissioned — blocked on the 3D-presentation-layer refactor
(promoting render/GLB/walkthrough/serve from villa scripts into framework
commands), which is Phase 1 of this plan.

## Why this exists
The owner's product vision: a user opens a website, sees a project's
floor plans (bare + furnished), walks through the 3D model, and submits
feedback (camera pose + strokes + comment). An AI agent picks each
feedback up as a work order, implements it in the repo — specs, tests,
review chain, exactly the local loop used to build villa-maketa — and
publishes a new version. The user refreshes.

## The topology
**The local machine is the factory, the cloud is the shop window.**
Blender, git, tests and the agent stay local; the cloud runs no code of
ours at all.

```
 local (agent)                          cloud (one Supabase project)
─────────────────────────────────────────────────────────────────────
 feedback poll ◄──────────────────────  Postgres (feedback table)
 implement → verify → commit → push ─►  GitHub (model + code history)
 <cli> publish <project> ────────────┬► storage: plans, GLBs, pages
   1. refuse if tree dirty/unpushed  │   (static; user just refreshes)
   2. build everything from HEAD     │
   3. stamp build.json with git SHA ─┘
```

## Contract
- **Git owns the building model and all code.** The database NEVER
  stores the model (ADR-001: building.json is source code; the agent's
  entire toolchain — validators, tests, diffs, review — works on files).
- **Postgres owns the feedback inbox.** Two tables, no more:
  `projects(id, name, git_remote)` and `feedback(id, project_id,
  comment, where_label, camera JSONB, strokes JSONB, screenshot_key,
  viewed_sha, resolved_sha, status new|in_progress|resolved|rejected,
  created_at, resolved_at)`. The resolved-feedback list IS the public
  changelog — no separate versions table (owner KISS decision, see log).
- **Artifacts live in S3-style storage, never in Postgres** (30 MB GLB
  blobs in a database help nobody) and never in git (derived,
  regenerable — ADR-001).
- **Publishing is a deliberate local CLI step**, not a push side effect:
  build from a clean, pushed HEAD; upload big artifacts under
  SHA-named keys FIRST, the small entry-point HTML LAST. The HTML
  references `<name>-<sha>.glb`, so the entry file is the atomic "what's
  live" pointer — a refreshing user always gets a complete old build or
  a complete new one, never a torn pair. No release-pointer row needed.
- **Every build stamps its git SHA** (build.json + shown in the page);
  the feedback form submits it as `viewed_sha`, so every feedback row
  says exactly which build the user was looking at, and `resolved_sha`
  says which commit fixed it. Full audit trail across git + one table.
- **No app server.** The browser posts feedback straight to Postgres via
  Supabase's REST layer with an insert-only anon policy; the site is
  static files. The agent talks to Postgres/storage directly and polls
  for `status=new` rows (outbound poll, no inbound webhook surface —
  Codex: duplicate/reordered webhooks cause duplicate work).

## Limits
- An insert-only public feedback endpoint can be spammed; acceptable
  while the audience is link-holders. Real auth (Supabase auth +
  `feedback.author_id`) slots in without schema surgery.
- Rollback = `git checkout <sha>` + rebuild + publish (~a minute of
  Blender). Instant rollback would need retained artifact bundles and a
  versions table — deliberately dropped (see log); reintroducible
  without breaking the two-table core.
- Publish trusts the local build environment (Blender version etc.);
  reproducible cloud builds are a non-goal until more than one person
  publishes.

## Phases
1. **Framework refactor** (prerequisite): `render / export-glb /
   walkthrough / serve / publish <project>` as framework commands with
   per-project config; one-command rebuild; villa = worked example.
2. **Cloud MVP**: Supabase project (Postgres + storage + REST), publish
   command, walkthrough feedback form posts to the cloud, agent polls.
3. **Later, on demand**: auth, previews/instant rollback (versions
   table returns), floor-plan browser UI, multi-user.

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-07 | Git + Postgres split: model in git, feedback in DB | both brainstorms (Gemini 4 alternatives, Codex 5) independently converged on it; DB-authoritative model rejected — silent divergence between DB, snapshots and artifacts, and the agent loses diffs/branching |
| 2026-08-07 | No versions table, no live-release row | owner KISS challenge: "git already is the version table"; the changelog is the resolved-feedback list; rollback-by-rebuild is fine at this scale |
| 2026-08-07 | No app server — static storage + Supabase REST for the one dynamic endpoint | owner: "agent pushes to S3, user just refreshes"; FastAPI only existed to serve files and accept one POST |
| 2026-08-07 | Atomicity via upload order (SHA-named big files first, entry HTML last) | replaces the compare-and-swap release pointer; the entry file IS the pointer |
| 2026-08-07 | Artifacts SHA-stamped (build.json, viewed_sha) | Codex's #1 failure mode: published artifact not matching the claimed git SHA |
| 2026-08-07 | Agent polls, no inbound webhook | Codex: webhook retries/reordering double the work; polling matches the existing "check the feedback" workflow |
| 2026-08-07 | Supabase as the whole cloud footprint | Postgres + S3-style storage + browser-facing REST in one service; zero servers to run |

## Related
[browser-walkthrough.md](browser-walkthrough.md) (the product this
deploys) · ADR-001 (JSON as source of truth) · ADR-003 (mutations via
apply actions — the future Phase 3 edit API) · worked example to be:
projects/villa-maketa.
