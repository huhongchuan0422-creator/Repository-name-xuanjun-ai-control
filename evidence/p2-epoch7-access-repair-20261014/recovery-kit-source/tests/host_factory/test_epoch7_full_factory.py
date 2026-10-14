"""Genuine pure whole-factory success; no host effects or compiler mocks."""
import copy
import unittest
from unittest import mock

import epoch7_host_factory as f
import epoch7_delta as d
import epoch7_bindings as bindings
import epoch7_openclaw_recipe as oc
import epoch7_quiet_startup as quiet
from test_epoch7_full_factory_fixture import make_seed


class FullFactoryTests(unittest.TestCase):
    def setUp(self):self.seed=make_seed()
    def prepare(self):
        # Sole test mapping: private historical sidefile preimage is unavailable
        # in the public kit. All real compilers and current-source pins stay on.
        with mock.patch.object(bindings,'RETAINED_NATIVE_SHA',f.sha(self.seed['native_before'])):
            return f.prepare_host_inputs(self.seed)
    def test_actual107_runtime_whole_compiler_and_seventeen_views(self):
        original=bindings.RETAINED_NATIVE_SHA
        before=f.input_digest(self.seed);result=self.prepare()
        self.assertEqual(bindings.RETAINED_NATIVE_SHA,original)
        self.assertEqual(result['state'],'COMPILED_NOT_ADMITTED');self.assertEqual(result['unresolved'],[])
        self.assertFalse(result['install_admission']);inputs=result['inputs']
        self.assertEqual(f.input_digest(self.seed),before)
        self.assertEqual(len(inputs['source_payloads']),107)
        self.assertEqual(len(inputs['resource_views']),17);self.assertEqual(len(inputs['unit_checkpoints']),17)
        reader=object.__new__(quiet.BoundedQuietStartup);reader.relay_metadata=None
        reader.bind_resource_views(inputs['resource_views'])
        self.assertEqual(reader.relay_metadata['uid'],0)
        blocks=inputs['service_role_contract']['units']
        self.assertEqual(set(blocks),{'nginx.service','xuanjun-development-dispatcher.service',oc.GATEWAY,oc.RELAY})
        self.assertEqual(blocks[oc.GATEWAY]['quiet_startup'],blocks[oc.RELAY]['quiet_startup'])
        root=blocks[oc.GATEWAY]['quiet_startup']['package_root']
        for view in inputs['resource_views']:
            pins={row['path']:row for row in view['historical']}
            for name,pin in oc.SOURCE_HASHES.items():self.assertEqual(pins[root+'/'+name]['sha256'],pin)
            self.assertIn('/etc/nginx/mime.types',pins)
        with mock.patch.object(bindings,'RETAINED_NATIVE_SHA',f.sha(self.seed['native_before'])):
            contract=f.compile_host_contract(inputs)
            self.assertEqual(contract,f.compile_host_contract(copy.deepcopy(inputs)))
        self.assertEqual(set(contract),{'host_contract','resource_observer','live_controls'})
        self.assertEqual(contract['live_controls']['schema'],2)
        self.assertEqual(contract['host_contract']['production_acceptance'],'PENDING')
    def test_historical_private_pin_is_not_relaxed_in_production(self):
        with self.assertRaisesRegex(ValueError,'NATIVE_RETAINED_BYTES'):f.prepare_host_inputs(self.seed)
        with mock.patch.object(bindings,'RETAINED_NATIVE_SHA','0'*64):
            with self.assertRaisesRegex(ValueError,'NATIVE_RETAINED_BYTES'):f.prepare_host_inputs(self.seed)
    def test_leaf_probe_cannot_replace_original_policy_or_observation(self):
        for case in ('policy','observation','cleanup'):
            value=copy.deepcopy(self.seed['observation'])
            if case=='policy':value['finite_probe']['policy']['nonce']='b'*32
            elif case=='observation':
                value['unit_metadata']['sections']['native_gateway']['evidence']['gateway_identity']['sha256']='0'*64
                value['unit_metadata_sha256']=d.digest(value['unit_metadata'])
            else:value['finite_probe']['result']['cleanup'][0]['status']='UNKNOWN'
            with self.subTest(case=case),self.assertRaises(ValueError):f.validated_finite_probe(value)
    def test_missing_probe_clean_hold_before_native_pin_mapping(self):
        self.seed['observation'].pop('finite_probe')
        result=f.prepare_host_inputs(self.seed)
        self.assertEqual(result['state'],'HOLD');self.assertIsNone(result['inputs'])
        self.assertFalse(result['install_admission'])
    def test_false_quiet_predicate_cannot_be_source_compiled(self):
        value=self.seed['observation']['openclaw_profile']
        value['recipe_evidence']['quiet_bootstrap']['config_projection']['proxy_enabled']=True
        self.seed['observation']['openclaw_profile_sha256']=d.digest(value)
        with self.assertRaisesRegex(ValueError,'QUIET_CONFIG'):self.prepare()
    def test_precomputed_future_service_or_resource_policy_is_not_authority(self):
        inputs=self.prepare()['inputs'];inputs['resource_views'][15]['historical'][0]['sha256']='0'*64
        with mock.patch.object(bindings,'RETAINED_NATIVE_SHA',f.sha(self.seed['native_before'])):
            with self.assertRaisesRegex(ValueError,'SOURCE_DERIVED_COMPLETE_RESOURCE_VIEWS|UNREVIEWED_CROSS_PHASE_MUTATION'):f.compile_host_contract(inputs)
    def test_timer_raw_bytes_and_source_bytes_are_compared_without_json_coercion(self):
        inputs=self.prepare()['inputs']
        key=next(iter(inputs['timer_raw_baseline']));inputs['timer_raw_baseline'][key]+=b'\n'
        with mock.patch.object(bindings,'RETAINED_NATIVE_SHA',f.sha(self.seed['native_before'])):
            with self.assertRaisesRegex(ValueError,'DERIVED_OBSERVATION_FIELDS'):f.compile_host_contract(inputs)

    def test_changed_source_bytes_cannot_reuse_derived_facts(self):
        inputs=self.prepare()['inputs'];name=next(iter(inputs['service_facts']['source_bytes']))
        inputs['service_facts']['source_bytes'][name]+=b'\n# fixture drift\n'
        with mock.patch.object(bindings,'RETAINED_NATIVE_SHA',f.sha(self.seed['native_before'])):
            with self.assertRaisesRegex(ValueError,'MEASURED_SERVICE_FACTS'):f.compile_host_contract(inputs)

if __name__=='__main__':unittest.main()
