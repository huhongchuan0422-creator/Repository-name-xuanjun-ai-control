"""Synthetic original authority changes while SaaS fulfillment is in flight."""
import unittest
from unittest.mock import patch
import test_community_saas_finance_integration as fixtures
from scripts.community_saas_phase2 import Principal


class FulfillmentAuthorityContext(unittest.TestCase):
    def setUp(self):
        for name in ('socket.socket.bind','socket.socket.connect'):
            guard=patch(name,side_effect=AssertionError('NO_NETWORK_OR_LISTENER'));guard.start();self.addCleanup(guard.stop)
        self.fx=fixtures.SyntheticFinanceIntegration();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.c=self.fx.fx.center;self.api=self.fx.api
        self.original_grant=self.api.operations.grants['owner']
        self.changed=False

    def change_authority(self,*,in_place=False):
        if self.changed:return
        self.changed=True
        # Only fixture configuration and temporary original Center records.
        commit=not self.c.db.in_transaction
        self.c.db.execute("INSERT INTO projects SELECT 'project2','tenant2','customer2',owner,authority_ref,revision,expires,payload,active FROM projects WHERE id='project1'")
        self.c.db.execute("INSERT INTO members VALUES('project2',?,'OWNER',1)",(self.fx.fx.uid1,))
        self.c.db.execute("UPDATE members SET active=0 WHERE project='project1' AND user_id=?",(self.fx.fx.uid1,))
        old=self.c.db.execute("SELECT payload FROM projects WHERE id='project1'").fetchone()[0]
        self.c.db.execute("UPDATE projects SET payload=? WHERE id='project2'",(self.c.encrypt(self.c.decrypt(old,'project:project1'),'project:project2'),))
        if commit:self.c.db.commit()
        principal=Principal('tenant2','PLATFORM_OWNER');scope={'tenant_id':'tenant2','merchant_id':'merchant2','store_id':'store2'}
        self.api.runtime.bindings[principal]=scope
        replacement={**self.original_grant,'project':'project2','tenant':'tenant2','principal':principal,'scope':scope}
        if in_place:self.api.operations.grants['owner'].update(replacement)
        else:self.api.operations.grants['owner']=replacement

    def rotate_during_verify(self,reverse=False,in_place=False):
        authority=self.api.reversal_finance if reverse else self.api.finance
        verify=authority.verify
        def change(claim,receipt,now):
            confirmation=verify(claim,receipt,now)
            self.change_authority(in_place=in_place)
            return confirmation
        return patch.object(authority,'verify',side_effect=change)

    def test_valid_cross_tenant_workspace_replacement_during_verify_cannot_grant_old_tenant(self):
        proof=self.fx.proof();before=self.fx.snapshot()
        with self.rotate_during_verify():
            with self.assertRaises(PermissionError):self.fx.call(proof)
        self.assertEqual(self.api._operator(self.fx.web['token'],self.fx.web['csrf'],'owner')['tenant'],'tenant2')
        self.assertEqual(self.fx.snapshot(),before)

    def test_in_place_grant_change_cannot_mutate_the_frozen_authority(self):
        proof=self.fx.proof();before=self.fx.snapshot()
        with self.rotate_during_verify(in_place=True):
            with self.assertRaises(PermissionError):self.fx.call(proof)
        self.assertEqual(self.fx.snapshot(),before)

    def test_valid_cross_tenant_workspace_replacement_during_reversal_cannot_revoke_old_tenant(self):
        self.fx.call();proof=self.fx.proof(reverse=True);before=self.fx.snapshot()
        with self.rotate_during_verify(reverse=True):
            with self.assertRaises(PermissionError):self.fx.call(proof,reverse=True)
        self.assertEqual(self.fx.snapshot(),before)

    def test_original_project_revision_change_during_verify_requires_fresh_request(self):
        verify=self.api.finance.verify;proof=self.fx.proof();before=self.fx.snapshot()
        def revision(claim,receipt,now):
            result=verify(claim,receipt,now)
            self.c.db.execute("UPDATE projects SET revision=revision+1 WHERE id='project1'");self.c.db.commit()
            return result
        with patch.object(self.api.finance,'verify',side_effect=revision):
            with self.assertRaises(PermissionError):self.fx.call(proof)
        self.assertEqual(self.fx.snapshot(),before)

    def advance_project_revision(self):
        commit=not self.c.db.in_transaction
        self.c.db.execute("UPDATE projects SET revision=revision+1 WHERE id='project1'")
        if commit:self.c.db.commit()

    def test_local_authority_and_price_configuration_changes_fail_before_reservation(self):
        from scripts.community_saas_finance_authority import SignedFinanceAuthority
        proof=self.fx.proof();before=self.fx.snapshot()
        mutations=[lambda:setattr(self.api,'authority_id','replacement_authority'),
                   lambda:setattr(self.api,'finance',SignedFinanceAuthority(self.fx.trust)),
                   lambda:self.api.prices[('storefront_catalog','offer1',1)].update(price_version=2),
                   lambda:self.api.finance._keys.clear()]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                self.api.authority_id='synthetic_authority';self.api.finance=SignedFinanceAuthority(self.fx.trust)
                self.api.prices[('storefront_catalog','offer1',1)]={'price_version':1,'perpetual':False}
                verify=self.api.finance.verify
                def changed(claim,receipt,now):
                    result=verify(claim,receipt,now);mutate();return result
                with patch.object(self.api.finance,'verify',side_effect=changed):
                    with self.assertRaises(PermissionError):self.fx.call(proof)
                self.assertEqual(self.fx.snapshot(),before)

    def test_reservation_guard_rolls_back_original_center_effects(self):
        proof=self.fx.proof();before=self.fx.snapshot();audit=self.c.audit
        def changed(project,actor,event,obj):
            result=audit(project,actor,event,obj)
            if event=='SAAS_FULFILLMENT_RESERVED':self.advance_project_revision()
            return result
        with patch.object(self.c,'audit',side_effect=changed):
            with self.assertRaises(PermissionError):self.fx.call(proof)
        self.assertEqual(self.fx.snapshot(),before)

    def test_reversal_reservation_guard_rolls_back_original_center_effects(self):
        self.fx.call();proof=self.fx.proof(reverse=True);before=self.fx.snapshot();audit=self.c.audit
        def changed(project,actor,event,obj):
            result=audit(project,actor,event,obj)
            if event=='SAAS_REVERSAL_RESERVED':self.advance_project_revision()
            return result
        with patch.object(self.c,'audit',side_effect=changed):
            with self.assertRaises(PermissionError):self.fx.call(proof,reverse=True)
        self.assertEqual(self.fx.snapshot(),before)

    def test_order_commit_guard_preserves_reservation_for_explicit_authorized_recovery(self):
        from scripts.community_saas_fulfillment import advance
        proof=self.fx.proof();changed=False
        def commit_then_change(*args,**kwargs):
            nonlocal changed
            result=advance(*args,**kwargs)
            if not changed:changed=True;self.advance_project_revision()
            return result
        with patch('scripts.community_saas_fulfillment.advance',side_effect=commit_then_change):
            with self.assertRaises(PermissionError):self.fx.call(proof)
        self.assertEqual(self.fx.q.execute('SELECT count(*) FROM module_events').fetchone()[0],0)
        pending=self.api.inspect(self.fx.web['token'],self.fx.web['csrf'],'owner','order1')
        self.assertEqual(pending['state'],'RESERVED');self.assertTrue(pending['recovery_required'])
        self.assertEqual(self.fx.s.execute('SELECT count(*) FROM saas_order_lifecycle_events').fetchone()[0],1)
        self.assertEqual(self.fx.call(proof)['state'],'COMPLETED')
        self.assertEqual(self.fx.q.execute('SELECT count(*) FROM module_events').fetchone()[0],1)
        self.assertTrue(self.fx.call(proof)['duplicate'])

    def test_module_commit_guard_cannot_claim_completion_and_recovery_does_not_grant_twice(self):
        from scripts.community_saas_fulfillment import grant
        proof=self.fx.proof()
        def commit_then_change(*args,**kwargs):
            result=grant(*args,**kwargs);self.advance_project_revision();return result
        with patch('scripts.community_saas_fulfillment.grant',side_effect=commit_then_change):
            with self.assertRaises(PermissionError):self.fx.call(proof)
        pending=self.api.inspect(self.fx.web['token'],self.fx.web['csrf'],'owner','order1')
        self.assertEqual(pending['state'],'RESERVED');self.assertFalse(pending['entitlement_granted'])
        # The original module DB committed before the authority changed. This
        # is an unresolved cross-DB operation, not a fictional global rollback.
        self.assertEqual(self.fx.q.execute('SELECT count(*) FROM module_events').fetchone()[0],1)
        self.assertEqual(self.fx.call(proof)['state'],'COMPLETED')
        self.assertEqual(self.fx.q.execute('SELECT count(*) FROM module_events').fetchone()[0],1)

    def test_reversal_module_commit_guard_preserves_explicit_recovery(self):
        self.fx.call();proof=self.fx.proof(reverse=True);save=self.api._save
        def changed(key,data):
            if data['state']=='REVERSED':self.advance_project_revision()
            return save(key,data)
        with patch.object(self.api,'_save',side_effect=changed):
            with self.assertRaises(PermissionError):self.fx.call(proof,reverse=True)
        pending=self.api.inspect(self.fx.web['token'],self.fx.web['csrf'],'owner','order1')
        self.assertEqual(pending['state'],'REVERSAL_RESERVED');self.assertTrue(pending['recovery_required'])
        self.assertEqual(self.fx.q.execute("SELECT count(*) FROM module_events WHERE action='REVERSE'").fetchone()[0],1)
        self.assertEqual(self.fx.call(proof,reverse=True)['state'],'REVERSED')
        self.assertEqual(self.fx.q.execute("SELECT count(*) FROM module_events WHERE action='REVERSE'").fetchone()[0],1)

    def test_status_and_completed_receipt_recheck_authority_before_returning_private_results(self):
        self.fx.call();load=self.api._load
        def changed(key):
            result=load(key);self.advance_project_revision();return result
        with patch.object(self.api,'_load',side_effect=changed):
            with self.assertRaises(PermissionError):self.api.inspect(self.fx.web['token'],self.fx.web['csrf'],'owner','order1')
            with self.assertRaises(PermissionError):self.fx.call()
        self.assertTrue(self.fx.call()['duplicate'])

    def test_requirement_read_rechecks_the_original_context(self):
        from scripts.community_saas_fulfillment import plan_finance_claim
        def changed(*args):
            result=plan_finance_claim(*args);self.advance_project_revision();return result
        with patch('scripts.community_saas_fulfillment.plan_finance_claim',side_effect=changed):
            with self.assertRaises(PermissionError):self.api.dispatch(self.fx.web['token'],self.fx.web['csrf'],
                {'workspace':'owner','operation':'requirements','params':{'order_id':'order1'}})


if __name__=='__main__':unittest.main()
