import pytest
from pydantic import ValidationError

from app.config import Settings


def test_run_day_accepts_comma_separated_days():
    settings = Settings(run_day="wed,fri")

    assert settings.run_day == "wed,fri"


def test_run_day_normalizes_case_whitespace_and_duplicates():
    settings = Settings(run_day=" Wed , FRI , wed ")

    assert settings.run_day == "wed,fri"


def test_run_day_rejects_invalid_day():
    with pytest.raises(ValidationError):
        Settings(run_day="funday")


def test_run_day_rejects_empty():
    with pytest.raises(ValidationError):
        Settings(run_day="")


def test_run_minute_defaults_and_validates_range():
    assert Settings().run_minute == 30
    with pytest.raises(ValidationError):
        Settings(run_minute=60)
