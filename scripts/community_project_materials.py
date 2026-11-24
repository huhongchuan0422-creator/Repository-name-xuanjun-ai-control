"""Private project documents through the unchanged original Center.

No scanner, identity, storage directory, or reviewer authority is created here.
The admitted host supplies Center.scanner; absence is deliberately unavailable.
"""
from scripts.community_admin_route_gate import community_route, community_project
import base64
import binascii
import re
import unicodedata

from scripts.community_merchant_contract import valid_id

MAX_DOCUMENT_BYTES = 5_000_000
MAX_UPLOAD_BODY = 6_680_000
_MIME_EXTENSIONS = {
    'application/pdf': ('.pdf',),
    'image/png': ('.png',),
    'image/jpeg': ('.jpg', '.jpeg'),
}


class ProjectMaterials:
    def __init__(self, commerce):
        self.commerce = commerce
        self.center = commerce.center

    def authorize_upload(self, token, scene):
        """Used before reading the file body and again immediately before save."""
        identity = self.commerce.identity
        identity._time(self.center.now())
        if type(scene) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', scene):
            raise ValueError('INVALID_PROJECT_MATERIAL_SCENE')
        uid, project, principal = identity._resolve(token, scene)
        if principal.role != 'CUSTOMER':
            raise PermissionError('CONSUMER_SESSION_REQUIRED')
        source, _, _ = self.center.project(uid, project, ('OWNER', 'EDITOR'))
        if source['tenant'] != self.commerce.runtime.bindings[principal]['tenant_id']:
            raise PermissionError('PROJECT_MATERIAL_TENANT_DENIED')
        return uid, project

    def upload(self, token, scene, body):
        uid, project = self.authorize_upload(token, scene)
        if (type(body) is not dict or set(body) != {'item', 'revision', 'filename', 'content_base64'}
                or not valid_id(body['item']) or type(body['revision']) is not int
                or body['revision'] < 0):
            raise ValueError('INVALID_PROJECT_DOCUMENT_FIELDS')
        filename, encoded = body['filename'], body['content_base64']
        if (type(filename) is not str or not 1 <= len(filename) <= 180
                or filename != filename.strip() or filename in ('.', '..')
                or any(c in filename for c in '/\\:')
                or any(unicodedata.category(c).startswith('C') for c in filename)):
            raise ValueError('INVALID_PROJECT_DOCUMENT_FILENAME')
        if (type(encoded) is not str or not encoded
                or len(encoded) > 4 * ((MAX_DOCUMENT_BYTES + 2) // 3)):
            raise ValueError('INVALID_PROJECT_DOCUMENT_ENCODING')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('INVALID_PROJECT_DOCUMENT_ENCODING') from None
        if (not 1 <= len(raw) <= MAX_DOCUMENT_BYTES
                or base64.b64encode(raw).decode('ascii') != encoded):
            raise ValueError('INVALID_PROJECT_DOCUMENT_ENCODING')
        mime = ('application/pdf' if raw.startswith(b'%PDF-') else
                'image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else
                'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None)
        if mime is None or not filename.lower().endswith(_MIME_EXTENSIONS[mime]):
            raise ValueError('PROJECT_DOCUMENT_FORMAT_MISMATCH')
        requirement, _ = self.center.requirement(uid, project, body['item'], ('OWNER', 'EDITOR'))
        if requirement['submission_type'] != 'PRIVATE_DOCUMENT':
            raise PermissionError('PRIVATE_DOCUMENT_REQUIREMENT_REQUIRED')
        # Recheck authority after decoding; the Core owns all version, scanning,
        # quota, encryption, audit and independent-review enforcement.
        if self.authorize_upload(token, scene) != (uid, project):
            raise PermissionError('PROJECT_MATERIAL_IDENTITY_CHANGED')
        return self.center.save(uid, project, body['item'], body['revision'], 'DOCUMENT', raw)

    @community_route('/community/project-materials')
    def reviewer(self, session, csrf, body):
        if (type(csrf) is not str or not csrf or type(body) is not dict
                or set(body) != {'workspace', 'operation', 'params'}
                or not valid_id(body['workspace'])
                or type(body['operation']) is not str
                or body['operation'] not in ('checklist', 'download')
                or type(body['params']) is not dict):
            raise ValueError('INVALID_PROJECT_MATERIAL_REVIEW_FIELDS')
        operation, params = body['operation'], body['params']
        expected = set() if operation == 'checklist' else {'object_id'}
        if set(params) != expected or operation == 'download' and not valid_id(params['object_id']):
            raise ValueError('INVALID_PROJECT_MATERIAL_REVIEW_FIELDS')
        uid = self.center.session(session, csrf)
        project = body['workspace']
        self.center.project(uid, project, ('REVIEWER',))
        if operation == 'checklist':
            return self.center.checklist(uid, project)
        raw, mime = self.center.download(uid, project, params['object_id'])
        return dict(content_base64=base64.b64encode(raw).decode('ascii'), mime=mime,
                    filename=params['object_id'] + _MIME_EXTENSIONS[mime][0])
