# Feature: Web deployment — publish-to-cloud feedback loop

## Status
LIVE (MVP) since 2026-08-08 on Azure. Designed 2026-08-07 (owner + Claude,
brainstormed with Gemini + Codex) originally against Supabase; retargeted to
Azure same week when the owner picked reusing his existing subscription
footprint (see decision log). The 3D-presentation-layer framework refactor
(render/GLB/walkthrough as framework commands) remains the roadmap Phase 1;
the cloud MVP shipped ahead of it at the project layer.

## Why this exists
The owner's product vision: a user opens a website, sees a project's
floor plans (bare + furnished), walks through the 3D model, and submits
feedback (camera pose + strokes + comment). An AI agent picks each
feedback up as a work order, implements it in the repo — specs, tests,
review chain, exactly the local loop used to build villa-maketa — and
publishes a new version. The user refreshes.

## The topology
**The local machine is the factory, the cloud is the shop window.**
Blender, git, tests and the agent stay local; the cloud runs one small
FastAPI app (pages + feedback inbox) and stores the heavy bytes in blob.

```
 local (agent)                          cloud (Azure, one subscription)
─────────────────────────────────────────────────────────────────────────
 feedback poll (psql) ◄───────────────  Postgres: building_designer DB
 implement → verify → commit → push ─►  GitHub (model + code history)
 archicad-builder publish <proj> ────┬► blob `projects` container:
   1. refuse if tree dirty/unpushed  │    villa-<sha>.glb, walkthrough-
   2. artifacts SHA-named FIRST      │    <sha>.html, plan PNGs
   3. build.json LAST (the pointer) ─┘
                                        App Service: app-building-designer
 user browser ──────────────────────►     GET /            catalog (from DB)
   pages + POST feedback (same origin)    GET /<proj>/     homepage: plans,
   GLB: 307 redirect → blob (CORS GET)                     build sha, feedback
                                          GET /<proj>/walkthrough  (proxied
                                                           from blob, same
                                                           origin as POST)
                                          POST /<proj>/feedback → Postgres +
                                                           PNG to blob
```

## Azure inventory (all the IDs)

| Piece | Value |
|---|---|
| **Subscription** | `DEV - PracticeVaultAI` — id `a61ae357-4a6e-477b-9b41-d24cc4ab07ae`, tenant `e5ddde8b-8897-4800-b643-b0e76f7e57cc` |
| **Web app** | `app-building-designer` → https://app-building-designer.azurewebsites.net (RG `rg-building-designer`, Python 3.11 Linux, gunicorn+uvicorn) |
| **App Service plan** | `asp-pvlt-dev` — P0v3 Linux, East US 2, RG `rg-app-dev` (shared with the pvlt dev apps; we're a tenant, don't scale/delete it) |
| **Postgres** | `www-site-db-server.postgres.database.azure.com` — Flexible Server, PG 16, B1ms Burstable, Central US, RG `rg-data-dev` (shared with www-site) |
| **Database** | `building_designer`, user `wwwadmin` (server admin; creds in www-site/storage.md and in the app settings — NOT in this repo) |
| **Storage account** | `stbuildingdesigner` — Standard_LRS StorageV2, Germany West Central, RG `rg-building-designer` |
| **Blob containers** | `projects` (public blob read — artifacts + build.json), `feedback` (private — submitted screenshots) |
| **Blob CORS** | GET/HEAD/OPTIONS from `*` on the blob service (the walkthrough page fetches the GLB cross-origin after the 307) |
| **Legacy static site** | `$web` on the same account (first deploy 2026-08-07, superseded) — now only a redirect page to the app |

Deploy/update the app:
```bash
az account set --subscription a61ae357-4a6e-477b-9b41-d24cc4ab07ae
cd webapp && zip -r /tmp/webapp.zip main.py templates requirements.txt
az webapp deploy -g rg-building-designer -n app-building-designer \
  --src-path /tmp/webapp.zip --type zip     # Oryx builds requirements.txt
```
App settings (set once; values live in Azure, not git): `DATABASE_URL`,
`AZURE_STORAGE_CONNECTION_STRING`, `SCM_DO_BUILD_DURING_DEPLOYMENT=true`,
startup command `gunicorn -w 2 -k uvicorn.workers.UvicornWorker main:app`.

Postgres firewall: no public AllowAll; Azure services allowed + pinned dev
IPs (add yours: `az postgres flexible-server firewall-rule create
--resource-group rg-data-dev --server-name www-site-db-server ...`).

Agent feedback poll:
```bash
psql "$DATABASE_URL" -c "SELECT id, comment, where_label FROM feedback \
  WHERE status='new' ORDER BY created_at"
```

## Contract
- **Git owns the building model and all code.** The database NEVER
  stores the model (ADR-001: building.json is source code; the agent's
  entire toolchain — validators, tests, diffs, review — works on files).
- **Postgres owns the feedback inbox.** Two tables, no more:
  `projects(id, name, git_remote, created_at)` and `feedback(id,
  project_id, comment, where_label, camera JSONB, strokes JSONB,
  screenshot_key, viewed_sha, resolved_sha, status
  new|in_progress|resolved|rejected, created_at, resolved_at)`. The
  resolved-feedback list IS the public changelog — no separate versions
  table (owner KISS decision, see log).
- **Artifacts live in blob storage, never in Postgres** (30 MB GLB blobs
  in a database help nobody) and never in git (derived, regenerable —
  ADR-001).
- **Pages and the feedback POST share one origin** (the app), exactly
  like serve.py locally — the walkthrough's relative `fetch('feedback')`
  works unchanged in both worlds. The app *proxies* walkthrough.html
  from blob (never redirects it) to preserve that origin; the GLB is a
  307 redirect to blob so 30 MB never flows through the app.
- **Publishing is a deliberate local CLI step** (`archicad-builder publish`),
  not a push side effect: refuse a dirty/unpushed tree; upload
  SHA-stamped artifacts FIRST, `build.json` LAST. build.json is the
  per-project release pointer the app reads (cached ≤15 s) — a
  refreshing user always gets a complete old build or a complete new
  one, never a torn pair.
- **Every build stamps its git SHA** (build.json, shown on the project
  homepage); feedback rows record `viewed_sha` (what the user saw) and
  `resolved_sha` (what fixed it). Full audit trail across git + one
  table.
- **The app never redeploys for a model update** — publish touches blob
  only; the app picks up the new build.json within its cache TTL.

## Limits
- The feedback POST is unauthenticated; acceptable while the audience is
  link-holders. Real auth slots in without schema surgery.
- Rollback = `git checkout <sha>` + rebuild + publish (~a minute of
  Blender). Old SHA-named artifacts stay in blob, so re-pointing
  build.json by hand also works in a pinch.
- Publish trusts the local build environment (Blender version etc.);
  reproducible cloud builds are a non-goal until more than one person
  publishes.
- The shared Postgres (B1ms) and plan belong to other projects too —
  we are a low-traffic tenant on both.

## Phases
1. ~~**Framework refactor**~~ ✅ shipped 2026-08-09: `archicad-builder
   pipeline <project>` runs every step in a declared order and skips only
   what it can prove is unchanged; `publish` moved from `webapp/` into the
   CLI and now refuses artifacts the pipeline did not produce cleanly.
   Design and freshness rules: [project-pipeline.md](project-pipeline.md).
   The villa's rendering scripts stay at the project layer until a second
   project needs a walkthrough (that decision is logged there).
2. ~~Cloud MVP~~ ✅ shipped 2026-08-08 (this page).
3. **Later, on demand**: auth, instant rollback UI, agent auto-poll
   daemon, multi-user.

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-07 | Git + Postgres split: model in git, feedback in DB | both brainstorms (Gemini 4 alternatives, Codex 5) independently converged on it; DB-authoritative model rejected — silent divergence between DB, snapshots and artifacts, and the agent loses diffs/branching |
| 2026-08-07 | No versions table, no live-release row | owner KISS challenge: "git already is the version table"; the changelog is the resolved-feedback list; rollback-by-rebuild is fine at this scale |
| 2026-08-07 | ~~No app server — Supabase REST for the one dynamic endpoint~~ superseded 2026-08-08 | see next row |
| 2026-08-08 | Azure instead of Supabase; mini app server returns (FastAPI on the existing `asp-pvlt-dev` plan) | owner: reuse the existing subscription footprint (Postgres `www-site-db-server`, plan `asp-pvlt-dev`) + "feedback and root page should be on the same server, models in blob"; Azure has no anonymous-insert REST layer, so the one POST endpoint needs our code anyway — giving it the pages too costs nothing and removes CORS entirely |
| 2026-08-08 | build.json is the release pointer (uploaded last), replacing "entry HTML last" | with an app in front, HTML is rendered, not uploaded; the pointer moved into data. Same atomicity argument |
| 2026-08-08 | GLB via 307 redirect to blob; walkthrough.html proxied through the app | redirect keeps 30 MB off the app; proxy keeps the page same-origin so the F-key POST stays a relative URL (works identically under serve.py locally) |
| 2026-08-08 | One subdirectory per project under one app + `projects/<name>/` blob prefix; homepage per project | owner: "one subdirectory per project, and I should have a homepage per project" |
| 2026-08-08 | Walkthrough shows a streaming progress bar (MB / %) while the GLB downloads | owner: 30 MB with a static "Loading scene…" message "just seems stuck" |
| 2026-08-07 | Artifacts SHA-stamped (build.json, viewed_sha) | Codex's #1 failure mode: published artifact not matching the claimed git SHA |
| 2026-08-07 | Agent polls, no inbound webhook | Codex: webhook retries/reordering double the work; polling matches the existing "check the feedback" workflow |

## Related
[browser-walkthrough.md](browser-walkthrough.md) (the product this
deploys) · ADR-001 (JSON as source of truth) · ADR-003 (mutations via
apply actions — the future Phase 3 edit API) · app code: `webapp/` ·
worked example: projects/villa-maketa.
