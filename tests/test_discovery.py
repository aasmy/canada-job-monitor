import unittest
from jobmonitor.discovery import parse_feed,detect_source
from jobmonitor.filtering import evaluate
import yaml

CONFIG=yaml.safe_load(open('config.yaml',encoding='utf8'))
class DiscoveryTests(unittest.TestCase):
    def test_feed(self):
        feed='''<rss><channel><item><title>Junior Software Engineer</title><link>https://simplify.jobs/a/job-123</link><description>Canada, remote</description></item></channel></rss>'''
        result=parse_feed(feed)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].source,'simplify')
        self.assertIn('REVIEW',evaluate(result[0],CONFIG)[1])
    def test_atom(self):
        atom='<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Software Developer</title><link href="https://example.com/job"/><summary>Vancouver</summary></entry></feed>'
        self.assertEqual(len(parse_feed(atom)),1)
    def test_target(self):
        self.assertEqual(detect_source('https://www.linkedin.com/jobs/view/123'),'linkedin')
if __name__=='__main__':unittest.main()
