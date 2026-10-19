"""No-listener DOM contract for original applicant and reviewer history pages."""
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
class OnboardingHistoryDOM(unittest.TestCase):
    def test_applicant_history_context(self):self.run_page('/merchant/join')
    def test_reviewer_history_context(self):self.run_page('/merchant/review')
    def run_page(self,path):
        subprocess.run(['node',str(ROOT/'tests/community_onboarding_history_dom.cjs'),
            str(ROOT/'demos/community-stage/onboarding.js'),str(ROOT/'demos/community-stage/onboarding.html'),path],check=True,timeout=30)
