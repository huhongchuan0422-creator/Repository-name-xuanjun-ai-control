"""Local CLI for the reusable TEST_ONLY scheduler kernel."""
from __future__ import print_function

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from reusable_task_gateway import (GatewayKernel, TestOnlyExecutor,
                                    TestTenantAuthority)
from task_supervisor import Supervisor
from task_writer_fence import Fence


def demo_graph(tenant):
    def task(task_id, output, priority, resources, dependencies=None,
             preemptible=True, evidence='evidence-v1'):
        return {
            'task_id': task_id, 'node_id': 'node-' + task_id,
            'stage': 'TEST_ONLY', 'owner': 'test-executor',
            'entry': 'TEST_ONLY', 'checkpoint_sha256': 'a' * 64,
            'spec_sha256': 'b' * 64, 'input_version': 'input-v1',
            'output_version': output, 'priority': priority,
            'preemptible': preemptible,
            'module_id': 'xuanjun.scheduler.kernel',
            'resources': resources, 'dependencies': dependencies or [],
            'completion_evidence': [{'evidence_ref': evidence}],
        }
    return {
        'graph_id': 'demo-graph', 'tenant_id': tenant,
        'project_id': 'demo-project', 'graph_version': 'v1',
        'tasks': [
            task('demo-b', 'b-v1', 50, ['fake:demo-b'],
                 evidence='evid-demo-b'),
            task('demo-a', 'a-v1', 100, ['fake:shared'], dependencies=[{
                'task_id': 'demo-b', 'version': 'b-v1',
                'evidence_ref': 'evid-demo-b'}]),
            task('demo-c', 'c-v1', 10, ['fake:shared'],
                 preemptible=False),
        ],
    }


def run_demo(gateway, authority, tenant, lock_root):
    context = authority.issue(tenant, 'local-demo')
    gateway.register_graph(context, demo_graph(tenant))
    gateway.save_waiting_checkpoint(
        context, 'demo-a', 'demo-a-prior', 'demo-a-checkpoint',
        {'cursor': 7}, ['fake:shared'])
    fence = Fence(gateway.supervisor, lock_root)
    executor = TestOnlyExecutor(gateway, fence, context)
    try:
        valid_until = time.time() + 600
        executor.start('demo-c', 'demo-c-attempt', ['fake:shared'],
                       valid_until)
        executor.start('demo-b', 'demo-b-attempt', ['fake:demo-b'],
                       valid_until)
        executor.progress('demo-b', 'demo-b-attempt', 'demo-b-progress',
                          'demo-test-run')
        executor.complete_success('demo-b', 'demo-b-attempt', 'f' * 64,
                                  [{'evidence_ref': 'evid-demo-b'}])
        outbox = gateway.db.execute('''SELECT outbox_id,event_id FROM outbox
          WHERE task_id='demo-b' ''').fetchone()
        gateway.mark_outbox_sent(context, outbox['outbox_id'],
                                 'test-transport-receipt')
        gateway.receive_outbox(context, outbox['outbox_id'])
        gateway.acknowledge_event(context, outbox['event_id'])
        gateway.save_checkpoint(
            context, 'demo-c', 'demo-c-attempt', 'demo-c-checkpoint',
            {'cursor': 4}, [], 'RECONCILED', ['fake:shared'])
        controller = {'role': 'REVOCATION_CONTROLLER',
                      'caller_id': 'test-gateway'}
        fence.begin_revocation('demo-c', controller)
        fence.drain('demo-c', controller, timeout=1)
        fence.invalidate_source_resources('demo-c', 'demo-release')
        gateway.supervisor.complete_revocation('demo-c')
        gateway.release_revoked_resources(
            context, 'demo-c', 'demo-c-attempt', 'demo-c-checkpoint',
            'demo-release')
        grant = gateway.issue_resume_grant(
            context, 'demo-a', 'demo-a-checkpoint', time.time() + 600)
        executor.start('demo-a', 'demo-a-attempt', ['fake:shared'],
                       time.time() + 600, 'demo-a-checkpoint',
                       grant['grant_id'])
        return gateway.projection(context)
    finally:
        fence.close()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    parser.add_argument('--test-authority-key', required=True,
                        help='TEST_ONLY key, minimum 32 characters')
    sub = parser.add_subparsers(dest='command')
    project = sub.add_parser('project')
    project.add_argument('--tenant', required=True)
    project.add_argument('--principal', default='local-viewer')
    demo = sub.add_parser('demo')
    demo.add_argument('--tenant', required=True)
    demo.add_argument('--lock-root', required=True)
    args = parser.parse_args(argv)
    if args.command is None:
        parser.error('a command is required')
    supervisor = Supervisor(args.db)
    try:
        authority = TestTenantAuthority(
            args.test_authority_key.encode('utf-8'))
        gateway = GatewayKernel(supervisor, authority)
        if args.command == 'project':
            context = authority.issue(args.tenant, args.principal)
            value = gateway.projection(context)
        else:
            value = run_demo(gateway, authority, args.tenant,
                             os.path.realpath(args.lock_root))
        print(json.dumps(value, ensure_ascii=False,
                         sort_keys=True, indent=2))
    finally:
        supervisor.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
