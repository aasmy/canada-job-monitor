import tempfile
import unittest
from pathlib import Path

import yaml

from jobmonitor.filtering import analyze
from jobmonitor.notify import format_telegram, freshness
from jobmonitor.sources import Job, canonicalize_url
from jobmonitor.store import connect


CONFIG = yaml.safe_load(open("config.yaml", encoding="utf8"))


class StorageNotifyTests(unittest.TestCase):
    def test_canonical_url_removes_tracking(self):
        self.assertEqual(
            canonicalize_url("https://www.example.com/job/123/?utm_source=x&ok=1#top"),
            "https://example.com/job/123?ok=1",
        )

    def test_sqlite_pending_deduplicates_same_company_title_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = connect(str(Path(tmp) / "jobs.sqlite3"))
            try:
                first = Job("greenhouse", "1", "Acme", "Junior Software Developer", "Vancouver, BC", "https://boards.greenhouse.io/acme/jobs/1", "Python")
                second = Job("lever", "2", "Acme", "Junior Software Developer", "Vancouver, BC", "https://jobs.lever.co/acme/2", "Python")
                match = analyze(first, CONFIG)
                store.record(first, match)
                store.record(second, match)
                store.commit()
                self.assertEqual(len(store.pending_notifications(10)), 1)
            finally:
                store.close()

    def test_source_health_tracks_success_and_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = connect(str(Path(tmp) / "jobs.sqlite3"))
            try:
                store.record_source_successes([("hackernews", 90, 2, "direct")])
                alerts = store.record_source_errors(["rss-feed: Timeout"])
                store.commit()
                self.assertEqual(alerts, [])
                self.assertEqual(store.record_source_errors(["rss-feed: Timeout"]), [])
                alerts = store.record_source_errors(["rss-feed: Timeout"])
                self.assertEqual(alerts[0][0], "rss-feed")
            finally:
                store.close()

    def test_telegram_html_is_escaped(self):
        job = Job("test", "1", "A < B", "Junior Software Developer", "Remote - Canada", "https://example.com", "Python & React")
        text = format_telegram(job, analyze(job, CONFIG))
        self.assertIn("A &lt; B", text)
        self.assertIn("python", text)

    def test_unknown_publication_date_is_not_recent(self):
        self.assertEqual(freshness(""), "Publication date unknown")


if __name__ == "__main__":
    unittest.main()
