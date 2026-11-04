# RosterHelix 2.0 — Clean-room public beta

A new, standalone, premium-dark fantasy football site. It is **not** a patch of the existing RosterHelix repository. Public Player Explorer, Start/Sit and Trade Lab work without accounts; accounts are optional for saved league settings. Admin-only CSV import is protected by a signed-in session, same-origin requests, CSRF token and `ADMIN_EMAIL`.

## Run locally

Requires Python 3.11+. No external Python dependencies.

```sh
python server.py
```

Open http://localhost:8000. Data is stored in `./data/rosterhelix.sqlite3` by default. Use `PORT` and `ROSTERHELIX_DATA_DIR` environment variables to configure it.

## Critical limitations

- **This is a working beta, not a finished prediction engine.** Player Explorer displays historical PPR/half/standard scoring averages; Start/Sit and Trade Lab compare recent-game averages. They do not incorporate injuries, current matchups, future projections, replacement value, or roster context. No fake data is generated.
- Import supports normalized game-level CSVs, **not** arbitrary legacy RosterHelix CSV schemas. Inspect and map historical CSV column names before importing. Do not upload the original file blindly.
- Import upserts on `(season, week, player, team)` and accepts 50,000 rows per upload, max 8 MiB. Large datasets must be split into batches. It is not an automatic NFL data sync.
- Optional user accounts currently support registration, login, logout and saved league name/scoring. Roster editing, password reset, rate limiting, email verification, and production security hardening remain future work. Do not launch public registration at scale before implementing these safeguards.
- Account creation is public, and the configured `ADMIN_EMAIL` determines admin status. **Create your owner account before sharing the staging URL.** Production should additionally use an admin invitation/bootstrap secret to prevent email squatting. Do not expose a live instance until this is addressed.

## Import format

Required columns: `season,week,player`. Optional: `team,pos,opponent,passing_yards,passing_tds,interceptions,rushing_yards,rushing_tds,receptions,receiving_yards,receiving_tds,targets,fumbles_lost`. One row per player-game; empty numeric values default to zero. Verify that your original data uses matching units and scoring semantics.

## Safe Render rollout

1. **Do not overwrite** `rosterhelix.onrender.com` or its existing disk yet.
2. Create a separate staging repository/service (name can differ from production), with a **new disk** at `/var/data`. Do not attach the original production disk.
3. Configure `ADMIN_EMAIL` with your owner email; create that account privately before distributing staging URL.
4. Test `/api/health`, public pages, guest analyzers, sign-up, login, CSRF, admin CSV import, and Render restart persistence.
5. Copy and normalize historical CSV files **from a verified off-Render backup**, test record counts, and compare against original historical data. Original known baseline: approximately 64,089 player-games; confirm actual count from current source.
6. After signoff, back up the original production code and persistent data externally. Cut over the original Render service deliberately; preserve old disk and code until rollback is proven. Render services cannot simply share an existing disk; migration must be planned.

## API

- `GET /api/health`, `/api/stats`, `/api/players?q=&scoring=ppr&season=2025`
- `GET /api/auth/me`, `POST /api/auth/register`, `/api/auth/login`, `/api/auth/logout`
- `GET /api/leagues`, `POST /api/leagues` (authenticated)
- `POST /api/admin/import` (admin, CSV body, CSRF)

## Deployment security checklist

Use HTTPS; set admin email; add signup rate limiting, password reset, email verification, admin bootstrap/invite, security headers and request logging before broad public launch. Never commit account DBs, API keys, or session tokens to GitHub.
