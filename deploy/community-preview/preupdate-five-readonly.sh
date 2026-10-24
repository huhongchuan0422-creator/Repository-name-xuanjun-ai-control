#!/bin/bash
# REVIEW CANDIDATE ONLY; no sudo/network/install outside bounded readonly Python.
set -eu
if [ "$#" -ne 0 ]; then exit 2; fi
community_preupdate_exit=0
/usr/bin/python3 -I -B -S - <<'COMMUNITY_PREUPDATE_READONLY_PY' || community_preupdate_exit=$?
# Generated exact readonly helper composition; no site installation or mutation.
import types,hashlib,json,os,re,stat
v=types.ModuleType('fixed_approved_observer')
exec(compile('"""Fixed UK community read-only observation candidate. Never a deploy/preview gate.\n\nPython 3.6 stdlib. No CLI inputs, environment reads, secret/DB body reads or writes.\nThe accompanying shell embeds these exact bytes and only invokes this main.\n"""\nimport hashlib\nimport json\nimport os\nimport re\nimport selectors\nimport signal\nimport stat\nimport subprocess\nimport time\nfrom urllib.error import HTTPError\nfrom urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener\n\nHOST = \'iZd7oeikknn1z21sq6ji6zZ\'\nDOCKER = [\'/usr/bin/docker\', \'--host\', \'unix:///var/run/docker.sock\']\nCURRENT = \'xuanjun-community-preview\'\nROLLBACK = \'xuanjun-community-preview-before-2330dd55\'\nROOT = \'/var/lib/xuanjun-community-preview\'\nRUN = \'/run/xuanjun-community-preview\'\nSTAGE = \'/opt/xuanjun-community-preview/roles-upgrade-2330dd55\'\nURL = \'https://uk.wenwenwenyiyiyi.work/community-preview/community/health\'\nROOT_ANCHOR = \'/\'\nROOT_UID = 0\nPROJECT_UID = 10001\nUNKNOWN = \'UNKNOWN\'\nSHA = re.compile(r\'^[0-9a-f]{40}$\')\nIMAGE = re.compile(r\'^sha256:[0-9a-f]{64}$\')\nCID = re.compile(r\'^[0-9a-f]{64}$\')\nDIGEST = CID\nMETA_PATHS = {\'config_directory\': ROOT+\'/config\', \'data_directory\': ROOT+\'/data\',\n              \'runtime_directory\': RUN, \'host_plan_reference\': ROOT+\'/config/host.json\',\n              \'center_keys_reference\': ROOT+\'/config/center-keys.json\',\n              \'wechat_secret_reference\': ROOT+\'/config/wechat.json\'}\nROUTE_PATHS = {\'community_route\': \'/etc/nginx/community-preview.inc\',\n               \'shared_vhost_file_digest_only\': \'/etc/nginx/conf.d/xuanjun-p2-owner.conf\'}\nTRANSACTION_PATHS = {\'attempt\': STAGE+\'/attempt.json\',\n                     \'resume_receipt\': STAGE+\'/resume-01/receipt.json\'}\n\nclass Hold(Exception):\n    pass\n\n\nclass TotalDeadline(BaseException):\n    pass\n\n\ndef owner_for(path):\n    return PROJECT_UID if path in (ROOT+\'/config\', ROOT+\'/data\', RUN) else ROOT_UID\n\n\ndef identity(s):\n    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_size,\n            s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)\n\n\ndef protected(s, uid, directory=False):\n    if s.st_uid not in (uid if isinstance(uid, tuple) else (uid,)) or s.st_mode & 0o022:\n        raise Hold(\'UNPROTECTED_PATH\')\n    if directory and not stat.S_ISDIR(s.st_mode):\n        raise Hold(\'DIRECTORY_REQUIRED\')\n\n\ndef parent_fd(path):\n    if not isinstance(path, str) or not path.startswith(\'/\') or any(p in (\'\', \'.\', \'..\') for p in path.split(\'/\')[1:]):\n        raise Hold(\'FIXED_ABSOLUTE_PATH_REQUIRED\')\n    fd = os.open(ROOT_ANCHOR, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)\n    try:\n        protected(os.fstat(fd), ROOT_UID, True)\n        parts = path.split(\'/\')[1:]\n        current = \'\'\n        for part in parts[:-1]:\n            current += \'/\'+part\n            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)\n            try:\n                protected(os.fstat(child), owner_for(current), True)\n            except BaseException:\n                os.close(child)\n                raise\n            os.close(fd)\n            fd = child\n        return fd, parts[-1]\n    except BaseException:\n        os.close(fd)\n        raise\n\n\ndef safe_file(path, body=False, limit=65536):\n    """Dir-fd traversal; metadata only for secret/data references.\n\n    Content reads are reserved to two route files and two transaction receipts.\n    """\n    if body and path not in set(ROUTE_PATHS.values()) | set(TRANSACTION_PATHS.values()):\n        raise Hold(\'BODY_READ_OUT_OF_SCOPE\')\n    parent, name = parent_fd(path)\n    fd = None\n    try:\n        parent_before = identity(os.fstat(parent))\n        before = os.stat(name, dir_fd=parent, follow_symlinks=False)\n        allowed = (ROOT_UID, PROJECT_UID) if path in META_PATHS.values() and path.startswith(ROOT+\'/config/\') else owner_for(path)\n        protected(before, allowed, stat.S_ISDIR(before.st_mode))\n        if not (stat.S_ISDIR(before.st_mode) or stat.S_ISREG(before.st_mode)):\n            raise Hold(\'REGULAR_FILE_OR_DIRECTORY_REQUIRED\')\n        expected_directory = path in (ROOT+\'/config\', ROOT+\'/data\', RUN)\n        if (path in META_PATHS.values() and stat.S_ISDIR(before.st_mode) != expected_directory) or (path == \'/usr/bin/docker\' and not stat.S_ISREG(before.st_mode)):\n            raise Hold(\'EXPECTED_REFERENCE_TYPE\')\n        result = {\'status\': \'OBSERVED\', \'type\': \'DIRECTORY\' if stat.S_ISDIR(before.st_mode) else \'REGULAR_FILE\',\n                  \'uid\': before.st_uid, \'gid\': before.st_gid, \'mode\': format(stat.S_IMODE(before.st_mode), \'04o\'),\n                  \'device\': before.st_dev, \'inode\': before.st_ino, \'nlink\': before.st_nlink, \'size\': before.st_size,\n                  \'mtime_ns\': before.st_mtime_ns, \'ctime_ns\': before.st_ctime_ns}\n        if body:\n            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:\n                raise Hold(\'BODY_FILE_BOUNDARY\')\n            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)\n            if identity(os.fstat(fd)) != identity(before):\n                raise Hold(\'FILE_CHANGED\')\n            pieces = []\n            used = 0\n            while used <= limit:\n                chunk = os.read(fd, min(4096, limit+1-used))\n                if not chunk:\n                    break\n                pieces.append(chunk)\n                used += len(chunk)\n            raw = b\'\'.join(pieces)\n            if used > limit or len(raw) != before.st_size or identity(os.fstat(fd)) != identity(before):\n                raise Hold(\'FILE_CHANGED_OR_OVERSIZED\')\n            result[\'sha256\'] = hashlib.sha256(raw).hexdigest()\n            result[\'bytes\'] = used\n        if identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity(before):\n            raise Hold(\'PATH_REPLACED\')\n        current_parent, current_name = parent_fd(path)\n        try:\n            if (current_name != name or identity(os.fstat(parent)) != parent_before\n                    or identity(os.fstat(current_parent)) != parent_before\n                    or identity(os.stat(current_name, dir_fd=current_parent, follow_symlinks=False)) != identity(before)):\n                raise Hold(\'PARENT_OR_PATH_CHANGED\')\n        finally:\n            os.close(current_parent)\n        return (result, raw) if body else result\n    finally:\n        if fd is not None:\n            os.close(fd)\n        os.close(parent)\n\n\ndef capture(args, timeout=8, budget=65536):\n    """Bound both pipes; kill the process group and reap on every exit path."""\n    poller = selectors.DefaultSelector()\n    p = None\n    reaped = False\n    try:\n        p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,\n                             start_new_session=True, env={\'PATH\': \'/usr/bin:/bin\', \'LANG\': \'C\', \'LC_ALL\': \'C\',\n                                                         \'DOCKER_CONFIG\': \'/proc/self/fd/-1\'})\n        poller.register(p.stdout, selectors.EVENT_READ, \'out\')\n        poller.register(p.stderr, selectors.EVENT_READ, \'err\')\n        end = time.monotonic()+timeout\n        out = []\n        total = 0\n        while poller.get_map():\n            left = end-time.monotonic()\n            if left <= 0:\n                raise Hold(\'COMMAND_TIMEOUT\')\n            for key, _ in poller.select(min(left, 0.1)):\n                data = os.read(key.fileobj.fileno(), 4096)\n                if not data:\n                    poller.unregister(key.fileobj)\n                    continue\n                total += len(data)\n                if total > budget:\n                    raise Hold(\'COMMAND_OUTPUT_LIMIT\')\n                if key.data == \'out\':\n                    out.append(data)\n        left = end-time.monotonic()\n        if left <= 0:\n            raise Hold(\'COMMAND_TIMEOUT\')\n        return_code = p.wait(timeout=left)\n        reaped = True\n        if return_code != 0:\n            raise Hold(\'COMMAND_REJECTED\')\n        return b\'\'.join(out).decode(\'utf-8\')\n    except subprocess.TimeoutExpired:\n        raise Hold(\'COMMAND_TIMEOUT\')\n    finally:\n        # A child could leave descendants holding pipes, even after its own exit.\n        if p is not None and not reaped:\n            try:\n                os.killpg(p.pid, signal.SIGKILL)\n            except ProcessLookupError:\n                pass\n        poller.close()\n        if p is not None:\n            p.stdout.close()\n            p.stderr.close()\n            if not reaped:\n                p.wait(timeout=2)\n\n\ndef exact_json(raw):\n    def unique(pairs):\n        result = {}\n        for key, value in pairs:\n            if key in result:\n                raise Hold(\'DUPLICATE_JSON_KEY\')\n            result[key] = value\n        return result\n    return json.loads(raw, object_pairs_hook=unique,\n                      parse_constant=lambda value: (_ for _ in ()).throw(Hold(\'NONFINITE_JSON\')))\n\n\ndef base_template():\n    return \'\\n\'.join(\'{{json \'+s+\'}}\' for s in (\'.Id\', \'.Image\', \'.State.Running\', \'.Config.User\'))\n\n\ndef current_template():\n    entry = json.dumps(json.dumps([\'python\', \'-B\', \'-m\', \'scripts.community_platform_host\'], separators=(\',\', \':\')))\n    cmd = json.dumps(json.dumps([\'--plan\', ROOT+\'/config/host.json\', \'--center-keys\', ROOT+\'/config/center-keys.json\',\n                               \'--wechat-secret\', ROOT+\'/config/wechat.json\'], separators=(\',\', \':\')))\n    template = base_template()+\'\\n{{json (eq (json .Config.Entrypoint) \'+entry+\')}}\\n\'\n    template += \'{{json (eq (json .Config.Cmd) \'+cmd+\')}}\\n{{len .Mounts}}\\n{{range .Mounts}}\'\n    for i, (path, rw, token) in enumerate(((ROOT+\'/config\', False, \'CONFIG_RO\'), (ROOT+\'/data\', True, \'DATA_RW\'), (RUN, True, \'RUNTIME_RW\'))):\n        template += \'{{\'+(\'if\' if i == 0 else \'else if\')+\' and (eq .Type "bind") (eq .Source \'+json.dumps(path)+\') (eq .Destination \'+json.dumps(path)+\') (eq .RW \'+str(rw).lower()+\')}}\'+json.dumps(token)+\'\\n\'\n    return template+\'{{else}}"UNKNOWN"\\n{{end}}{{end}}\'\n\n\ndef project_container(raw, current=False):\n    lines = raw.splitlines()\n    if len(lines) < 4:\n        raise Hold(\'CONTAINER_SHAPE\')\n    values = [exact_json(line) for line in lines]\n    cid, image, running, user = values[:4]\n    if type(cid) is not str or CID.fullmatch(cid) is None or type(image) is not str or IMAGE.fullmatch(image) is None or type(running) is not bool:\n        raise Hold(\'CONTAINER_TYPES\')\n    result = {\'status\': \'OBSERVED\', \'container_id\': cid, \'image_id\': image, \'running\': running,\n              \'original_nonroot_user\': \'MATCH\' if user == \'10001:1008\' else UNKNOWN}\n    if current:\n        if len(values) < 7 or type(values[4]) is not bool or type(values[5]) is not bool or type(values[6]) is not int:\n            raise Hold(\'BINDING_TYPES\')\n        mounts = values[7:]\n        if len(mounts) != values[6] or any(type(v) is not str or v not in (\'CONFIG_RO\', \'DATA_RW\', \'RUNTIME_RW\', UNKNOWN) for v in mounts):\n            raise Hold(\'MOUNT_SHAPE\')\n        result.update(entrypoint_match=values[4], command_reference_match=values[5],\n                      original_mounts_match=len(mounts) == 3 and set(mounts) == {\'CONFIG_RO\', \'DATA_RW\', \'RUNTIME_RW\'})\n    elif len(values) != 4:\n        raise Hold(\'ROLLBACK_SHAPE\')\n    return result\n\n\ndef project_image(raw, expected):\n    values = [exact_json(line) for line in raw.splitlines()]\n    if len(values) != 4 or values[0] != expected:\n        raise Hold(\'IMAGE_BINDING\')\n    refs = values[1]\n    if refs is None:\n        refs = []\n    if type(refs) is not list or len(refs) > 16:\n        raise Hold(\'REPO_DIGEST_SHAPE\')\n    digests = []\n    for ref in refs:\n        if type(ref) is not str or re.fullmatch(r\'[A-Za-z0-9./:_-]{1,200}@sha256:[0-9a-f]{64}\', ref) is None:\n            raise Hold(\'REPO_DIGEST_TYPE\')\n        digests.append(ref.rsplit(\'@\', 1)[1])\n    revision = values[2]\n    return {\'status\': \'OBSERVED\', \'image_id\': expected, \'repository_digest_state\': \'PRESENT\' if refs else \'EMPTY\',\n            \'repository_digest_hashes\': sorted(set(digests)),\n            \'oci_revision\': revision if type(revision) is str and SHA.fullmatch(revision) else UNKNOWN,\n            \'original_nonroot_user\': \'MATCH\' if values[3] == \'10001:1008\' else UNKNOWN}\n\n\ndef project_transaction(value):\n    if type(value) is not dict:\n        raise Hold(\'TRANSACTION_OBJECT_REQUIRED\')\n    result = {}\n    states = {\'PREPARED\', \'PUBLIC_ORIGINAL_ROLE_ASSETS_READY_AUTH_ACCEPTANCE_PENDING\',\n              \'PUBLIC_READY_AUTH_ACCEPTANCE_PENDING\', \'KNOWN_FAILURE\', \'ROLLED_BACK\'}\n    for key, pattern in ((\'source_sha\', SHA), (\'image_id\', IMAGE), (\'container_id\', CID),\n                         (\'old_id\', CID), (\'new_image\', IMAGE), (\'owner_vhost_sha256\', DIGEST)):\n        v = value.get(key)\n        result[key] = v if type(v) is str and pattern.fullmatch(v) else UNKNOWN\n    result[\'phase\'] = \'PREPARED\' if value.get(\'phase\') == \'PREPARED\' else UNKNOWN\n    result[\'state\'] = value.get(\'state\') if type(value.get(\'state\')) is str and value[\'state\'] in states else UNKNOWN\n    result[\'rollback_container\'] = ROLLBACK if value.get(\'rollback_container\') == ROLLBACK else UNKNOWN\n    result[\'private_inputs_and_data\'] = \'REUSED_UNCHANGED\' if value.get(\'private_inputs_and_data\') == \'REUSED_UNCHANGED\' else UNKNOWN\n    for key in (\'payments\', \'role_acceptance\', \'wechat_login_verified\'):\n        result[key] = value[key] if type(value.get(key)) is bool else UNKNOWN\n    return result\n\n\nclass NoRedirect(HTTPRedirectHandler):\n    def redirect_request(self, *args, **kwargs):\n        return None\n\n\n# Parent bounds the entire child lifetime, including DNS and TLS setup. The\n# child frame is never relayed; only the typed parent projection is printed.\nHTTP_PROBE = r"""import json\nfrom urllib.error import HTTPError\nfrom urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener\nclass NoRedirect(HTTPRedirectHandler):\n    def redirect_request(self,*args,**kwargs):return None\nurl=\'https://uk.wenwenwenyiyiyi.work/community-preview/community/health\'\ntry:\n    try:\n        response=build_opener(ProxyHandler({}),NoRedirect()).open(Request(url,headers={\'Accept\':\'application/json\'}),timeout=8)\n    except HTTPError as error:\n        if error.code!=503:raise ValueError()\n        response=error\n    with response:\n        code=getattr(response,\'status\',getattr(response,\'code\',None))\n        if code not in (200,503) or response.geturl()!=url or response.headers.get_content_type()!=\'application/json\':raise ValueError()\n        raw=response.read(4097)\n        if len(raw)>4096:raise ValueError()\n    print(json.dumps({\'http_status\':code,\'body_hex\':raw.hex()},sort_keys=True))\nexcept Exception:\n    raise SystemExit(\'HEALTH_UNAVAILABLE\')\n"""\n\n\ndef health(open_url=None, now=None):\n    if open_url is None:\n        frame = exact_json(capture([\'/usr/bin/python3\', \'-I\', \'-B\', \'-S\', \'-c\', HTTP_PROBE], timeout=10, budget=10000))\n        if (type(frame) is not dict or set(frame) != {\'http_status\', \'body_hex\'}\n                or type(frame[\'http_status\']) is not int or frame[\'http_status\'] not in (200, 503)\n                or type(frame[\'body_hex\']) is not str or len(frame[\'body_hex\']) > 8192\n                or re.fullmatch(\'[0-9a-f]*\', frame[\'body_hex\']) is None):\n            raise Hold(\'HEALTH_CHILD_FRAME\')\n        http_status = frame[\'http_status\']\n        raw = bytes.fromhex(frame[\'body_hex\'])\n    else:\n        # Controlled response injection for offline tests; main never accepts\n        # an opener, URL or callback from a request, argument or environment.\n        try:\n            response = open_url(Request(URL, headers={\'Accept\': \'application/json\'}), timeout=10)\n        except HTTPError as error:\n            if error.code != 503:\n                raise Hold(\'HEALTH_HTTP\')\n            response = error\n        with response:\n            http_status = getattr(response, \'status\', getattr(response, \'code\', None))\n            if http_status not in (200, 503) or response.geturl() != URL or response.headers.get_content_type() != \'application/json\':\n                raise Hold(\'HEALTH_RESPONSE\')\n            raw = response.read(4097)\n            if len(raw) > 4096:\n                raise Hold(\'HEALTH_SIZE\')\n    value = exact_json(raw.decode(\'utf-8\'))\n    if type(value) is not dict:\n        raise Hold(\'HEALTH_OBJECT\')\n    observed = int(time.time()) if now is None else now\n    if type(observed) is not int or observed < 0:\n        raise Hold(\'LOCAL_TIME\')\n    remote = value.get(\'observed_at\')\n    valid_time = type(remote) is int and 0 <= remote <= 9007199254740991\n    freshness = UNKNOWN if not valid_time else (\'FUTURE\' if remote > observed+30 else \'STALE\' if observed-remote > 600 else \'FRESH\')\n    sha = value.get(\'runtime_source_sha\')\n    return {\'status\': \'OBSERVED\', \'http_status\': http_status, \'observed_at\': observed,\n            \'backend_status\': value.get(\'status\') if type(value.get(\'status\')) is str and value[\'status\'] in (\'READY\', \'MAINTENANCE\', \'UNAVAILABLE\') else UNKNOWN,\n            \'scope\': \'PROCESS_AND_DATABASE_CONNECTIVITY\' if value.get(\'scope\') == \'PROCESS_AND_DATABASE_CONNECTIVITY\' else UNKNOWN,\n            \'production_acceptance\': False if value.get(\'production_acceptance\') is False else UNKNOWN,\n            \'runtime_source_sha\': sha if type(sha) is str and SHA.fullmatch(sha) else UNKNOWN,\n            \'version_source\': \'IMAGE_BUILD_STAMP\' if value.get(\'version_source\') == \'IMAGE_BUILD_STAMP\' else UNKNOWN,\n            \'backend_observed_at\': remote if valid_time else UNKNOWN, \'freshness\': freshness}\n\n\ndef observe(command=capture):\n    report = {\'candidate\': \'ISSUE76_UK_READONLY_VERSION_OBSERVATION\', \'executable\': False,\n              \'preview_version_acceptance\': \'NOT_EVALUATED_EXACT_SOURCE_MATCH_STILL_REQUIRED\',\n              \'scope\': \'COMMUNITY_ONLY_SHARED_VHOST_FILE_DIGEST_NO_P2_RUNTIME_OR_DATA\', \'snapshot_atomic\': False, \'sections\': {}}\n    sections = report[\'sections\']\n    for key in (\'current_container\', \'current_image\', \'rollback_container\', \'current_container_recheck\'):\n        sections[key] = {\'status\': \'NOT_OBSERVED\'}\n    def collect(key, call):\n        try:\n            sections[key] = call()\n        except FileNotFoundError:\n            sections[key] = {\'status\': \'MISSING\'}\n        except Exception:\n            sections[key] = {\'status\': \'HOLD_UNKNOWN\'}\n        return sections[key]\n    collect(\'docker_binary\', lambda: safe_file(\'/usr/bin/docker\'))\n    if sections[\'docker_binary\'].get(\'type\') == \'REGULAR_FILE\':\n        current = collect(\'current_container\', lambda: project_container(command(DOCKER+[\'container\', \'inspect\', \'--format\', current_template(), CURRENT]), True))\n        if current.get(\'status\') == \'OBSERVED\':\n            fmt = \'\\n\'.join((\'{{json .Id}}\', \'{{json .RepoDigests}}\', \'{{json (index .Config.Labels "org.opencontainers.image.revision")}}\', \'{{json .Config.User}}\'))\n            collect(\'current_image\', lambda: project_image(command(DOCKER+[\'image\', \'inspect\', \'--format\', fmt, current[\'image_id\']]), current[\'image_id\']))\n        collect(\'rollback_container\', lambda: project_container(command(DOCKER+[\'container\', \'inspect\', \'--format\', base_template(), ROLLBACK])))\n    for key, path in sorted(META_PATHS.items()):\n        collect(key, lambda p=path: safe_file(p))\n    for key, path in sorted(ROUTE_PATHS.items()):\n        collect(key, lambda p=path: safe_file(p, True)[0])\n    for key, path in sorted(TRANSACTION_PATHS.items()):\n        def transaction(p=path):\n            meta, raw = safe_file(p, True)\n            return {\'status\': \'OBSERVED\', \'metadata\': meta, \'projection\': project_transaction(exact_json(raw.decode(\'utf-8\')))}\n        collect(key, transaction)\n    health_report = collect(\'runtime_health\', health)\n    initial = sections.get(\'current_container\', {})\n    if initial.get(\'status\') == \'OBSERVED\':\n        def recheck():\n            last = project_container(command(DOCKER+[\'container\', \'inspect\', \'--format\', base_template(), CURRENT]))\n            if any(last[key] != initial[key] for key in (\'container_id\', \'image_id\', \'running\', \'original_nonroot_user\')):\n                raise Hold(\'CURRENT_CONTAINER_CHANGED\')\n            return {\'status\': \'OBSERVED\', \'identity_image_state_recheck\': \'MATCH\'}\n        collect(\'current_container_recheck\', recheck)\n    image = sections.get(\'current_image\', {})\n    runtime = health_report.get(\'runtime_source_sha\', UNKNOWN)\n    revision = image.get(\'oci_revision\', UNKNOWN)\n    report[\'runtime_image_revision_relation\'] = UNKNOWN if UNKNOWN in (runtime, revision) else \'MATCH\' if runtime == revision else \'DIFFERENT\'\n    report[\'state\'] = \'OBSERVED_NOT_ACCEPTANCE\' if all(s.get(\'status\') == \'OBSERVED\' for s in sections.values()) else \'HOLD_PARTIAL_OBSERVATION\'\n    return report\n\n\ndef main():\n    if os.getuid() != 0 or os.geteuid() != 0 or os.uname().nodename.split(\'.\')[0] != HOST:\n        print(\'{"candidate":"ISSUE76_UK_READONLY_VERSION_OBSERVATION","executable":false,"state":"HOLD_HOST_OR_IDENTITY"}\')\n        return 2\n    def deadline(*args):\n        raise TotalDeadline(\'TOTAL_TIMEOUT\')\n    previous = signal.signal(signal.SIGALRM, deadline)\n    signal.alarm(60)\n    try:\n        report = observe()\n        raw = json.dumps(report, sort_keys=True, allow_nan=False)\n        if len(raw.encode(\'utf-8\')) > 16384:\n            raise Hold(\'REPORT_SIZE\')\n        print(raw)\n        return 0 if report[\'state\'] == \'OBSERVED_NOT_ACCEPTANCE\' else 2\n    except (Exception, TotalDeadline):\n        print(\'{"candidate":"ISSUE76_UK_READONLY_VERSION_OBSERVATION","executable":false,"state":"HOLD_BOUNDED_OBSERVATION"}\')\n        return 2\n    finally:\n        signal.alarm(0)\n        signal.signal(signal.SIGALRM, previous)\n\n\nif __name__ == \'__main__\':\n    raise SystemExit(main())\n','<approved-observer>','exec'),v.__dict__)
original=types.ModuleType('fixed_original_readonly_validation')
exec(compile("ROOT='/var/lib/xuanjun-community-preview'\n\n\nRUN='/run/xuanjun-community-preview'\n\n\nclass Rejected(RuntimeError):pass\n\n\nINSPECT_FIELDS=[('id','.Id'),('image','.Image'),('running','.State.Running'),('status','.State.Status'),\n    ('user','.Config.User'),('cmd','.Config.Cmd'),('entrypoint','.Config.Entrypoint'),('mounts','.Mounts'),\n    ('cpu','.HostConfig.NanoCpus'),('memory','.HostConfig.Memory'),('swap','.HostConfig.MemorySwap'),\n    ('pids','.HostConfig.PidsLimit'),('readonly','.HostConfig.ReadonlyRootfs'),('privileged','.HostConfig.Privileged'),\n    ('restart','.HostConfig.RestartPolicy.Name'),('network','.HostConfig.NetworkMode'),('capdrop','.HostConfig.CapDrop'),\n    ('security','.HostConfig.SecurityOpt'),('tmpfs','.HostConfig.Tmpfs'),('log','.HostConfig.LogConfig')]\n\n\ndef validate(info,image,cid=None,running=True):\n    if (cid is not None and info['id']!=cid) or info['image']!=image or info['running'] is not running:\n        raise Rejected('EXACT_CONTAINER_STATE_REQUIRED')\n    expected={'user':'10001:1008','cpu':500000000,'memory':536870912,'swap':536870912,\n        'pids':64,'readonly':True,'privileged':False,'restart':'no','capdrop':['ALL'],\n        'entrypoint':['python','-B','-m','scripts.community_platform_host'],\n        'cmd':['--plan',ROOT+'/config/host.json','--center-keys',ROOT+'/config/center-keys.json','--wechat-secret',ROOT+'/config/wechat.json']}\n    if any(info[k]!=v for k,v in expected.items()):raise Rejected('CONTAINER_SCOPE_CHANGED')\n    if info['network'] not in ('default','bridge') or info['security'] not in (['no-new-privileges'],['no-new-privileges:true']):\n        raise Rejected('CONTAINER_ISOLATION_CHANGED')\n    if info['tmpfs']!={'/tmp':'rw,noexec,nosuid,nodev,size=16777216,mode=1777'}:\n        raise Rejected('TMPFS_CHANGED')\n    if info['log']!={'Type':'json-file','Config':{'max-size':'10m','max-file':'2'}}:\n        raise Rejected('LOG_LIMIT_CHANGED')\n    expected_mounts={(ROOT+'/config',ROOT+'/config',False),(ROOT+'/data',ROOT+'/data',True),(RUN,RUN,True)}\n    if len(info['mounts'])!=3 or any(m.get('Type')!='bind' for m in info['mounts']) or {(m['Source'],m['Destination'],m['RW']) for m in info['mounts']}!=expected_mounts:\n        raise Rejected('EXACT_EXISTING_MOUNTS_REQUIRED')\n\n",'<approved-validation>','exec'),original.__dict__)
approved=types.ModuleType('fixed_b09_readonly_helpers')
approved.__dict__.update(controller=types.SimpleNamespace(Hold=v.Hold),observation=v,original=original,plan=types.SimpleNamespace(DOCKER=v.DOCKER),hashlib=hashlib,json=json)
exec(compile('def require(ok,reason):\n    if not ok:raise controller.Hold(reason)\n\n\ndef digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(\',\',\':\')).encode()).hexdigest()\n\n\ndef stable_metadata(path):\n    # Metadata only, never config/key/DB bytes. Directory timestamps/size change\n    # during legitimate data/socket writes and are deliberately not identities.\n    value=observation.safe_file(path)\n    if value[\'type\']==\'REGULAR_FILE\':require(value[\'nlink\']==1,\'REFERENCE_HARDLINK_DENIED\')\n    keys=(\'type\',\'uid\',\'gid\',\'mode\',\'device\',\'inode\')\n    if value[\'type\']==\'REGULAR_FILE\':keys+=(\'nlink\',\'size\',\'mtime_ns\',\'ctime_ns\')\n    return {key:value[key] for key in keys}\n\n\ndef inspect_bound(cid,image):\n    # Same original typed projection/validation, with bounded original readonly\n    # child transport; additionally prove no published port/device/cap addition.\n    fields=original.INSPECT_FIELDS+[(\'ports\',\'.HostConfig.PortBindings\'),\n        (\'published\',\'.NetworkSettings.Ports\'),(\'devices\',\'.HostConfig.Devices\'),(\'capadd\',\'.HostConfig.CapAdd\')]\n    fmt=\'\\n\'.join(\'{{json \'+field+\'}}\' for _,field in fields)\n    rows=observation.capture(plan.DOCKER+[\'container\',\'inspect\',\'--format\',fmt,cid],timeout=8,budget=32768).splitlines()\n    require(len(rows)==len(fields),\'CURRENT_INSPECT_SHAPE\')\n    value={key:observation.exact_json(raw) for (key,_),raw in zip(fields,rows)}\n    require(type(value[\'running\']) is bool,\'CURRENT_RUNNING_UNKNOWN\')\n    for key in (\'cpu\',\'memory\',\'swap\',\'pids\'):require(type(value[key]) is int,\'CURRENT_RESOURCE_TYPE\')\n    for key in (\'readonly\',\'privileged\'):require(type(value[key]) is bool,\'CURRENT_ISOLATION_TYPE\')\n    original.validate(value,image,cid,running=value[\'running\'])\n    require(value[\'ports\'] in (None,{}) and value[\'published\'] in (None,{})\n            and value[\'devices\'] in (None,[]) and value[\'capadd\'] in (None,[]),\'NO_NEW_PORT_DEVICE_CAPABILITY\')\n    return value\n\n\nPRIVATE_PROBE = r"""import http.client,json,socket\nclass Local(http.client.HTTPConnection):\n    def connect(self):\n        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\n        self.sock.settimeout(8)\n        self.sock.connect(\'/run/xuanjun-community-preview/preview.sock\')\ntry:\n    c=Local(\'localhost\',timeout=8)\n    c.request(\'GET\',\'/community/health\',headers={\'Accept\':\'application/json\',\'Host\':\'uk.wenwenwenyiyiyi.work\'})\n    r=c.getresponse()\n    if r.status not in (200,503) or r.getheader(\'Content-Type\',\'\').split(\';\')[0].strip()!=\'application/json\':raise ValueError()\n    raw=r.read(4097)\n    if len(raw)>4096:raise ValueError()\n    print(json.dumps({\'http_status\':r.status,\'body_hex\':raw.hex()},sort_keys=True))\n    c.close()\nexcept Exception:raise SystemExit(\'PRIVATE_HEALTH_UNAVAILABLE\')\n"""\n\n','<approved-composition-readonly>','exec'),approved.__dict__)
"""Five fixed-object readonly observations, NOT update/preview admission.

No installed source/backup path is known: report UNKNOWN without searching.
The offline bundler embeds approved readonly helpers; no installation is needed.
"""
import hashlib
import json
import math
import os
import re
import signal
import stat
import sys
import time

PRODUCT='f13155ed63a3137d41766ee587d9b4b96a81477f'
IMAGE='sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a'
COMPOSITION='b09b837b338def5db8485bda8c4fa4e98d98139f'
BASE='/opt/xuanjun-community-preview'
APPROVAL=BASE+'/update-approval.json'
JOURNAL=BASE+'/update-journal'
SOCKET=v.RUN+'/preview.sock'
PUBLIC_PINS={
 'scripts/community_preview_update_composition.py':'f3007cdd26d53e7348164d404186602335ee5f237963f5d6f627e5376cfdc4f1',
 'scripts/community_preview_update_checkpoint.py':'a73c1fe8ebb71abaefeb56ca880057e23876b5c005d315e4fb1268d3087064fd',
 'scripts/community_preview_release_plan.py':'e0870cfaf7f1bb16b8664e644ec616e150b0ada93146a8d955e64c5f3f7ec4b9',
 'scripts/community_preview_upgrade.py':'2584441af33e6db1c5d24596f6cbc82077364a0b2b18554c6ba550ec8f66e0ee',
 'scripts/community_preview_version_inspect.py':'98773bcd199f5cb50d15fb3bba1b6959541a12c3f5f2a4879dcd88e5d3bb6cc3'}


def wall():
    value=time.time()
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:raise v.Hold('CLOCK_UNKNOWN')
    return int(value)


def metadata(path,directory):
    result=v.safe_file(path)
    if (result['type']=='DIRECTORY') is not directory:raise v.Hold('FIXED_OBJECT_TYPE')
    if not directory and result['nlink']!=1:raise v.Hold('FIXED_FILE_LINK')
    return result


def socket_metadata():
    parent,name=v.parent_fd(SOCKET)
    try:
        p_before=v.identity(os.fstat(parent));before=os.stat(name,dir_fd=parent,follow_symlinks=False)
        # Original socket is project-owned 0660 (nginx group); never open/read it
        # as a regular file. Parent chain retains original protected policy.
        if not stat.S_ISSOCK(before.st_mode) or before.st_uid!=v.PROJECT_UID or stat.S_IMODE(before.st_mode)!=0o660:
            raise v.Hold('ORIGINAL_SOCKET_TYPE_OWNER_MODE')
        other,leaf=v.parent_fd(SOCKET)
        try:
            if (v.identity(os.fstat(parent))!=p_before or v.identity(os.fstat(other))!=p_before or leaf!=name
                    or v.identity(os.stat(leaf,dir_fd=other,follow_symlinks=False))!=v.identity(before)):
                raise v.Hold('SOCKET_OR_PARENT_CHANGED')
        finally:os.close(other)
        return dict(status='OBSERVED',type='UNIX_SOCKET',uid=before.st_uid,gid=before.st_gid,
                    mode='0660',device=before.st_dev,inode=before.st_ino)
    finally:os.close(parent)


def health_probe(probe,private=False):
    # Reuse exact approved bounded public/private probes, not a new endpoint.
    raw=v.capture(['/usr/bin/python3','-I','-B','-S','-c',probe],timeout=10,budget=10000)
    frame=v.exact_json(raw)
    if (type(frame) is not dict or set(frame)!={'http_status','body_hex'}
            or type(frame['http_status']) is not int or frame['http_status'] not in (200,503)
            or type(frame['body_hex']) is not str or len(frame['body_hex'])>8192
            or re.fullmatch('[0-9a-f]*',frame['body_hex']) is None):raise v.Hold('HEALTH_FRAME')
    body=v.exact_json(bytes.fromhex(frame['body_hex']).decode('utf-8'))
    if type(body) is not dict:raise v.Hold('HEALTH_OBJECT')
    remote=body.get('observed_at');local=wall()
    valid=type(remote) is int and 0<=remote<=9007199254740991
    return dict(status='OBSERVED',http_status=frame['http_status'],
        transport='ORIGINAL_UNIX_SOCKET' if private else 'ANONYMOUS_HTTPS_NO_REDIRECT_PROXY',
        endpoint=SOCKET+':/community/health' if private else v.URL,
        backend_status=body.get('status') if type(body.get('status')) is str and body['status'] in ('READY','MAINTENANCE','UNAVAILABLE') else 'UNKNOWN',
        scope='PROCESS_AND_DATABASE_CONNECTIVITY' if body.get('scope')=='PROCESS_AND_DATABASE_CONNECTIVITY' else 'UNKNOWN',
        production_acceptance=False if body.get('production_acceptance') is False else 'UNKNOWN',
        runtime_source_sha=body.get('runtime_source_sha') if type(body.get('runtime_source_sha')) is str and v.SHA.fullmatch(body['runtime_source_sha']) else 'UNKNOWN',
        version_source='IMAGE_BUILD_STAMP' if body.get('version_source')=='IMAGE_BUILD_STAMP' else 'UNKNOWN',
        collection_observed_at=local,backend_observed_at=remote if valid else 'UNKNOWN',
        freshness='UNKNOWN' if not valid else 'FUTURE' if remote>local+30 else 'STALE' if local-remote>600 else 'FRESH')


def names_for(current):
    names=[v.CURRENT,v.CURRENT+'-before-'+PRODUCT[:12]+'-'+current['container_id'][:12],
                   v.CURRENT+'-failed-'+PRODUCT[:12]+'-'+current['container_id'][:12]]
    result={}
    fmt='{{json .Id}}\n{{json .Name}}\n{{json .Image}}\n{{json .State.Running}}'
    for name in names:
        try:
            rows=v.capture(v.DOCKER+['container','ls','--all','--no-trunc','--format','{"id":{{json .ID}},"name":{{json .Names}}}',
                '--filter','name=^/'+name+'$'],timeout=8,budget=4096).splitlines()
            if not rows:
                result[name]=dict(status='OBSERVED_ABSENT');continue
            if len(rows)!=1:raise v.Hold('EXACT_NAME_QUERY')
            lookup=v.exact_json(rows[0])
            if (type(lookup) is not dict or set(lookup)!={'id','name'} or lookup['name']!=name
                    or type(lookup['id']) is not str or not v.CID.fullmatch(lookup['id'])):raise v.Hold('EXACT_NAME_QUERY')
            values=[v.exact_json(r) for r in v.capture(v.DOCKER+['container','inspect','--format',fmt,lookup['id']],timeout=8,budget=4096).splitlines()]
            if (len(values)!=4 or type(values[0]) is not str or not v.CID.fullmatch(values[0])
                    or values[0]!=lookup['id'] or values[1]!='/'+name or type(values[2]) is not str or not v.IMAGE.fullmatch(values[2])
                    or type(values[3]) is not bool):raise v.Hold('NAME_FRAME')
            result[name]=dict(status='OBSERVED',container_id=values[0],image_id=values[2],running=values[3])
        except Exception:
            # Nonzero CLI cannot distinguish absent from daemon/permission error.
            result[name]=dict(status='UNKNOWN_NOT_PROVEN_ABSENT')
    current_name=result[v.CURRENT]
    if current_name.get('container_id')!=current['container_id'] or current_name.get('image_id')!=current['image_id']:
        raise v.Hold('FIXED_NAME_REBOUND')
    return result


def current_projection():
    fmt='{{json .Id}}\n{{json .Image}}'
    rows=v.capture(v.DOCKER+['container','inspect','--format',fmt,v.CURRENT],timeout=8,budget=4096).splitlines()
    if len(rows)!=2:raise v.Hold('CURRENT_SHAPE')
    cid,image=[v.exact_json(r) for r in rows]
    if type(cid) is not str or not v.CID.fullmatch(cid) or type(image) is not str or not v.IMAGE.fullmatch(image):raise v.Hold('CURRENT_IDS')
    info=approved.inspect_bound(cid,image)  # original full readonly isolation validation
    image_fmt='{{json .Id}}\n{{json .RepoDigests}}\n{{json (index .Config.Labels "org.opencontainers.image.revision")}}\n{{json .Config.User}}'
    image_info=v.project_image(v.capture(v.DOCKER+['image','inspect','--format',image_fmt,image],timeout=8,budget=4096),image)
    config={p:approved.stable_metadata(p) for p in (v.ROOT+'/config',v.ROOT+'/config/host.json',v.ROOT+'/config/center-keys.json',v.ROOT+'/config/wechat.json')}
    data={p:approved.stable_metadata(p) for p in (v.ROOT+'/data',v.RUN)}
    routes={p:v.safe_file(p,True)[0]['sha256'] for p in v.ROUTE_PATHS.values()}
    isolation={k:value for k,value in info.items() if k not in ('id','image','running','status')}
    # Exactly the four calculable composition digests. No invented backup file
    # capability: the fifth field must remain UNKNOWN without a real reference.
    return dict(status='OBSERVED_PARTIAL_NO_BACKUP_BINDING',container_id=cid,image_id=image,
        oci_revision=image_info['oci_revision'],running=info['running'],user=info['user'],observed_at=wall(),
        config_identity_sha256=approved.digest(config),data_identity_sha256=approved.digest(data),
        routing_sha256=approved.digest(routes),isolation_sha256=approved.digest(isolation),backup_reference_sha256='UNKNOWN',
        isolation_validation='ORIGINAL_NONROOT_NO_PUBLISHED_PORT_DEVICE_CAPADD',
        source_references=dict(config=config,data=data,route_sha256=routes))


def loaded_image():
    fmt='{{json .Id}}\n{{json .RepoDigests}}\n{{json (index .Config.Labels "org.opencontainers.image.revision")}}\n{{json .Config.User}}'
    value=v.project_image(v.capture(v.DOCKER+['image','inspect','--format',fmt,IMAGE],timeout=8,budget=4096),IMAGE)
    value['candidate_relation']='EXACT_ID_OCI_USER_MATCH' if value['oci_revision']==PRODUCT and value['original_nonroot_user']=='MATCH' else 'HOLD_IMAGE_METADATA_MISMATCH'
    return value


def observe(report):
    sections=report['sections']
    def collect(key,call):
        try:sections[key]=call()
        except FileNotFoundError:sections[key]=dict(status='MISSING_FIXED_PATH')
        except v.TotalDeadline:
            sections[key]=dict(status='HOLD_TOTAL_TIMEOUT');raise
        except Exception:sections[key]=dict(status='HOLD_UNKNOWN')
        return sections[key]
    collect('docker_binary',lambda:metadata('/usr/bin/docker',False))
    if sections['docker_binary'].get('status')=='OBSERVED':
        current=collect('current',current_projection)
        if current.get('container_id'):
            collect('phase_names',lambda:names_for(current))
        collect('f131_loaded_image',loaded_image)
    collect('socket',socket_metadata)
    collect('public_health',lambda:health_probe(v.HTTP_PROBE))
    if sections['socket'].get('status')=='OBSERVED':collect('private_health',lambda:health_probe(approved.PRIVATE_PROBE,True))
    for label,path,isdir in (('root_base',BASE,True),('historical_stage',v.STAGE,True),
                            ('approval',APPROVAL,False),('journal_parent',JOURNAL,True)):
        value=collect(label,lambda p=path,d=isdir:metadata(p,d))
        if label in ('approval','journal_parent'):
            required='0600' if label=='approval' else '0700'
            value['required_mode']=required
            value['protected_policy_relation']='MATCH' if value.get('status')=='OBSERVED' and value.get('mode')==required else 'HOLD_NOT_PROVEN'
    # Known original object, classified ROUTE ONLY; never relabel as data backup.
    route_backup=collect('historical_route_backup',lambda:metadata(v.STAGE+'/include.before',False))
    route_backup['scope']='ROUTE_BACKUP_ONLY_NOT_DATABASE_OR_RECOVERY_PROOF'
    sections['root_caller_sources']=dict(status='UNKNOWN_INSTALLED_PATHS_NOT_PROVIDED_NO_SEARCH',
        files={p:dict(expected_source_sha256=h,installed_path='UNKNOWN',observed_sha256='UNKNOWN',owner='UNKNOWN',mode='UNKNOWN') for p,h in PUBLIC_PINS.items()})
    sections['database_backup']=dict(status='UNKNOWN_NO_FIXED_BACKUP_REFERENCE_OR_RESTORE_PROOF',
        reference_path='UNKNOWN',reference_sha256='UNKNOWN',verified_restore='UNKNOWN',downgrade_compatibility='UNKNOWN')
    initial_socket=sections.get('socket',{})
    if initial_socket.get('status')=='OBSERVED':
        def socket_recheck():
            last=socket_metadata()
            if last!=initial_socket:raise v.Hold('SOCKET_CHANGED')
            return dict(status='OBSERVED',identity='MATCH')
        collect('socket_recheck',socket_recheck)
    public=sections.get('public_health',{});private=sections.get('private_health',{})
    report['private_public_runtime_relation']='UNKNOWN'
    if all(h.get('runtime_source_sha') not in (None,'UNKNOWN') for h in (public,private)):
        report['private_public_runtime_relation']='MATCH' if public['runtime_source_sha']==private['runtime_source_sha'] else 'DIFFERENT'
    initial=sections.get('current',{})
    if initial.get('container_id'):
        def recheck():
            last=current_projection()
            if any(last[k]!=initial[k] for k in initial if k!='observed_at'):raise v.Hold('CURRENT_BINDING_CHANGED')
            return dict(status='OBSERVED',identity_image_isolation_four_digests='MATCH',names=names_for(last))
        collect('current_recheck',recheck)
    return report


def main():
    if len(sys.argv)!=1 or os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!=v.HOST:
        print('{"state":"HOLD_HOST_IDENTITY_OR_ARGUMENTS","site_updated":false}');return 2
    keys=('docker_binary','current','phase_names','f131_loaded_image','socket','public_health','private_health',
          'root_base','historical_stage','approval','journal_parent','root_caller_sources','database_backup','socket_recheck','current_recheck')
    report=dict(candidate='UK_PREUPDATE_FIVE_FIXED_OBJECT_READONLY',composition_source=COMPOSITION,product_source=PRODUCT,
        sections={k:dict(status='NOT_OBSERVED') for k in keys},state='HOLD_MISSING_INSTALLATION_AND_RECOVERY_PROOF',
        executable_update=False,site_updated=False,preview_acceptance='HOLD_NOT_EVALUATED',production_acceptance=False,
        snapshot_atomic=False,execution_permission='NOT_GRANTED',observation_validity_seconds=600,
        docker_boundary='CLI_DAEMON_MAY_ACCESS_ENV_PYTHON_RECEIVES_FIXED_WHITELIST_ONLY')
    def deadline(*args):raise v.TotalDeadline('TOTAL_TIMEOUT')
    previous=signal.signal(signal.SIGALRM,deadline);signal.alarm(90)
    try:observe(report)
    except (Exception,v.TotalDeadline):report['state']='HOLD_PARTIAL_BOUNDED_OBSERVATION'
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous)
    try:
        raw=json.dumps(report,sort_keys=True,allow_nan=False)
        if len(raw.encode())>32768:raise v.Hold('OUTPUT_BOUND')
        print(raw)
    except Exception:print('{"state":"HOLD_OUTPUT_BOUND","site_updated":false}')
    return 2  # Missing installation/backup cannot become admission by HTTP200.


if __name__=='__main__':raise SystemExit(main())
COMMUNITY_PREUPDATE_READONLY_PY
printf 'COMMUNITY_PREUPDATE_READONLY_EXIT_CODE=%s\n' "$community_preupdate_exit"
exit "$community_preupdate_exit"
