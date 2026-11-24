"""Original main read-route assembly only; synthetic authority, no live effects."""
import json,unittest
from types import SimpleNamespace
from unittest.mock import patch
import task_center_app as app
from task_delivery_observer import MetadataReader,Unavailable
from task_delivery_ledger.core import Store
import test_handoff_backup_script_main_delta as fixture

class ReadConsumerBinding(unittest.TestCase):
    write_config=fixture.ScriptMainBackup.write_config
    setUp=fixture.ScriptMainBackup.setUp

    def invoke(self,extra=(),reader=None,host=None):
        captured=[]
        class Stop(Exception):pass
        def capture(*args,**kwargs):
            handler=app.build_handler(args[0],args[1],args[2],args[3],
                session_store=self.sessions,delivery_ledger_reader=kwargs['delivery_ledger_reader'],
                handoff_host=kwargs['handoff_host'],ledger_bridge=kwargs['ledger_bridge'])
            closure=dict(zip(handler.do_GET.__code__.co_freevars,
                (cell.cell_contents for cell in handler.do_GET.__closure__)))
            kwargs['delivery_ledger_reader']=closure['delivery_ledger_reader']
            captured.append(kwargs)
            raise Stop()
        with patch.object(app,'make_server',side_effect=capture),patch.object(Store,'__init__',side_effect=AssertionError('no store creation')):
            with self.assertRaises(Stop):
                app.main(self.argv+list(extra),identity_provider=fixture.FormalHandoffIdentityProvider(),
                    session_store=self.sessions,handoff_host=host or self.host,ledger_bridge=self.bridge,
                    delivery_ledger_reader=reader)
        return captured[0]

    def test_main_connects_existing_bridge_and_fails_unavailable_without_creating_ledger(self):
        bound=self.invoke();reader=bound['delivery_ledger_reader']
        self.assertIsInstance(reader,MetadataReader)
        self.assertIs(reader.ledger_authority,bound['ledger_bridge'])
        self.assertEqual(reader.handoff_verifier,bound['ledger_bridge'].verify_current)
        with self.assertRaises(Unavailable):reader.view()
        self.assertFalse((self.root/'ledger').exists())

    def test_cli_reader_retains_observations_and_uses_final_reassembled_host(self):
        extra=['--delivery-ledger-root',self.bridge.root,'--delivery-ledger-namespace',self.bridge.namespace,
            '--delivery-ledger-writer',self.bridge.writer,'--handoff-backup-inventory-file',str(self.config)]
        bound=self.invoke(extra);reader=bound['delivery_ledger_reader'];bridge=bound['ledger_bridge']
        self.assertIsNot(bridge,self.bridge)
        self.assertIs(bridge.host,bound['handoff_host'])
        self.assertIs(reader.ledger_authority,bridge)
        self.assertEqual(reader.handoff_verifier,bridge.verify_current)
        self.assertIsNone(reader.observation_reader)
        self.assertFalse((self.root/'ledger').exists())

    def test_main_reader_reaches_original_admin_route_without_granting_authority(self):
        # Synthetic existing metadata only, not a new production ledger.
        Store(self.bridge.root,self.bridge.writer)
        bound=self.invoke();reader=bound['delivery_ledger_reader']
        handler=app.build_handler(self.path,b'0123456789abcdef0123456789abcdef',
            'tenant-1','viewer',session_store=self.sessions,delivery_ledger_reader=reader,
            handoff_host=bound['handoff_host'],ledger_bridge=bound['ledger_bridge'])
        def call(token=None):
            h=handler.__new__(handler);h.path='/api/admin/delivery-ledger';h.command='GET'
            h.headers={'Host':'localhost:8765'};h.server=SimpleNamespace(server_port=8765)
            if token:h.headers['Cookie']=self.sessions.COOKIE+'='+token
            out=[];h._send=lambda status,body,kind,extra_headers=None:out.append((status,body))
            h.do_GET();return out[0]
        self.assertEqual(call()[0],403)
        status,body=call(self.token);self.assertEqual(status,200)
        value=json.loads(body)
        self.assertEqual(value['ledger_state'],'AVAILABLE_METADATA_ONLY')
        self.assertEqual(value['source_trust'],'UNAVAILABLE')
        self.assertEqual(value['writer_verification'],'UNKNOWN')
        self.assertEqual(value['tasks'],[])

    def test_existing_reader_options_are_preserved(self):
        from task_delivery_observation import ApprovedObservationReader
        observation=ApprovedObservationReader(str(self.root/'missing-observation'),'main-development-handoff-20261117')
        backup=ApprovedObservationReader(str(self.root/'missing-backup'),'main-backup-observation-20261117')
        reader=MetadataReader(self.bridge.root,self.bridge.namespace,self.bridge.writer,'tenant-1',
            observation_reader=observation,backup_observation_reader=backup)
        bound=self.invoke(reader=reader);result=bound['delivery_ledger_reader']
        self.assertIs(result.ledger_authority,self.bridge)
        self.assertIs(result.observation_reader,observation)
        self.assertIs(result.backup_observation_reader,backup)
        self.assertIsNone(reader.ledger_authority)

    def test_different_reader_route_is_not_silently_replaced(self):
        for field,value in [('root',str(self.root/'other')),('namespace','other'),('writer','other'),('tenant_id','other')]:
            reader=MetadataReader(self.bridge.root,self.bridge.namespace,self.bridge.writer,'tenant-1')
            setattr(reader,field,value)
            with patch.object(app,'make_server',side_effect=AssertionError('must not bind')):
                with self.assertRaisesRegex(ValueError,'HANDOFF_LEDGER_READER_BINDING_REQUIRED'):
                    self.invoke(reader=reader)

    def test_other_verifier_or_authority_is_not_overwritten(self):
        for field,value in [('handoff_verifier',lambda event:True),('ledger_authority',object())]:
            reader=MetadataReader(self.bridge.root,self.bridge.namespace,self.bridge.writer,'tenant-1')
            setattr(reader,field,value)
            with self.assertRaisesRegex(ValueError,'HANDOFF_LEDGER_READER_BINDING_REQUIRED'):
                self.invoke(reader=reader)
