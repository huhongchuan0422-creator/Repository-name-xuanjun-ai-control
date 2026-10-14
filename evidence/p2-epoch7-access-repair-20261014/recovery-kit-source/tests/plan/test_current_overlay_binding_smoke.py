"""Local assembled-source smoke. Synthetic provenance; never emits a package."""
import importlib.util
import json
import pathlib
import unittest
import epoch7_bindings as binding
from test_epoch7_bindings import reconciliation_fixture

ROOT=pathlib.Path(__file__).resolve().parents[2]
CANDIDATE=ROOT/'p2-epoch7-repair'
FROZEN=ROOT/'p2-epoch5-repair/runtime-v4-extracted/xuanjun-p2-package'

class CurrentOverlaySmoke(unittest.TestCase):
    def test_current_explicit_overlay_and24_bindings(self):
        spec=importlib.util.spec_from_file_location('local_runtime_overlay_builder',str(CANDIDATE/'package-candidate/build_runtime_overlay.py'))
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        paths={}
        for name in ('ledger_read_client','ledger_read_projection','ledger_read_transport',
                     'ledger_server_identity','native_ledger_bridge','owner_dashboard',
                     'root_broker','uk_owner_callback_core'):
            paths['stage1/'+name+'.py']=CANDIDATE/'projection-candidate'/ (name+'.py')
        for name in ('native_peer_identity','owner_process_identity'):
            paths['stage1/'+name+'.py']=CANDIDATE/'identity-candidate/stage1'/(name+'.py')
        paths['stage1/ledger_service.py']=CANDIDATE/'service-wiring-candidate/ledger_service.py'
        for name in ('ledger.mjs','plugin.mjs'):
            paths['plugins/p2-native-controller/'+name]=CANDIDATE/'plugin-candidate'/name
        for name in ('xuanjun-github-intake.service','xuanjun-ledger.service',
                     'xj-root-broker.socket','xj-root-broker.service',
                     'uk-owner-workbench/xuanjun-uk-owner-dashboard.service'):
            paths['deploy/'+name]=CANDIDATE/'identity-candidate/unit-overlay/deploy'/name
        paths['deploy/p2-native-ledger-client.json.template']=CANDIDATE/'projection-candidate/deploy/p2-native-ledger-client.json.template'
        overlays={p:{'source_path':str(source),'sha256':binding.sha(source.read_bytes())} for p,source in paths.items()}
        prepared=builder.prepare(str(FROZEN),overlays)
        oldraw=(FROZEN/'deploy/integration-manifest.json').read_bytes()
        oldpayload={p:(FROZEN/p).read_bytes() for p in json.loads(oldraw.decode())['files']}
        plan=(ROOT/'p2-epoch5-repair/compiled-plan-v4.private.json').read_bytes()
        compiled=binding.compile_retained_bindings(plan,
            oldraw,oldpayload,prepared['manifest_bytes'],prepared['payload'],'1'*40,'2'*40,
            control_reconciliation=reconciliation_fixture(plan))
        self.assertEqual(len(compiled['rendered_targets']),24)
        self.assertEqual(prepared['counts']['deleted'],0)
        self.assertEqual(prepared['counts']['added'],5)
        self.assertEqual(prepared['counts']['final'],107)
        self.assertFalse(compiled['install_admission'])
        self.assertIn(b'SupplementaryGroups=xuanjun-dispatcher',compiled['rendered_targets']['/etc/systemd/system/xuanjun-ledger.service'])
        self.assertIn(b'DirectoryMode=0711',compiled['rendered_targets']['/etc/systemd/system/xj-root-broker.socket'])

if __name__=='__main__':unittest.main()
