"""Persistent job history for SQLite locally and PostgreSQL/Supabase in production."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable


SCHEMA_COLUMNS = """
       job_key TEXT PRIMARY KEY,
       duplicate_key TEXT NOT NULL,
       source TEXT NOT NULL,
       source_id TEXT NOT NULL,
       company TEXT,
       title TEXT,
       location TEXT,
       remote_status TEXT,
       description TEXT,
       published_at TEXT,
       first_seen TEXT NOT NULL,
       last_seen TEXT NOT NULL,
       url TEXT,
       canonical_url TEXT,
       relevance_score INTEGER NOT NULL DEFAULT 0,
       match_explanation TEXT,
       skills TEXT,
       eligible INTEGER NOT NULL DEFAULT 0,
       notified INTEGER NOT NULL DEFAULT 0,
       notified_at TEXT,
       notification_error TEXT
"""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def duplicate_key(job) -> str:
    company = " ".join((job.company or "").lower().split())
    title = " ".join((job.title or "").lower().split())
    location = " ".join((job.location or "").lower().replace("remote - ", "remote ").split())
    if company and company not in {"web", "linkedin", "indeed", "googlejobs", "hackernews"}:
        return f"{company}|{title}|{location[:80]}"
    return job.best_url()


class Store:
    def count_jobs(self) -> int: raise NotImplementedError
    def record(self, job, match) -> bool: raise NotImplementedError
    def pending_notifications(self, limit: int) -> list[str]: raise NotImplementedError
    def mark_notified(self, key: str) -> None: raise NotImplementedError
    def mark_notification_failed(self, key: str, error: str) -> None: raise NotImplementedError
    def record_source_errors(self, errors: Iterable[str]) -> list[tuple[str, int, str]]: raise NotImplementedError
    def record_source_successes(self, rows: Iterable[tuple[str, int, int, str]]) -> None: raise NotImplementedError
    def commit(self) -> None: raise NotImplementedError
    def close(self) -> None: raise NotImplementedError


class SQLiteStore(Store):
    def __init__(self, path: str):
        self.db = sqlite3.connect(path, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=30000")
        self._create()

    def _create(self):
        self.db.execute(f"CREATE TABLE IF NOT EXISTS jobs ({SCHEMA_COLUMNS})")
        existing = {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}
        for name, spec in {
            "duplicate_key": "TEXT DEFAULT ''",
            "source": "TEXT DEFAULT ''",
            "source_id": "TEXT DEFAULT ''",
            "remote_status": "TEXT",
            "description": "TEXT",
            "published_at": "TEXT",
            "canonical_url": "TEXT",
            "relevance_score": "INTEGER NOT NULL DEFAULT 0",
            "match_explanation": "TEXT",
            "skills": "TEXT",
            "notified_at": "TEXT",
            "notification_error": "TEXT",
        }.items():
            if name not in existing:
                self.db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {spec}")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_pending ON jobs(eligible, notified, first_seen)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_duplicate ON jobs(duplicate_key)")
        self.db.execute("""CREATE TABLE IF NOT EXISTS source_health (
            source TEXT PRIMARY KEY,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            last_seen TEXT NOT NULL,
            last_notified_count INTEGER NOT NULL DEFAULT 0,
            last_success TEXT,
            last_failure TEXT,
            jobs_retrieved INTEGER NOT NULL DEFAULT 0,
            matched_jobs INTEGER NOT NULL DEFAULT 0,
            integration_type TEXT,
            configured_status TEXT,
            quota_status TEXT
        )""")
        health_existing = {row[1] for row in self.db.execute("PRAGMA table_info(source_health)")}
        for name, spec in {
            "last_success": "TEXT",
            "last_failure": "TEXT",
            "jobs_retrieved": "INTEGER NOT NULL DEFAULT 0",
            "matched_jobs": "INTEGER NOT NULL DEFAULT 0",
            "integration_type": "TEXT",
            "configured_status": "TEXT",
            "quota_status": "TEXT",
        }.items():
            if name not in health_existing:
                self.db.execute(f"ALTER TABLE source_health ADD COLUMN {name} {spec}")
        self.db.commit()

    def count_jobs(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])

    def record(self, job, match) -> bool:
        timestamp = now_utc()
        key = job.stable_id()
        exists = self.db.execute("SELECT notified FROM jobs WHERE job_key=?", (key,)).fetchone()
        values = (
            key, duplicate_key(job), job.source, job.source_id, job.company, job.title, job.location,
            job.workplace, job.description, job.posted_at, timestamp, timestamp, job.url, job.best_url(),
            match.score, match.explanation, ", ".join(match.skills), int(match.eligible),
        )
        if exists is None:
            self.db.execute("""INSERT INTO jobs (
                job_key, duplicate_key, source, source_id, company, title, location, remote_status,
                description, published_at, first_seen, last_seen, url, canonical_url, relevance_score,
                match_explanation, skills, eligible
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
            return True
        self.db.execute("""UPDATE jobs SET duplicate_key=?, source=?, source_id=?, company=?, title=?,
            location=?, remote_status=?, description=?, published_at=?, last_seen=?, url=?,
            canonical_url=?, relevance_score=?, match_explanation=?, skills=?, eligible=?
            WHERE job_key=?""", values[1:10] + values[11:] + (key,))
        return False

    def pending_notifications(self, limit: int) -> list[str]:
        rows = self.db.execute("""SELECT MIN(job_key) FROM jobs
            WHERE eligible=1 AND notified=0
            GROUP BY duplicate_key
            ORDER BY MIN(first_seen)
            LIMIT ?""", (limit,)).fetchall()
        return [row[0] for row in rows]

    def mark_notified(self, key: str) -> None:
        self.db.execute("UPDATE jobs SET notified=1, notified_at=?, notification_error=NULL WHERE job_key=?", (now_utc(), key))

    def mark_notification_failed(self, key: str, error: str) -> None:
        self.db.execute("UPDATE jobs SET notification_error=? WHERE job_key=?", (error[:500], key))

    def record_source_errors(self, errors: Iterable[str]) -> list[tuple[str, int, str]]:
        alerts = []
        timestamp = now_utc()
        for error in errors:
            source = (error.split(":", 1)[0] or "unknown")[:120]
            row = self.db.execute("SELECT consecutive_failures, last_notified_count FROM source_health WHERE source=?", (source,)).fetchone()
            if row is None:
                count, notified = 1, 0
                self.db.execute("""INSERT INTO source_health (
                    source, consecutive_failures, last_error, last_seen, last_notified_count,
                    last_failure, configured_status
                ) VALUES (?,?,?,?,?,?,?)""", (source, count, error[:1000], timestamp, notified, timestamp, "failing"))
            else:
                count, notified = int(row[0]) + 1, int(row[1])
                self.db.execute("UPDATE source_health SET consecutive_failures=?, last_error=?, last_seen=?, last_failure=? WHERE source=?", (count, error[:1000], timestamp, timestamp, source))
            if count >= 3 and count not in {notified} and (count in {3, 12, 48} or count % 96 == 0):
                alerts.append((source, count, error))
                self.db.execute("UPDATE source_health SET last_notified_count=? WHERE source=?", (count, source))
        return alerts

    def record_source_successes(self, rows: Iterable[tuple[str, int, int, str]]) -> None:
        timestamp = now_utc()
        for source, jobs_retrieved, matched_jobs, integration_type in rows:
            self.db.execute("""INSERT INTO source_health (
                source, consecutive_failures, last_error, last_seen, last_notified_count,
                last_success, last_failure, jobs_retrieved, matched_jobs, integration_type,
                configured_status, quota_status
            ) VALUES (?,0,NULL,?,0,?,NULL,?,?,?,'working','ok')
            ON CONFLICT(source) DO UPDATE SET
                consecutive_failures=0, last_error=NULL, last_seen=excluded.last_seen,
                last_success=excluded.last_success, jobs_retrieved=excluded.jobs_retrieved,
                matched_jobs=excluded.matched_jobs, integration_type=excluded.integration_type,
                configured_status='working', quota_status='ok'""",
                (source[:120], timestamp, timestamp, int(jobs_retrieved), int(matched_jobs), integration_type))

    def commit(self) -> None:
        self.db.commit()

    def close(self) -> None:
        self.db.close()


class PostgresStore(Store):
    def __init__(self, dsn: str):
        import psycopg
        self.psycopg = psycopg
        self.db = psycopg.connect(dsn, autocommit=False)
        with self.db.cursor() as cur:
            cur.execute(f"CREATE TABLE IF NOT EXISTS jobs ({SCHEMA_COLUMNS.replace('INTEGER', 'INT')})")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_pending ON jobs(eligible, notified, first_seen)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_duplicate ON jobs(duplicate_key)")
            cur.execute("""CREATE TABLE IF NOT EXISTS source_health (
                source TEXT PRIMARY KEY,
                consecutive_failures INT NOT NULL DEFAULT 0,
                last_error TEXT,
                last_seen TEXT NOT NULL,
                last_notified_count INT NOT NULL DEFAULT 0,
                last_success TEXT,
                last_failure TEXT,
                jobs_retrieved INT NOT NULL DEFAULT 0,
                matched_jobs INT NOT NULL DEFAULT 0,
                integration_type TEXT,
                configured_status TEXT,
                quota_status TEXT
            )""")
        self.db.commit()

    def count_jobs(self) -> int:
        with self.db.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM jobs")
            return int(cur.fetchone()[0])

    def record(self, job, match) -> bool:
        timestamp = now_utc()
        key = job.stable_id()
        values = {
            "job_key": key, "duplicate_key": duplicate_key(job), "source": job.source,
            "source_id": job.source_id, "company": job.company, "title": job.title,
            "location": job.location, "remote_status": job.workplace, "description": job.description,
            "published_at": job.posted_at, "first_seen": timestamp, "last_seen": timestamp,
            "url": job.url, "canonical_url": job.best_url(), "relevance_score": match.score,
            "match_explanation": match.explanation, "skills": ", ".join(match.skills),
            "eligible": int(match.eligible),
        }
        with self.db.cursor() as cur:
            cur.execute("SELECT 1 FROM jobs WHERE job_key=%(job_key)s FOR UPDATE", values)
            exists = cur.fetchone() is not None
            cur.execute("""INSERT INTO jobs (
                job_key, duplicate_key, source, source_id, company, title, location, remote_status,
                description, published_at, first_seen, last_seen, url, canonical_url, relevance_score,
                match_explanation, skills, eligible
            ) VALUES (
                %(job_key)s, %(duplicate_key)s, %(source)s, %(source_id)s, %(company)s, %(title)s,
                %(location)s, %(remote_status)s, %(description)s, %(published_at)s, %(first_seen)s,
                %(last_seen)s, %(url)s, %(canonical_url)s, %(relevance_score)s, %(match_explanation)s,
                %(skills)s, %(eligible)s
            ) ON CONFLICT (job_key) DO UPDATE SET
                duplicate_key=EXCLUDED.duplicate_key, source=EXCLUDED.source, source_id=EXCLUDED.source_id,
                company=EXCLUDED.company, title=EXCLUDED.title, location=EXCLUDED.location,
                remote_status=EXCLUDED.remote_status, description=EXCLUDED.description,
                published_at=EXCLUDED.published_at, last_seen=EXCLUDED.last_seen, url=EXCLUDED.url,
                canonical_url=EXCLUDED.canonical_url, relevance_score=EXCLUDED.relevance_score,
                match_explanation=EXCLUDED.match_explanation, skills=EXCLUDED.skills, eligible=EXCLUDED.eligible""", values)
        return not exists

    def pending_notifications(self, limit: int) -> list[str]:
        with self.db.cursor() as cur:
            cur.execute("""SELECT MIN(job_key) FROM jobs
                WHERE eligible=1 AND notified=0
                GROUP BY duplicate_key
                ORDER BY MIN(first_seen)
                LIMIT %s""", (limit,))
            return [row[0] for row in cur.fetchall()]

    def mark_notified(self, key: str) -> None:
        with self.db.cursor() as cur:
            cur.execute("UPDATE jobs SET notified=1, notified_at=%s, notification_error=NULL WHERE job_key=%s", (now_utc(), key))

    def mark_notification_failed(self, key: str, error: str) -> None:
        with self.db.cursor() as cur:
            cur.execute("UPDATE jobs SET notification_error=%s WHERE job_key=%s", (error[:500], key))

    def record_source_errors(self, errors: Iterable[str]) -> list[tuple[str, int, str]]:
        alerts = []
        timestamp = now_utc()
        with self.db.cursor() as cur:
            for error in errors:
                source = (error.split(":", 1)[0] or "unknown")[:120]
                cur.execute("""INSERT INTO source_health (source, consecutive_failures, last_error, last_seen, last_notified_count)
                    VALUES (%s, 1, %s, %s, 0)
                    ON CONFLICT (source) DO UPDATE SET
                    consecutive_failures=source_health.consecutive_failures+1,
                    last_error=EXCLUDED.last_error,
                    last_seen=EXCLUDED.last_seen,
                    last_failure=EXCLUDED.last_seen,
                    configured_status='failing'
                    RETURNING consecutive_failures, last_notified_count""", (source, error[:1000], timestamp))
                count, notified = cur.fetchone()
                count, notified = int(count), int(notified)
                if count >= 3 and count not in {notified} and (count in {3, 12, 48} or count % 96 == 0):
                    alerts.append((source, count, error))
                    cur.execute("UPDATE source_health SET last_notified_count=%s WHERE source=%s", (count, source))
        return alerts

    def record_source_successes(self, rows: Iterable[tuple[str, int, int, str]]) -> None:
        timestamp = now_utc()
        with self.db.cursor() as cur:
            for source, jobs_retrieved, matched_jobs, integration_type in rows:
                cur.execute("""INSERT INTO source_health (
                    source, consecutive_failures, last_error, last_seen, last_notified_count,
                    last_success, last_failure, jobs_retrieved, matched_jobs, integration_type,
                    configured_status, quota_status
                ) VALUES (%s,0,NULL,%s,0,%s,NULL,%s,%s,%s,'working','ok')
                ON CONFLICT(source) DO UPDATE SET
                    consecutive_failures=0, last_error=NULL, last_seen=EXCLUDED.last_seen,
                    last_success=EXCLUDED.last_success, jobs_retrieved=EXCLUDED.jobs_retrieved,
                    matched_jobs=EXCLUDED.matched_jobs, integration_type=EXCLUDED.integration_type,
                    configured_status='working', quota_status='ok'""",
                    (source[:120], timestamp, timestamp, int(jobs_retrieved), int(matched_jobs), integration_type))

    def commit(self) -> None:
        self.db.commit()

    def close(self) -> None:
        self.db.close()


def connect(path: str | None = None) -> Store:
    dsn = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    if dsn:
        return PostgresStore(dsn)
    return SQLiteStore(path or os.getenv("SQLITE_DB_PATH", "jobs.sqlite3"))


def record(db: Store, key, job, eligible):
    """Backward-compatible helper for older tests/scripts."""
    LegacyMatch = type("LegacyMatch", (), {
        "score": 100 if eligible else 0,
        "explanation": "",
        "skills": (),
        "eligible": eligible,
    })
    return db.record(job, LegacyMatch)


def mark_notified(db: Store, key: str):
    db.mark_notified(key)
