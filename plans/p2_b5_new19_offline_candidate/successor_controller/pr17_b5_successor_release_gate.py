"""External controller binder checked afresh at each mutation boundary.

The caller must supply a separately approved digest and protected readers.
Nothing in this module creates an approval, accepts a self-declared digest, or
selects an alternate path when a protected read fails.
"""
import hashlib
import re

import pr17_b5_successor_review as c53


class ExternalReleaseGate:
    @classmethod
    def from_registered(cls, evidence_store, binding, *, read_binder,
                        read_manifest, read_source, read_current,
                        read_installed_runtime):
        from pr17_b5_successor_witness import SuccessorEvidenceStore
        c53.require(type(evidence_store) is SuccessorEvidenceStore and
                    type(binding) is dict,
                    'EXTERNAL_BINDER_ENROLLMENT_SOURCE')
        row, _ = evidence_store.read_exact(binding, 'release')
        return cls(approved_sha256=row['payload']['binder_sha256'],
                   read_binder=read_binder, read_manifest=read_manifest,
                   read_source=read_source, read_current=read_current,
                   read_installed_runtime=read_installed_runtime,
                   evidence_store=evidence_store, evidence_binding=binding)

    def __init__(self, *, approved_sha256, read_binder, read_manifest,
                 read_source, read_current, read_installed_runtime,
                 evidence_store=None, evidence_binding=None):
        c53.require(type(approved_sha256) is str and
                    re.fullmatch('[0-9a-f]{64}', approved_sha256),
                    'EXTERNAL_BINDER_APPROVED_PIN_UNKNOWN')
        for reader in (read_binder, read_manifest, read_source, read_current,
                       read_installed_runtime):
            c53.require(callable(reader), 'EXTERNAL_BINDER_PROTECTED_READER_UNKNOWN')
        self.approved_sha256 = approved_sha256
        self.read_binder = read_binder
        self.read_manifest = read_manifest
        self.read_source = read_source
        self.read_current = read_current
        self.read_installed_runtime = read_installed_runtime
        self.evidence_store = evidence_store
        self.evidence_binding = evidence_binding

    def check(self, phase, spec):
        c53.require(phase in ('preflight', 'publish', 'start', 'recover'),
                    'EXTERNAL_BINDER_PHASE')
        if self.evidence_store is not None:
            from pr17_b5_successor_witness import SuccessorEvidenceStore
            c53.require(type(self.evidence_store) is SuccessorEvidenceStore and
                        type(self.evidence_binding) is dict,
                        'EXTERNAL_BINDER_ENROLLMENT_SOURCE')
            enrolled, _ = self.evidence_store.read_exact(
                self.evidence_binding, 'release')
            approval=enrolled['payload']
            c53.require(approval['binder_sha256']==self.approved_sha256 and
                        approval['catalog_sha256']==self.evidence_binding['catalog_sha256'],
                        'EXTERNAL_BINDER_ENROLLMENT_CHANGED')
        raw = self.read_binder()
        c53.require(type(raw) is bytes and len(raw) <= 16384 and
                    c53.sha(raw) == self.approved_sha256,
                    'EXTERNAL_BINDER_APPROVED_BYTES_CHANGED')
        record = c53.strict_json(raw)
        if self.evidence_store is not None:
            c53.require(type(record) is dict and all(
                    approval[key]==record.get(key) for key in (
                    'controller_commit','controller_manifest_sha256',
                    'controller_code_pin_sha256','successor_spec_sha256',
                    'runtime_manifest_sha256','runtime_code_pin_sha256',
                    'target_release')) and
                    self.evidence_binding['job']==record['job'] and
                    self.evidence_binding['project']==record['project'] and
                    self.evidence_binding['recipient']==record['recipient'] and
                    tuple(self.evidence_binding['ids'])==tuple(
                        spec['batch']['draft_request_ids']),
                    'EXTERNAL_BINDER_ENROLLMENT_SCOPE')
        c53.require(set(record) == {
            'schema', 'state', 'controller_commit', 'controller_manifest_sha256',
            'controller_code_pin_sha256',
            'successor_spec_sha256', 'runtime_release_commit',
            'runtime_manifest_sha256', 'runtime_code_pin_sha256',
            'job', 'project', 'recipient', 'target_release'},
            'EXTERNAL_BINDER_FIELDS')
        c53.require(record['schema'] == 'PR17_B5_SUCCESSOR_EXTERNAL_BINDER_V1' and
                    record['state'] == 'SOURCE_IDENTITY_ONLY_NOT_INSTALL_ADMISSION' and
                    type(record['controller_commit']) is str and
                    re.fullmatch('[0-9a-f]{40}', record['controller_commit']) and
                    record['successor_spec_sha256'] == c53.binder.SPEC_SHA256 and
                    record['runtime_release_commit'] == c53.COMMIT and
                    record['runtime_manifest_sha256'] == c53.MANIFEST and
                    record['runtime_code_pin_sha256'] == c53.PIN and
                    record['job'] == spec['fixed_paths']['job_proposed'] and
                    record['project'] == c53.PROJ and
                    record['recipient'] == c53.RECIP and
                    record['target_release'] == spec['fixed_paths']['target_release'],
                    'EXTERNAL_BINDER_WRONG_RELEASE_OR_SPEC')
        manifest_raw = self.read_manifest()
        c53.require(type(manifest_raw) is bytes and len(manifest_raw) <= 16384 and
                    c53.sha(manifest_raw) == record['controller_manifest_sha256'],
                    'EXTERNAL_CONTROLLER_MANIFEST_CHANGED')
        manifest = c53.strict_json(manifest_raw)
        files = manifest.get('files')
        exact = {'successor_controller/'+name for name in (
            'pr17_b5_successor_authority.py', 'pr17_b5_successor_backend.py',
            'pr17_b5_successor_binder.py', 'pr17_b5_successor_loader.py',
            'pr17_b5_successor_local.py', 'pr17_b5_successor_release_gate.py',
            'pr17_b5_successor_review.py', 'pr17_b5_successor_runtime.py',
            'pr17_b5_successor_witness.py')}
        exact.update(('successor_contract.py', 'successor_source_loader.py',
                      'successor_analyst_read.py'))
        c53.require(manifest.get('schema') ==
                    'PR17_B5_SUCCESSOR_CONTROLLER_SOURCE_V1' and
                    type(files) is list and len(files) == len(exact) and
                    {x.get('path') for x in files} == exact,
                    'EXTERNAL_CONTROLLER_SOURCE_SET')
        c53.require(c53.sha(c53.canon(sorted(
                    (x['path'],x['bytes'],x['sha256']) for x in files))) ==
                    record['controller_code_pin_sha256'],
                    'EXTERNAL_CONTROLLER_CODE_PIN')
        for row in files:
            name = row.get('path')
            c53.require(type(name) is str and all(ord(c)<128 for c in name) and
                        '..' not in name.split('/') and
                        (name.startswith('successor_controller/') or
                         name in ('successor_contract.py',
                                  'successor_source_loader.py',
                                  'successor_analyst_read.py')),
                        'EXTERNAL_CONTROLLER_PATH')
            c53.require(type(row.get('bytes')) is int and 0 < row['bytes'] <= 262144
                        and type(row.get('sha256')) is str and
                        re.fullmatch('[0-9a-f]{64}', row['sha256']),
                        'EXTERNAL_CONTROLLER_RECORD')
            content = self.read_source(name)
            c53.require(type(content) is bytes and len(content) == row['bytes'] and
                        hashlib.sha256(content).hexdigest() == row['sha256'],
                        'EXTERNAL_CONTROLLER_BYTES_CHANGED')
        current = self.read_current()
        c53.require(type(current) is dict and set(current) == set(c53.BASES),
                    'EXTERNAL_CURRENT_SET')
        expected = (spec['fixed_paths']['target_release'] if phase in ('start','recover')
                    else [base+'/releases/e78bd7749414d1637012f57b65d2019955282fc3'
                          for base in c53.BASES])
        c53.require(all(current[base] == target for base, target in
                        zip(c53.BASES, expected)), 'EXTERNAL_CURRENT_RELEASE_CHANGED')
        if phase in ('start','recover'):
            runtime_rows = spec.get('source',{}).get('source_records')
            c53.require(type(runtime_rows) is list and len(runtime_rows)==42 and
                        len({r['path'] for r in runtime_rows})==42,
                        'EXTERNAL_INSTALLED_RUNTIME_SET')
            for base in c53.BASES:
                manifest_bytes = self.read_installed_runtime(
                    base,c53.binder.MANIFEST_PATH)
                c53.require(type(manifest_bytes) is bytes and
                            c53.sha(manifest_bytes)==c53.MANIFEST,
                            'EXTERNAL_INSTALLED_RUNTIME_MANIFEST')
                for row in runtime_rows:
                    content=self.read_installed_runtime(base,row['path'])
                    c53.require(type(content) is bytes and
                                len(content)==row['bytes'] and
                                c53.sha(content)==row['sha256'],
                                'EXTERNAL_INSTALLED_RUNTIME_BYTES_CHANGED')
        return record['controller_commit']
