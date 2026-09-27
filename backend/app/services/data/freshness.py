"""Honest freshness labels. Nothing in AgriFlow is streamed, so nothing is ever labelled LIVE.

CURRENT      reading is at most 90 minutes old (weather "current conditions")
RECENT       reading is older than 90 minutes but within 24 hours
DAILY        daily dataset whose latest observation is today or within the last 3 days
HISTORICAL   older data, or an uploaded (static) dataset
UNAVAILABLE  no data
ERROR        the source exists but its latest fetch failed; any value shown is the last verified one
"""

from datetime import UTC, date, datetime, timedelta, timezone

from pydantic import BaseModel

IST = timezone(timedelta(hours=5, minutes=30), "IST")


class Freshness(BaseModel):
    label: str
    tone: str  # good | neutral | warn | bad
    detail: str


def today_ist() -> date:
    return datetime.now(IST).date()


def _ago(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h ago"
    return f"{hours // 24} days ago"


def unavailable(detail: str = "No data has been fetched yet") -> Freshness:
    return Freshness(label="UNAVAILABLE", tone="bad", detail=detail)


def for_reading(observed_at: datetime | None, now: datetime | None = None) -> Freshness:
    if observed_at is None:
        return unavailable()
    now = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    age = now - observed_at
    if age <= timedelta(minutes=90):
        return Freshness(label="CURRENT", tone="good", detail=f"Reading from {_ago(age)}")
    if age <= timedelta(hours=24):
        return Freshness(label="RECENT", tone="neutral", detail=f"Updated {_ago(age)}")
    return Freshness(label="HISTORICAL", tone="warn", detail=f"Last reading {_ago(age)}")


def for_daily(obs_date: date | None, today: date | None = None) -> Freshness:
    if obs_date is None:
        return unavailable()
    today = today or today_ist()
    days = (today - obs_date).days
    when = obs_date.strftime("%d %b %Y")
    if days <= 0:
        return Freshness(label="DAILY", tone="good", detail=f"Today's report ({when})")
    if days <= 3:
        return Freshness(label="DAILY", tone="neutral", detail=f"Latest report {when}")
    return Freshness(label="HISTORICAL", tone="warn", detail=f"Latest report {when} — {days} days old")


def failed(last_verified: datetime | date | None, reason: str | None = None) -> Freshness:
    """The latest fetch failed. Values (if any) are the last verified ones and must be shown as stale."""
    if isinstance(last_verified, datetime):
        lv = last_verified.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
    elif isinstance(last_verified, date):
        lv = last_verified.strftime("%d %b %Y")
    else:
        lv = None
    detail = "Latest update failed" + (f" · last verified data: {lv}" if lv else " · no verified data yet")
    if reason:
        detail += f" · reason: {reason}"
    return Freshness(label="ERROR", tone="bad", detail=detail)
