"""Original UI sources, no socket/provider/funds execution."""
from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class FinanceUIContract(unittest.TestCase):
 def run_node(self,name,source,html):
  subprocess.run(['node',str(ROOT/'tests'/name),str(ROOT/'demos/community-stage'/source),str(ROOT/'demos/community-stage'/html),'/merchant/review'],check=True,timeout=30)
 def test_financial_selection(self):self.run_node('community_finance_selection_dom.cjs','workbench.js','workbench.html')
 def test_financial_cards(self):self.run_node('community_finance_cards_dom.cjs','workbench.js','workbench.html')
 def test_reviewer_selection(self):self.run_node('community_review_selection_dom.cjs','onboarding.js','onboarding.html')

 def test_platform_selection(self):subprocess.run(['node',str(ROOT/'tests/community_platform_selection_dom.mjs')],check=True,timeout=30)

 def test_platform_order_cards(self):subprocess.run(['node',str(ROOT/'tests/community_platform_orders_dom.cjs'),str(ROOT/'demos/community-stage/communities.js'),str(ROOT/'demos/community-stage/admin-shell.js')],check=True,timeout=30)

 def test_finance_navigation(self):self.run_node('community_finance_navigation_dom.cjs','workbench.js','workbench.html')

 def test_platform_review_cards(self):subprocess.run(['node',str(ROOT/'tests/community_platform_review_dom.cjs'),str(ROOT/'demos/community-stage/communities.js'),str(ROOT/'demos/community-stage/admin-shell.js')],check=True,timeout=30)

 def test_finance_read_semantics(self):self.run_node('community_finance_read_semantics_dom.cjs','workbench.js','workbench.html')
