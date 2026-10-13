import unittest
import yaml
from jobmonitor.sources import Job
from jobmonitor.filtering import evaluate

with open("config.yaml", encoding="utf-8") as fh:
    CONFIG = yaml.safe_load(fh)


def job(title, location, description=""):
    return Job("test", "1", "Company", title, location, "https://example.com/job", description)

class FilteringTests(unittest.TestCase):
    def test_canadian_junior(self):
        self.assertTrue(evaluate(job("Junior Software Developer", "Vancouver, BC", "0-2 years experience"), CONFIG)[0])

    def test_canada_remote(self):
        self.assertTrue(evaluate(job("Software Engineer", "Remote - Canada"), CONFIG)[0])

    def test_ambiguous_remote_not_accepted(self):
        self.assertFalse(evaluate(job("Software Engineer", "Remote - USA"), CONFIG)[0])

    def test_senior_excluded(self):
        self.assertFalse(evaluate(job("Senior Software Engineer", "Toronto, Canada"), CONFIG)[0])

    def test_experience_excluded(self):
        self.assertFalse(evaluate(job("Backend Developer", "Canada", "5+ years of experience"), CONFIG)[0])

    def test_role_excluded(self):
        self.assertFalse(evaluate(job("Product Manager", "Canada"), CONFIG)[0])

if __name__ == "__main__":
    unittest.main()
