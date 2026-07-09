# Weekly Deal Watcher

A small self-hosted Python job that checks Kroger promo prices for watchlist items and publishes the best weekly deals to Todoist and/or email. It runs as a single Docker container with SQLite stored on a mounted volume.

## Quick Start

1. Copy `.env.example` to `.env` and fill in Kroger, Gemini, Todoist, and optional SMTP settings.
	On Linux hosts, set `PUID` and `PGID` to the owner of the local `data` directory if your user is not `1000:1000`.
2. Copy `watchlist.example.yaml` to `data/watchlist.yaml` and edit your watchlist.
3. Find your Kroger location ID or IDs:

```powershell
python -m scripts.find_location 45202
```

Set `KROGER_LOCATION_ID` to one ID, or comma-separated IDs for multiple nearby stores.

4. Start the scheduler:

```powershell
docker compose up -d --build
```

5. Force a run:

```powershell
docker compose exec app python -m app.pipeline --now
```

## Notes

- `OUTPUT_MODE` accepts comma-separated values: `todoist`, `email`, or both. `keep_api` and `tasks` are intentionally deferred.
- Todoist defaults to `https://api.todoist.com/api/v1`. If Todoist changes endpoint versions again, set `TODOIST_API_BASE_URL` in `.env`; 410 responses are surfaced with that hint.
- Gemini defaults to `gemini-3.5-flash`, the current stable Flash model listed in Google AI Studio docs on 2026-07-08.
- Set `MOCK_KROGER=1` for a local fixture-backed run without Kroger API calls.
