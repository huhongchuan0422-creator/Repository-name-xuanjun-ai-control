"""Owner-approved withdrawal of own drafts/corrections; original history stays."""
import unittest
from unittest.mock import patch
import test_community_merchant_onboarding as fixtures
from scripts.community_onboarding_history import ITEM

class AdmissionWithdrawal(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.MerchantAdmissionJourney();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.c=self.f.fx.center
    def withdraw(self,app):return self.f.call('withdraw',dict(application=app['application'],revision=app['revision']))
    def history(self,app):return self.f.call('history',dict(application=app['application'],after_revision=0))['records']
    def test_owner_withdraws_draft_and_retains_materials_and_prior_history(self):
        app=self.f.upload(self.f.draft(),'business_license');history=self.history(app)
        files={p.name:p.read_bytes() for p in self.c.objects.iterdir()}
        snapshots=list(self.c.db.execute('SELECT id,payload FROM versions WHERE project=? AND item=? ORDER BY seq',(app['application'],ITEM)))
        result=self.withdraw(app)
        self.assertEqual((result['application'],result['revision'],result['status']),(app['application'],app['revision']+1,'WITHDRAWN'))
        self.assertEqual(result['fields'],app['fields']);self.assertEqual(result['materials'],app['materials']);self.assertFalse(result['payment_enabled'])
        after=self.history(result);self.assertEqual(after[:-1],history);self.assertEqual(after[-1]['event'],'WITHDRAW');self.assertEqual(after[-1]['actor'],self.f.fx.uid1)
        self.assertEqual(after[-1]['status_before'],'DRAFT');self.assertEqual(after[-1]['status_after'],'WITHDRAWN')
        self.assertEqual(files,{p.name:p.read_bytes() for p in self.c.objects.iterdir()})
        self.assertEqual(snapshots,list(self.c.db.execute('SELECT id,payload FROM versions WHERE project=? AND item=? AND seq<=? ORDER BY seq',(app['application'],ITEM,app['revision']))))
    def test_correction_withdrawal_preserves_original_reason_and_does_not_generate_review_notice(self):
        app=self.f.review(self.f.complete(),'CORRECTION','ORIGINAL_CORRECTION_REASON')
        notices=self.f.call('notices',dict(application=app['application'],after_id=''))
        result=self.withdraw(app);self.assertEqual(result['status'],'WITHDRAWN')
        self.assertEqual(next(r['note'] for r in self.history(result) if r['event']=='CORRECTION'),'ORIGINAL_CORRECTION_REASON')
        self.assertEqual(self.f.call('notices',dict(application=app['application'],after_id='')),notices)
    def test_only_draft_and_correction_are_withdrawable_not_submitted_reviewing_rejected_or_approved(self):
        makers=[lambda:self.f.complete(),lambda:self.f.review(self.f.complete(),'BEGIN_REVIEW'),
                lambda:self.f.review(self.f.complete(),'REJECT'),lambda:self.f.review(self.f.complete(),'APPROVE')]
        for make in makers:
            app=make();before=self.history(app)
            with self.assertRaises(ValueError):self.withdraw(app)
            self.assertEqual(self.history(app),before)
    def test_other_account_and_reviewer_cannot_withdraw_owners_application(self):
        app=self.f.draft()
        with self.assertRaises(PermissionError):self.f.call('withdraw',dict(application=app['application'],revision=app['revision']),True)
        self.assertEqual(self.f.call('read',dict(application=app['application']))['status'],'DRAFT')
    def test_owner_without_project_can_withdraw_but_csrf_epoch_and_binding_are_current(self):
        app=self.f.draft();web=self.f.applicant
        with self.assertRaises(PermissionError):self.f.service.dispatch(web['token'],'',dict(operation='withdraw',params=dict(application=app['application'],revision=app['revision'])))
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.f.fx.uid1,))
        self.assertEqual(self.withdraw(app)['status'],'WITHDRAWN')
        app=self.f.draft();self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.f.fx.uid1,))
        with self.assertRaises(PermissionError):self.withdraw(app)
    def test_terminal_application_blocks_all_platform_edits_but_allows_new_application_and_history(self):
        withdrawn=self.withdraw(self.f.draft())
        for attempt in [lambda:self.f.draft(withdrawn),lambda:self.f.upload(withdrawn,'business_license'),
          lambda:self.f.call('submit',dict(application=withdrawn['application'],revision=withdrawn['revision'])),
          lambda:self.f.review(withdrawn,'REOPEN'),lambda:self.f.review(withdrawn,'CORRECTION'),
          lambda:self.f.call('review_material',dict(application=withdrawn['application'],revision=withdrawn['revision'],kind='business_license',decision='ACCEPTED',note='not permitted'),True),
          lambda:self.f.call('open_workbench',dict(application=withdrawn['application'],revision=withdrawn['revision'],workspace='any'),True)]:
            with self.assertRaises((ValueError,PermissionError)):attempt()
        new=self.f.draft();self.assertNotEqual(new['application'],withdrawn['application']);self.assertEqual(new['status'],'DRAFT')
        self.assertEqual(self.history(withdrawn)[-1]['event'],'WITHDRAW')
    def test_duplicate_stale_invalid_and_injected_actor_requests_do_not_add_history(self):
        app=self.f.draft()
        for revision in [True,-1,0,app['revision']+1]:
            with self.assertRaises(ValueError):self.f.call('withdraw',dict(application=app['application'],revision=revision))
        with self.assertRaises(ValueError):self.f.call('withdraw',dict(application=app['application'],revision=app['revision'],user_id=self.f.fx.uid1))
        withdrawn=self.withdraw(app);before=self.history(withdrawn)
        for previous in [app,withdrawn]:
            with self.assertRaises(ValueError):self.withdraw(previous)
        self.assertEqual(self.history(withdrawn),before)
    def test_history_failure_rolls_back_withdrawal_and_original_app_remains_editable(self):
        app=self.f.draft();before=self.history(app)
        with patch('scripts.community_onboarding_history.append',side_effect=OSError('synthetic history failure')):
            with self.assertRaises(OSError):self.withdraw(app)
        self.assertEqual(self.history(app),before);self.assertEqual(self.f.draft(app)['status'],'DRAFT')
    def test_epoch_change_during_withdrawal_denies_commit(self):
        app=self.f.draft();original=self.c.audit
        def audit(*args):
            original(*args)
            if args[2]=='MERCHANT_ONBOARDING_WITHDRAW':self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.f.fx.uid1,))
        with patch.object(self.c,'audit',side_effect=audit):
            with self.assertRaises(PermissionError):self.withdraw(app)
        self.assertEqual(self.f.call('read',dict(application=app['application']))['status'],'DRAFT')
    def test_fifty_one_withdrawn_applications_filter_and_page_without_loss(self):
        from scripts import community_onboarding_offline as workflow
        template=self.f.draft();owner,meta,data=self.f.service._load(template['application'],self.f.fx.uid1)
        with self.c.tx():
            for index in range(51):
                app='ma_'+format(index,'032x')
                workflow.save_draft(self.c.db,owner,app,owner,data['fields'],encode=lambda value,app=app:self.f.service._encode(value,'onboarding-fields:'+app),manage_transaction=False)
                self.f.service._meta(app,owner,meta)
                workflow.transition(self.c.db,owner,app,owner,'MERCHANT','WITHDRAW',1,manage_transaction=False)
        for review in [False,True]:
            op='review_list' if review else 'mine';one=self.f.call(op,dict(status='WITHDRAWN'),review)
            two=self.f.call(op,dict(status='WITHDRAWN',cursor=one['next_cursor']),review)
            self.assertEqual((len(one['applications']),len(two['applications'])),(50,1))
            self.assertEqual(len({a['application'] for a in one['applications']+two['applications']}),51);self.assertIsNone(two['next_cursor'])
        self.assertEqual(self.f.call('mine',dict(status='WITHDRAWN'),True)['applications'],[])
        with self.assertRaises(ValueError):self.f.call('mine',dict(status='EXPIRED'))
    def test_withdrawal_survives_center_reopen_and_time_does_not_auto_expire_draft(self):
        from scripts.community_merchant_onboarding import MerchantOnboarding
        withdrawn=self.withdraw(self.f.draft());other=self.f.draft()
        self.f.fx.reopen();self.c=self.f.fx.center;self.f.service=MerchantOnboarding(self.c,{self.f.fx.uid2:'project1'})
        self.assertEqual(self.f.call('read',dict(application=withdrawn['application']))['status'],'WITHDRAWN')
        self.f.fx.stage.now+=100000;self.f.applicant=self.c.login('one@example.org','FixturePassword123!')
        self.assertEqual(self.f.call('read',dict(application=other['application']))['status'],'DRAFT')
    def test_concurrent_same_revision_has_one_withdraw_event(self):
        import concurrent.futures,threading
        from scripts.pr122_customer_core import Center
        from scripts.community_merchant_onboarding import MerchantOnboarding
        app=self.f.draft();barrier=threading.Barrier(2);web=self.f.applicant;root=self.f.fx.tmp.name;now=self.c.now()
        def contender():
            c=Center(root,{'testkey':b'k'*32},'testkey',clock=lambda:now,mail_ready=True)
            try:
                service=MerchantOnboarding(c,{self.f.fx.uid2:'project1'});barrier.wait(timeout=10)
                try:return service.dispatch(web['token'],web['csrf'],dict(operation='withdraw',params=dict(application=app['application'],revision=app['revision'])))['status']
                except ValueError:return 'CONFLICT'
            finally:c.db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(lambda _:contender(),range(2)))
        self.assertCountEqual(results,['WITHDRAWN','CONFLICT']);self.assertEqual(sum(r['event']=='WITHDRAW' for r in self.history(app)),1)
    def configure_wechat(self):
        from scripts.community_wechat_applyment import WechatApplyment
        from scripts.community_wechat_sp_readonly import PartnerOrderReader
        reader=PartnerOrderReader.__new__(PartnerOrderReader);reader._mchid='1900000123'
        service=WechatApplyment(self.f.service,reader,submission_enabled=True);self.f.service.wechat_applyment=service
        return service
    def test_withdrawn_wechat_draft_mutations_are_rejected_before_provider_io_and_original_data_stays(self):
        service=self.configure_wechat();app=self.f.draft()
        saved=self.f.call('wechat_save',dict(application=app['application'],expected_version=0,profile={'synthetic':'private retained'}))
        withdrawn=self.withdraw(app);before=service._read(app['application'])
        operations=[('wechat_save',dict(expected_version=1,profile={})),('wechat_submit_review',dict(expected_version=1)),
          ('wechat_media',dict(kind='business_license')),('wechat_review',dict(expected_version=1,decision='INTERNAL_APPROVED',opinion='not permitted')),('wechat_execute',dict(expected_version=1))]
        with patch('scripts.community_wechat_applyment.request',side_effect=AssertionError('NO_PROVIDER_IO')) as transport:
            for op,params in operations:
                with self.assertRaisesRegex(PermissionError,'WITHDRAWN_APPLICATION_READ_ONLY'):
                    self.f.call(op,dict(application=app['application'],**params),op in ('wechat_review','wechat_execute'))
            self.assertEqual(transport.call_count,0)
        self.assertEqual(service._read(app['application']),before)
        self.assertEqual(self.f.call('wechat_read',dict(application=app['application'])),saved)
    def test_preexisting_provider_unknown_and_query_recovery_survive_local_withdrawal(self):
        service=self.configure_wechat();app=self.f.draft();record=dict(version=1,state='SUBMISSION_UNKNOWN',business_code='fixture-code',provider_sp_mchid=service.reader._mchid,provider_state='NOT_SUBMITTED',profile={})
        with self.c.tx():service._save(app['application'],self.f.fx.uid1,record)
        self.withdraw(app);self.assertEqual(service._read(app['application']),record)
        response=dict(business_code='fixture-code',applyment_id=123,applyment_state='APPLYMENT_STATE_AUDITING')
        with patch('scripts.community_wechat_applyment.request',return_value=(response,'a'*64,dict(signed_at=self.c.now(),signature_sha256='b'*64))) as transport:
            result=self.f.call('wechat_query',dict(application=app['application']),True)
        self.assertEqual(transport.call_count,1);self.assertEqual(transport.call_args.args[1],'GET');self.assertEqual(result['provider_state'],'APPLYMENT_STATE_AUDITING')
        self.assertEqual(self.f.call('read',dict(application=app['application']))['status'],'WITHDRAWN')
    def test_already_sent_media_response_keeps_evidence_without_reopening_application(self):
        service=self.configure_wechat();app=self.f.upload(self.f.draft(),'business_license')
        def sent(*args,**kwargs):
            self.withdraw(app);return dict(media_id='synthetic-existing-response'),'a'*64
        with patch('scripts.community_wechat_applyment.request',side_effect=sent) as transport:
            result=self.f.call('wechat_media',dict(application=app['application'],kind='business_license'))
        self.assertEqual(transport.call_count,1);self.assertEqual(result['media_id'],'synthetic-existing-response')
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA'").fetchone()[0],1)
        self.assertEqual(self.f.call('read',dict(application=app['application']))['status'],'WITHDRAWN')
    def test_owner_binding_revoked_during_withdrawal_denies_commit(self):
        app=self.f.draft();before=self.history(app);original=self.c.audit
        def audit(*args):
            original(*args)
            if args[2]=='MERCHANT_ONBOARDING_WITHDRAW':
                self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=?",(app['application'],))
        with patch.object(self.c,'audit',side_effect=audit):
            with self.assertRaises(PermissionError):self.withdraw(app)
        self.assertEqual(self.f.call('read',dict(application=app['application']))['status'],'DRAFT');self.assertEqual(self.history(app),before)
    def test_withdrawal_before_media_send_rejects_without_provider_io(self):
        self.configure_wechat();app=self.f.upload(self.f.draft(),'business_license');original=self.c.decrypt;changed=False
        def decrypt(data,aad):
            nonlocal changed
            value=original(data,aad)
            if aad.startswith('object:') and not changed:
                changed=True;self.withdraw(app)
            return value
        with patch.object(self.c,'decrypt',side_effect=decrypt),patch('scripts.community_wechat_applyment.request',side_effect=AssertionError('NO_PROVIDER_IO')) as transport:
            with self.assertRaisesRegex(PermissionError,'WITHDRAWN_APPLICATION_READ_ONLY'):
                self.f.call('wechat_media',dict(application=app['application'],kind='business_license'))
        self.assertEqual(transport.call_count,0);self.assertEqual(self.f.call('read',dict(application=app['application']))['status'],'WITHDRAWN')
