import subprocess
import unittest
from pathlib import Path

class WorkflowSyntaxTests(unittest.TestCase):
    def test_yaml_parse_and_every_run_block_bash_syntax(self):
        script=Path(__file__).with_name("validate_workflow_syntax.py")
        result=subprocess.run(["python",str(script)],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+"\n"+result.stderr)
        self.assertIn("WORKFLOW_YAML_PARSE=PASS",result.stdout)
        self.assertIn("WORKFLOW_RUN_BLOCKS_BASH_N=",result.stdout)

if __name__=="__main__": unittest.main()
