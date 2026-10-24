import unittest
from scripts.resume_prerequisite_view import FIELDS, resume_view


def evidence():
    e = dict.fromkeys(FIELDS, True)
    e.update(observed_at=100, binding_sha256='a' * 64)
    return e


class ResumeTests(unittest.TestCase):
    def test_report_never_resumes(self):
        r = resume_view(evidence(), 100)
        self.assertEqual(r['status'], 'PREREQUISITES_REPORTED')
        self.assertFalse(r['resume_granted'])

    def test_every_gate_required(self):
        for field in FIELDS:
            for value in (None, False, 1, 'true'):
                e = evidence(); e[field] = value
                self.assertEqual(resume_view(e, 100)['status'], 'HOLD')

    def test_missing_schema(self):
        e = evidence(); del e['owner_authorized']
        self.assertEqual(resume_view(e, 100)['status'], 'HOLD')

    def test_stale_future_nan(self):
        for value in (None, True, float('nan'), float('inf'), 101, -1, 10 ** 1000):
            e = evidence(); e['observed_at'] = value
            self.assertEqual(resume_view(e, 100)['status'], 'HOLD')
        self.assertEqual(resume_view(evidence(), 401)['status'], 'HOLD')

    def test_time_boundary(self):
        self.assertEqual(resume_view(evidence(), 400)['status'], 'PREREQUISITES_REPORTED')

    def test_binding_missing(self):
        e = evidence(); e['binding_sha256'] = None
        self.assertEqual(resume_view(e, 100)['status'], 'HOLD')

    def test_bad_clock(self):
        for value in (True, -1, float('nan'), 10 ** 1000):
            with self.assertRaises(ValueError): resume_view(evidence(), value)

    def test_all_reasons_together(self):
        e = evidence(); e['budget_available'] = False; e['effects_reconciled'] = None
        self.assertEqual(len(resume_view(e, 100)['reasons']), 2)
