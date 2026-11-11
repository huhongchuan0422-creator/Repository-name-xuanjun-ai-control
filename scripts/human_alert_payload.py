"""Minimal alert text for existing outbox; no sender or approval action."""
import re
from urllib.parse import urlsplit

REASONS = {'VERIFICATION': '需要人工验证', 'RESOURCE': '资源不足，任务已暂停',
           'SECURITY': '安全门禁未通过', 'HANDOFF': '任务交接等待确认',
           'DELIVERY': '通知投递失败，请查看工作台'}


def alert_payload(task_id, reason, deadline, workspace_origin):
    if (not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', task_id)
            or not isinstance(reason, str) or reason not in REASONS
            or type(deadline) is not int or not 0 <= deadline <= 253402300799
            or not isinstance(workspace_origin, str) or len(workspace_origin) > 200):
        raise ValueError('INVALID_ALERT_INPUT')
    parsed = urlsplit(workspace_origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
            or not re.fullmatch(r'https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?', workspace_origin)
            or parsed.port is not None and not 1 <= parsed.port <= 65535):
        raise ValueError('INVALID_WORKSPACE_ORIGIN')
    url = workspace_origin + '/owner/tasks/' + task_id
    return {'schema': 'HUMAN_ALERT_PAYLOAD_V1',
            'text': '任务 %s：%s。截止时间（Unix秒）：%d。查看工作台：%s' %
                    (task_id, REASONS[reason], deadline, url),
            'workspace_url': url, 'approval_granted': False,
            'send_performed': False, 'recipient_verification': 'EXISTING_OUTBOX_REQUIRED'}
