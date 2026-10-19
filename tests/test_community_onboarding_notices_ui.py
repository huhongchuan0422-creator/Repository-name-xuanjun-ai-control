"""No-listener DOM contract for private original application result notices."""
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
class OnboardingNoticesDOM(unittest.TestCase):
    def test_applicant_notice_context_and_read_acknowledgement(self):self.run_page('/merchant/join')
    def test_reviewer_page_does_not_borrow_applicant_notice_access(self):self.run_page('/merchant/review')
    def run_page(self,path):
        subprocess.run(['node',str(ROOT/'tests/community_onboarding_notices_dom.cjs'),
            str(ROOT/'demos/community-stage/onboarding.js'),str(ROOT/'demos/community-stage/onboarding.html'),path],check=True,timeout=30)
