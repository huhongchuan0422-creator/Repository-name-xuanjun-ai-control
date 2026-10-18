import os
import tempfile
import unittest
from static_database_defaults import Defaults

class DefaultTests(unittest.TestCase):
    def values(self,s):return Defaults(s,'/opt/trading-system/database/connection.py','/opt/trading-system').factories()
    def test_literal(self):self.assertEqual(self.values('from sqlalchemy import create_engine\ne=create_engine("sqlite:///a.db")'),[(2,'sqlite:///a.db')])
    def test_alias(self):self.assertEqual(self.values('import sqlalchemy as sa\ne=sa.create_engine("sqlite:///a.db")'),[(2,'sqlite:///a.db')])
    def test_path_default(self):
        s='from pathlib import Path\nimport os\nfrom sqlalchemy import create_engine\nROOT=Path(__file__).resolve().parents[1]\nURL=os.getenv("TRADING_DATABASE_URL",f"sqlite:///{ROOT / \'data\' / \'trading.db\'}")\ne=create_engine(URL)'
        self.assertEqual(self.values(s),[(6,'sqlite:////opt/trading-system/data/trading.db')])
    def test_simple_function(self):self.assertEqual(self.values('from sqlalchemy import create_engine\ndef url():\n return "sqlite:///a.db"\ne=create_engine(url())'),[(4,'sqlite:///a.db')])
    def test_local(self):self.assertEqual(self.values('from sqlalchemy import create_engine\ndef engine():\n url="sqlite:///a.db"\n return create_engine(url)'),[(4,'sqlite:///a.db')])
    def test_or_default(self):self.assertEqual(self.values('import os\nfrom sqlalchemy import create_engine\ne=create_engine(os.getenv("TRADING_DATABASE_URL") or "sqlite:///a.db")'),[(3,'sqlite:///a.db')])
    def test_other_environment_not_assumed_absent(self):self.assertEqual(self.values('import os\nfrom sqlalchemy import create_engine\ne=create_engine(os.getenv("SECRET","sqlite:///a.db"))'),[(3,None)])
    def test_no_arbitrary_call(self):
        with tempfile.TemporaryDirectory() as d:
            p=d+'/must-not-exist'
            s=f'from sqlalchemy import create_engine\nimport os\ne=create_engine(os.system("touch {p}"))'
            self.assertEqual(self.values(s),[(3,None)]);self.assertFalse(os.path.exists(p))
    def test_no_source_import(self):self.assertEqual(self.values('import missing_business_module\nfrom sqlalchemy import create_engine\ne=create_engine("sqlite:///a.db")'),[(3,'sqlite:///a.db')])
    def test_no_comprehension(self):self.assertEqual(self.values('from sqlalchemy import create_engine\ne=create_engine([x for x in "secret"])'),[(2,None)])
    def test_conditional_not_resolved(self):self.assertEqual(self.values('from sqlalchemy import create_engine\ne=create_engine("sqlite:///a.db" if True else "sqlite:///b.db")'),[(2,None)])
    def test_keywords_not_evaluated(self):self.assertEqual(self.values('from sqlalchemy import create_engine\ne=create_engine(str(x="secret"))'),[(2,None)])
    def test_nested_function_rejected(self):self.assertEqual(self.values('from sqlalchemy import create_engine\ndef url():\n if True:return "sqlite:///a.db"\ne=create_engine(url())'),[(4,None)])
    def test_arbitrary_attribute_rejected(self):self.assertEqual(self.values('from sqlalchemy import create_engine\ne=create_engine("x".__class__)'),[(2,None)])

if __name__=='__main__':unittest.main()
