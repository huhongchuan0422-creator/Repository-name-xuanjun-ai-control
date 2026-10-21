import os
import socket
import tempfile
import unittest
from unittest.mock import patch, Mock
from pathlib import Path
from scripts import community_owner_readonly_supplement_20261021 as probe


class SupplementTests(unittest.TestCase):
    def test_combined_cpu_mount_and_membership(self):
        mounts = probe.mounts_from('1 0 0:1 / /sys/fs/cgroup/cpu,cpuacct rw - cgroup cgroup rw,cpu,cpuacct\n2 0 0:2 / /sys/fs/cgroup/pids rw - cgroup cgroup rw,pids')
        self.assertEqual(mounts[0]['controllers'], ['cpu'])
        self.assertEqual(probe.group_path(mounts[0], '/system.slice/example.service'), '/sys/fs/cgroup/cpu,cpuacct/system.slice/example.service')
        self.assertEqual(mounts[1]['controllers'], ['pids'])

    def test_v2_and_mount_root_boundary(self):
        mount = probe.mounts_from('1 0 0:1 /slice /sys/fs/cgroup rw - cgroup2 cgroup rw')[0]
        self.assertEqual(probe.group_path(mount, '/slice/child'), '/sys/fs/cgroup/child')
        for bad in ('/other/child', '/slice/../escape'):
            with self.assertRaises(ValueError):
                probe.group_path(mount, bad)
        self.assertEqual(probe.mounts_from('1 0 0:1 / /sys/fs/cgroup-escape rw - cgroup cgroup rw,cpu'), [])

    def test_symlink_parent_and_leaf_rejected_size_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'real').mkdir()
            (root / 'real' / 'data').write_bytes(b'12345')
            (root / 'alias').symlink_to(root / 'real', target_is_directory=True)
            (root / 'leaf').symlink_to(root / 'real' / 'data')
            for path in (root / 'alias' / 'data', root / 'leaf'):
                with self.assertRaises(OSError):
                    probe.read_absolute(str(path), 10)
            with self.assertRaises(ValueError):
                probe.read_absolute(str(root / 'real' / 'data'), 4)
            self.assertEqual(probe.read_absolute(str(root / 'real' / 'data'), 5), b'12345')

    def test_dns_failures_are_distinct_and_not_authoritative(self):
        self.assertEqual(probe.classify_dns(socket.EAI_AGAIN), 'TEMPORARY_RESOLVER_FAILURE')
        self.assertIn('NOT_AUTHORITATIVE_NXDOMAIN', probe.classify_dns(socket.EAI_NONAME))
        self.assertEqual(probe.classify_dns(socket.EAI_FAIL), 'NONRECOVERABLE_RESOLVER_FAILURE')
        self.assertEqual(probe.classify_dns(99999), 'OTHER_RESOLVER_FAILURE')

    def test_mount_based_probe_reads_combined_path_without_alias_fallback(self):
        reads = []
        def reader(path, limit):
            reads.append(path)
            if path.endswith('/mountinfo'):
                return b'1 0 0:1 / /sys/fs/cgroup/cpu,cpuacct rw - cgroup cgroup rw,cpu,cpuacct'
            if path.endswith('/cgroup'):
                return b'3:cpu,cpuacct:/\n'
            if path.endswith('cpu.cfs_period_us'):
                return b'100000\n'
            if path.endswith('cpu.cfs_quota_us'):
                raise PermissionError('do not retry elsewhere')
            self.fail('Unexpected read '+path)
        with patch.object(probe, 'read_absolute', reader):
            result = probe.cgroup_probe()
        self.assertEqual(result['entries'][0]['values']['cpu.cfs_quota_us'], 'PERMISSION_DENIED')
        self.assertEqual(result['entries'][0]['values']['cpu.cfs_period_us'], '100000')
        self.assertTrue(all('/self/' not in p and '/cpu/' not in p for p in reads))

    def test_dns_timeout_kills_only_created_resolver_child(self):
        child = Mock()
        child.communicate.side_effect = [probe.subprocess.TimeoutExpired('fixed resolver', 8), (b'', None)]
        with patch.object(probe.subprocess, 'Popen', return_value=child):
            result = probe.dns_probe()
        self.assertEqual(result['status'], 'RESOLVER_TIMEOUT')
        child.kill.assert_called_once_with()

    def test_wrong_host_rejected_before_any_probe(self):
        with patch.object(probe.os, 'uname', return_value=Mock(nodename='wrong-host')), patch.object(probe, 'cgroup_probe') as cg, patch.object(probe, 'domestic_probe') as domestic, patch.object(probe, 'dns_probe') as dns:
            with self.assertRaises(SystemExit):
                probe.main()
        cg.assert_not_called()
        domestic.assert_not_called()
        dns.assert_not_called()

    def test_constraints_export_only_declared_column_names(self):
        source = '''class CustomerSource(Base):
 source_type=Column(String(40),nullable=False)
 source_id=Column(String(128),nullable=False)
 __table_args__=(UniqueConstraint('source_type','source_id',name='SECRET_CONSTRAINT_NAME'),UniqueConstraint('NOT_A_FIELD'))
'''
        result = probe.constraint_structure(source)
        self.assertEqual(result[0]['unique_constraints'], [['source_type', 'source_id'], ['<UNRESOLVED_FIELD>']])
        self.assertNotIn('SECRET_CONSTRAINT_NAME', str(result))
        self.assertNotIn('NOT_A_FIELD', str(result))

    def test_transaction_structure_keeps_commit_rollback_not_secrets(self):
        source = '''DATABASE_URL='SECRET_CONNECTION_STRING'
@contextmanager
def session_scope(factory=None):
 session=(factory or SessionLocal)()
 try:
  yield session
  session.commit()
 except Exception:
  session.rollback()
  raise ValueError('SECRET_LITERAL')
 finally:
  session.close()
'''
        result = str(probe.transaction_structure(source))
        for name in ('commit', 'rollback', 'close', 'Yield'):
            self.assertIn(name, result)
        self.assertNotIn('SECRET_CONNECTION_STRING', result)
        self.assertNotIn('SECRET_LITERAL', result)


if __name__ == '__main__':
    unittest.main()
