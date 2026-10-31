"""Deterministic typo candidates from authorized requests; no model or publication.

This is an execution primitive for the protected build pipeline, not an HTTP
writer, arbitrary code editor, fee decision or new source-signing authority.
"""
import html
import re
import unicodedata
from html.parser import HTMLParser
from scripts.pr122_customer_core import canonical, digest, Denied, Conflict
from scripts.pr122_customer_changes import Changes
from scripts.pr122_customer_change_authority import load
from scripts.pr122_customer_preview import original

SAFE_TAGS = {'p', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'em', 'strong', 'small', 'li'}
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
BLOCKED = {'script', 'style', 'template', 'noscript', 'svg', 'math', 'a', 'button', 'label', 'form', 'table', 'select', 'textarea', 'option'}
SENSITIVE = re.compile(r'价格|费用|收费|付费|免费|金额|抵扣|权益|折扣|分成|分账|收益|佣金|支付|退款|合同|协议|权限|登录|注册|密码|密钥|保密|隐私|授权|验收|余额|订单|订阅|成本|price|fee|cost|pay|refund|discount|commission|contract|permission|login|password|secret|privacy|acceptance|balance|order|subscription', re.I)


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        next_row = [i]
        for j, y in enumerate(b, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (x != y)))
        row = next_row
    return row[-1]


def recipe(request):
    if type(request) is not str or len(request) > 200:
        raise Denied('EXPLICIT_SMALL_TEXT_REQUEST_REQUIRED')
    match = re.fullmatch(r'(?:将|把)「([^「」\r\n]+)」(?:改为|改成)「([^「」\r\n]+)」[。]?', request.strip())
    if not match:
        raise Denied('EXPLICIT_SMALL_TEXT_REQUEST_REQUIRED')
    before, after = match.groups()
    for value in (before, after):
        if not 1 <= len(value) <= 80 or unicodedata.normalize('NFKC', value) != value or any(unicodedata.category(c).startswith('C') or c.isdigit() or c in '<>&$¥￥€%％' for c in value) or SENSITIVE.search(value):
            raise Denied('SENSITIVE_OR_UNSUPPORTED_TEXT_CHANGE')
    if before == after or distance(before, after) > 4:
        raise Denied('TYPO_SCOPE_EXCEEDED')
    return before, after


class TextNodes(HTMLParser):
    def __init__(self, source, before):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.before = before
        self.stack = []
        self.zones = []
        self.hits = []
        self.starts = [0]
        for match in re.finditer('\n', source):
            self.starts.append(match.end())

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append(tag)
            self.zones.append(attrs.count(('data-xj-small-text', 'TYPO_ONLY_V1')) == 1)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            raise Denied('SMALL_EDIT_REQUIRES_WELL_FORMED_HTML')
        self.stack.pop()
        self.zones.pop()

    def handle_data(self, data):
        if self.before not in data:
            return
        if not self.stack or not self.zones[-1] or self.stack[-1] not in SAFE_TAGS or any(tag in BLOCKED for tag in self.stack) or SENSITIVE.search(unicodedata.normalize('NFKC', data)) or any(c.isdigit() or c in '$¥￥€%％' for c in data):
            raise Denied('CHANGE_IS_NOT_INERT_DISPLAY_TEXT')
        if data.count(self.before) != 1:
            raise Denied('AMBIGUOUS_SMALL_TEXT_CHANGE')
        line, col = self.getpos()
        self.hits.append(self.starts[line - 1] + col + data.index(self.before))


def build_candidate(center, reviewer, project, case):
    """Uses current local evidence only; returns bytes, never writes/executes them."""
    p, _, _ = center.project(reviewer, project, {'REVIEWER'})
    service = Changes(center)
    events = service._events(reviewer, project, case)
    first, last = events[0], events[-1]
    request = first['payload']
    if first['kind'] != 'REQUEST' or first['actor'] != p['owner'] or request.get('intent') != 'RECTIFICATION' or last['kind'] != 'ASSESSMENT' or last['payload'].get('state') != 'FREE_APPROVED' or last['payload'].get('category') != 'IN_SCOPE_SMALL' or last['payload'].get('totals') != {'cny_minor': 0, 'usd_minor': 0}:
        raise Denied('CURRENT_FREE_SMALL_ASSESSMENT_REQUIRED')
    if request.get('preview', {}).get('contract_ref') != p['authority_ref']:
        raise Denied('REQUEST_CONTRACT_BINDING')
    before, after = recipe(request['request'])
    authority = load(center)
    found, raw, _ = original(center, p['owner'], project, digest(request['page'].encode()), request['page_sha256'])
    if not request['page'].endswith(('.html', '/')) or len(raw) > 1000000:
        raise Denied('SMALL_HTML_PAGE_REQUIRED')
    source = raw.decode('utf-8', errors='strict')
    parser = TextNodes(source, before)
    parser.feed(source)
    parser.close()
    if parser.stack or len(parser.hits) != 1:
        raise Denied('UNIQUE_BALANCED_DISPLAY_TEXT_REQUIRED')
    offset = parser.hits[0]
    changed = (source[:offset] + html.escape(after, quote=False) + source[offset + len(before):]).encode('utf-8')
    # Re-read current authorization/evidence before returning a candidate. An
    # asynchronous publisher must recheck again; this is no publication permit.
    p2, _, _ = center.project(reviewer, project, {'REVIEWER'})
    if p2 != p or load(center) != authority or service._events(reviewer, project, case)[-1]['id'] != last['id']:
        raise Conflict('SMALL_EDIT_SOURCE_CHANGED')
    receipt = {'purpose': 'PR122_ZERO_MODEL_TEXT_CANDIDATE_V1', 'project': project, 'case': case, 'request_sha256': service._request_sha(events), 'assessment_event_id': last['id'], 'assessment_sha256': digest(canonical(last['payload'])), 'contract_ref': p['authority_ref'], 'page': request['page'], 'before_sha256': digest(raw), 'after_sha256': digest(changed), 'source_commit': found['source_commit'], 'manifest_sha256': found['manifest_sha256'], 'authority_sha256': authority['source_sha256'], 'operation': 'ONE_INERT_TEXT_REPLACEMENT', 'changed_text_nodes': 1, 'model_api_calls': 0, 'historical_contract_lookups': 0, 'fee_cny_minor': 0, 'fee_usd_minor': 0, 'state': 'CANDIDATE_ONLY_AWAIT_TEST_REVIEW_AND_PUBLISH', 'on_chain': False}
    return {'page_bytes': changed, 'receipt': receipt, 'receipt_sha256': digest(canonical(receipt))}
