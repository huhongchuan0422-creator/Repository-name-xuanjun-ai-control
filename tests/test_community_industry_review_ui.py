import subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class IndustryReviewUi(unittest.TestCase):
    def test_explicit_original_reviewer_conditions(self):
        subprocess.run(['node',str(ROOT/'tests/community_industry_review_dom.cjs'),str(ROOT/'demos/community-stage/onboarding.js')],check=True,timeout=30)
