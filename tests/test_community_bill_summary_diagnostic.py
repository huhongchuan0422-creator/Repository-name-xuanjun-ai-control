"""Pinned sample arithmetic diagnostics never promote financial acceptance."""
import json
import unittest
from scripts.community_provider_bills import (
    _parse_document,sample_summary_diagnostic,SPLIT_SUMMARY_COLUMNS)
from test_community_profitsharing_bill_schema import bill_bytes,fixture_rows


class SummaryDiagnostic(unittest.TestCase):
    def bill(self,rows=None,summary=None):
        _,records,schema,reported=_parse_document(bill_bytes(rows=rows,summary=summary))
        return dict(rows=records,schema=schema,reported_summary=reported)

    def test_success_categories_follow_pinned_example_arithmetic_only(self):
        result=sample_summary_diagnostic(self.bill())
        self.assertEqual(result['status'],'SAMPLE_ARITHMETIC_EQUAL_UNVERIFIED_SEMANTICS')
        self.assertEqual(result['differing_columns'],[])
        self.assertFalse(result['establishes_reconciliation'])
        self.assertEqual(result['coverage'],'PINNED_SAMPLE_ARITHMETIC_ONLY')

    def test_amount_discrepancy_labels_do_not_expose_raw_values(self):
        result=sample_summary_diagnostic(self.bill(summary=['4','9.91','2.03','8.07','7.09']))
        self.assertEqual(result['differing_columns'],[SPLIT_SUMMARY_COLUMNS[i] for i in (1,3,4)])
        self.assertEqual(result['failed_return_semantics'],'UNSPECIFIED_NONZERO')
        self.assertFalse(result['establishes_reconciliation'])
        for raw in ('9.91','2.03','8.07','7.09'):self.assertNotIn(raw,json.dumps(result))

    def test_nonzero_failure_column_never_assumed_wrong_or_zero(self):
        result=sample_summary_diagnostic(self.bill(summary=['4','0.01','3.00','0.02','0.01']))
        self.assertEqual(result['differing_columns'],[])
        self.assertEqual(result['failed_return_semantics'],'UNSPECIFIED_NONZERO')
        self.assertFalse(result['establishes_reconciliation'])

    def test_empty_sample_and_legacy_summary_are_separate(self):
        result=sample_summary_diagnostic(self.bill(rows=[],summary=['0','0','0','0','0']))
        self.assertEqual(result['status'],'SAMPLE_ARITHMETIC_EQUAL_UNVERIFIED_SEMANTICS')
        bill=self.bill();del bill['reported_summary']
        self.assertEqual(sample_summary_diagnostic(bill)['status'],'UNAVAILABLE_LEGACY_SUMMARY')

    def test_unknown_or_corrupt_retained_values_fail_closed(self):
        for schema in (None,[],False,{'id':'unknown'}):
            bill=self.bill();bill['schema']=schema
            self.assertEqual(sample_summary_diagnostic(bill)['status'],'UNKNOWN_SCHEMA')
        bill=self.bill();bill['rows'][0]['业务类型']='unknown'
        self.assertEqual(sample_summary_diagnostic(bill)['status'],'UNKNOWN_BUSINESS_OR_STATE')
        bill=self.bill();bill['reported_summary'][SPLIT_SUMMARY_COLUMNS[1]]='private-invalid'
        result=sample_summary_diagnostic(bill)
        self.assertEqual(result['status'],'INVALID_RETAINED_SUMMARY')
        self.assertNotIn('private-invalid',json.dumps(result))


if __name__=='__main__':unittest.main()
