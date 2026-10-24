"""No network, credentials, server, or batch operations."""
import pathlib
import json
import sys
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).parent.resolve()
sys.path[:0]=[str(HERE/'reused-6825'),str(HERE/'new19-source')]
import freeze_runtime_source as freeze
import pr17_c53_r2_authority_adapter as adapter
from production.cloud_connection.worker import Network, Github, Cloud


class FreezeAndCallerTests(unittest.TestCase):
    def test_maintenance_cannot_manufacture_analyst_authorization(self):
        with self.assertRaisesRegex(adapter.c53.Hold,
                                    'ANALYST_HTTP_REQUEST_CONTEXT_REQUIRED'):
            adapter.request_local_authorization_only()

    def test_inventory_matches_every_source_and_excludes_own_manifest(self):
        value=freeze.inventory()
        self.assertEqual(json.loads((HERE/'RUNTIME_SOURCE_MANIFEST.json').read_bytes()),
                         value)
        self.assertEqual(value['schema'],'B5_RUNTIME_SOURCE_V1')
        self.assertNotIn('RUNTIME_SOURCE_MANIFEST.json',
                         [row['path'] for row in value['files']])
        self.assertEqual(len(value['files']),
                         len(set(row['path'] for row in value['files'])))
        self.assertEqual(len(value['code_pin_sha256']),64)

    def test_external_binder_refuses_uncommitted_or_wrong_head(self):
        with self.assertRaisesRegex(ValueError,'REAL_COMMIT_REQUIRED'):
            freeze.binder('not-a-commit')
        with mock.patch.object(freeze,'git',return_value='M changed-source'):
            with self.assertRaisesRegex(ValueError,'WORKTREE_NOT_CLEAN'):
                freeze.binder('a'*40)
        with mock.patch.object(freeze,'git',side_effect=lambda *args:
                               '' if args[0]=='status' else 'b'*40):
            with self.assertRaisesRegex(ValueError,'COMMIT_NOT_CURRENT_HEAD'):
                freeze.binder('a'*40)

    def test_original_factory_uses_one_original_network_without_io(self):
        sentinel=object()
        class Policy:
            pass
        with mock.patch.object(adapter,'build_original_for_prepared_bundle',wraps=adapter.build_original_for_prepared_bundle):
            with mock.patch('production.cloud_connection.fixed_actions.ApprovedObjectsPolicy',return_value=Policy()), \
                 mock.patch('pr17_b5_deployment_composition.OriginalComposition') as composition:
                with self.assertRaisesRegex(Exception,'ORIGINAL_REQUEST_CONTEXT_UNAVAILABLE'):
                    adapter.build_original_for_prepared_bundle({},None)
                composition.return_value=sentinel
                raw=b'fixed-policy'
                result=adapter.build_original_for_prepared_bundle(
                    {'files':{adapter.c53.binder.BIND:raw},'requests':[{}]*19},
                    lambda:'request-local-only')
                self.assertIs(result,sentinel)
                kwargs=composition.call_args.kwargs
                self.assertIs(type(kwargs['github']),Github)
                self.assertIs(type(kwargs['cloud']),Cloud)
                self.assertIs(type(kwargs['github'].network),Network)
                self.assertIs(kwargs['github'].network,kwargs['cloud'].network)
                self.assertEqual(kwargs['github'].token_owner,1003)
                self.assertFalse(kwargs['test_only'])


if __name__=='__main__':unittest.main()
