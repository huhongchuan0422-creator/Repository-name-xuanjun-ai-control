"""Bounded GitHub read-only evidence. No GitHub writes and no cloud credentials.

An uninterrupted run_number sequence is mandatory. Deleted/missing history,
pagination truncation, expired artifacts, or ambiguous provenance fail closed.
Artifact redirect requests never carry the GitHub Authorization header.
"""
import hashlib
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
REPOSITORY_ID = 1413132159
OWNER_ID = 332398908
BRANCH = 'feature/work-pr122-site-hub-integration-20261016'
WORKFLOW_PATH = '.github/workflows/pr122-staging-readonly.yml'
DISPATCH_JOB = 'domestic-staging-readonly-cloud'
QUERY_JOB = 'domestic-staging-readonly-query'
SHA40 = re.compile(r'[0-9a-f]{40}')
MAX_PAGES = 20
MAX_JSON = 4 * 1024 * 1024
MAX_ARTIFACT = 128 * 1024


class Hold(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Hold(code)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Hold('JSON_CONSTANT')))
    except (ValueError, UnicodeError, TypeError):
        raise Hold('INVALID_EVIDENCE_JSON') from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHub:
    def __init__(self, token, opener=None):
        require(type(token) is str and token and '\n' not in token and '\r' not in token,
                'GITHUB_TOKEN_REQUIRED')
        self.token = token
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def request(self, path, limit=MAX_JSON, redirect=False):
        require(path.startswith('/repos/' + REPOSITORY + '/') and not any(
            x in path for x in ('://', '#', '..', '\\')), 'GITHUB_PATH_REJECTED')
        req = urllib.request.Request('https://api.github.com' + path, headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': 'Bearer ' + self.token,
            'X-GitHub-Api-Version': '2022-11-28',
        })
        try:
            with self.opener.open(req, timeout=20) as response:
                raw = response.read(limit + 1)
        except urllib.error.HTTPError as error:
            if redirect and error.code == 302:
                location = error.headers.get('Location', '')
                parsed = urllib.parse.urlsplit(location)
                host = parsed.hostname or ''
                require(parsed.scheme == 'https' and not parsed.username and not parsed.password
                        and parsed.port in (None, 443) and not parsed.fragment
                        and (host.endswith('.blob.core.windows.net')
                             or host.endswith('.actions.githubusercontent.com')),
                        'ARTIFACT_REDIRECT_REJECTED')
                # Deliberately no Authorization, cookies, redirects, or retries.
                try:
                    with self.opener.open(urllib.request.Request(location), timeout=20) as response:
                        raw = response.read(limit + 1)
                except Exception:
                    raise Hold('ARTIFACT_READBACK_UNAVAILABLE') from None
            else:
                raise Hold('GITHUB_READ_UNAVAILABLE') from None
        except Exception:
            raise Hold('GITHUB_READ_UNAVAILABLE') from None
        require(len(raw) <= limit, 'EVIDENCE_RESPONSE_TOO_LARGE')
        return raw

    def get(self, suffix):
        return strict_json(self.request('/repos/' + REPOSITORY + suffix))

    def collection(self, suffix, key):
        rows = []
        total = None
        separator = '&' if '?' in suffix else '?'
        for page in range(1, MAX_PAGES + 1):
            result = self.get(suffix + separator + 'per_page=100&page=' + str(page))
            require(type(result) is dict and type(result.get('total_count')) is int
                    and result['total_count'] >= 0 and type(result.get(key)) is list,
                    'HISTORY_SCHEMA')
            if total is None:
                total = result['total_count']
            require(result['total_count'] == total and len(result[key]) <= 100,
                    'HISTORY_CHANGED_OR_TRUNCATED')
            rows.extend(result[key])
            require(len(rows) <= total, 'HISTORY_COUNT_MISMATCH')
            if len(rows) == total:
                require(all(type(r) is dict and type(r.get('id')) is int for r in rows)
                        and len({r['id'] for r in rows}) == len(rows), 'HISTORY_DUPLICATE_OR_ID')
                return rows
            require(len(result[key]) == 100, 'HISTORY_MISSING_PAGE')
        raise Hold('HISTORY_PAGINATION_LIMIT')

    def run(self, run_id):
        require(type(run_id) is int and run_id > 0, 'RUN_ID')
        return self.get('/actions/runs/' + str(run_id))

    def runs(self, workflow_id):
        require(type(workflow_id) is int and workflow_id > 0, 'WORKFLOW_ID')
        return self.collection('/actions/workflows/' + str(workflow_id) + '/runs', 'workflow_runs')

    def jobs(self, run_id):
        return self.collection('/actions/runs/' + str(run_id) + '/jobs?filter=all', 'jobs')

    def artifacts(self, run_id):
        return self.collection('/actions/runs/' + str(run_id) + '/artifacts', 'artifacts')

    def read_artifact(self, run_id, name, member, artifact_id=None):
        artifacts = [a for a in self.artifacts(run_id) if a.get('name') == name]
        require(len(artifacts) == 1, 'ARTIFACT_NOT_UNIQUE')
        artifact = artifacts[0]
        require(artifact_id is None or artifact.get('id') == artifact_id,
                'ARTIFACT_ID_BINDING')
        require(artifact.get('expired') is False and type(artifact.get('size_in_bytes')) is int
                and 0 < artifact['size_in_bytes'] <= MAX_ARTIFACT, 'ARTIFACT_UNAVAILABLE')
        digest = artifact.get('digest')
        require(type(digest) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', digest),
                'ARTIFACT_DIGEST_UNAVAILABLE')
        raw = self.request('/repos/' + REPOSITORY + '/actions/artifacts/'
                           + str(artifact['id']) + '/zip', MAX_ARTIFACT, redirect=True)
        require(hashlib.sha256(raw).hexdigest() == digest[7:], 'ARTIFACT_DIGEST_MISMATCH')
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                infos = archive.infolist()
                require(len(infos) == 1 and infos[0].filename == member
                        and not infos[0].is_dir() and not infos[0].flag_bits & 1
                        and 0 < infos[0].file_size <= 32768, 'ARTIFACT_MEMBER_SCHEMA')
                content = archive.read(infos[0])
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
            if isinstance(error, Hold):
                raise
            raise Hold('ARTIFACT_ZIP_INVALID') from None
        value = strict_json(content)
        require(content == encoded(value), 'ARTIFACT_NONCANONICAL')
        return value


def run_binding(run, run_id, head):
    require(type(run) is dict and run.get('id') == run_id
            and run.get('event') == 'pull_request'
            and run.get('path') == WORKFLOW_PATH
            and run.get('repository', {}).get('id') == REPOSITORY_ID
            and run.get('head_repository', {}).get('id') == REPOSITORY_ID
            and run.get('head_branch') == BRANCH and run.get('head_sha') == head
            and run.get('actor', {}).get('id') == OWNER_ID
            and run.get('triggering_actor', {}).get('id') == OWNER_ID
            and type(run.get('workflow_id')) is int and run['workflow_id'] > 0
            and type(run.get('run_number')) is int and run['run_number'] > 0,
            'RUN_PROVENANCE_MISMATCH')


def validate_event(event, env, mode):
    require(mode in ('dispatch', 'query'), 'ACTION_MODE')
    pr = event.get('pull_request', {})
    head = pr.get('head', {}).get('sha')
    require(type(head) is str and SHA40.fullmatch(head), 'HEAD_SHA')
    prefix = 'pr122-staging-readonly-' if mode == 'dispatch' else 'pr122-staging-readonly-query-'
    require(env.get('GITHUB_EVENT_NAME') == 'pull_request' and event.get('action') == 'labeled'
            and env.get('GITHUB_REPOSITORY') == REPOSITORY
            and env.get('GITHUB_REPOSITORY_ID') == str(REPOSITORY_ID)
            and env.get('GITHUB_ACTOR_ID') == str(OWNER_ID)
            and env.get('GITHUB_RUN_ATTEMPT') == '1'
            and event.get('sender', {}).get('id') == OWNER_ID
            and event.get('repository', {}).get('id') == REPOSITORY_ID
            and event.get('repository', {}).get('full_name') == REPOSITORY
            and event.get('number') == 122 and pr.get('number') == 122
            and pr.get('state') == 'open'
            and pr.get('head', {}).get('ref') == BRANCH
            and pr.get('head', {}).get('repo', {}).get('id') == REPOSITORY_ID
            and pr.get('base', {}).get('repo', {}).get('id') == REPOSITORY_ID
            and event.get('label', {}).get('name') == prefix + head,
            'EVENT_NOT_EXACT_OWNER_ADMISSION')
    run_id = env.get('GITHUB_RUN_ID', '')
    require(type(run_id) is str and run_id.isdecimal() and int(run_id) > 0, 'RUN_ID')
    return head, int(run_id)


def live_admission(api, event, env, mode):
    head, run_id = validate_event(event, env, mode)
    pr = api.get('/pulls/122')
    require(pr.get('number') == 122 and pr.get('state') == 'open'
            and pr.get('head', {}).get('sha') == head
            and pr.get('head', {}).get('ref') == BRANCH
            and pr.get('head', {}).get('repo', {}).get('id') == REPOSITORY_ID
            and pr.get('base', {}).get('repo', {}).get('id') == REPOSITORY_ID,
            'CURRENT_PR_HEAD_CHANGED')
    run = api.run(run_id)
    run_binding(run, run_id, head)
    require(run.get('run_attempt') == 1, 'RERUN_NOT_ADMITTED')
    runs = api.runs(run['workflow_id'])
    require(runs and len({r.get('run_number') for r in runs}) == len(runs)
            and all(type(r.get('run_number')) is int and r['run_number'] > 0 for r in runs),
            'RUN_SEQUENCE_INVALID')
    # A deleted Actions run leaves a run_number gap. Reject rather than allowing
    # missing history to look like a fresh label. No retention/window cutoff.
    require({r['run_number'] for r in runs} == set(range(1, max(r['run_number'] for r in runs) + 1))
            and any(r['id'] == run_id for r in runs), 'RUN_HISTORY_GAP_HOLD')
    consumed = []
    for row in runs:
        require(row.get('workflow_id') == run['workflow_id']
                and row.get('path') == WORKFLOW_PATH
                and row.get('repository', {}).get('id') == REPOSITORY_ID,
                'WORKFLOW_HISTORY_IDENTITY')
        if row['id'] == run_id or row.get('head_sha') != head:
            continue
        jobs = api.jobs(row['id'])
        require(any(job.get('name') == DISPATCH_JOB for job in jobs),
                'CLOUD_JOB_HISTORY_MISSING')
        for job in jobs:
            if job.get('name') != DISPATCH_JOB:
                continue
            require(job.get('run_id') == row['id'] and 'started_at' in job
                    and 'status' in job and 'conclusion' in job and 'steps' in job,
                    'JOB_HISTORY_INCOMPLETE')
            # GitHub gives skipped jobs a non-null started_at as well. Only this
            # explicit zero-step terminal shape proves the cloud job never ran.
            if job['status'] == 'completed' and job['conclusion'] == 'skipped' and job['steps'] == []:
                continue
            # Queued, in-progress, cancelled, missing/partial execution, and any
            # actual started step all consume admission conservatively.
            consumed.append(row)
    if mode == 'dispatch':
        require(not consumed, 'HEAD_CLOUD_JOB_ALREADY_STARTED_NO_REPLAY')
    else:
        require(len(consumed) == 1, 'QUERY_SOURCE_NOT_UNIQUE')
        run_binding(consumed[0], consumed[0]['id'], head)
        require(consumed[0].get('run_attempt') == 1, 'QUERY_SOURCE_RERUN_AMBIGUOUS')
    return {'head_sha': head, 'run_id': run_id, 'workflow_id': run['workflow_id'],
            'source_run_id': consumed[0]['id'] if consumed else run_id}
