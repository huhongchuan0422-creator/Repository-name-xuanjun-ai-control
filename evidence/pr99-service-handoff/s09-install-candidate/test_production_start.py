import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
s=importlib.util.spec_from_file_location('production_start',Path(__file__).with_name('production_start.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class StartTests(unittest.TestCase):
 def test_units_dedicated_identity_and_final_only(self):
  units=m.units('xuanjun-s07');self.assertEqual(len(units),3)
  for b in units.values():
   self.assertIn(b'User=xuanjun-s07',b);self.assertIn(b'domestic-final-v1/rootfs',b)
   self.assertNotIn(b'domestic-r2',b);self.assertNotIn(b'[Install]',b)
   self.assertIn(b'NoNewPrivileges=yes',b)
 def test_shared_copy_identity_rejected(self):
  with self.assertRaisesRegex(RuntimeError,'DEDICATED_IDENTITY_NAME'):m.units('nobody')
 def test_foreign_unit_never_stopped(self):
  with patch.object(m.os.path,'lexists',lambda p:True),patch.object(m,'read',lambda p:b'foreign'),patch.object(m,'ctl') as ctl:
   with self.assertRaisesRegex(RuntimeError,'ROLLBACK_FOREIGN_UNIT'):m.rollback_owned({'x.service':b'owned'})
   ctl.assert_not_called()
 def test_start_failure_preserves_data_and_stops_owned(self):
  with tempfile.TemporaryDirectory() as d:
   state=Path(d)/'state';p={'unit_hashes':{'x.service':m.sha(b'owned')},'source_writer_fence_receipt_sha256':'a'*64,'expires_at':99999999999}
   with patch.object(m,'STATE',state),patch.object(m,'admit',lambda:(p,{'x.service':b'owned'})),patch.object(m,'stopped',lambda n:True),patch.object(m,'health',lambda port:None),patch.object(m,'read',lambda p:b'permit'),patch.object(m,'create',lambda p,b,mode=0o600:None),patch.object(m,'ctl',side_effect=RuntimeError('injected')),patch.object(m,'rollback_owned',return_value={'status':'OWNED_APPS_STOPPED_DATA_PRESERVED'}) as rollback,patch.object(m.os.path,'lexists',lambda p:False):
    with self.assertRaisesRegex(RuntimeError,'injected'):m.start()
    rollback.assert_called_once_with({'x.service':b'owned'})
if __name__=='__main__':unittest.main()
