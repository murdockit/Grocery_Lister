from __future__ import annotations

import asyncio
import logging
import signal
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Settings, get_settings
from app.db import init_db
from app.pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

JOB_ID = "weekly-deal-watcher"

# APScheduler's default misfire_grace_time is 1 second: if the scheduler check is even
# briefly delayed (event loop jitter, host load, a container restart near the fire time)
# the entire week's run is silently skipped with only a WARNING log, and there's no other
# retry until next week. A generous grace period means a delayed check still runs.
MISFIRE_GRACE_SECONDS = 3600


def register_weekly_job(
    scheduler: AsyncIOScheduler, settings: Settings, timezone: ZoneInfo
) -> None:
    scheduler.add_job(
        run_pipeline,
        CronTrigger(
            day_of_week=settings.run_day,
            hour=settings.run_hour,
            minute=settings.run_minute,
            timezone=timezone,
        ),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )


async def scheduler_main() -> None:
    settings = get_settings()
    init_db(settings.database_url)
    timezone = ZoneInfo(settings.tz)
    scheduler = AsyncIOScheduler(timezone=timezone)
    register_weekly_job(scheduler, settings, timezone)
    scheduler.start()
    logger.info(
        "Weekly Deal Watcher scheduled for %s at %02d:%02d %s",
        settings.run_day,
        settings.run_hour,
        settings.run_minute,
        settings.tz,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass
    await stop_event.wait()
    scheduler.shutdown(wait=False)


def main() -> None:
    asyncio.run(scheduler_main())


if __name__ == "__main__":
    main()
