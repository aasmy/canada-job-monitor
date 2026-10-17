"""Public company career board adapters; no site scraping or auth bypass."""
from dataclasses import dataclass
import html
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import requests

@dataclass(frozen=True)
class Job:
    source: str
    source_id: str
    company: str
    title: str
    location: str
    url: str
    description: str = ""
    posted_at: str = ""
    canonical_url: str = ""
    workplace: str = ""

    def stable_id(self) -> str:
        return f"{self.source}:{self.source_id or canonicalize_url(self.url)}"

    def best_url(self) -> str:
        return self.canonical_url or canonicalize_url(self.url) or self.url


def plain(value):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html.unescape(value or ""))).strip()


def fetch_json(session, url):
    response = session.get(url, timeout=20, headers={"User-Agent": "CanadaJobMonitor/2.0 (personal job alerts; contact repository owner)"})
    response.raise_for_status()
    return response.json()


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid", "igshid", "ref"}]
    clean = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower().removeprefix("www."),
        path=parsed.path.rstrip("/") or "/",
        query=urlencode(query, doseq=True),
        fragment="",
    )
    return urlunparse(clean)


def parse_datetime(value: str) -> str:
    """Return an ISO-8601 UTC timestamp when a source provides a trustworthy date."""
    if not value:
        return ""
    text = str(value).strip()
    try:
        if text.isdigit():
            number = int(text)
            if number > 10_000_000_000:
                number = number / 1000
            return datetime.fromtimestamp(number, timezone.utc).isoformat()
        if "," in text and re.search(r"\bGMT\b|[+-]\d{4}$", text):
            parsed = parsedate_to_datetime(text)
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return ""


def workplace_from_text(*values: str) -> str:
    text = " ".join(v or "" for v in values).lower()
    if "remote" in text:
        return "Remote"
    if "hybrid" in text:
        return "Hybrid"
    if "on-site" in text or "onsite" in text:
        return "On-site"
    return "Not stated"


def greenhouse(session, board, company):
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    for item in fetch_json(session, url).get("jobs", []):
        location = item.get("location", {}).get("name", "")
        description = plain(item.get("content", ""))
        yield Job("greenhouse", str(item["id"]), company, item.get("title", ""),
                  location, item.get("absolute_url", ""), description,
                  parse_datetime(item.get("first_published", "")),
                  canonicalize_url(item.get("absolute_url", "")),
                  workplace_from_text(location, description))


def lever(session, board, company):
    url = f"https://api.lever.co/v0/postings/{board}?mode=json"
    for item in fetch_json(session, url):
        categories = item.get("categories") or {}
        location = categories.get("location", "")
        all_locations = categories.get("allLocations") or []
        if all_locations:
            location = ", ".join(all_locations)
        sections = " ".join(str(section.get("text", "")) + " " + str(section.get("content", "")) for section in item.get("lists", []))
        description = plain(" ".join([item.get("descriptionPlain") or item.get("description") or "", sections, item.get("additionalPlain") or item.get("additional") or ""]))
        yield Job("lever", str(item["id"]), company, item.get("text", ""), location,
                  item.get("hostedUrl", ""), description,
                  parse_datetime(str(item.get("createdAt", ""))),
                  canonicalize_url(item.get("hostedUrl", "")),
                  workplace_from_text(location, description))


def ashby(session, board, company):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board}"
    for item in fetch_json(session, url).get("jobs", []):
        locations = [item.get("location", "")]
        locations.extend(x.get("location", "") for x in item.get("secondaryLocations", []))
        if item.get("isRemote"):
            locations.append("Remote")
        description = plain(item.get("descriptionPlain") or item.get("descriptionHtml") or "")
        job_url = item.get("jobUrl") or item.get("applyUrl", "")
        yield Job("ashby", str(item.get("id") or item.get("jobUrl") or item.get("applyUrl")),
                  company, item.get("title", ""), ", ".join(filter(None, locations)),
                  job_url, description, parse_datetime(item.get("publishedAt", "")),
                  canonicalize_url(job_url),
                  "Remote" if item.get("isRemote") else workplace_from_text(", ".join(filter(None, locations)), description))

ADAPTERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}


def due_sources(config, source: str, now: float | None = None) -> bool:
    intervals = config.get("monitor", {}).get("poll_intervals_minutes", {})
    minutes = int(intervals.get(source, config.get("monitor", {}).get("default_poll_interval_minutes", 15)))
    if minutes <= 15:
        return True
    bucket = int((now or time.time()) // 900)
    return bucket % max(1, minutes // 15) == 0


def collect(config):
    session = requests.Session()
    delay = float(config.get("monitor", {}).get("request_delay_seconds", 1.5))
    jobs, errors, successes = [], [], 0
    for source, adapter in ADAPTERS.items():
        if not due_sources(config, source):
            continue
        for item in config.get("sources", {}).get(source, []):
            if item.get("enabled", True) is False:
                continue
            board = item["board"]
            try:
                found = list(adapter(session, board, item.get("company", board)))
                jobs.extend(found)
                print(f"Source {source}/{board}: {len(found)} listings")
                successes += 1
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                errors.append(f"{source}/{board}: {type(exc).__name__}: {exc}")
            time.sleep(max(0, delay))
    return jobs, errors, successes
