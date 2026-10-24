"""Byte-pinned successor identity; draft source, never a grant or CLI."""
import pr17_c53_r2_transaction_candidate as historical

HOST=historical.HOST
E78_PIN=historical.E78_PIN
E78_MANIFEST=historical.E78_MANIFEST
RESOURCE_SHA=historical.RESOURCE_SHA
SOURCE_PRODUCER=historical.SOURCE_PRODUCER
ACTOR=historical.ACTOR
RECIPIENT=historical.RECIPIENT
PROJECT=historical.PROJECT
CERT=historical.CERT
ETC=historical.ETC
BIND=historical.BIND
CATALOG=historical.CATALOG
CUSTODY=historical.CUSTODY
DEST=historical.DEST
ARCHIVE_ROOT=historical.ARCHIVE_ROOT
PACKAGE_ROOT=historical.PACKAGE_ROOT
ARCHIVE_PREFIX=historical.ARCHIVE_PREFIX
ARCHIVE_SHA=historical.ARCHIVE_SHA
ARCHIVE_IDENTITY=historical.ARCHIVE_IDENTITY
TOKEN=historical.TOKEN
PIN_ORDER=historical.PIN_ORDER
MANIFEST_PATH=historical.MANIFEST_PATH
Hold=historical.Hold
require=historical.require
sha=historical.sha
canonical=historical.canonical
strict_json=historical.strict_json

SPEC_SHA256='3a4ac89fd1ac00599088f37df69675a05ff311bb45e981a0e8482ba2b72fbb82'
COMMIT='f0fe0d3978b72a11e4fa4cfb9928424d60124940'
MANIFEST='814c0779dfaaeefb79481864dd95a8e145f7074c60e8cc439fda7f9c5434098d'
CODEPIN='24cd8c0615fac2309e8a017b7985c4628fbabe8356bbcdf06fbe6575ce650aa1'


def verify_spec_bytes(raw):
    require(sha(raw)==SPEC_SHA256,'SUCCESSOR_SPEC_BYTES_CHANGED')
    spec=strict_json(raw)
    require(spec.get('schema')=='PR17_B5_STAGED_SUCCESSOR_V1' and
            spec.get('state')=='DRAFT_NO_LIVE_PERMISSION' and
            spec.get('release',{}).get('release_commit')==COMMIT and
            spec['release'].get('runtime_manifest_sha256')==MANIFEST and
            spec['release'].get('code_pin_sha256')==CODEPIN and
            len(spec.get('source',{}).get('source_records',()))==42,
            'SUCCESSOR_SPEC_IDENTITY')
    return spec


def verify_supplied_source(spec, blobs):
    require(type(blobs) is dict,'SOURCE_INPUT_TYPE')
    records={r['path']:r for r in spec['source']['source_records']}
    require(len(records)==42 and set(blobs)==set(records)|{MANIFEST_PATH},
            'SOURCE_42_PLUS_MANIFEST_REQUIRED')
    manifest=strict_json(blobs[MANIFEST_PATH])
    require(sha(blobs[MANIFEST_PATH])==MANIFEST and
            manifest.get('schema')=='B5_RUNTIME_SOURCE_V1' and
            manifest.get('code_pin_sha256')==CODEPIN and
            type(manifest.get('files')) is list and len(manifest['files'])==42,
            'SOURCE_MANIFEST_BINDING')
    require({x['path'] for x in manifest['files']}==set(records),
            'SOURCE_MANIFEST_PATHS')
    for row in manifest['files']:
        expected=records[row['path']]
        require(row=={k:expected[k] for k in ('path','bytes','sha256')},
                'SOURCE_MANIFEST_RECORD_CHANGED')
    for path,row in records.items():
        raw=blobs[path]
        require(type(raw) is bytes and len(raw)==row['bytes'] and
                sha(raw)==row['sha256'],'SOURCE_BYTES_CHANGED')
    pin=sha(canonical([[name,sha(blobs['production/cloud_connection/'+name])]
                      for name in PIN_ORDER]))
    require(pin==CODEPIN,'SOURCE_CODE_PIN_CHANGED')
    return {'state':'SOURCE_VERIFIED_NOT_ADMITTED','source_count':42,
            'installed_manifest_sha256':MANIFEST}


def rollback_classification(**kwargs):
    return historical.rollback_classification(**kwargs)
