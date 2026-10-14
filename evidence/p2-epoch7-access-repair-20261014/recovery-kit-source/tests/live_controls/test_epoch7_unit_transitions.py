import copy
import os
import pathlib
import sys
import unittest
HERE=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from test_epoch7_service_roles import fixture2
from test_epoch7_live_controls import process_view,h
import epoch7_live_controls as live
import epoch7_unit_transitions as ut
import epoch7_service_roles as sr


class UnitTransitionTests(unittest.TestCase):
    def setUp(self):
        self.ctx,self.c,self.active=fixture2()
        self.unit='xuanjun-uk-owner-callback.service';self.path=ut.ROOT+self.unit
        before=copy.deepcopy(self.c['checkpoints'][0]['units'][self.unit]['properties'])
        before.update(LoadState='masked',UnitFileState='masked')
        for point in self.c['checkpoints'][:15]:point['units'][self.unit]['properties']=copy.deepcopy(before)
        after=dict(before,LoadState='loaded',UnitFileState='disabled')
        self.c['unit_transition_contract']={'schema':1,'targets':{self.path:{'uid':0,'gid':0,'mode':420,'sha256':h('unit')}},
            'units':{self.unit:{'before':before,'reloaded':after}}}
        # process_view is a schema1 fixture generator; stopped schema2 needs no
        # symbolic main role lookup, so generate with a schema1 copy.
        temporary=copy.deepcopy(self.c);temporary['schema']=1
        temporary.pop('service_role_contract');temporary.pop('unit_transition_contract')
        self.v=process_view(temporary,5)
        self.v['service_role_evidence']={'context_sha256':None,'units':{},'processes':{}}
        row={'kind':'FILE','sha256':h('unit'),'uid':0,'gid':0,'mode':420,'dev':8,'ino':100,'nlink':1,
             'size':100,'mtime_ns':1234,'ctime_ns':1235}
        self.v['unit_transition_evidence']={'context_sha256':self.ctx['context_sha256'],
            'target_receipt':{'path':ut.retained.PROVISION,'sha256':h('actual current private receipt'),'targets':{self.path:row}},
            'reload':None}
    def check(self,index=5):
        live.validate_contract(self.c,self.ctx)
        return live.validate_process_view(self.v,self.c,self.c['checkpoints'][index],os.getpid(),
            context_sha256=self.ctx['context_sha256'],checkpoint_index=index)
    def props(self,**kw):
        for when in ('before','after'):self.v['units'][self.unit][when].update(kw)
    def reload(self):
        self.v['unit_transition_evidence']['reload']={'context_sha256':self.ctx['context_sha256'],
            'phase':'activate_new_services','operation':'daemon_reload','argv_sha256':sr.argv_hash(['/usr/bin/systemctl','daemon-reload']),
            'sequence':12,'returncode':0}
    def test_cached_old_or_new_file_properties_with_exact_cas(self):
        for load in ('masked','loaded'):
            for file in ('masked','disabled'):
                for reload in ('yes','no'):
                    self.props(LoadState=load,UnitFileState=file,NeedDaemonReload=reload);self.check()
    def test_missing_target_proof(self):
        self.v['unit_transition_evidence']=None
        with self.assertRaises(ValueError):self.check()
    def test_wrong_context(self):
        self.v['unit_transition_evidence']['context_sha256']=h('other context')
        with self.assertRaisesRegex(ValueError,'CONTEXT'):self.check()
    def test_wrong_receipt_path(self):
        self.v['unit_transition_evidence']['target_receipt']['path']='/tmp/unowned.json'
        with self.assertRaisesRegex(ValueError,'OWN_PROVISIONING'):self.check()
    def test_wrong_target_hash(self):
        self.v['unit_transition_evidence']['target_receipt']['targets'][self.path]['sha256']=h('other target')
        with self.assertRaisesRegex(ValueError,'CAS_METADATA'):self.check()
    def test_extra_target_rejected(self):
        self.v['unit_transition_evidence']['target_receipt']['targets']['/tmp/extra']={}
        with self.assertRaises(ValueError):self.check()
    def test_cas_link_owner_type_metadata_rejected(self):
        for key,value in [('nlink',2),('uid',1002),('ino',0),('kind','MASK')]:
            old=self.v['unit_transition_evidence']['target_receipt']['targets'][self.path][key]
            self.v['unit_transition_evidence']['target_receipt']['targets'][self.path][key]=value
            with self.assertRaises(ValueError):self.check()
            self.v['unit_transition_evidence']['target_receipt']['targets'][self.path][key]=old
    def test_active_or_main_without_start_not_admitted(self):
        self.props(ActiveState='active',SubState='running',MainPID=123)
        with self.assertRaisesRegex(ValueError,'STAY_STOPPED'):self.check()
    def test_reload_requires_exact_new_state(self):
        self.reload()
        with self.assertRaisesRegex(ValueError,'POST_RELOAD'):self.check(14)
        self.props(LoadState='loaded',UnitFileState='disabled',NeedDaemonReload='no');self.check(14)
    def test_reload_wrong_context_or_command(self):
        self.reload();self.props(LoadState='loaded',UnitFileState='disabled')
        self.v['unit_transition_evidence']['reload']['argv_sha256']=h('unmask')
        with self.assertRaisesRegex(ValueError,'BINDING'):self.check(14)
    def test_need_reload_yes_after_success_rejected(self):
        self.reload();self.props(LoadState='loaded',UnitFileState='disabled',NeedDaemonReload='yes')
        with self.assertRaises(ValueError):self.check(14)
    def test_reload_receipt_cannot_be_from_future_phase(self):
        self.reload();self.props(LoadState='loaded',UnitFileState='disabled')
        with self.assertRaisesRegex(ValueError,'PREMATURE_RELOAD'):self.check(5)
    def test_old_masked_file_state_not_accepted_after_reload(self):
        self.reload();self.props(LoadState='loaded',UnitFileState='masked')
        with self.assertRaisesRegex(ValueError,'POST_RELOAD'):self.check(14)
    def test_unreviewed_unitfile_state(self):
        self.props(UnitFileState='enabled-runtime')
        with self.assertRaisesRegex(ValueError,'FINITE'):self.check()
    def test_proof_cannot_appear_before_replacement(self):
        with self.assertRaisesRegex(ValueError,'PREMATURE'):self.check(4)
    def test_index_required_not_inferred_from_similar_stopped_view(self):
        with self.assertRaisesRegex(ValueError,'INDEX_REQUIRED'):
            live.validate_process_view(self.v,self.c,self.c['checkpoints'][5],os.getpid(),context_sha256=self.ctx['context_sha256'])
    def test_cleanup_after_partial_failure_does_not_demand_target_receipt(self):
        self.v['unit_transition_evidence']=None
        live.validate_cleanup_process_view(self.v,self.c,os.getpid())

class GatewayRestorationTests(unittest.TestCase):
    def setUp(self):
        self.ctx,self.c,self.active=fixture2();self.unit=ut.GATEWAY
        before=copy.deepcopy(self.c['checkpoints'][0]['units'][self.unit]['properties'])
        before.update(LoadState='masked',UnitFileState='masked')
        for point in self.c['checkpoints'][:15]:point['units'][self.unit]['properties']=copy.deepcopy(before)
        self.policy={'path':ut.ROOT+self.unit,'sha256':h(self.unit),'uid':0,'gid':0,'mode':420,
            'legacy_receipt_sha256':h('protected legacy receipt'),'boot_before':'disabled','before':before}
        self.c['unit_transition_contract']={'schema':1,'targets':{},'units':{},'gateway_restoration':self.policy}
        temporary=copy.deepcopy(self.c);temporary['schema']=1
        temporary.pop('service_role_contract');temporary.pop('unit_transition_contract')
        self.v=process_view(temporary,14)
        self.v['service_role_evidence']={'context_sha256':None,'units':{},'processes':{}}
        self.evidence={'context_sha256':self.ctx['context_sha256'],'target_receipt':None,
                       'reload':None,'gateway_restoration':None}
        self.v['unit_transition_evidence']=self.evidence

    def props(self,**kwargs):
        for side in ('before','after'):self.v['units'][self.unit][side].update(kwargs)

    def receipt(self,sequence):
        return {'context_sha256':self.ctx['context_sha256'],'phase':'activate_new_services',
            'operation':'daemon_reload','argv_sha256':sr.argv_hash(['/usr/bin/systemctl','daemon-reload']),
            'sequence':sequence,'returncode':0}

    def restored(self,reloaded=False,persistence='OWN_CAPTURE_PENDING_PUBLICATION'):
        meta={'kind':'FILE','sha256':h(self.unit),'uid':0,'gid':0,'mode':420,'dev':8,'ino':200,
              'nlink':1,'size':250,'mtime_ns':123,'ctime_ns':124}
        self.evidence['gateway_restoration']={'context_sha256':self.ctx['context_sha256'],
            'legacy_receipt_sha256':self.policy['legacy_receipt_sha256'],'observed_after':meta,
            'reload':self.receipt(9) if reloaded else None,'persistence':persistence}
        self.props(LoadState='loaded',UnitFileState='disabled',NeedDaemonReload='no' if reloaded else 'yes')

    def check(self,index=14,pending=False):
        live.validate_contract(self.c,self.ctx)
        return live.validate_process_view(self.v,self.c,self.c['checkpoints'][index],os.getpid(),
            context_sha256=self.ctx['context_sha256'],checkpoint_index=index,
            allow_pending_service_receipts=pending)

    def test_masked_before_own_restore_with_no_fake_target_cas(self):self.check()

    def test_restored_disabled_pending_allowed_only_inside_effect(self):
        self.restored();self.check(pending=True)
        with self.assertRaisesRegex(ValueError,'PERSISTED'):self.check()

    def test_disabled_without_own_restoration_rejected(self):
        self.props(LoadState='loaded',UnitFileState='disabled')
        with self.assertRaisesRegex(ValueError,'NOT_OWN_RESTORED'):self.check()

    def test_forged_restore_context_or_legacy_receipt_rejected(self):
        self.restored()
        for key in ('context_sha256','legacy_receipt_sha256'):
            original=self.evidence['gateway_restoration'][key]
            self.evidence['gateway_restoration'][key]=h('different')
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'OWN_RESTORE_CONTEXT'):self.check(pending=True)
            self.evidence['gateway_restoration'][key]=original

    def test_wrong_restored_bytes_owner_or_inode_rejected(self):
        self.restored();meta=self.evidence['gateway_restoration']['observed_after']
        for key,value in (('sha256',h('different')),('uid',1002),('nlink',2),('ino',0),('mode',511)):
            old=meta[key];meta[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'RESTORED_FILE'):self.check(pending=True)
            meta[key]=old

    def test_restore_cannot_appear_before_activation(self):
        self.restored()
        with self.assertRaisesRegex(ValueError,'OWN_RESTORE_CONTEXT'):self.check(5,True)

    def test_source_bound_loaded_disabled_after_legacy_reload(self):
        self.restored(True,'PERSISTED');self.check()

    def test_cached_mask_or_need_reload_after_legacy_reload_rejected(self):
        self.restored(True,'PERSISTED')
        for key,value in (('LoadState','masked'),('UnitFileState','masked'),('NeedDaemonReload','yes')):
            old=self.v['units'][self.unit]['before'][key];self.props(**{key:value})
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'EXACT_POST_RELOAD'):self.check()
            self.props(**{key:old})

    def test_empty_selected_target_set_does_not_accept_fake_receipt(self):
        self.evidence['target_receipt']={'path':ut.retained.PROVISION,'sha256':h('fake'),'targets':{}}
        with self.assertRaisesRegex(ValueError,'EMPTY_TARGET_PROOF'):self.check()

    def test_active_boundary_requires_both_reload_order_and_persisted_restore(self):
        self.restored(True,'PERSISTED');self.evidence['reload']=self.receipt(10)
        self.v=copy.deepcopy(self.active);self.v['unit_transition_evidence']=self.evidence
        self.check(16)
        self.evidence['reload']=self.receipt(8)
        with self.assertRaisesRegex(ValueError,'RESTORE_BEFORE_RUNTIME_RELOAD'):self.check(16)

    def test_baseline_cannot_be_changed_to_preapprove_restoration(self):
        self.policy['before']['SubState']='failed'
        with self.assertRaisesRegex(ValueError,'BASELINE'):self.check()


if __name__=='__main__':unittest.main()
