import unittest
from unittest.mock import Mock

from jobmonitor.sources import greenhouse, lever, ashby
from jobmonitor.simplify import parse_list
from jobmonitor.filtering import analyze
from jobmonitor.store import SQLiteStore
from jobmonitor.sources import Job
import yaml


class CompanySourcesTests(unittest.TestCase):
    def session(self, payload):
        session = Mock()
        session.get.return_value.json.return_value = payload
        return session

    def test_greenhouse_update_is_not_publication(self):
        session = self.session({'jobs': [{'id': 123, 'title': 'Software Engineer',
            'location': {'name': 'Canada'}, 'absolute_url': 'https://example.com/jobs/123',
            'updated_at': '2026-10-01T00:00:00Z'}]})
        job = list(greenhouse(session, 'affirm', 'Affirm'))[0]
        self.assertEqual(job.posted_at, '')
        self.assertEqual(job.company, 'Affirm')

    def test_lever_includes_required_qualifications(self):
        session = self.session([{'id': 'abc', 'text': 'Software Developer',
            'categories': {'location': 'Toronto, Canada'}, 'hostedUrl': 'https://example.com/abc',
            'lists': [{'text': 'Requirements', 'content': '<li>5 years of experience</li>'}]}])
        job = list(lever(session, 'pointclickcare', 'PointClickCare'))[0]
        self.assertIn('5 years of experience', job.description)

    def test_ashby_keeps_canada_secondary_location(self):
        session = self.session({'jobs': [{'id': 'abc', 'title': 'Software Developer',
            'location': 'Remote', 'secondaryLocations': [{'location': 'Canada'}],
            'isRemote': True, 'jobUrl': 'https://example.com/abc',
            'publishedAt': '2026-10-01T00:00:00Z'}]})
        job = list(ashby(session, 'cohere', 'Cohere'))[0]
        self.assertIn('Canada', job.location)
        self.assertTrue(job.posted_at)

    def test_simplify_prefers_employer_url_and_unknown_date(self):
        document = '''<table><tr><td>Acme</td><td>Software Engineer I</td>
            <td>Toronto, Canada</td><td><a href="https://employer.com/jobs/123">Apply</a>
            <a href="https://simplify.jobs/p/123">Simplify</a></td><td>0d</td></tr></table>'''
        job = parse_list(document)[0]
        self.assertEqual(job.url, 'https://employer.com/jobs/123')
        self.assertEqual(job.posted_at, '')

    def test_simplify_rejects_format_change(self):
        with self.assertRaises(ValueError):
            parse_list('Something changed')

    def test_company_boilerplate_does_not_make_overseas_role_canadian(self):
        with open('config.yaml', encoding='utf8') as fh:
            config = yaml.safe_load(fh)
        job = Job('ashby', 'overseas', 'Acme', 'Software Engineer', 'London, UK',
                  'https://example.com/jobs/overseas', 'Our company has offices in Canada.')
        self.assertFalse(analyze(job, config).eligible)

    def test_analyst_does_not_match_company_software_description(self):
        with open('config.yaml', encoding='utf8') as fh:
            config = yaml.safe_load(fh)
        job = Job('lever', 'analyst', 'Acme', 'Billing Analyst', 'Canada',
                  'https://example.com/jobs/analyst', 'Collaborate with a software developer.')
        self.assertFalse(analyze(job, config).eligible)

    def test_same_employer_url_does_not_alert_twice(self):
        with open('config.yaml', encoding='utf8') as fh:
            config = yaml.safe_load(fh)
        store = SQLiteStore(':memory:')
        try:
            first = Job('greenhouse', '123', 'Affirm', 'Software Engineer I', 'Canada',
                        'https://example.com/jobs/123')
            other = Job('simplify', '123', 'Affirm', 'Software Engineer 1', 'Toronto, Canada',
                        'https://example.com/jobs/123?ref=Simplify')
            for job in [first, other]:
                store.record(job, analyze(job, config))
            pending = store.pending_notifications(10)
            self.assertEqual(len(pending), 1)
            store.mark_notified(pending[0])
            self.assertEqual(store.pending_notifications(10), [])
        finally:
            store.close()
