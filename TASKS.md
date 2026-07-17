# Task Board

Priority order. Deployment rule: batch changes into as few pushes as possible —
every push can trigger a Netlify build (free plan, credits reset ~6th of month).
Never push without explicit approval.

## P0 — Security
- [x] SEC-1: Shared-secret auth (`X-Dashboard-Key` vs `DASHBOARD_KEY` env) in `netlify/functions/github.js`
- [x] SEC-2: CORS locked to `https://radiant-bublanina-25b939.netlify.app`
- [x] SEC-3: `insights` prompt validated (string, non-empty, ≤4000 chars)
- [x] SEC-4: `portfolio.html` + `index.html` migrated off browser-held GitHub PAT onto `/api/github` with dashboard key
- [x] SEC-5: `deploy.py` deleted
- [ ] SEC-5b (user action): set `DASHBOARD_KEY` in Netlify env, then revoke + re-issue the fine-grained GitHub PAT

## P1 — Reliability
- [x] REL-1: Shared `concurrency: repo-write` group in both workflows
- [x] REL-2: Commit/push step retries up to 3× after refetch on rejected push
- [x] REL-3: `if: failure()` ntfy alert step (channel swing13cat) in both workflows

## P2 — Cost & hygiene
- [x] COST-1: `netlify.toml` build-ignore for data-only commits (verified against real history)
- [x] DOC-1: Original CLAUDE.md restored + framework header merged
- [ ] Run first Fable review
