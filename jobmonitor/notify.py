"""Telegram notification formatting and delivery."""
from __future__ import annotations

from datetime import datetime, timezone
import html
import time
import requests


def _escape(value) -> str:
    return html.escape(str(value or ""), quote=False)


def freshness(posted_at: str, first_seen: str | None = None) -> str:
    if not posted_at:
        return "Publication date unknown"
    try:
        posted = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
    except ValueError:
        return "Publication date unknown"
    delta = datetime.now(timezone.utc) - posted.astimezone(timezone.utc)
    hours = delta.total_seconds() / 3600
    if hours < 0:
        return "Publication date in future or source clock skew"
    if hours <= 24:
        return "Published within 24 hours"
    if hours <= 72:
        return "Published within 3 days"
    if hours <= 168:
        return "Published within 7 days"
    return "Older than 7 days"


def format_telegram(job, match, discovered="Just now") -> str:
    skills = ", ".join(match.skills[:8]) if match.skills else "Not stated"
    text = f"""<b>New Job Found</b>

Company: {_escape(job.company or "Not stated")}
Position: {_escape(job.title)}
Location: {_escape(job.location or "Not stated - verify before applying")}
Workplace: {_escape(job.workplace or "Not stated")}
Experience: {_escape(match.experience)}
Match Score: {int(match.score)}/100
Published: {_escape(freshness(job.posted_at))}
Discovered: {_escape(discovered)}
Source: {_escape(job.source)}
Skills: {_escape(skills)}
Application: {_escape(job.best_url())}

Why: {_escape(match.explanation)}"""
    return text[:3900]


def _post_with_retries(token, payload, attempts=3):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=20)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram rejected message: {data}")
            return data
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(min(8, 2 ** attempt))
    raise RuntimeError(f"Telegram delivery failed after {attempts} attempts: {last_error}")


def send_telegram(token, chat_id, job, match):
    payload = {
        "chat_id": chat_id,
        "text": format_telegram(job, match),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    return _post_with_retries(token, payload)


def send_error_notification(token, chat_id, source: str, count: int, error: str):
    text = f"""<b>Job Monitor Source Warning</b>

Source: {_escape(source)}
Consecutive failures: {count}
Last error: {_escape(error[:1000])}"""
    return _post_with_retries(token, {
        "chat_id": chat_id,
        "text": text[:3900],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })


def send_test_notification(token, chat_id):
    text = """<b>Canada Job Monitor Test</b>

Telegram delivery is working. This message was sent by the manual test command/workflow."""
    return _post_with_retries(token, {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })
