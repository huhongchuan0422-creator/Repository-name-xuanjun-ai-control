"""Original generated navigation closure; no browser or business execution."""
from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class PlatformHomeNavigation(unittest.TestCase):
 def test_all_original_generated_platform_modules_have_home_links(self):
  subprocess.run(['node',str(ROOT/'tests/community_platform_home_reachability.cjs'),str(ROOT/'demos/community-stage/ui-preview/preview.js'),str(ROOT/'demos/community-stage/ui-preview/sources.js')],check=True,timeout=30)
