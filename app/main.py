from __future__ import annotations

import asyncio
import logging
import signal
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.db import init_db
from app.pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def scheduler_main() -> None:
    settings = get_settings()
    init_db(settings.database_url)
    timezone = ZoneInfo(settings.tz)
    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(
        run_pipeline,
        CronTrigger(
            day_of_week=settings.run_day,
            hour=settings.run_hour,
            minute=settings.run_minute,
            timezone=timezone,
        ),
        id="weekly-deal-watcher",
        replace_existing=True,
        max_instances=1,
    )
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
