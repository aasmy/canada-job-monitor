import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from jobmonitor.dashboard import _freshness, _jobs, _html
from jobmonitor.discovery import parse_feed
from jobmonitor.freshness import age_days, is_recent, alert_allowed
from jobmonitor.main import run, load_config
from jobmonitor.sources import Job
from jobmonitor.store import SQLiteStore
from jobmonitor.filtering import analyze


class FreshnessTests(unittest.TestCase):
    def test_discovery_today_never_makes_undated_job_fresh(self):
        self.assertEqual(_freshness('', datetime.now(timezone.utc).isoformat())[1], 'unknown')

    def test_old_job_newly_discovered_stays_old(self):
        old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        self.assertEqual(_freshness(old, datetime.now(timezone.utc).isoformat())[1], 'older')
        self.assertFalse(alert_allowed(Job('ashby', '1', 'A', 'Developer', 'Canada', 'https://example.com', posted_at=old), {}))

    def test_recency_boundaries(self):
        now = datetime(2026, 10, 17, tzinfo=timezone.utc)
        self.assertTrue(is_recent((now - timedelta(days=7)).isoformat(), now=now))
        self.assertFalse(is_recent((now - timedelta(days=7, seconds=1)).isoformat(), now=now))
        for value in ['', 'invalid', (now + timedelta(days=1)).isoformat()]:
            self.assertIsNone(age_days(value, now))

    def test_google_alert_entry_date_is_not_job_publication(self):
        feed = '''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
            <title>Software Engineer</title><link href="https://example.com/job"/>
            <updated>2026-10-17T00:00:00Z</updated></entry></feed>'''
        self.assertEqual(parse_feed(feed)[0].posted_at, '')

    def test_unknown_dates_require_explicit_alert_opt_in(self):
        job = Job('simplify', '1', 'A', 'Developer', 'Canada', 'https://example.com')
        self.assertFalse(alert_allowed(job, {}))
        self.assertTrue(alert_allowed(job, {'notifications': {'include_unknown_publication_dates': True}}))

    def test_dashboard_discards_legacy_feed_dates(self):
        row = ('A', 'Developer', 'Canada', '', 'linkedin', 'https://example.com', '',
               80, '', '', datetime.now(timezone.utc).isoformat(), '2026-10-17', '', 0, 1)
        job = _jobs([row])[0]
        self.assertEqual(job['published'], '')
        self.assertEqual(job['freshnessGroup'], 'unknown')
        page = _html([job], [])
        self.assertIn('value="last7" selected', page)
        self.assertIn('First discovered:', page)
        self.assertNotIn('Published or seen', page)

    def test_pending_old_and_undated_jobs_do_not_block_fresh_alert(self):
        config = load_config('config.yaml')
        config['monitor']['max_notifications_per_run'] = 1
        now = datetime.now(timezone.utc)
        old = Job('ashby', 'a', 'A', 'Junior Software Developer', 'Canada', 'https://example.com/a',
                  posted_at=(now - timedelta(days=100)).isoformat())
        unknown = Job('ashby', 'b', 'B', 'Junior Software Developer', 'Canada', 'https://example.com/b')
        fresh = Job('ashby', 'c', 'C', 'Junior Software Developer', 'Canada', 'https://example.com/c',
                    posted_at=(now - timedelta(hours=1)).isoformat())
        store = SQLiteStore(':memory:')
        store.record(old, analyze(old, config))
        store.commit()
        with patch('jobmonitor.main.load_config', return_value=config), \
             patch('jobmonitor.main.discover', return_value=([old, unknown, fresh], [], 1)), \
             patch('jobmonitor.main.connect', return_value=store), \
             patch.dict('os.environ', TELEGRAM_BOT_TOKEN='test', TELEGRAM_CHAT_ID='test'), \
             patch('jobmonitor.main.send_telegram', return_value={'ok': True, 'result': {'message_id': 1}}) as send:
            self.assertEqual(run([]), 0)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[2].source_id, 'c')
