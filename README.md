# Weekly Deal Watcher

A small self-hosted Python job that checks Kroger promo prices for watchlist items and publishes the best weekly deals to Todoist and/or email. It runs as a single Docker container with SQLite stored on a mounted volume.

It also learns over time: checking a task off in Todoist (or leaving it unchecked) feeds back into the system as a purchase/ignore signal. Every 4th run, it distills that history into new "learned" preferences (or deactivates ones you keep ignoring) and reports what changed in a "what I learned" email.

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
- Todoist defaults to `https://api.todoist.com/api/v1`. If Todoist changes endpoint versions again, set `TODOIST_API_BASE_URL` in `.env`; 410 responses are surfaced with that hint. Completed-task lookups use the unified API's `tasks/completed/by_completion_date` endpoint, since the plain `tasks` endpoint only returns active tasks.
- Gemini defaults to `gemini-3.5-flash`, the current stable Flash model listed in Google AI Studio docs on 2026-07-08.
- Set `MOCK_KROGER=1` for a local fixture-backed run without Kroger API calls.

## The learning loop

Each run, before publishing this week's list, the pipeline reads back last run's Todoist tasks: a checked-off task becomes a `purchased` signal, a still-open task becomes an `ignored` signal. These accumulate in the `decisions` table alongside `preferences` (your `watchlist.yaml` entries as `source=seed`, plus anything the system has learned as `source=learned`).

Every 4th successful run, a distillation pass looks at that history and:

- **Promotes** an item to a new learned preference once it's been purchased 3+ times, using the highest price you actually paid as its "good price."
- **Demotes** (deactivates) a learned preference after 6 consecutive ignored appearances. A week where *everything* published was ignored is treated as a weak signal (you probably skipped shopping that week) and doesn't count against any specific item.
- Never modifies or removes `source=seed` rows - `watchlist.yaml` is always authoritative for those. Add an item to `blocklist` to veto a learned preference (or keep a seed item from ever being suggested).
- Caps learned preferences at 50.

Changes are logged and, if any occurred, emailed as a short "what I learned" digest (requires the `email` output mode / SMTP settings to be configured).

Cold start: with no decision history yet, scoring relies purely on `watchlist.yaml`. Expect it to get noticeably smarter after 4-6 weeks of check-off data.
