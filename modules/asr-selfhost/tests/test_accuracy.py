from unittest import TestCase
from accuracy import compare

class Score(TestCase):
    def test_critical_negation_cannot_pass(self):
        cases = [{"id":"neg","reference":"不允许提交。","critical_clauses":["不允许"]}]
        out=compare(cases, {"neg":"允许提交。"})
        self.assertFalse(out["zero_strict_errors"])
        self.assertEqual(out["results"][0]["missing_critical_clauses"],["不允许"])
        self.assertEqual(out["character_edits"],1)

    def test_punctuation_and_extra_hallucinated_silence_dont_pass(self):
        cases=[{"id":"words","reference":"明天见。"},{"id":"silence","reference":""}]
        out=compare(cases,{"words":"明天见", "silence":"收到"})
        self.assertFalse(out["zero_strict_errors"])
        self.assertEqual(out["character_edits"],2)
        self.assertEqual(out["exact_samples"],0)
