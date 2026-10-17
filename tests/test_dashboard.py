import json
import unittest
import tempfile
from pathlib import Path

from jobmonitor.dashboard import _jobs, _html, _health, generate


def row(source, title='Software Engineer I', published='', company='Acme'):
    return (company, title, 'Canada', 'Remote', source,
            'https://example.com/jobs/123?utm_source=list', '', 80, 'role matches',
            'python', published, '2026-10-17', '2026-10-17', 0, 1, 'Description')


class DashboardTests(unittest.TestCase):
    def test_employer_and_aggregator_share_one_progress_key(self):
        jobs = _jobs([row('simplify', 'Software Engineer 1'), row('greenhouse')])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['source'], 'greenhouse')
        self.assertEqual(set(jobs[0]['sources']), {'simplify', 'greenhouse'})
        self.assertEqual(jobs[0]['id'], _jobs([row('greenhouse')])[0]['id'])

    def test_job_content_cannot_escape_the_json_script(self):
        dangerous = '</script><script>alert(1)</script>'
        page = _html(_jobs([row('greenhouse', company=dangerous)]), [])
        data = page.split('<script id="job-data" type="application/json">')[1].split('</script>')[0]
        self.assertNotIn('</script>', data)
        self.assertEqual(json.loads(data)[0]['company'], dangerous)

    def test_invalid_application_scheme_is_not_published(self):
        data = list(row('greenhouse'))
        data[5] = 'javascript:alert(1)'
        self.assertEqual(_jobs([data]), [])

    def test_public_source_activity_omits_raw_request_errors(self):
        health = _health([('feed', 'failing', 'indirect', 0, 0, 1, '', '',
                           'Request failed https://example.com?api_key=private-token', '')])
        self.assertNotIn('private-token', _html([], health))

    def test_resume_readers_are_packaged_beside_the_generated_page(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'index.html'
            generate(str(Path(folder) / 'missing.sqlite3'), str(output))
            for filename in ['pdf.min.mjs', 'pdf.worker.min.mjs', 'mammoth.browser.min.js']:
                self.assertTrue((Path(folder) / 'vendor' / filename).is_file())
            page = output.read_text(encoding='utf8')
            self.assertIn('id="resumes-workspace"', page)
            self.assertNotIn('__HUB_MATCHING__', page)
            self.assertNotIn('__HUB_RESUMES__', page)
