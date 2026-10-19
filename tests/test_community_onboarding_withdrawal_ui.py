"""No-listener DOM checks for the Owner-approved original withdrawal flow."""
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
class OnboardingWithdrawalDOM(unittest.TestCase):
    def test_applicant_withdrawal_confirmation_terminal_and_stale_responses(self):self.run_page('/merchant/join')
    def test_reviewer_cannot_withdraw_applicant_application(self):self.run_page('/merchant/review')
    def run_page(self,path):
        subprocess.run(['node',str(ROOT/'tests/community_onboarding_withdrawal_dom.cjs'),
            str(ROOT/'demos/community-stage/onboarding.js'),str(ROOT/'demos/community-stage/onboarding.html'),path],check=True,timeout=30)
