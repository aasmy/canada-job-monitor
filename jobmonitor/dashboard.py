"""Generate a self-contained job hub from the monitor database."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .freshness import age_days
from .sources import canonicalize_url

TEMPLATES = Path(__file__).parent / 'templates'


def _connect_rows(db_path: str):
    query = """SELECT company, title, location, remote_status, source, url, canonical_url,
        relevance_score, match_explanation, skills, published_at, first_seen, last_seen,
        notified, eligible, description FROM jobs WHERE eligible=1
        ORDER BY first_seen DESC LIMIT 500"""
    health_query = """SELECT source, configured_status, integration_type, jobs_retrieved,
        matched_jobs, consecutive_failures, last_success, last_failure, last_error, quota_status
        FROM source_health ORDER BY source"""
    dsn = os.getenv('DATABASE_URL') or os.getenv('SUPABASE_DB_URL')
    if dsn:
        import psycopg
        with psycopg.connect(dsn) as db:
            with db.cursor() as cur:
                cur.execute(query)
                jobs = cur.fetchall()
                cur.execute(health_query)
                return jobs, cur.fetchall()
    if not Path(db_path).exists():
        return [], []
    with sqlite3.connect(db_path) as db:
        try:
            jobs = db.execute(query).fetchall()
            try:
                health = db.execute(health_query).fetchall()
            except sqlite3.OperationalError:
                health = []
            return jobs, health
        except sqlite3.OperationalError:
            return [], []


def _freshness(published_at: str, first_seen: str) -> tuple[str, str]:
    age = age_days(published_at)
    if age is None:
        return 'Publication date unknown', 'unknown'
    if age <= 1:
        return 'Published within 24 hours', 'fresh'
    if age <= 3:
        return 'Published within 3 days', 'recent'
    if age <= 7:
        return 'Published within 7 days', 'week'
    return 'Published more than 7 days ago', 'older'


def _jobs(rows):
    # Employer records take precedence when the same application appears on a list.
    deduplicated = {}
    direct = {'greenhouse', 'lever', 'ashby'}
    for row in sorted(rows, key=lambda row: row[4] not in direct):
        company, title, location, workplace, source, url, canonical, score, why, skills, published, first_seen, last_seen, notified, eligible = row[:15]
        canonical = canonicalize_url(canonical or url or '')
        if not canonical.startswith(('https://', 'http://')):
            continue
        if canonical in deduplicated:
            existing = deduplicated[canonical]
            if source not in existing['sources']:
                existing['sources'].append(source)
            continue
        if source not in direct | {'hackernews'} or age_days(published) is None:
            published = ''
        freshness, freshness_group = _freshness(published, first_seen)
        deduplicated[canonical] = {
            'id': hashlib.sha256(canonical.encode()).hexdigest()[:24],
            'company': company or 'Company not stated', 'title': title or 'Untitled role',
            'location': location or 'Location not stated', 'workplace': workplace or 'Not stated',
            'source': source or 'unknown', 'sources': [source or 'unknown'], 'url': canonical,
            'score': int(score or 0), 'why': why or '', 'skills': skills or '',
            'published': published or '', 'firstSeen': first_seen or '', 'lastSeen': last_seen or '',
            'notified': bool(notified), 'freshness': freshness, 'freshnessGroup': freshness_group,
            'description': row[15] if len(row) > 15 else '',
        }
    return list(deduplicated.values())


def _health(rows):
    return [{
        'source': r[0] or 'unknown', 'status': r[1] or 'unknown', 'type': r[2] or 'unknown',
        'jobs': int(r[3] or 0), 'matches': int(r[4] or 0), 'failures': int(r[5] or 0),
        'lastSuccess': r[6] or '', 'lastFailure': r[7] or '',
        'lastError': r[8] or '', 'quota': r[9] or '',
    } for r in rows]


def _html(jobs: list[dict], health: list[dict]) -> str:
    def safe_json(value):
        return json.dumps(value, ensure_ascii=True).replace('<', '\\u003c')

    now = datetime.now(timezone.utc)
    icons = {path.stem: path.read_text(encoding='utf8') for path in (TEMPLATES / 'icons').glob('*.svg')}
    values = {
        'DATA': safe_json(jobs), 'HEALTH': safe_json(health), 'ICONS': safe_json(icons),
        'UPDATED': html.escape(now.isoformat()),
        'CSS': (TEMPLATES / 'hub.css').read_text(encoding='utf8'),
        'JS': (TEMPLATES / 'hub.js').read_text(encoding='utf8'),
    }
    template = (TEMPLATES / 'hub.html').read_text(encoding='utf8')
    return re.sub(r'__HUB_(DATA|HEALTH|ICONS|UPDATED|CSS|JS)__', lambda m: values[m[1]], template)


def generate(db_path: str, output: str):
    job_rows, health_rows = _connect_rows(db_path)
    jobs = _jobs(job_rows)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_html(jobs, _health(health_rows)), encoding='utf8')
    return len(jobs)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='jobs.sqlite3')
    parser.add_argument('--output', default='public/index.html')
    args = parser.parse_args(argv)
    count = generate(args.db, args.output)
    print(f'Generated dashboard with {count} jobs at {args.output}')


if __name__ == '__main__':
    main()
