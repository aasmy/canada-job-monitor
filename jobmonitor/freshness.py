"""Publication-based freshness. Discovery and feed-update times are not publication."""
from datetime import datetime, timezone


def age_days(published_at: str, now: datetime | None = None) -> float | None:
    if not published_at:
        return None
    try:
        posted = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    age = ((now or datetime.now(timezone.utc)) - posted).total_seconds() / 86400
    return age if age >= 0 else None


def is_recent(published_at: str, days: int = 7, now: datetime | None = None) -> bool:
    age = age_days(published_at, now)
    return age is not None and age <= days


def alert_allowed(job, config: dict) -> bool:
    settings = config.get('notifications', {})
    age = age_days(job.posted_at)
    if age is None:
        # Future or malformed dates must never be opted into as fresh.
        return not job.posted_at and bool(settings.get('include_unknown_publication_dates', False))
    return age <= int(settings.get('max_publication_age_days', 7))
