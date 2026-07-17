# STATUS — SP500 Swing Scanner
Updated: 2026-07-16

## Now
All P0/P1/P2 fixes from the 2026-07-16 review are implemented and committed
locally. Push is HELD until user sets DASHBOARD_KEY in Netlify env (functions
read env at deploy time — pushing first would waste a build on a 500ing function).

## Next
- [ ] User sets DASHBOARD_KEY in Netlify UI, then push the batch commit
- [ ] User revokes + re-issues the fine-grained GitHub PAT (old one lived in localStorage)
- [ ] Check "Auto Publishing Locked" on Netlify — new deploy won't go live until unlocked/published
- [ ] After deploy: enter dashboard key once on portfolio page; verify add/remove + insights
- [ ] Run first Fable review

## Recently done
- 2026-07-17: Implemented SEC-1..5, REL-1..3, COST-1, DOC-1 (see TASKS.md); function auth + ignore rule verified locally
- 2026-07-16: Full architecture + security review; TASKS.md rewritten with prioritized backlog
- 2026-07-15: Auto-refresh portfolio after add/remove position (7ef141f)

## Decisions / gotchas
- NEVER push without user approval — every push = a Netlify build; free plan, credits reset ~6th of month
- Netlify site: https://radiant-bublanina-25b939.netlify.app (siteId in .netlify/state.json); CORS is locked to this origin
- Dashboard key = DASHBOARD_KEY Netlify env var; stored client-side in localStorage 'dashboard_key' (shared by index.html + portfolio.html, same origin)
- Dashboards read data from GitHub Pages (portfolio.html) and jsDelivr (dashboard/) — Netlify builds are NOT needed for data updates (netlify.toml ignore rule relies on this)
- results.json schema in CLAUDE.md is richer than current scanner.py output (sector, position_sizing, exit_plan, regime…) — doc may predate a scanner simplification; reconcile before trusting either
- Netlify CLI session expired locally; user works via Netlify web UI
