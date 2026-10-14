"""Close Work review blockers B1/B2 on the pinned P2 package.

B1 binds the dispatcher to the exact packaged controller and its transport
configuration. B2 disables both retained legacy Codex worker run entry points
before any process/transport creation. Python 3.6 compatible.
"""
from __future__ import print_function
import hashlib
import json
import pathlib
import sys

OPENCLAW_BIN='/home/xuanjun_dev/.openclaw/bin/openclaw'
OPENCLAW_SHA256='b6aff1f40be0d46330c167e44525ef9080d66e40bb36dbb66c3811b4103fe3f2'
OPENCLAW_OWNER_UID=1002
GATEWAY_HOME='/home/xuanjun_dev'
GATEWAY_PATH='/home/xuanjun_dev/.openclaw/bin:/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin:/usr/bin:/bin'

def replace_once(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:
        raise ValueError('REVIEW_BLOCKER_SOURCE_DRIFT:'+path.name+':'+old[:48])
    path.write_text(text.replace(old,new))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    source=pathlib.Path(sys.argv[1]).resolve()
    stage1=source/'stage1';deploy=source/'deploy'

    for name in ('codex_worker.py','codex_app_server_worker.py'):
        path=stage1/name
        replace_once(path,
"""    def run(self, prompt, timeout_seconds=900, heartbeat=None,
            lease_check=None, heartbeat_seconds=5):
        if not isinstance(prompt, str) or not prompt.strip():""",
"""    def run(self, prompt, timeout_seconds=900, heartbeat=None,
            lease_check=None, heartbeat_seconds=5):
        raise RuntimeError('delegated model dispatch prohibited by owner policy')
        if not isinstance(prompt, str) or not prompt.strip():""")

    controller=stage1/'native_gateway_controller.py'
    controller_sha=sha(controller)
    transport=stage1/'native_gateway_controller.py.json'
    transport.write_text(json.dumps({
        'openclaw_bin':OPENCLAW_BIN,
        'openclaw_sha256':OPENCLAW_SHA256,
        'openclaw_owner_uid':OPENCLAW_OWNER_UID,
        'gateway_home':GATEWAY_HOME,
        'gateway_path':GATEWAY_PATH,
    },sort_keys=True,separators=(',',':'))+'\n')

    service=deploy/'xuanjun-development-dispatcher.service'
    base='/opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/stage1/'
    controller_path=base+'native_gateway_controller.py'
    common=' --native-controller '+controller_path+' --native-controller-sha256 '+controller_sha
    replace_once(service,
        'ExecStartPre=/usr/bin/python3 '+base+'development_service.py --config /etc/xuanjun-development/dispatcher.json --check-config',
        'ExecStartPre=/usr/bin/python3 '+base+'development_service.py --config /etc/xuanjun-development/dispatcher.json --check-config'+common)
    replace_once(service,
        'ExecStart=/usr/bin/python3 '+base+'development_service.py --config /etc/xuanjun-development/dispatcher.json',
        'ExecStart=/usr/bin/python3 '+base+'development_service.py --config /etc/xuanjun-development/dispatcher.json'+common)

    development=stage1/'development_service.py'
    replace_once(development,
"""    config = load_config(args.config)
    if args.check_config:
        print('CONFIG_OK source_commit=' + config['source_commit'])
        return 0
    lock = acquire_dispatcher_lock(config['dispatcher_lock'])""",
"""    config = load_config(args.config)
    if args.check_config:
        native_runtime = load_reviewed_controller(args.native_controller,
                                                  args.native_controller_sha256, config)
        if getattr(native_runtime, 'binary_sha256', None) != args.native_controller_sha256:
            raise ValueError('reviewed native controller digest not retained')
        print('CONFIG_CONTROLLER_OK source_commit=' + config['source_commit'] +
              ' controller_sha256=' + args.native_controller_sha256)
        return 0
    lock = acquire_dispatcher_lock(config['dispatcher_lock'])""")

    print('P2_WORK_REVIEW_BLOCKERS_B1_B2_APPLIED')

if __name__=='__main__':
    main()
