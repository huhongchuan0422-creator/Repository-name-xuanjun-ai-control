import unittest
from scripts.human_alert_payload import alert_payload, REASONS


class AlertTests(unittest.TestCase):
    def test_fixed_minimal_payload(self):
        r = alert_payload('T1', 'VERIFICATION', 100, 'https://work.example')
        self.assertEqual(r['workspace_url'], 'https://work.example/owner/tasks/T1')
        self.assertFalse(r['send_performed']); self.assertFalse(r['approval_granted'])

    def test_no_freeform_reason(self):
        with self.assertRaises(ValueError): alert_payload('T1', 'SECRET', 100, 'https://work.example')

    def test_all_templates(self):
        for reason in REASONS:
            self.assertIn(REASONS[reason], alert_payload('T1', reason, 100, 'https://work.example')['text'])

    def test_unsafe_origins(self):
        for origin in ('http://work.example', 'https://user:secret@work.example',
                       'https://work.example/?token=secret', 'https://work.example#secret',
                       'https://work.example/owner/approve', 'https://work.example:99999',
                       'https://work.example\n', '//work.example', 'https://'):
            with self.assertRaises(ValueError): alert_payload('T1', 'SECURITY', 100, origin)

    def test_id_injection(self):
        for task in ('../x', '<script>', 'T?token=x', 'T\nX', '', None):
            with self.assertRaises(ValueError): alert_payload(task, 'SECURITY', 100, 'https://work.example')

    def test_deadline_not_bool(self):
        for deadline in (True, -1, '100', float('inf')):
            with self.assertRaises(ValueError): alert_payload('T1', 'SECURITY', deadline, 'https://work.example')

    def test_port(self):
        self.assertIn(':443/', alert_payload('T1', 'HANDOFF', 100, 'https://work.example:443')['workspace_url'])
