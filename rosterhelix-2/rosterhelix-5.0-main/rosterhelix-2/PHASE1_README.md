# RosterHelix 3.0 — Phase 1 (from current GitHub ZIP)

This is a minimal, compatibility-preserving update to the `rosterhelix-2` application.

## Changes
- Enables 2026 in the administrator NFLverse importer.
- Uses a dynamically determined NFL season instead of a 2025 ceiling.
- Defaults `/api/players` to the latest **imported** season instead of aggregating all seasons.
- Adds a SQLite index for season/week filtering.
- Adds `/api/health` version marker `3.0-phase1` and current-season fields to `/api/stats`.

## Before deploying
1. Back up the existing persistent database at `/var/data/rosterhelix.sqlite3`.
2. Check Render **Settings > Root Directory** is `rosterhelix-2` (or equivalent Blueprint setting). The `render.yaml` is in this folder.
3. Commit this folder's contents to the existing GitHub repo, preserving its folder structure.
4. Verify `https://rosterhelix.onrender.com/api/health` returns `3.0-phase1`. If it does not, you are testing a different service/deployment.
5. Verify `/api/stats` responds with counts. Sign in with the configured administrator account, navigate to Account & Data, and import 2026.
6. Verify `/api/players?season=2026` includes `ppg` and `trend`, not only names and IDs.

## Limitations
- This release does **not** yet automate imports or migrate to Postgres.
- This release does **not** guarantee nflverse's upstream 2026 CSV layout is unchanged. If the importer fails, retain the error message for diagnosis.
- Start/Sit and Trade Lab still compare historical recent form; they are not validated future projections.
- No live Render database or network integration was tested in this sandbox.
- Never upload or share database backups containing user accounts or sessions publicly.
