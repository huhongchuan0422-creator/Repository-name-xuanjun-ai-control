"""Fail-closed P2 metadata preimages and privacy projection, LOCAL candidate only.

Pure stdlib. No kit import, I/O, host access, source execution, or input fingerprint
export. Full preimages include SENSITIVE DIGESTS and MUST remain onsite. Only
privacy_project produces the narrowed export candidate. Closed schemas describe
metadata, never arbitrary input dictionaries.
The literal templates below come from the public real-factory synthetic fixture,
then are constrained by the public source contracts. Unsupported shape/path is a
static HOLD, not a license to redact and continue with an original-object hash.
Synthetic fixture support does not assert that the unavailable actual Seed fits.
"""
import copy
import hashlib
import json
import re
from types import MappingProxyType

MAX_BYTES = 8 * 1024 * 1024
MAX_SEGMENT_BYTES = 2097152
MAX_RECORDS = 32768
MAX_ROWS = 8192
MAX_TOTAL_INDICES = 17 * 15 * MAX_ROWS

# Exact authenticated private Packet identity, not a proof-supplied allowlist.
PACKET_SIZE = 29665
PACKET_SHA256 = '2bf597ef911cba70b5c94559ee36d8f90c2a339a3de1bfd2d8f58547900b8dec'
PACKET_INVENTORY_COUNT = 47
PACKET_DIRECTORY_COUNT = 9

SECTIONS = ('access',
 'activation',
 'boot',
 'database',
 'gateway',
 'generation',
 'historical',
 'identities',
 'native',
 'plugin',
 'release',
 'runtime_access',
 'sandbox',
 'targets',
 'tls')

TEMPLATES = {'acceptance_contract': {'access': [{'identity': {'gid': 1006,
                                                  'groups': '@groups',
                                                  'nss_groups': '@groups',
                                                  'uid': 1004,
                                                  'unit': 'xuanjun-uk-owner-callback.service',
                                                  'unit_supplementary_groups': '@groups',
                                                  'user': 'xuanjun-callback'},
                                     'paths': [{'kind': 'file',
                                                'path': '/etc/xuanjun-development/p2-owner-process-identity.json',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/etc/xuanjun-owner-callback/owner-callback-auth',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/etc/xuanjun-owner-callback/owner-callback-hmac',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/etc/xuanjun-owner-callback/owner-chat-id',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/etc/xuanjun-owner-callback/owner-user-id',
                                                'sha256': '@sha256'},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases',
                                                'sha256': None},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633',
                                                'sha256': None},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1',
                                                'sha256': None},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/activation_control.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/dependency_evidence_view.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_client.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_projection.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_transport.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_server_identity.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_ledger_operations.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_peer_identity.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_callback_server.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_dashboard.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_process_identity.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/run_usage_projection.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/task_cost_projection.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/uk_owner_callback_core.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/var/lib/xuanjun-development/activation/active.json',
                                                'sha256': '@sha256'}],
                                     'role': 'callback'},
                                    {'identity': {'gid': 1006,
                                                  'groups': '@groups',
                                                  'nss_groups': '@groups',
                                                  'uid': 1004,
                                                  'unit': 'xuanjun-uk-owner-dashboard.service',
                                                  'unit_supplementary_groups': '@groups',
                                                  'user': 'xuanjun-callback'},
                                     'paths': [{'kind': 'file',
                                                'path': '/etc/xuanjun-development/p2-ledger-server-identity.json',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/etc/xuanjun-owner-callback/owner-dashboard-token',
                                                'sha256': '@sha256'},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases',
                                                'sha256': None},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633',
                                                'sha256': None},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1',
                                                'sha256': None},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/activation_control.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/dependency_evidence_view.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_client.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_projection.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_transport.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_server_identity.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_peer_identity.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_dashboard.html',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_dashboard.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/run_usage_projection.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/task_cost_projection.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/var/lib/xuanjun-development/activation/active.json',
                                                'sha256': '@sha256'}],
                                     'role': 'dashboard'},
                                    {'identity': {'gid': 1003,
                                                  'groups': '@groups',
                                                  'nss_groups': '@groups',
                                                  'uid': 1003,
                                                  'unit': 'xuanjun-development-dispatcher.service',
                                                  'unit_supplementary_groups': '@groups',
                                                  'user': 'xuanjun-dispatcher'},
                                     'paths': [{'kind': 'file',
                                                'path': '/etc/xuanjun-development/dispatcher.json',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/etc/xuanjun-development/p2-native-ledger-client.json',
                                                'sha256': '@sha256'},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases',
                                                'sha256': None},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633',
                                                'sha256': None},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1',
                                                'sha256': None},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/activation_control.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/codex_worker.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/development_loop.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/development_pipeline.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/development_service.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/execution_ledger.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/execution_supervision.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_projection.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_transport.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_server_identity.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_child_adapter.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_gateway_controller.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_gateway_controller.py.json',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_github_notifier.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_pipeline_runtime.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_snapshot_access.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_service_context_preflight.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/task_supervisor_inventory_adapter.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/var/lib/xuanjun-development/activation/active.json',
                                                'sha256': '@sha256'}],
                                     'role': 'dispatcher'},
                                    {'identity': {'gid': 1002,
                                                  'groups': '@groups',
                                                  'nss_groups': '@groups',
                                                  'uid': 1002,
                                                  'unit': 'xuanjun-uk-openclaw.service',
                                                  'unit_supplementary_groups': '@groups',
                                                  'user': 'xuanjun_dev'},
                                     'paths': [{'kind': 'file',
                                                'path': '/etc/xuanjun-development/p2-ledger-server-identity.json',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/etc/xuanjun-development/p2-native-controller.binding.json',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/etc/xuanjun-development/p2-native-ledger-client.json',
                                                'sha256': '@sha256'},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases',
                                                'sha256': None},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633',
                                                'sha256': None},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1',
                                                'sha256': None},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/activation_control.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_projection.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_transport.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_server_identity.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_ledger_bridge.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_peer_identity.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_feishu_bridge_cycle.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_feishu_history.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_feishu_https.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_feishu_transport.py',
                                                'sha256': '@sha256'}],
                                     'role': 'gateway'},
                                    {'identity': {'gid': 1006,
                                                  'groups': '@groups',
                                                  'nss_groups': '@groups',
                                                  'uid': 1003,
                                                  'unit': 'xuanjun-ledger.service',
                                                  'unit_supplementary_groups': '@groups',
                                                  'user': 'xuanjun-dispatcher'},
                                     'paths': [{'kind': 'file',
                                                'path': '/etc/xuanjun-development/p2-ledger-server-identity.json',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/etc/xuanjun-development/p2-native-ledger-client.json',
                                                'sha256': '@sha256'},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases',
                                                'sha256': None},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633',
                                                'sha256': None},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1',
                                                'sha256': None},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/activation_control.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/codex_worker.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/dependency_evidence_view.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/development_loop.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/development_pipeline.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/development_service.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/execution_ledger.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/execution_supervision.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_client.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_projection.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_transport.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_server_identity.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_service.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_child_adapter.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_github_notifier.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_ledger_operations.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_peer_identity.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_pipeline_runtime.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_snapshot_access.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_dashboard.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_feishu_claim_guard.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_feishu_ledger_endpoint.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_process_identity.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/run_usage_projection.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/task_cost_projection.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/task_supervisor_inventory_adapter.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/uk_owner_callback_core.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/var/lib/xuanjun-development/activation/active.json',
                                                'sha256': '@sha256'}],
                                     'role': 'ledger'},
                                    {'identity': {'gid': 1002,
                                                  'groups': '@groups',
                                                  'nss_groups': '@groups',
                                                  'uid': 1002,
                                                  'unit': 'xuanjun-p2-gateway-relay.service',
                                                  'unit_supplementary_groups': '@groups',
                                                  'user': 'xuanjun_dev'},
                                     'paths': [{'kind': 'file',
                                                'path': '/etc/xuanjun-development/p2-gateway-relay.json',
                                                'sha256': '@sha256'},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases',
                                                'sha256': None},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633',
                                                'sha256': None},
                                               {'kind': 'directory',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1',
                                                'sha256': None},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/activation_control.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_projection.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_transport.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_server_identity.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_child_adapter.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_gateway_controller.py',
                                                'sha256': '@sha256'},
                                               {'kind': 'file',
                                                'path': '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_gateway_relay.py',
                                                'sha256': '@sha256'}],
                                     'role': 'relay'}],
                         'access_worker_sha256': '@sha256',
                         'https_worker_sha256': '@sha256',
                         'sequence_contract_sha256': '@sha256',
                         'tls': {'certificate_sha256': '@sha256',
                                 'config_sha256': '@sha256',
                                 'domain': 'uk.wenwenwenyiyiyi.work',
                                 'journal': '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/tls-lifecycle.json',
                                 'journal_sha256': '@sha256',
                                 'manifest_sha256': '@sha256',
                                 'root': '/var/lib/xuanjun-development/tls-acme',
                                 'tree_sha256': '@sha256'}},
 'access_rows': [{'before_binding': {'access_acl': '@acl',
                                     'default_acl': '',
                                     'dev': '@u64',
                                     'gid': 0,
                                     'ino': '@u64',
                                     'kind': 'DIRECTORY',
                                     'mode': 488,
                                     'sha256': None,
                                     'state_source': 'stage_exact_release_observed',
                                     'uid': 0},
                  'path': '/opt/xuanjun-control-releases',
                  'proposal': {'after_acl': '@acl',
                               'after_sha256': '@sha256',
                               'before_sha256': '@sha256',
                               'default_acl': False,
                               'permission_applied': False,
                               'purpose': 'release_traversal',
                               'recursive': False,
                               'requires_exact_inode_owner_mode_and_approval': True}},
                 {'before_binding': {'access_acl': '@acl',
                                     'default_acl': '',
                                     'gid': 0,
                                     'kind': 'FILE',
                                     'mode': 416,
                                     'sha256': '@sha256',
                                     'state_source': 'inner_provision_observed_after',
                                     'uid': 0},
                  'path': '/etc/xuanjun-development/p2-native-ledger-client.json',
                  'proposal': {'after_acl': '@acl',
                               'after_sha256': '@sha256',
                               'before_sha256': '@sha256',
                               'default_acl': False,
                               'permission_applied': False,
                               'purpose': 'ledger_client_binding_read',
                               'recursive': False,
                               'requires_exact_inode_owner_mode_and_approval': True}}],
 'additive_targets': [{'actual_host_pins_verified': False,
                       'after': {'gid': 0, 'kind': 'FILE', 'mode': 420, 'sha256': '@sha256', 'uid': 0},
                       'before': {'kind': 'ABSENT',
                                  'parent': {'acl_sha256': '@sha256',
                                             'dev': '@u64',
                                             'gid': 0,
                                             'ino': '@u64',
                                             'kind': 'DIRECTORY',
                                             'mode': 493,
                                             'path': '/etc/xuanjun-development',
                                             'uid': 0},
                                  'path': '/etc/xuanjun-development/p2-ledger-server-identity.json'},
                       'install_admission': 'NOT_GRANTED',
                       'kind': 'OFFLINE_ADDITIVE_IDENTITY_NOT_INSTALL_PLAN',
                       'operation': 'CREATE_EXCLUSIVE_PROTECTED_FILE',
                       'path': '/etc/xuanjun-development/p2-ledger-server-identity.json',
                       'permission_applied': False,
                       'provenance': {'activation_binding_sha256': '@sha256',
                                      'config_schema': 2,
                                      'runtime_manifest_sha256': '@sha256',
                                      'source_files': {'/etc/systemd/system/xuanjun-ledger.service': '@sha256',
                                                       '/etc/systemd/system/xuanjun-ledger.socket': '@sha256',
                                                       '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_service.py': '@sha256',
                                                       '/usr/bin/systemctl': '@sha256',
                                                       '/usr/lib/systemd/systemd': '@sha256'},
                                      'topology_evidence_sha256': '@sha256',
                                      'topology_review': {'approval_body_sha256': '@sha256',
                                                          'evidence_sha256': '@sha256',
                                                          'review_id': '@u64'},
                                      'validator_source_sha256': '@sha256'},
                       'purpose': 'LEDGER_SERVER_IDENTITY_PINS',
                       'requires_complete_new_review': True,
                       'schema': 1},
                      {'actual_host_pins_verified': False,
                       'after': {'gid': 0, 'kind': 'FILE', 'mode': 420, 'sha256': '@sha256', 'uid': 0},
                       'before': {'kind': 'ABSENT',
                                  'parent': {'acl_sha256': '@sha256',
                                             'dev': '@u64',
                                             'gid': 0,
                                             'ino': '@u64',
                                             'kind': 'DIRECTORY',
                                             'mode': 493,
                                             'path': '/etc/xuanjun-development',
                                             'uid': 0},
                                  'path': '/etc/xuanjun-development/p2-owner-process-identity.json'},
                       'install_admission': 'NOT_GRANTED',
                       'kind': 'OFFLINE_ADDITIVE_IDENTITY_NOT_INSTALL_PLAN',
                       'operation': 'CREATE_EXCLUSIVE_PROTECTED_FILE',
                       'path': '/etc/xuanjun-development/p2-owner-process-identity.json',
                       'permission_applied': False,
                       'provenance': {'callback_script_sha256': '@sha256',
                                      'config_schema': 1,
                                      'interpreter_observation_sha256': '@sha256',
                                      'rendered_unit_sha256': '@sha256',
                                      'runtime_manifest_sha256': '@sha256'},
                       'purpose': 'OWNER_PROCESS_IDENTITY_PINS',
                       'requires_complete_new_review': True,
                       'schema': 1}],
 'retained_delta': {'attempt_create_policy': 'O_EXCL_FSYNC_NO_RESUME_NO_RESET',
                    'authorized_attempts': 0,
                    'automatic_retry': False,
                    'cache_import_delete_or_rewrite': False,
                    'candidate_sha256': '@sha256',
                    'changes': [{'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/nginx/conf.d/xuanjun-p2-owner.conf'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/systemd/system/nginx.service'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'REPLACE_EXACT_FILE',
                                 'path': '/etc/systemd/system/xj-root-broker.service'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/systemd/system/xj-root-broker.socket'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'REPLACE_EXACT_FILE',
                                 'path': '/etc/systemd/system/xuanjun-development-dispatcher.service'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'REPLACE_EXACT_FILE',
                                 'path': '/etc/systemd/system/xuanjun-github-intake.service'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/systemd/system/xuanjun-github-intake.timer'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'REPLACE_EXACT_FILE',
                                 'path': '/etc/systemd/system/xuanjun-ledger.service'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/systemd/system/xuanjun-ledger.socket'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'REPLACE_EXACT_FILE',
                                 'path': '/etc/systemd/system/xuanjun-p2-gateway-relay.service'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/systemd/system/xuanjun-p2-gateway-relay.socket'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'REPLACE_EXACT_FILE',
                                 'path': '/etc/systemd/system/xuanjun-p2-tls-renew.service'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/systemd/system/xuanjun-p2-tls-renew.timer'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/systemd/system/xuanjun-uk-openclaw.service.d/20-p2-docker.conf'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'MASK',
                                            'link': '/dev/null',
                                            'uid': 0},
                                 'operation': 'REPLACE_EXACT_OWNER_MASK',
                                 'path': '/etc/systemd/system/xuanjun-uk-owner-callback.service'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'MASK',
                                            'link': '/dev/null',
                                            'uid': 0},
                                 'operation': 'REPLACE_EXACT_OWNER_MASK',
                                 'path': '/etc/systemd/system/xuanjun-uk-owner-dashboard.service'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/xuanjun-development/dispatcher.json'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/xuanjun-development/nginx-main.conf'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/xuanjun-development/p2-gateway-relay.json'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'REPLACE_EXACT_FILE',
                                 'path': '/etc/xuanjun-development/p2-native-controller.binding.json'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 416,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 416,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/xuanjun-development/p2-native-ledger-client.json'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/xuanjun-development/p2-owner-feishu-binding.json'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'RETAIN',
                                 'path': '/etc/xuanjun-development/root-broker.json'},
                                {'after': {'gid': 0,
                                           'kind': 'FILE',
                                           'mode': 420,
                                           'sha256': '@sha256',
                                           'uid': 0},
                                 'before': {'ctime_ns': '@u64',
                                            'dev': '@u64',
                                            'gid': 0,
                                            'ino': '@u64',
                                            'kind': 'FILE',
                                            'mode': 420,
                                            'mtime_ns': '@u64',
                                            'nlink': 1,
                                            'sha256': '@sha256',
                                            'size': '@u64',
                                            'uid': 0},
                                 'operation': 'REPLACE_EXACT_FILE',
                                 'path': '/etc/xuanjun-development/tls-renewal.json'}],
                    'controller_transition': {'after': {'binary_sha256': '@sha256',
                                                        'config_sha256': '@sha256',
                                                        'db_path': '/var/lib/xuanjun-development/generations/1/state.sqlite',
                                                        'epoch': 8,
                                                        'generation': 1,
                                                        'instance': '@uuid',
                                                        'ledger_socket': '/run/xuanjun-development/ledger.sock',
                                                        'ledger_uuid': '@uuid',
                                                        'release_sha256': '@sha256',
                                                        'schema': 1,
                                                        'state': 'PREPARED'},
                                              'before': {'binary_sha256': '@sha256',
                                                         'config_sha256': '@sha256',
                                                         'db_path': '/var/lib/xuanjun-development/generations/1/state.sqlite',
                                                         'epoch': 7,
                                                         'generation': 1,
                                                         'instance': '@uuid',
                                                         'ledger_socket': '/run/xuanjun-development/ledger.sock',
                                                         'ledger_uuid': '@uuid',
                                                         'release_sha256': '@sha256',
                                                         'schema': 1,
                                                         'state': 'PREPARED'},
                                              'operation': 'REPLACE_EXACT_REVIEWED_CONTROLLER',
                                              'preserved_identity': {'db_path': '/var/lib/xuanjun-development/generations/1/state.sqlite',
                                                                     'generation': 1,
                                                                     'instance': '@uuid',
                                                                     'ledger_socket': '/run/xuanjun-development/ledger.sock',
                                                                     'ledger_uuid': '@uuid',
                                                                     'schema': 1}},
                    'dry_run_calls': 0,
                    'effects': 0,
                    'expected_epoch': 7,
                    'failure_policy': 'FENCE_STOP_RETAIN_NO_REPLAY',
                    'generation_change': {'after': {'access_acl': '@acl',
                                                    'default_acl': '',
                                                    'dev': '@u64',
                                                    'gid': 1006,
                                                    'ino': '@u64',
                                                    'kind': 'DIRECTORY',
                                                    'mode': 448,
                                                    'path': '/var/lib/xuanjun-development/generations/1',
                                                    'uid': 1003},
                                          'before': {'access_acl': '@acl',
                                                     'default_acl': '',
                                                     'dev': '@u64',
                                                     'gid': 1006,
                                                     'ino': '@u64',
                                                     'kind': 'DIRECTORY',
                                                     'mode': 488,
                                                     'path': '/var/lib/xuanjun-development/generations/1',
                                                     'uid': 1003},
                                          'operation': 'FD_ANCHORED_CHMOD_ONLY',
                                          'recursive': False},
                    'install_admission': 'NOT_GRANTED',
                    'issuance_calls': 0,
                    'kind': 'OFFLINE_EPOCH7_DELTA_NOT_INSTALL_PLAN',
                    'legacy_restart': False,
                    'new_attempt_name': 'epoch7-recovery-execution-successor-a5602f7e70e22edba.json',
                    'prerequisite_replay': False,
                    'preserve': {'caches': {'/opt/xuanjun-control-releases/integration-1111111111111111': '@sha256',
                                            '/opt/xuanjun-control-releases/integration-153653ebc48d6b20': '@sha256',
                                            '/opt/xuanjun-control-releases/integration-338e488c4203e23d': '@sha256'},
                                 'database': {'dev': '@u64',
                                              'gid': 0,
                                              'ino': '@u64',
                                              'logical_manifest_sha256': '@sha256',
                                              'mode': 384,
                                              'nlink': 1,
                                              'path': '/var/lib/xuanjun-development/generations/1/state.sqlite',
                                              'sha256': '@sha256',
                                              'sidecars': [],
                                              'uid': 0},
                                 'receipts': {'bootstrap-files.json': '@sha256',
                                              'epoch3-recovery-execution.json': '@sha256',
                                              'epoch4-runtime-provisioning.json': '@sha256',
                                              'epoch5-prior-native-binding.json': '@sha256',
                                              'epoch5-prior-tls-lifecycle.json': '@sha256',
                                              'epoch5-recovery-execution.json': '@sha256',
                                              'epoch6-runtime-provisioning.json': '@sha256',
                                              'epoch6-tls-renewal-candidate.json': '@sha256',
                                              'ledger-cutover.json': '@sha256',
                                              'legacy-units.json': '@sha256',
                                              'owner-isolation-receipt.json': '@sha256',
                                              'prerequisites.json': '@sha256',
                                              'publisher-bootstrap.json': '@sha256',
                                              'recovery-execution.json': '@sha256',
                                              'rpm-prerequisites.json': '@sha256',
                                              'runtime-provisioning.json': '@sha256',
                                              'sandbox-profile.json': '@sha256'},
                                 'retained_resource_sha256': '@sha256',
                                 'tls': {'certificate_sha256': '@sha256',
                                         'config_identity_sha256': '@sha256',
                                         'journal_sha256': '@sha256',
                                         'release_sha256': '@sha256',
                                         'state': 'READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED',
                                         'tree_fingerprint_sha256': '@sha256'}},
                    'proposed_epoch': 8,
                    'renewal_calls': 0,
                    'runtime_manifest_sha256': '@sha256',
                    'sandbox_change': {'expected_profile_sha256': '@sha256',
                                       'new_journal_name': 'epoch7-sandbox-profile.json',
                                       'operation': 'NEW_JOURNAL_FROM_VERIFIED_RESTORED_PROFILE',
                                       'preserve_journal_sha256': '@sha256'},
                    'schema': 1,
                    'snapshot_sha256': '@sha256',
                    'tls_change': {'archive_name': 'epoch7-prior-tls-lifecycle.json',
                                   'before_journal_sha256': '@sha256',
                                   'certificate_sha256': '@sha256',
                                   'config_identity_sha256': '@sha256',
                                   'dry_run_calls': 0,
                                   'issuance_calls': 0,
                                   'new_release_sha256': '@sha256',
                                   'old_release_sha256': '@sha256',
                                   'operation': 'ARCHIVE_EXACT_THEN_REBIND_RELEASE_METADATA_ONLY',
                                   'renewal_calls': 0,
                                   'retained_state': 'READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED'},
                    'transaction_id': 'c529c379-9341-4510-8384-fc6be1e412e5'}}

FIXED_RESOURCE_PATHS = ['/etc/cron.d',
 '/etc/cron.daily',
 '/etc/cron.hourly',
 '/etc/cron.monthly',
 '/etc/cron.weekly',
 '/etc/crontab',
 '/etc/nginx/conf.d/xuanjun-p2-owner.conf',
 '/etc/nginx/mime.types',
 '/etc/passwd',
 '/etc/systemd/system/nginx.service',
 '/etc/systemd/system/xj-root-broker.service',
 '/etc/systemd/system/xj-root-broker.socket',
 '/etc/systemd/system/xuanjun-development-dispatcher.service',
 '/etc/systemd/system/xuanjun-github-intake.service',
 '/etc/systemd/system/xuanjun-github-intake.timer',
 '/etc/systemd/system/xuanjun-ledger.service',
 '/etc/systemd/system/xuanjun-ledger.socket',
 '/etc/systemd/system/xuanjun-p2-gateway-relay.service',
 '/etc/systemd/system/xuanjun-p2-gateway-relay.socket',
 '/etc/systemd/system/xuanjun-p2-tls-renew.service',
 '/etc/systemd/system/xuanjun-p2-tls-renew.timer',
 '/etc/systemd/system/xuanjun-uk-openclaw.service',
 '/etc/systemd/system/xuanjun-uk-openclaw.service.d/20-p2-docker.conf',
 '/etc/systemd/system/xuanjun-uk-owner-callback.service',
 '/etc/systemd/system/xuanjun-uk-owner-dashboard.service',
 '/etc/systemd/system/xuanjun-uk-stage1-minimal.service',
 '/etc/xuanjun-development/dispatcher.json',
 '/etc/xuanjun-development/nginx-main.conf',
 '/etc/xuanjun-development/p2-gateway-relay.json',
 '/etc/xuanjun-development/p2-ledger-server-identity.json',
 '/etc/xuanjun-development/p2-native-binding.json',
 '/etc/xuanjun-development/p2-native-controller.binding.json',
 '/etc/xuanjun-development/p2-native-ledger-client.json',
 '/etc/xuanjun-development/p2-owner-feishu-binding.json',
 '/etc/xuanjun-development/p2-owner-process-identity.json',
 '/etc/xuanjun-development/root-broker.json',
 '/etc/xuanjun-development/tls-renewal.json',
 '/etc/xuanjun-owner-callback/owner-callback-auth',
 '/etc/xuanjun-owner-callback/owner-callback-hmac',
 '/etc/xuanjun-owner-callback/owner-chat-id',
 '/etc/xuanjun-owner-callback/owner-dashboard-token',
 '/etc/xuanjun-owner-callback/owner-user-id',
 '/home/xuanjun_dev/.config/systemd/user',
 '/home/xuanjun_dev/.nvm/versions/node/v24.21.0/bin/node',
 '/home/xuanjun_dev/.openclaw/bin/openclaw',
 '/home/xuanjun_dev/.openclaw/extensions/xuanjun-p2-native-controller',
 '/home/xuanjun_dev/.openclaw/openclaw.json',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/build-info.json',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/cli/run-main.js',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/config-env-vars-CFjF0--K.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/dotenv-BAzkwZo-.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/dotenv-global-CP3dmTvh.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/entry.js',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/entry.respawn-3dMNRLSy.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/gateway-run-argv-DFDqy1EF.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/home-dir-D0b-ywue.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/node-version-DdJ6cN09.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/paths-CtO6iw0c.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/pre-bootstrap-8enrRXrE.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/pre-bootstrap-qgGGBbez.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/proxy-lifecycle-Dl57fEmL.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/run-BNH_gC9b.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/run-command-D-K_dOJ-.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/run-command-DZaWbUcA.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/runtime-guard-BRBHlR8W.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/runtime-guard-BavKlA92.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/shell-env-Cxj7hKd1.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/shell-env-Dc8Sl1Pk.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/state-dir-CfAW6S2K.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/utils-DUAwk2p5.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/gateway-run-argv.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/node-compile-cache.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/node-host-launcher.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/node-runtime-recovery.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/node-sqlite.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/node-version.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/openclaw.mjs',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/package.json',
 '/home/xuanjun_dev/uk-stage1-minimal/state.sqlite',
 '/home/xuanjun_dev/uk-stage1-minimal/state.sqlite-journal',
 '/home/xuanjun_dev/uk-stage1-minimal/state.sqlite-shm',
 '/home/xuanjun_dev/uk-stage1-minimal/state.sqlite-wal',
 '/opt/xuanjun-control-releases',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/INTEGRATION_MANIFEST.json',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/INTEGRATION_BINDING.md',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/UK_DISPATCHER_ROLLOUT.md',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/dispatcher.example.json',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/p2-gateway-relay.json.template',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/p2-native-controller.binding.json.template',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/p2-native-ledger-client.json.template',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/p2-nginx-main.conf',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/p2-nginx.service',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/p2-owner-feishu-binding.json.template',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/p2-tls-renewal.json.template',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/root-broker.example.json',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/uk-owner-workbench/README.md',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/uk-owner-workbench/nginx.conf.template',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/uk-owner-workbench/xuanjun-uk-owner-callback.service',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/uk-owner-workbench/xuanjun-uk-owner-dashboard.service',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/xj-root-broker.service',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/xj-root-broker.socket',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/xuanjun-development-dispatcher.service',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/xuanjun-github-intake.service',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/xuanjun-github-intake.timer',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/xuanjun-ledger.service',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/xuanjun-ledger.socket',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/xuanjun-p2-gateway-relay.service',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/xuanjun-p2-gateway-relay.socket',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/xuanjun-p2-tls-renew.service',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/xuanjun-p2-tls-renew.timer',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/xuanjun-uk-openclaw-p2-docker.conf',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins/p2-native-controller/canonical.mjs',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins/p2-native-controller/controller.mjs',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins/p2-native-controller/host.mjs',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins/p2-native-controller/index.mjs',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins/p2-native-controller/ledger.mjs',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins/p2-native-controller/openclaw.plugin.json',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins/p2-native-controller/package.json',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins/p2-native-controller/plugin.mjs',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins/p2-native-controller/sdk-layout.mjs',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins/p2-native-controller/strict-json.mjs',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins/p2-native-controller/workspace.mjs',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/scripts/uk-integration-install.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/scripts/uk-owner-workbench-config.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/scripts/uk-p2-install.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/scripts/uk-p2-tls-renew.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/scripts/xj-root-broker-client',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/activation_control.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/callback_schema_gate.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/codex_app_server_worker.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/codex_worker.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/dependency_evidence_view.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/development_loop.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/development_pipeline.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/development_service.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/execution_ledger.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/execution_supervision.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/github_issue_consumer.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_backup.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_cutover_transaction.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_install_stage.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_client.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_projection.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_read_transport.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_server_identity.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/ledger_service.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/legacy_host_adapter.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/legacy_quiescence.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/mechanical_wake.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/mechanical_wake_service.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_child_adapter.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_gateway_controller.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_gateway_controller.py.json',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_github_notifier.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_ledger_bridge.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_ledger_operations.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_peer_identity.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_pipeline_runtime.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/native_snapshot_access.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_approval_dispatch.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_callback_server.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_dashboard.html',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_dashboard.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_feishu_bridge_cycle.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_feishu_claim_guard.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_feishu_history.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_feishu_https.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_feishu_ledger_endpoint.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_feishu_transport.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_notification_outbox.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_process_identity.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/owner_update_router.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_auxiliary_isolation.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_bootstrap_files.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_fixed_host_runtime.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_gateway_relay.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_install_entrypoint.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_legacy_adoption.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_prerequisites.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_publisher_bootstrap.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_rpm_prerequisites.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_sandbox_profile.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_service_context_preflight.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/p2_tls_lifecycle.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/root_broker.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/run_usage_projection.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/task_cost_projection.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/task_supervisor_inventory_adapter.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/telegram_owner_transport.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/uk_owner_callback_core.py',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1/uk_owner_notify_worker.py',
 '/opt/xuanjun-control-releases/integration-1111111111111111',
 '/opt/xuanjun-control-releases/integration-1111111111111111/stage1/native.py',
 '/opt/xuanjun-control-releases/integration-153653ebc48d6b20',
 '/opt/xuanjun-control-releases/integration-153653ebc48d6b20/stage1/native.py',
 '/opt/xuanjun-control-releases/integration-153653ebc48d6b20/stage1/native_ledger_bridge.py',
 '/opt/xuanjun-control-releases/integration-338e488c4203e23d',
 '/opt/xuanjun-control-releases/integration-338e488c4203e23d/stage1/native.py',
 '/run/xuanjun-p2-install.lock',
 '/run/xuanjun-p2-runner-isolation.guard',
 '/usr/bin/git',
 '/usr/bin/openssl',
 '/usr/bin/python3',
 '/usr/bin/rpm',
 '/usr/bin/systemctl',
 '/usr/lib/systemd/systemd',
 '/usr/libexec/platform-python3.6',
 '/usr/sbin/nginx',
 '/usr/sbin/runuser',
 '/var/lib/xuanjun-development/.p2-publisher-synthetic',
 '/var/lib/xuanjun-development/activation/activation.lock',
 '/var/lib/xuanjun-development/activation/active.json',
 '/var/lib/xuanjun-development/activation/epochs.jsonl',
 '/var/lib/xuanjun-development/backups/c529c379-9341-4510-8384-fc6be1e412e5.sqlite',
 '/var/lib/xuanjun-development/backups/c529c379-9341-4510-8384-fc6be1e412e5.sqlite-journal',
 '/var/lib/xuanjun-development/backups/c529c379-9341-4510-8384-fc6be1e412e5.sqlite-shm',
 '/var/lib/xuanjun-development/backups/c529c379-9341-4510-8384-fc6be1e412e5.sqlite-wal',
 '/var/lib/xuanjun-development/control.git',
 '/var/lib/xuanjun-development/generations/1',
 '/var/lib/xuanjun-development/generations/1/state.sqlite',
 '/var/lib/xuanjun-development/service-home/.config/.p2-publisher-synthetic',
 '/var/lib/xuanjun-development/service-home/.config/gh',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520/protected-core-install-plan.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/bootstrap-files.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch3-prior-receipts/native-binding-original.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch3-recovery-execution.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch4-runtime-provisioning.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch5-prior-native-binding.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch5-prior-tls-lifecycle.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch5-recovery-execution.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch6-runtime-provisioning.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch6-tls-renewal-candidate.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-generation-access.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-owner-identity-publication.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-plugin-effects.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-prior-native-binding.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-prior-tls-lifecycle.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-recovery-execution-successor-a5602f7e70e22edba.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-recovery-execution.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-recovery-sequence.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-sandbox-profile-candidate.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-sandbox-profile-original.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-sandbox-profile.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-server-identity-publication.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-target-before-2be4fcc5ded53de7d29e5a882f7925b15db58da1458a2a38366a2ed3e46c2c88.private',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-target-before-342ed050eff958a7343263ec7900170e726a2d1b7c4f81496756c1944156cfab.private',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-target-before-40d0d5e12c9d1986dbdbe520953d462ec6b1af4697de6ad1431ff75e2bd742f7.private',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-target-before-5e2e8c343bf71ea94d38eed15d43413a0986961a19a7ea388a9f374a27728c58.private',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-target-before-7279b9b3e1f14bdbccbb885c48464ef7601f5baa67d5560985ff147e3bafe230.private',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-target-before-811c27ee21f77b0c7ae999acbb4a3546812cc710408a9de319e1ec2c825069c5.private',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-target-before-824127c6e8c42631c4cd7148c9164f92bb019891c7536d5ca965bce722b48db5.private',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-target-before-bb6d3708af250736cd68726aad132719e00e3b212695dc4fdc984855267b1a52.private',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-target-before-d6d792e588dadd4109429fedf374ff5a150e0bbf427ddb0c4b1b3707396f7661.private',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-target-before-d934713f163a0331b4a478fa12fadf7740eeac96d359acd4c058fc91ac726aa9.private',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch8-runtime-provisioning.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch8-tls-renewal-candidate.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/ledger-access.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/ledger-cutover.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/legacy-units.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/owner-isolation-receipt.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/prerequisites.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/publisher-bootstrap.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/recovery-execution.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/rpm-prerequisites.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/runtime-boot.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/runtime-provisioning.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/sandbox-profile-candidate.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/sandbox-profile-original.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/sandbox-profile.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/tls-lifecycle.json',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/xuanjun-uk-openclaw.service.backup',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/xuanjun-uk-stage1-minimal.service.backup',
 '/var/spool/at',
 '/var/spool/cron']

FIXED_DIRECTORY_PATHS = ['/',
 '/etc',
 '/etc/nginx',
 '/etc/nginx/conf.d',
 '/etc/systemd',
 '/etc/systemd/system',
 '/etc/systemd/system/xuanjun-uk-openclaw.service.d',
 '/etc/xuanjun-development',
 '/etc/xuanjun-owner-callback',
 '/home',
 '/home/xuanjun_dev',
 '/home/xuanjun_dev/.nvm',
 '/home/xuanjun_dev/.nvm/versions',
 '/home/xuanjun_dev/.nvm/versions/node',
 '/home/xuanjun_dev/.nvm/versions/node/v24.21.0',
 '/home/xuanjun_dev/.nvm/versions/node/v24.21.0/bin',
 '/home/xuanjun_dev/.openclaw',
 '/home/xuanjun_dev/.openclaw/bin',
 '/home/xuanjun_dev/.openclaw/tools',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist',
 '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/cli',
 '/home/xuanjun_dev/uk-stage1-minimal',
 '/opt',
 '/opt/xuanjun-control-releases',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/deploy/uk-owner-workbench',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/plugins/p2-native-controller',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/scripts',
 '/opt/xuanjun-control-releases/integration-0ac28c96636ee633/stage1',
 '/opt/xuanjun-control-releases/integration-153653ebc48d6b20',
 '/opt/xuanjun-control-releases/integration-153653ebc48d6b20/stage1',
 '/run',
 '/usr',
 '/usr/bin',
 '/usr/lib',
 '/usr/lib/systemd',
 '/usr/libexec',
 '/usr/sbin',
 '/var',
 '/var/lib',
 '/var/lib/xuanjun-development',
 '/var/lib/xuanjun-development/activation',
 '/var/lib/xuanjun-development/backups',
 '/var/lib/xuanjun-development/generations',
 '/var/lib/xuanjun-development/generations/1',
 '/var/lib/xuanjun-p2-preparation',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5',
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch3-prior-receipts']

PROJECTION_FIELDS = {'/home/xuanjun_dev/.openclaw/openclaw.json': [['plugins',
                                                'entries',
                                                'xuanjun-p2-native-controller',
                                                'enabled'],
                                               ['plugins',
                                                'entries',
                                                'xuanjun-p2-native-controller',
                                                'config']],
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-generation-access.json': [['state',
                                                                                                                                                                   'stage']],
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-owner-identity-publication.json': [['state',
                                                                                                                                                                            'stage']],
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-plugin-effects.json': [['state'],
                                                                                                                                                               ['previous']],
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-recovery-execution-successor-a5602f7e70e22edba.json': [['transaction_id']],
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-sandbox-profile.json': [['state'],
                                                                                                                                                                ['original_sha256'],
                                                                                                                                                                ['candidate_sha256']],
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch7-server-identity-publication.json': [['state',
                                                                                                                                                                             'stage']],
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/epoch8-runtime-provisioning.json': [['state',
                                                                                                                                                                      'stage']],
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/ledger-access.json': [['state']],
 '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/runtime-boot.json': [['state'],
                                                                                                                                                      ['units']]}

ROOT_FIELDS = {'schema', 'retained_delta', 'additive_targets', 'access_rows',
    'acceptance_contract', 'timer_saved_baseline', 'timer_contract', 'resources'}
TRANSACTION = '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5'
RELEASE_PARENT = '/opt/xuanjun-control-releases'
RELEASE = RELEASE_PARENT + '/integration-0ac28c96636ee633'
MANIFEST = '0ac28c96636ee63364015b375202779e2ef1dd0bd9f1b81e77d4387b6754316c'
DB = '/var/lib/xuanjun-development/generations/1/state.sqlite'
SOCKET = '/run/xuanjun-development/ledger.sock'
PYTHON_PATHS = ('/usr/libexec/platform-python3.6', '/usr/libexec/platform-python3.6m')
NODE_ROOT = '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0'
NODE_ANCESTORS = ('/', '/home', '/home/xuanjun_dev', '/home/xuanjun_dev/.openclaw',
    '/home/xuanjun_dev/.openclaw/tools', NODE_ROOT, NODE_ROOT + '/bin')
META_INTS = {'uid', 'gid', 'mode', 'dev', 'ino', 'nlink', 'size', 'mtime_ns', 'ctime_ns'}
ATTRS = {'access_acl', 'default_acl', 'capability'}
USERS = {'root', 'nginx', 'xuanjun_dev', 'xuanjun-dispatcher', 'xuanjun-callback', 'xj_codex_worker'}
GROUPS = USERS | {'docker', 'xuanjun-control-db', 'xuanjun-ledger-client'}
TIMER = 'xuanjun-p2-tls-renew.timer'
SERVICE = 'xuanjun-p2-tls-renew.service'
PROPERTIES = {TIMER: ('NextElapseUSecMonotonic', 'LastTriggerUSecMonotonic', 'ActiveEnterTimestampMonotonic'),
    SERVICE: ('ActiveEnterTimestampMonotonic', 'ExecMainStartTimestampMonotonic')}

class StaticHold(ValueError):
    """Only a bounded public code; never echo values or exception text."""


def need(condition, code='PREIMAGE_SCHEMA_HOLD'):
    if not condition:
        raise StaticHold(code)


def canonical(value, maximum=MAX_SEGMENT_BYTES):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise StaticHold('PREIMAGE_CANONICAL_HOLD') from None
    need(len(raw) <= maximum, 'PREIMAGE_SIZE_HOLD')
    return raw


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _keys(value, keys):
    need(type(value) is dict and set(value) == set(keys))


def _uint(value, maximum=(1 << 64) - 1, minimum=0):
    need(type(value) is int and minimum <= value <= maximum)


def _hash(value):
    need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None)


def _groups(value, zero=False):
    need(type(value) is list and len(value) <= 32)
    for item in value:
        _uint(item, 65535, 0 if zero else 1)
    need(value == sorted(set(value)))


def _acl(value):
    need(type(value) is str and 1 <= len(value) <= 4096 and value.endswith('\n'))
    lines = value.splitlines()
    need(len(lines) <= 35 and len(set(lines)) == len(lines))
    slots = set()
    for line in lines:
        match = re.fullmatch(r'(user|group|mask|other):([0-9]{1,10})?:([r-][w-][x-])', line)
        need(match is not None)
        kind, ident, unused = match.groups()
        need(ident is None or kind in ('user', 'group') and str(int(ident)) == ident and int(ident) <= 4294967294)
        need((kind, ident) not in slots)
        slots.add((kind, ident))
    need({('user', None), ('group', None), ('other', None)} <= slots)
    need(not any(ident is not None for kind, ident in slots) or ('mask', None) in slots)


def _budget(value):
    """Bound structure before recursion, copying, hashing, or transport output."""
    todo = [(value, 0)]
    nodes = 0
    while todo:
        node, depth = todo.pop()
        nodes += 1
        need(nodes <= 500000 and depth <= 24, 'PREIMAGE_STRUCTURE_BOUND_HOLD')
        if type(node) is dict:
            need(len(node) <= MAX_ROWS and all(type(k) is str and len(k) <= 4096 for k in node))
            todo.extend((v, depth + 1) for v in node.values())
        elif type(node) is list:
            need(len(node) <= MAX_RECORDS)
            todo.extend((v, depth + 1) for v in node)
        elif type(node) is str:
            need(len(node) <= 4096)
        else:
            need(type(node) in (int, bool, type(None)))
    canonical(value, MAX_BYTES)


def _match(value, schema, trail=()):
    """Recursive closed literal schemas. No runtime schema is inferred from input."""
    if schema == '@sha256':
        _hash(value); return
    if schema == '@u64':
        _uint(value, minimum=1 if trail and trail[-1] in ('ino', 'nlink', 'review_id') else 0); return
    if schema == '@uuid':
        need(type(value) is str and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value) is not None)
        return  # Lowercase 8-4-4-4-12 hexadecimal is the canonical UUID spelling.
    if schema == '@acl':
        _acl(value); return
    if schema == '@groups':
        _groups(value); return
    if trail == ('retained_delta', 'preserve', 'caches'):
        need(type(value) is dict and 3 <= len(value) <= 16)
        for path, item in value.items():
            need(type(path) is str and re.fullmatch(re.escape(RELEASE_PARENT) + r'/integration-[0-9a-f]{16}', path) is not None)
            _hash(item)
        need(RELEASE_PARENT + '/integration-153653ebc48d6b20' in value)
        return
    if len(trail) == 4 and trail[:2] == ('retained_delta', 'changes') and trail[-1] == 'operation':
        need(value in ('RETAIN', 'REPLACE_EXACT_FILE', 'REPLACE_EXACT_OWNER_MASK')); return
    if len(trail) == 5 and trail[:2] == ('retained_delta', 'changes') and trail[-2] in ('before', 'after'):
        if trail[-1] == 'mode' and schema != 0o777:
            need(type(value) is int and value in (0o600, 0o640, 0o644)); return
        if trail[-1] == 'gid':
            _uint(value, (1 << 32) - 1); return
    if type(schema) is dict:
        need(type(value) is dict)
        expected = dict(schema)
        # Exact optional complete stamp groups explicitly supported by original delta.
        if 'kind' in schema and 'dev' in schema and 'ino' in schema:
            kind = schema['kind']
            stamp = {'size', 'mtime_ns', 'ctime_ns'}
            if kind == 'FILE' and 'nlink' in schema:
                for k in stamp: expected.pop(k, None)
                if stamp & set(value): expected.update({k: '@u64' for k in stamp})
            elif kind in ('DIRECTORY', 'MASK') and trail[:1] == ('retained_delta',):
                stamp |= {'nlink'}
                if kind == 'MASK': stamp |= {'mode'}
                for k in stamp: expected.pop(k, None)
                if stamp & set(value):
                    expected.update({k: (511 if k == 'mode' else '@u64') for k in stamp})
        _keys(value, expected)
        for key, sub in expected.items(): _match(value[key], sub, trail + (key,))
        return
    if type(schema) is list:
        need(type(value) is list and len(value) == len(schema))
        for i, sub in enumerate(schema): _match(value[i], sub, trail + (i,))
        return
    need(type(value) is type(schema) and value == schema)


# Only known public payload relative paths, not arbitrary path suffixes.
_RELEASE_RELATIVES = frozenset(path.split('/integration-', 1)[1][17:] for path in FIXED_RESOURCE_PATHS
    if '/integration-' in path and len(path.split('/integration-', 1)[1]) > 17)
# Public inventory fixture and source validator retain only CPython 3.6 caches
# of known public stage1 modules. No wildcard filename or arbitrary suffix.
_RELEASE_RELATIVES |= frozenset('stage1/__pycache__/' + name[len('stage1/'):-3] + '.cpython-36.pyc'
    for name in _RELEASE_RELATIVES if name.startswith('stage1/') and name.endswith('.py')
    and '/' not in name[len('stage1/'):])
_FIXED_PATHS = frozenset(FIXED_RESOURCE_PATHS) | frozenset(FIXED_DIRECTORY_PATHS) | frozenset(PYTHON_PATHS) | frozenset(NODE_ANCESTORS) | {
    NODE_ROOT + '/bin/node', '/home/xuanjun_dev/.openclaw/tools/node',
    '/var/lib/xuanjun-development/tls-acme', '/opt/xuanjun-runtime',
    '/opt/xuanjun-runtime/codex-0.160.0', '/opt/xuanjun-runtime/codex-0.160.0/codex',
    '/opt/xuanjun-runtime/gh', '/opt/xuanjun-runtime/gh/gh'}


# These finite additions are independently present in the authenticated public
# factory source. They do not grant neighboring names or a different kind.
_EXECUTABLE_ALIAS_PATHS = frozenset(('/usr/bin/python3.6', '/etc/alternatives/python3',
    '/usr/libexec/platform-python', '/usr/bin/runuser', '/usr/bin/nginx'))
_DIRECT_SOURCE_PATH = NODE_ROOT + '/lib/node_modules/openclaw/dist/is-main-DYSvvM1W.mjs'
_DIRECT_SOURCE_SHA256 = 'cedd59a24eadaaf873515fabea73b776a66d40773c8ee5298f4946b9eef10469'
_ROOT_FILE_ACL = 'user::rw-\ngroup::---\nother::---\n'
_ROOT_DIRECTORY_ACL = 'user::rwx\ngroup::---\nother::---\n'
_PATH_SCOPE_TOKEN = object()


class _PacketPathScope:
    """An immutable local-only result of exact Packet authentication."""
    __slots__ = ('files', 'directories')

    def __init__(self, token, files, directories):
        need(token is _PATH_SCOPE_TOKEN, 'PREIMAGE_PATH_SCOPE_HOLD')
        object.__setattr__(self, 'files', MappingProxyType(dict(files)))
        object.__setattr__(self, 'directories', MappingProxyType({
            path: MappingProxyType(dict(row)) for path, row in directories.items()}))

    def __setattr__(self, name, value):
        raise StaticHold('PREIMAGE_PATH_SCOPE_HOLD')

    def __delattr__(self, name):
        raise StaticHold('PREIMAGE_PATH_SCOPE_HOLD')


def _check_path_scope(path_scope):
    need(path_scope is None or type(path_scope) is _PacketPathScope, 'PREIMAGE_PATH_SCOPE_HOLD')


def _transaction_scope_path(path, root=False):
    need(type(path) is str and len(path) <= 4096, 'PREIMAGE_PATH_SCOPE_HOLD')
    if root and path == TRANSACTION: return
    need(path.startswith(TRANSACTION + '/'), 'PREIMAGE_PATH_SCOPE_HOLD')
    parts = path[len(TRANSACTION) + 1:].split('/')
    need(all(1 <= len(part) <= 255 and part not in ('.', '..') and
        re.fullmatch(r'[A-Za-z0-9_.-]+', part) is not None for part in parts),
        'PREIMAGE_PATH_SCOPE_HOLD')


def path_scope_from_packet(packet):
    """Authenticate the exact canonical Packet plus LF before deriving scope.

    The caller independently supplies the retained private Packet onsite/offline.
    Neither a proof nor its claimed scope can confer path authority. This result
    and the inventory it contains MUST NOT be exported in any projection.
    """
    try:
        need(type(packet) is dict, 'PREIMAGE_PACKET_BINDING_HOLD')
        _budget(packet)
        raw = canonical(packet, MAX_BYTES) + b'\n'
        need(len(raw) == PACKET_SIZE and hashlib.sha256(raw).hexdigest() == PACKET_SHA256,
            'PREIMAGE_PACKET_BINDING_HOLD')
        measured = packet['measured_predecessor']
        _keys(measured, {'measurement', 'transaction_inventory', 'transaction_directories', 'transaction_parent_delta'})
        measurement = measured['measurement']
        _keys(measurement, {'schema', 'record', 'ancestors', 'absent'})
        need(type(measurement['schema']) is int and measurement['schema'] == 1)
        need(all(type(measurement[key]) is dict for key in ('record', 'ancestors', 'absent')))
        delta = measured['transaction_parent_delta']; _keys(delta, {'size', 'mtime_ns', 'ctime_ns'})
        for row in delta.values():
            _keys(row, {'historical', 'live'})
            for value in row.values(): _uint(value)
        files = measured['transaction_inventory']; directories = measured['transaction_directories']
        need(type(files) is dict and len(files) == PACKET_INVENTORY_COUNT, 'PREIMAGE_PATH_SCOPE_HOLD')
        need(type(directories) is dict and len(directories) == PACKET_DIRECTORY_COUNT and
            TRANSACTION in directories, 'PREIMAGE_PATH_SCOPE_HOLD')
        for path, sha in files.items():
            _transaction_scope_path(path); _hash(sha)
            need(path not in directories and path.rsplit('/', 1)[0] in directories, 'PREIMAGE_PATH_SCOPE_HOLD')
        for path, row in directories.items():
            _transaction_scope_path(path, root=True)
            _keys(row, META_INTS | {'path', 'kind', 'access_acl', 'default_acl'})
            need(row['path'] == path and row['kind'] == 'DIRECTORY', 'PREIMAGE_PATH_SCOPE_HOLD')
            for key in META_INTS: _uint(row[key], (1 << 32) - 1 if key in ('uid', 'gid') else (1 << 64) - 1)
            need(row['dev'] > 0 and row['ino'] > 0 and row['nlink'] > 0 and
                (row['uid'], row['gid'], row['mode']) == (0, 0, 0o700) and
                row['access_acl'] == _ROOT_DIRECTORY_ACL and row['default_acl'] == '', 'PREIMAGE_PATH_SCOPE_HOLD')
            need(path == TRANSACTION or path.rsplit('/', 1)[0] in directories, 'PREIMAGE_PATH_SCOPE_HOLD')
        return _PacketPathScope(_PATH_SCOPE_TOKEN, files, directories)
    except StaticHold:
        raise
    except (ValueError, TypeError, KeyError, IndexError, UnicodeError, OverflowError, RecursionError, AttributeError):
        raise StaticHold('PREIMAGE_PATH_SCOPE_HOLD') from None


def _path(value, path_scope=None):
    _check_path_scope(path_scope)
    need(type(value) is str and len(value) <= 4096 and '\x00' not in value)
    if value in _FIXED_PATHS or value in _EXECUTABLE_ALIAS_PATHS or value == _DIRECT_SOURCE_PATH: return
    if path_scope is not None and (value in path_scope.files or value in path_scope.directories): return
    match = re.fullmatch(re.escape(RELEASE_PARENT) + r'/integration-[0-9a-f]{16}(?:/(.+))?', value)
    if match:
        relative = match.group(1)
        need(relative is None or relative in _RELEASE_RELATIVES or
            any(item.startswith(relative + '/') for item in _RELEASE_RELATIVES))
        return
    if re.fullmatch(re.escape(TRANSACTION) + r'/epoch7-target-before-[0-9a-f]{64}\.private', value): return
    for parent in ('/var/lib/xuanjun-development', '/var/lib/xuanjun-development/service-home/.config'):
        if re.fullmatch(re.escape(parent) + r'/\.p2-publisher-[a-z0-9_]{8}', value): return
    # Fixed retained Certbot lineage, account metadata and conventional bounded
    # filenames only. The observer permits a larger tree; unsupported names HOLD.
    tls = '/var/lib/xuanjun-development/tls-acme'
    domain = 'uk.wenwenwenyiyiyi.work'
    fixed_tls = {'client.ini', 'config', 'work', 'logs', 'config/.certbot.lock',
        'work/.certbot.lock', 'logs/.certbot.lock', 'config/accounts', 'config/archive',
        'config/live', 'config/live/README', 'config/renewal', 'config/keys', 'config/csr',
        'config/renewal-hooks', 'config/renewal-hooks/pre', 'config/renewal-hooks/deploy',
        'config/renewal-hooks/post', 'config/archive/' + domain, 'config/live/' + domain,
        'config/live/' + domain + '/README', 'config/renewal/' + domain + '.conf'}
    fixed_tls |= {'config/live/' + domain + '/' + name + '.pem' for name in ('cert', 'chain', 'fullchain', 'privkey')}
    if value.startswith(tls + '/'):
        relative = value[len(tls) + 1:]
        if relative in fixed_tls: return
        if re.fullmatch(r'config/archive/' + re.escape(domain) + r'/(?:cert|chain|fullchain|privkey)[1-9][0-9]{0,5}\.pem', relative): return
        if re.fullmatch(r'config/(?:keys/[0-9]{4}_key|csr/[0-9]{4}_csr)-certbot\.pem', relative): return
        if re.fullmatch(r'logs/letsencrypt\.log(?:\.[1-9][0-9]{0,2})?', relative): return
        if re.fullmatch(r'config/accounts/acme-(?:v02|staging-v02)\.api\.letsencrypt\.org(?:/directory(?:/[0-9a-f]{32}(?:/(?:meta|private_key|regr)\.json)?)?)?', relative): return
    need(False, 'PREIMAGE_UNSUPPORTED_PATH_HOLD')


def _meta(row, kind, extras=()):
    _keys(row, META_INTS | {'kind'} | set(extras))
    need(row['kind'] == kind)
    for key in META_INTS: _uint(row[key], (1 << 32) - 1 if key in ('uid', 'gid') else (1 << 64) - 1)
    need(row['mode'] <= 0o7777 and row['dev'] > 0 and row['ino'] > 0 and row['nlink'] > 0)
    for key in ATTRS & set(extras): need(row[key] is False)
    if 'sha256' in extras: _hash(row['sha256'])
    if 'elf_header' in extras: need(row['elf_header'] is True)


def _python_identity(value):
    _keys(value, {'schema', 'kind', 'retained_sha256', 'owner_report_sha256', 'package_claim_sha256',
        'package_signature_authenticity', 'sample', 'reread'})
    fixed = {'schema': 1, 'kind': 'EXACT_RETAINED_PYTHON_TWO_NAME_V1',
        'retained_sha256': 'ba19929d7038d0c2304f528213fa11e5f10c1ce65f0a891afa459bd167c7e5f6',
        'owner_report_sha256': '88cc60f8c3bc465c4025eeda297f98a0b00d5ca5e0a80d3266e52e00f997e2f3',
        'package_claim_sha256': '36aa67e302e6c0b3a9494128aa184a46ba06edbfbf3828209682caa7c7559b8d',
        'package_signature_authenticity': 'NOT_VERIFIED', 'reread': 'EXACT_PRE_POST'}
    for k, v in fixed.items(): need(type(value[k]) is type(v) and value[k] == v)
    sample = value['sample']; _keys(sample, {'files', 'ancestors'})
    _keys(sample['files'], PYTHON_PATHS); _keys(sample['ancestors'], {'/', '/usr', '/usr/libexec'})
    for row in sample['files'].values():
        _meta(row, 'FILE', ATTRS | {'sha256', 'elf_header'})
        need((row['uid'], row['gid'], row['mode'], row['nlink'], row['size']) == (0, 0, 0o755, 2, 15352))
        need(row['sha256'] == fixed['retained_sha256'])
    need(sample['files'][PYTHON_PATHS[0]] == sample['files'][PYTHON_PATHS[1]])
    for path, row in sample['ancestors'].items():
        _meta(row, 'DIRECTORY', ATTRS)
        need(row['uid'] == row['gid'] == 0 and row['mode'] == (0o555 if path == '/' else 0o755))
    need(len({(row['dev'], row['ino']) for row in sample['ancestors'].values()}) == 3)


def _node_reference(value):
    _keys(value, {'schema', 'kind', 'reference_path', 'link', 'final', 'ancestors', 'reread'})
    need(type(value['schema']) is int and value['schema'] == 1 and value['kind'] == 'FIXED_NODE_DIRECTORY_ALIAS'
        and value['reference_path'] == '/home/xuanjun_dev/.openclaw/tools/node/bin/node' and value['reread'] == 'EXACT_PRE_POST')
    link = value['link']; _keys(link, {'path', 'target', 'metadata'})
    need(link['path'] == '/home/xuanjun_dev/.openclaw/tools/node' and link['target'] in ('node-v24.21.0', NODE_ROOT))
    _meta(link['metadata'], 'SYMLINK'); row = link['metadata']
    need((row['uid'], row['gid']) in ((0, 0), (1002, 1002)) and (row['mode'], row['nlink']) == (0o777, 1) and row['size'] == len(link['target']))
    final = value['final']; _keys(final, {'path', 'sha256', 'metadata'}); _hash(final['sha256'])
    need(final['path'] == NODE_ROOT + '/bin/node')
    _meta(final['metadata'], 'FILE', ATTRS | {'sha256', 'elf_header'}); row = final['metadata']
    need((row['uid'], row['gid'], row['nlink']) == (1002, 1002, 1) and row['mode'] & 0o100 and
        not row['mode'] & 0o7022 and 0 < row['size'] <= 268435456 and row['sha256'] == final['sha256'])
    _keys(value['ancestors'], NODE_ANCESTORS)
    for path, row in value['ancestors'].items():
        _meta(row, 'DIRECTORY', ATTRS)
        need(row['uid'] in ((0,) if path in ('/', '/home') else (0, 1002)) and row['gid'] in (0, 1002)
            and not row['mode'] & 0o7022 and row['mode'] & 0o100
            and (row['mode'] & 1 or row['uid'] == 1002 or row['gid'] == 1002 and row['mode'] & 0o10))


def _nss(value):
    _keys(value, {'path', 'kind', 'prerequisites', 'accounts', 'group_ids', 'nss_by_primary'})
    need(value['path'] == '/etc/passwd' and value['kind'] == 'NSS_BINDINGS')
    for name in ('prerequisites', 'accounts', 'group_ids', 'nss_by_primary'):
        need(type(value[name]) is dict and len(value[name]) <= 64)
    for name, row in value['prerequisites'].items():
        need(name in {'user:' + n for n in USERS} | {'group:' + n for n in GROUPS})
        if name.startswith('user:'):
            _keys(row, {'uid', 'gid', 'groups'}); _groups(row['groups'], True)
            _uint(row['uid'], 65535); _uint(row['gid'], 65535)
        else:
            _keys(row, {'gid', 'members'}); _uint(row['gid'], 65535)
            need(type(row['members']) is list and len(row['members']) <= len(USERS)
                and all(type(n) is str and n in USERS for n in row['members']) and row['members'] == sorted(set(row['members'])))
    need(set(value['accounts']) <= USERS and set(value['group_ids']) <= GROUPS and set(value['nss_by_primary']) <= USERS)
    for row in value['accounts'].values():
        _keys(row, {'uid', 'primary_gid', 'global_group_gids'})
        _uint(row['uid'], 65535); _uint(row['primary_gid'], 65535); _groups(row['global_group_gids'], True)
    for gid in value['group_ids'].values(): _uint(gid, 65535)
    for rows in value['nss_by_primary'].values():
        need(type(rows) is dict and 1 <= len(rows) <= 8)
        for gid, groups in rows.items():
            need(type(gid) is str and re.fullmatch(r'0|[1-9][0-9]{0,4}', gid) is not None and int(gid) <= 65535)
            _groups(groups, True)


def _activation(value):
    schema = TEMPLATES['retained_delta']['controller_transition']['before']
    expected = dict(schema, state='@state', epoch='@epoch')
    _keys(value, expected)
    for key, wanted in expected.items():
        if key == 'state': need(value[key] in ('PREPARED', 'QUIESCED', 'ACTIVE'))
        elif key == 'epoch': need(type(value[key]) is int and value[key] in (7, 8))
        else: _match(value[key], wanted)
    pins = {7: ('153653ebc48d6b20680e513402dad077d50dce953ab3d4b7cc1748bcff0f64e7', 'd3d546fa491596cc4d82feac9746f0368eb65f20f3fd134164dca8055337dd3e'),
        8: (MANIFEST, '1de3690ede78832da9dd2f2607db0b5ae88d6f9d4de87e1cb1ce64f35dab8421')}
    need((value['release_sha256'], value['binary_sha256']) == pins[value['epoch']])


def _directory_state(value):
    base = {'uid', 'gid', 'mode', 'access_acl', 'default_acl'}
    need(type(value) is dict and set(value) in (base, base | {'dev', 'ino'}))
    for key in set(value) - {'access_acl', 'default_acl'}: _uint(value[key])
    need(value['uid'] < 2**32 and value['gid'] < 2**32 and value['mode'] <= 0o777 and not value['mode'] & 0o022)
    need(value['default_acl'] == ''); _acl(value['access_acl'])


def _previously_supported_path(path):
    try:
        _path(path)
        return True
    except StaticHold as exc:
        if str(exc) != 'PREIMAGE_UNSUPPORTED_PATH_HOLD': raise
        return False


def _scoped_directory(path, row, path_scope=None):
    _check_path_scope(path_scope)
    # Exact public additions represent files/links, never directories.
    need(path not in _EXECUTABLE_ALIAS_PATHS and path != _DIRECT_SOURCE_PATH, 'PREIMAGE_PATH_KIND_HOLD')
    if _previously_supported_path(path): return
    need(path_scope is not None and path in path_scope.directories, 'PREIMAGE_PATH_SCOPE_HOLD')
    expected = path_scope.directories[path]
    need(all(key in expected and type(value) is type(expected[key]) and value == expected[key]
        for key, value in row.items()), 'PREIMAGE_PATH_METADATA_HOLD')


def _scoped_resource(value, path_scope=None):
    path = value['path']; kind = value['kind']
    if path == _DIRECT_SOURCE_PATH:
        need(kind == 'FILE' and value.get('sha256') == _DIRECT_SOURCE_SHA256, 'PREIMAGE_PATH_KIND_HOLD')
    if path in _EXECUTABLE_ALIAS_PATHS:
        need(kind in ('FILE', 'LINK'), 'PREIMAGE_PATH_KIND_HOLD')
    if _previously_supported_path(path): return
    need(path_scope is not None, 'PREIMAGE_PATH_SCOPE_HOLD')
    if path in path_scope.files:
        need(kind == 'FILE' and value.get('sha256') == path_scope.files[path] and
            all(type(value.get(key)) is int and value[key] == expected for key, expected in
                (('uid', 0), ('gid', 0), ('mode', 0o600))) and
            value.get('access_acl') == _ROOT_FILE_ACL, 'PREIMAGE_PATH_METADATA_HOLD')
    else:
        need(path in path_scope.directories and kind == 'DIRECTORY', 'PREIMAGE_PATH_KIND_HOLD')
        _scoped_directory(path, {key: item for key, item in value.items() if key not in ('path', 'kind')}, path_scope=path_scope)


def _resource(value, path_scope=None):
    need(type(value) is dict and 'kind' in value and 'path' in value)
    _path(value['path'], path_scope=path_scope); kind = value['kind']
    _scoped_resource(value, path_scope=path_scope)
    base = {'path', 'kind', 'uid', 'gid', 'mode', 'sha256', 'access_acl'}
    shapes = {'ABSENT': {'path', 'kind'}, 'FILE': base,
        'SANDBOX_STABLE': base, 'MASK': {'path', 'kind', 'uid', 'gid', 'link'},
        'LINK': {'path', 'kind', 'uid', 'gid', 'sha256'},
        'PUBLISHER_FINGERPRINT': {'path', 'kind', 'uid', 'gid', 'dev', 'ino', 'sha256'},
        'TREE_INVENTORY': {'path', 'kind', 'sha256'}, 'OPTIONAL_INVENTORY': {'path', 'kind', 'sha256'},
        'EPOCH_CHAIN': base | {'descriptor', 'prefix_size', 'prefix_sha256'},
        'DATABASE_IDENTITY': base - {'sha256'} | {'dev', 'ino', 'nlink'},
        'JSON_CONTEXT_PROJECTION': base | {'fields'}, 'JSON_BOUND_PROJECTION': base | {'fields'},
        'JSON_OPTIONAL_PROJECTION': base | {'fields'}}
    if kind == 'NSS_BINDINGS': _nss(value); return
    if kind == 'DIRECTORY':
        need(set(value) in ({'path', 'kind', 'uid', 'gid', 'mode', 'access_acl', 'default_acl'},
            {'path', 'kind', 'uid', 'gid', 'mode', 'access_acl', 'default_acl', 'dev', 'ino'}))
        _directory_state({k: v for k, v in value.items() if k not in ('path', 'kind')}); return
    need(type(kind) is str and kind in shapes)
    expected = shapes[kind]
    if kind == 'FILE':
        extras = set(value) - base
        need(extras in (set(), {'python_identity'}, {'node_reference'}))
        expected = base | extras
    _keys(value, expected)
    for key in ('uid', 'gid', 'mode', 'dev', 'ino', 'nlink', 'prefix_size'):
        if key in value: _uint(value[key])
    if 'uid' in value: need(value['uid'] < 2**32 and value['gid'] < 2**32)
    if 'mode' in value: need(value['mode'] <= 0o777 and not value['mode'] & 0o022)
    if 'access_acl' in value: _acl(value['access_acl'])
    for key in ('sha256', 'prefix_sha256'):
        if key in value: _hash(value[key])
    if kind == 'MASK': need(value['link'] == '/dev/null' and value['uid'] == value['gid'] == 0)
    if kind == 'EPOCH_CHAIN':
        need(value['path'] == '/var/lib/xuanjun-development/activation/epochs.jsonl')
        _activation(value['descriptor']); need(digest(value['descriptor']) == value['sha256'])
    if kind == 'DATABASE_IDENTITY': need(value['path'] == DB and value['nlink'] == 1)
    if kind == 'SANDBOX_STABLE': need(value['path'] == '/home/xuanjun_dev/.openclaw/openclaw.json')
    if 'fields' in value:
        need(value['path'] in PROJECTION_FIELDS and value['fields'] == PROJECTION_FIELDS[value['path']])
        _match(value['fields'], PROJECTION_FIELDS[value['path']])
    if 'python_identity' in value:
        need(value['path'] in PYTHON_PATHS); _python_identity(value['python_identity'])
        row = value['python_identity']['sample']['files'][value['path']]
        need(all(value[k] == row[k] for k in ('uid', 'gid', 'mode', 'sha256')))
    if 'node_reference' in value:
        _node_reference(value['node_reference']); row = value['node_reference']['final']
        need(value['path'] == row['path'] and value['sha256'] == row['sha256'])


def _timespan(value):
    need(type(value) is str and 1 <= len(value) <= 256)
    if value == '0': return 0
    units = [('y', 31557600000000), ('month', 2629800000000), ('w', 604800000000),
        ('d', 86400000000), ('h', 3600000000), ('min', 60000000), ('s', 1000000), ('ms', 1000), ('us', 1)]
    order = {name: index for index, (name, unused) in enumerate(units)}
    scale = dict(units); previous = -1; result = 0
    for part in value.split(' '):
        match = re.fullmatch(r'(0|[1-9][0-9]{0,19})(?:\.([0-9]{1,6}))?(month|min|ms|us|y|w|d|h|s)', part)
        need(match is not None); number, fraction, unit = match.groups()
        need(order[unit] > previous and (fraction is None or scale[unit] < 60000000)); previous = order[unit]
        amount = int(number) * scale[unit]
        if fraction is not None:
            numerator = int(fraction) * scale[unit]; denominator = 10**len(fraction)
            need(numerator % denominator == 0); amount += numerator // denominator
        result += amount; _uint(result, (1 << 64) - 2)
    return result


def _timer(saved, contract):
    _keys(saved, PROPERTIES)
    parsed = {}; hashes = {}
    for unit, names in PROPERTIES.items():
        raw = saved[unit]
        need(type(raw) is str and 1 <= len(raw) <= 4096 and raw.endswith('\n') and '\r' not in raw)
        rows = {}
        for line in raw.splitlines():
            key, separator, val = line.partition('=')
            need(separator and key in names and key not in rows)
            if key == 'NextElapseUSecMonotonic' and val == 'infinity': rows[key] = None
            elif 'USec' in key: rows[key] = _timespan(val)
            else:
                need(re.fullmatch(r'0|[1-9][0-9]{0,19}', val) is not None)
                rows[key] = int(val); _uint(rows[key], (1 << 64) - 2)
        _keys(rows, names); parsed[unit] = rows; hashes[unit] = hashlib.sha256(raw.encode('ascii')).hexdigest()
    need(parsed[TIMER]['LastTriggerUSecMonotonic'] == parsed[SERVICE]['ActiveEnterTimestampMonotonic'] == parsed[SERVICE]['ExecMainStartTimestampMonotonic'] == 0)
    expected = {'schema': 1, 'baseline': parsed, 'raw_sha256': hashes, 'tail_seconds': 60,
        'minimum_margin_seconds': 180, 'timer_unit': TIMER, 'timer_start_phase': 'post_install_checks', 'production_acceptance': 'PENDING'}
    need(canonical(contract) == canonical(expected), 'PREIMAGE_TIMER_BINDING_HOLD')


def _resources(value, path_scope=None):
    _keys(value, {'schema', 'records', 'ordered_index', 'directories'})
    need(type(value['schema']) is int and value['schema'] == 1)
    records = value['records']; indexes = value['ordered_index']; directories = value['directories']
    need(type(records) is list and 1 <= len(records) <= MAX_RECORDS)
    seen = set()
    for row in records:
        _resource(row, path_scope=path_scope); raw = canonical(row)
        need(raw not in seen, 'PREIMAGE_DUPLICATE_RECORD_HOLD'); seen.add(raw)
    need(type(indexes) is list and len(indexes) == 17)
    views = []; used = set(); next_first = 0; count = 0; segments = []
    for checkpoint, index in enumerate(indexes):
        _keys(index, SECTIONS); view = {}; segment = []
        for name in SECTIONS:
            ids = index[name]; need(type(ids) is list and 1 <= len(ids) <= MAX_ROWS)
            count += len(ids); need(count <= MAX_TOTAL_INDICES)
            for record_id in ids:
                _uint(record_id, len(records) - 1)
                if record_id not in used:
                    need(record_id == next_first, 'PREIMAGE_RECORD_ORDER_HOLD'); next_first += 1; used.add(record_id)
            rows = [records[i] for i in ids]
            need(len({row['path'] for row in rows}) == len(rows), 'PREIMAGE_DUPLICATE_PATH_HOLD')
            view[name] = rows; segment.append([name, len(rows), digest(rows)])
        views.append(view); segments.append([checkpoint, segment])
    need(len(used) == len(records), 'PREIMAGE_UNUSED_RECORD_HOLD')
    need(type(directories) is dict and 1 <= len(directories) <= MAX_ROWS and '/' in directories)
    leaves = []
    for path in sorted(directories):
        _path(path, path_scope=path_scope); rows = directories[path]; need(type(rows) is list and 1 <= len(rows) <= 3)
        for row in rows:
            _directory_state(row); _scoped_directory(path, row, path_scope=path_scope)
        leaves.append(digest(['EPOCH7_RESOURCE_DIRECTORY_LEAF_V1', path, rows]))
    return views, {'views_sha256': digest(['EPOCH7_RESOURCE_VIEWS_SEGMENTED_V1', 17, segments]),
        'directories_sha256': digest(['EPOCH7_RESOURCE_DIRECTORIES_SEGMENTED_V1', len(leaves), leaves]),
        'record_count': len(records), 'ordered_row_count': count, 'directory_count': len(directories)}


def _validate(preimages, path_scope=None):
    _budget(preimages); _keys(preimages, ROOT_FIELDS)
    need(type(preimages['schema']) is int and preimages['schema'] == 1)
    for key, schema in TEMPLATES.items(): _match(preimages[key], schema, (key,))
    delta = preimages['retained_delta']; changes = delta['changes']
    need(len(changes) == 24 and len({row['path'] for row in changes}) == 24)
    for row in changes:
        expected = 'REPLACE_EXACT_OWNER_MASK' if row['before']['kind'] == 'MASK' else ('RETAIN' if row['before']['sha256'] == row['after']['sha256'] else 'REPLACE_EXACT_FILE')
        need(row['operation'] == expected, 'PREIMAGE_DELTA_OPERATION_HOLD')
        if row['before']['kind'] == 'FILE':
            need(all(row['before'][k] == row['after'][k] for k in ('uid', 'gid', 'mode')), 'PREIMAGE_DELTA_PERMISSION_HOLD')
        else:
            need(row['before']['uid'] == row['before']['gid'] == 0)
            need((row['after']['uid'], row['after']['gid'], row['after']['mode']) == (0, 0, 0o644))
    transition = delta['controller_transition']
    _activation(transition['before']); _activation(transition['after'])
    need(transition['before']['state'] == transition['after']['state'] == 'PREPARED')
    for key, value in transition['preserved_identity'].items(): need(value == transition['before'][key] == transition['after'][key])
    need(delta['runtime_manifest_sha256'] == MANIFEST and delta['tls_change']['new_release_sha256'] == MANIFEST)
    generation = delta['generation_change']
    need(generation['before']['access_acl'] == 'user::rwx\ngroup::r-x\nother::---\n'
        and generation['after']['access_acl'] == 'user::rwx\ngroup::---\nother::---\n')
    tls_change = delta['tls_change']; tls_before = delta['preserve']['tls']
    need(tls_change['before_journal_sha256'] == tls_before['journal_sha256']
        and tls_change['certificate_sha256'] == tls_before['certificate_sha256']
        and tls_change['config_identity_sha256'] == tls_before['config_identity_sha256']
        and tls_change['old_release_sha256'] == tls_before['release_sha256'] == transition['before']['release_sha256'])
    need(delta['sandbox_change']['preserve_journal_sha256'] == delta['preserve']['receipts']['sandbox-profile.json'])
    for addition in preimages['additive_targets']:
        need(addition['path'] == addition['before']['path'] and addition['provenance']['runtime_manifest_sha256'] == MANIFEST)
    for row in preimages['access_rows']:
        before = row['before_binding']['access_acl']; after = row['proposal']['after_acl']
        need(hashlib.sha256(before.encode()).hexdigest() == row['proposal']['before_sha256'] and
            hashlib.sha256(after.encode()).hexdigest() == row['proposal']['after_sha256'], 'PREIMAGE_ACL_BINDING_HOLD')
        parsed = {tuple(line.split(':')[:2]): line.split(':')[2] for line in before.splitlines()}
        release = row['proposal']['purpose'] == 'release_traversal'
        base = ('rwx', 'r-x', '---') if release else ('rw-', 'r--', '---')
        need(tuple(parsed[k] for k in (('user', ''), ('group', ''), ('other', ''))) == base
            and parsed.get(('mask', ''), base[1]) == base[1], 'PREIMAGE_ACL_POLICY_HOLD')
        grant = '--x' if release else 'r--'
        for uid in ((1002, 1003, 1004) if release else (1003,)):
            key = ('user', str(uid)); need(key not in parsed or parsed[key] == grant)
            parsed[key] = grant
        parsed[('mask', '')] = parsed.get(('mask', ''), parsed[('group', '')])
        order = {'user': 0, 'group': 1, 'mask': 2, 'other': 3}
        keys = sorted(parsed, key=lambda k: (order[k[0]], -1 if not k[1] else int(k[1])))
        expected_after = ''.join('%s:%s:%s\n' % (k[0], k[1], parsed[k]) for k in keys)
        need(after == expected_after, 'PREIMAGE_ACL_POLICY_HOLD')
    acceptance = preimages['acceptance_contract']
    need(acceptance['access_worker_sha256'] == 'a7d5e0c95a954576ab5fc72ee238740dba8e8c497036fdd2ecdc6a99e1d481f8'
        and acceptance['https_worker_sha256'] == '8e0695a03cdf9f53d2d1304a2c7baacd54cbd2b8bc22e3394b02486fc46497ec')
    need(acceptance['tls']['manifest_sha256'] == MANIFEST)
    for row in acceptance['access']:
        ident = row['identity']
        need(ident['groups'] == sorted(set(ident['nss_groups'] + ident['unit_supplementary_groups'] + [ident['gid']])))
    _timer(preimages['timer_saved_baseline'], preimages['timer_contract'])
    return _resources(preimages['resources'], path_scope=path_scope)


def build_preimages(factory, inputs, proposal_tuple, timer_contract, path_scope=None):
    """Use the actual already-validated proposal tuple; never call or import a kit.

    factory is retained for call-site clarity; no authority is inferred from it.
    Every included full object passes its exact schema before any result returns.
    This original full result MUST remain onsite; export privacy_project instead.
    """
    try:
        need(type(inputs) is dict and type(proposal_tuple) is tuple and len(proposal_tuple) == 9)
        raw = inputs['timer_raw_baseline']; _keys(raw, PROPERTIES)
        need(all(type(v) is bytes for v in raw.values()))
        records = []; seen = {}; indexes = []
        views = inputs['resource_views']; need(type(views) is list and len(views) == 17)
        for view in views:
            _keys(view, SECTIONS); index = {}
            for name in SECTIONS:
                rows = view[name]; need(type(rows) is list and 1 <= len(rows) <= MAX_ROWS)
                ids = []
                for row in rows:
                    _resource(row, path_scope=path_scope); packed = canonical(row)
                    if packed not in seen:
                        need(len(records) < MAX_RECORDS); seen[packed] = len(records); records.append(copy.deepcopy(row))
                    ids.append(seen[packed])
                index[name] = ids
            indexes.append(index)
        value = {'schema': 1, 'retained_delta': proposal_tuple[1], 'additive_targets': sorted(inputs['additive_deltas'], key=lambda row: row['path']),
            'access_rows': inputs['access_rows'], 'acceptance_contract': proposal_tuple[8],
            'timer_saved_baseline': {k: v.decode('ascii') for k, v in raw.items()}, 'timer_contract': timer_contract,
            'resources': {'schema': 1, 'records': records, 'ordered_index': indexes, 'directories': inputs['resource_directories']}}
        _validate(value, path_scope=path_scope)
        return copy.deepcopy(value)
    except StaticHold:
        raise
    except (ValueError, TypeError, KeyError, IndexError, UnicodeError, OverflowError, RecursionError, AttributeError):
        raise StaticHold('PREIMAGE_BUILD_HOLD') from None


def verify_preimages(preimages, plan, body, path_scope=None):
    """ONSITE full metadata-preimage consistency only, never host/seed truth."""
    try:
        unused_views, resources = _validate(preimages, path_scope=path_scope)
        need(type(plan) is dict and type(body) is dict)
        auth = body['retained_authorization']; host = plan['host_contract']; observer = plan['resource_observer']
        delta = preimages['retained_delta']; additions = preimages['additive_targets']
        expected = {'delta_sha256': digest(delta), 'additive_targets_sha256': digest(additions),
            'complete_delta_sha256': digest({'retained_delta': delta, 'additive_targets': additions}),
            'security_delta_sha256': digest(preimages['access_rows'])}
        need(all(auth.get(k) == v for k, v in expected.items()), 'PREIMAGE_AUTHORIZATION_BINDING_HOLD')
        summaries = [{'path': row['path'], 'uid': row['after']['uid'], 'gid': row['after']['gid'],
            'mode': row['after']['mode'], 'sha256': row['after']['sha256'], 'provenance_sha256': digest(row['provenance'])} for row in additions]
        need(auth['additive_targets'] == summaries and type(auth['retained_target_count']) is int and auth['retained_target_count'] == 24
            and type(auth['total_target_count']) is int and auth['total_target_count'] == 26, 'PREIMAGE_ADDITION_BINDING_HOLD')
        need(host['acceptance_contract_sha256'] == digest(preimages['acceptance_contract']) and
            host['timer_contract_sha256'] == digest(preimages['timer_contract']), 'PREIMAGE_HOST_BINDING_HOLD')
        sequence_sha = digest(body['sequence_contract'])
        need(host['sequence_contract_sha256'] == sequence_sha == preimages['acceptance_contract']['sequence_contract_sha256'], 'PREIMAGE_SEQUENCE_BINDING_HOLD')
        need(observer['views_sha256'] == resources['views_sha256'] and observer['directories_sha256'] == resources['directories_sha256'], 'PREIMAGE_RESOURCE_BINDING_HOLD')
        # Original live checkpoints bind these exact 255 ordered sections too.
        checkpoints = plan['live_controls']['checkpoints']
        need(type(checkpoints) is list and len(checkpoints) == 17)
        for index, row in enumerate(checkpoints):
            need(type(row) is dict and 'resources' in row)
            need(row['resources'] == {name: digest(unused_views[index][name]) for name in SECTIONS}, 'PREIMAGE_CHECKPOINT_BINDING_HOLD')
        return {'retained_delta': True, 'additive_targets': True, 'access_rows': True,
            'acceptance_contract': True, 'timer_contract': True, 'resource_views': True, 'resource_directories': True,
            'retained_target_count': 24, 'additive_target_count': 2, 'checkpoint_count': 17, 'section_count': 255,
            'unique_resource_records': resources['record_count'], 'ordered_resource_rows': resources['ordered_row_count'],
            'directory_count': resources['directory_count'], 'original_seed_independently_read': False,
            'hidden_input_root_independently_recomputed': False, 'host_freshness_verified': False}
    except StaticHold:
        raise
    except (ValueError, TypeError, KeyError, IndexError, UnicodeError, OverflowError, RecursionError, AttributeError):
        raise StaticHold('PREIMAGE_VERIFY_HOLD') from None

# Privacy projection is a DIFFERENT object. Original full preimages above are
# retained for onsite checks only; no original-root offline recomputation claim
# survives replacing an affected whole segment with an opaque commitment.
PRIVACY_KIND = 'P2_PRIVATE_PREIMAGES_PRIVACY_PROJECTION_V1'
PRIVACY_DOMAIN = 'P2_PRIVATE_PREIMAGE_SEGMENT_V1'
PRIVACY_SCHEME = 'HMAC_SHA256_EPHEMERAL_KEY_V1'
PRIVATE_SEGMENTS = ('retained_delta', 'access_rows', 'acceptance_contract', 'resource_views')
ONSITE_ONLY_ROOTS = ('acceptance_contract_sha256', 'complete_delta_sha256', 'delta_sha256',
    'security_delta_sha256', 'views_sha256')
VISIBLE_FIELDS = {'additive_targets', 'timer_saved_baseline', 'timer_contract', 'resource_directories'}
PROJECTED_FIELDS = {'schema', 'kind', 'context', 'visible', 'withheld', 'coverage', 'onsite_only_roots'}
WITHHELD_FIELDS = {'scheme', 'domain', 'segment', 'commitment', 'onsite_pin_match',
    'offline_recomputation', 'original_preimage'}
COVERAGE_KIND = 'PROJECTED_METADATA_ONLY_NOT_ORIGINAL_PREIMAGE'
TARGET_CONTENT = 'WITHHELD_IN_RETAINED_DELTA_SEGMENT'


def _privacy_context(context):
    _keys(context, {'session_nonce', 'new_seed_sha256', 'old_seed_sha256'})
    need(type(context['session_nonce']) is str and re.fullmatch(r'[0-9a-f]{32}', context['session_nonce']) is not None)
    _hash(context['new_seed_sha256']); _hash(context['old_seed_sha256'])


def _target_projection(changes):
    output = []
    for index, row in enumerate(changes):
        before = {k: row['before'][k] for k in ('kind', 'uid', 'gid', 'mode') if k in row['before']}
        after = {k: row['after'][k] for k in ('kind', 'uid', 'gid', 'mode')}
        output.append({'index': index, 'role': 'RETAINED_TARGET', 'path': row['path'],
            'operation': row['operation'], 'before': before, 'after': after,
            'content_sha256': TARGET_CONTENT})
    return output


def _validate_target_projection(targets):
    expected = TEMPLATES['retained_delta']['changes']
    need(type(targets) is list and len(targets) == 24)
    for index, row in enumerate(targets):
        _keys(row, {'index', 'role', 'path', 'operation', 'before', 'after', 'content_sha256'})
        need(type(row['index']) is int and row['index'] == index and row['role'] == 'RETAINED_TARGET'
            and row['path'] == expected[index]['path'] and row['content_sha256'] == TARGET_CONTENT)
        before, after = row['before'], row['after']
        before_kind = expected[index]['before']['kind']
        need(type(before) is dict and before.get('kind') == before_kind)
        if before_kind == 'MASK':
            need(set(before) in ({'kind', 'uid', 'gid'}, {'kind', 'uid', 'gid', 'mode'}))
            need(row['operation'] == 'REPLACE_EXACT_OWNER_MASK')
            if 'mode' in before: need(type(before['mode']) is int and before['mode'] == 0o777)
        else:
            _keys(before, {'kind', 'uid', 'gid', 'mode'})
            need(row['operation'] in ('RETAIN', 'REPLACE_EXACT_FILE'))
        _keys(after, {'kind', 'uid', 'gid', 'mode'}); need(after['kind'] == 'FILE')
        for metadata in (before, after):
            need(type(metadata['uid']) is int and metadata['uid'] == 0)
            _uint(metadata['gid'], (1 << 32) - 1)
            if metadata['kind'] == 'FILE': need(type(metadata['mode']) is int and metadata['mode'] in (0o600, 0o640, 0o644))
        if before_kind == 'FILE': need(all(before[k] == after[k] for k in ('uid', 'gid', 'mode')))
        else: need(before['gid'] == after['gid'] == 0 and after['mode'] == 0o644)


def _visible_directory_digest(directories, path_scope=None):
    need(type(directories) is dict and 1 <= len(directories) <= MAX_ROWS and '/' in directories)
    leaves = []
    for path in sorted(directories):
        _path(path, path_scope=path_scope); rows = directories[path]; need(type(rows) is list and 1 <= len(rows) <= 3)
        for row in rows:
            _directory_state(row); _scoped_directory(path, row, path_scope=path_scope)
        leaves.append(digest(['EPOCH7_RESOURCE_DIRECTORY_LEAF_V1', path, rows]))
    return digest(['EPOCH7_RESOURCE_DIRECTORIES_SEGMENTED_V1', len(leaves), leaves])


def privacy_project(preimages, key, context, path_scope=None):
    """Export only the confirmed narrow projection; no raw sensitive digests.

    Caller MUST first run verify_preimages(preimages, exact_plan, exact_body).
    This function rechecks all original schemas, then binds every WHOLE hidden
    segment to the ephemeral key and exact seed/nonce context. It performs no
    original-root equality check itself and cannot authenticate host reports.
    The key must never be exported/persisted. HMACs are opaque to the recipient.
    This does not eliminate guessing risks in already-public material.
    """
    try:
        import hmac
        need(type(key) is bytes and len(key) == 32, 'PREIMAGE_PRIVACY_KEY_HOLD')
        _privacy_context(context)
        unused_views, unused_resources = _validate(preimages, path_scope=path_scope)
        segments = {'retained_delta': preimages['retained_delta'], 'access_rows': preimages['access_rows'],
            'acceptance_contract': preimages['acceptance_contract'], 'resource_views': preimages['resources']}
        withheld = {}
        for name in PRIVATE_SEGMENTS:
            # Resource segment is the entire lossless original transport, with
            # all records and ordered indexes. None of it is exported below.
            mac = hmac.new(key, digestmod=hashlib.sha256)
            mac.update(canonical([PRIVACY_DOMAIN, context, name]))
            mac.update(b'\0')
            mac.update(canonical(segments[name], MAX_BYTES))
            withheld[name] = {'scheme': PRIVACY_SCHEME, 'domain': PRIVACY_DOMAIN, 'segment': name,
                'commitment': mac.hexdigest(), 'onsite_pin_match': True,
                'offline_recomputation': 'NOT_AVAILABLE', 'original_preimage': 'NOT_EXPORTED'}
        value = {'schema': 2, 'kind': PRIVACY_KIND, 'context': copy.deepcopy(context),
            'visible': {'additive_targets': copy.deepcopy(preimages['additive_targets']),
                'timer_saved_baseline': copy.deepcopy(preimages['timer_saved_baseline']),
                'timer_contract': copy.deepcopy(preimages['timer_contract']),
                'resource_directories': copy.deepcopy(preimages['resources']['directories'])},
            'withheld': withheld,
            'coverage': {'kind': COVERAGE_KIND, 'targets': _target_projection(preimages['retained_delta']['changes']),
                'resource_section_counts': [{name: len(index[name]) for name in SECTIONS}
                    for index in preimages['resources']['ordered_index']]},
            'onsite_only_roots': list(ONSITE_ONLY_ROOTS)}
        _validate_projected(value, path_scope=path_scope)
        return value
    except StaticHold:
        raise
    except (ValueError, TypeError, KeyError, IndexError, UnicodeError, OverflowError, RecursionError, AttributeError):
        raise StaticHold('PREIMAGE_PRIVACY_PROJECTION_HOLD') from None


def _validate_projected(value, path_scope=None):
    _budget(value); _keys(value, PROJECTED_FIELDS)
    need(type(value['schema']) is int and value['schema'] == 2 and value['kind'] == PRIVACY_KIND)
    _privacy_context(value['context'])
    need(value['onsite_only_roots'] == list(ONSITE_ONLY_ROOTS))
    visible = value['visible']; _keys(visible, VISIBLE_FIELDS)
    _match(visible['additive_targets'], TEMPLATES['additive_targets'], ('additive_targets',))
    for addition in visible['additive_targets']:
        need(addition['path'] == addition['before']['path'] and addition['provenance']['runtime_manifest_sha256'] == MANIFEST)
        if addition['purpose'] == 'LEDGER_SERVER_IDENTITY_PINS':
            provenance = addition['provenance']
            need(provenance['validator_source_sha256'] == 'c18b35dcaa1c9abb0ce926e5e044e131b222c3b6960af6aa40ce451c3502cd33'
                and provenance['topology_review']['evidence_sha256'] == provenance['topology_evidence_sha256'])
    _timer(visible['timer_saved_baseline'], visible['timer_contract'])
    directory_digest = _visible_directory_digest(visible['resource_directories'], path_scope=path_scope)
    _keys(value['withheld'], PRIVATE_SEGMENTS)
    for name, row in value['withheld'].items():
        _keys(row, WITHHELD_FIELDS)
        need(row['scheme'] == PRIVACY_SCHEME and row['domain'] == PRIVACY_DOMAIN and row['segment'] == name
            and row['onsite_pin_match'] is True and row['offline_recomputation'] == 'NOT_AVAILABLE'
            and row['original_preimage'] == 'NOT_EXPORTED')
        _hash(row['commitment'])
    coverage = value['coverage']; _keys(coverage, {'kind', 'targets', 'resource_section_counts'})
    need(coverage['kind'] == COVERAGE_KIND); _validate_target_projection(coverage['targets'])
    counts = coverage['resource_section_counts']; need(type(counts) is list and len(counts) == 17)
    for index in counts:
        _keys(index, SECTIONS)
        for number in index.values(): _uint(number, MAX_ROWS, 1)
    return directory_digest


def verify_projected_preimages(projected, plan, body, path_scope=None):
    """Verify ONLY visible safe preimages; hidden roots remain onsite-only.

    A well-formed commitment cannot independently prove its hidden value or the
    Owner's computation. No HMAC equality/authenticity claim is made here.
    """
    try:
        directory_digest = _validate_projected(projected, path_scope=path_scope)
        visible = projected['visible']; additions = visible['additive_targets']
        need(type(plan) is dict and type(body) is dict)
        auth = body['retained_authorization']; host = plan['host_contract']; observer = plan['resource_observer']
        need(auth['additive_targets_sha256'] == digest(additions), 'PREIMAGE_VISIBLE_ADDITIONS_HOLD')
        summaries = [{'path': row['path'], 'uid': row['after']['uid'], 'gid': row['after']['gid'],
            'mode': row['after']['mode'], 'sha256': row['after']['sha256'],
            'provenance_sha256': digest(row['provenance'])} for row in additions]
        need(auth['additive_targets'] == summaries and type(auth['total_target_count']) is int
            and auth['total_target_count'] == 26 and type(auth['retained_target_count']) is int
            and auth['retained_target_count'] == 24, 'PREIMAGE_VISIBLE_SUMMARY_HOLD')
        need(host['timer_contract_sha256'] == digest(visible['timer_contract']), 'PREIMAGE_VISIBLE_TIMER_HOLD')
        need(observer['directories_sha256'] == directory_digest, 'PREIMAGE_VISIBLE_DIRECTORIES_HOLD')
        # We can require the fixed public plan's coverage shape, but cannot
        # compare its resource digests to hidden segment contents offline.
        checkpoints = plan['live_controls']['checkpoints']
        need(type(checkpoints) is list and len(checkpoints) == 17)
        for point in checkpoints:
            need(type(point) is dict and 'resources' in point); _keys(point['resources'], SECTIONS)
            for pin in point['resources'].values(): _hash(pin)
        return {'additive_targets': True, 'timer_contract': True, 'resource_directories': True,
            'retained_delta': False, 'access_rows': False, 'acceptance_contract': False, 'resource_views': False,
            'onsite_only_roots': list(ONSITE_ONLY_ROOTS), 'withheld_commitments': 4,
            'retained_target_count': 24, 'additive_target_count': 2, 'checkpoint_count': 17, 'section_count': 255,
            'directory_count': len(visible['resource_directories']), 'coverage_inventory_only': True,
            'original_seed_independently_read': False, 'hidden_input_root_independently_recomputed': False,
            'host_freshness_verified': False, 'hidden_commitments_independently_verified': False}
    except StaticHold:
        raise
    except (ValueError, TypeError, KeyError, IndexError, UnicodeError, OverflowError, RecursionError, AttributeError):
        raise StaticHold('PREIMAGE_PROJECTED_VERIFY_HOLD') from None
