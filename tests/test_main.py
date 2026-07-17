from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings
from app.main import JOB_ID, MISFIRE_GRACE_SECONDS, register_weekly_job


def test_register_weekly_job_sets_generous_misfire_grace_time():
    settings = Settings(run_day="wed,fri", run_hour=0, run_minute=30)
    timezone = ZoneInfo(settings.tz)
    scheduler = AsyncIOScheduler(timezone=timezone)

    register_weekly_job(scheduler, settings, timezone)

    job = scheduler.get_job(JOB_ID)
    assert job is not None
    assert job.misfire_grace_time == MISFIRE_GRACE_SECONDS
    assert job.misfire_grace_time > 1  # APScheduler's default of 1s is too tight
    assert job.max_instances == 1


def test_register_weekly_job_trigger_reflects_settings():
    settings = Settings(run_day="wed,fri", run_hour=0, run_minute=30)
    timezone = ZoneInfo(settings.tz)
    scheduler = AsyncIOScheduler(timezone=timezone)

    register_weekly_job(scheduler, settings, timezone)

    trigger = scheduler.get_job(JOB_ID).trigger
    assert str(trigger.fields[trigger.FIELD_NAMES.index("day_of_week")]) == "wed,fri"
    assert str(trigger.fields[trigger.FIELD_NAMES.index("hour")]) == "0"
    assert str(trigger.fields[trigger.FIELD_NAMES.index("minute")]) == "30"
