"""Synthetic original Center persistence; no network or real identity writes."""
import json
import unittest
from unittest.mock import patch
import test_community_center_operations as original
from scripts.authorization_consumption_community import ConsumptionReservation, ConsumptionUnknown, SCHEMA


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = original.ExistingCenterOperations()
        self.fixture.setUp()
        self.center = self.fixture.fx.center
        self.reservation = ConsumptionReservation(self.center)
        self.scope = dict(caller='synthetic-community', audience='synthetic-community', user_id=self.fixture.fx.uid1, tenant_id='tenant1', project_id='project1', operation='community.access')
        self.request = dict(self.scope, schema=SCHEMA, request_id='synthetic_request', issued_unix=self.center.now(), expires_unix=self.center.now()+20, authorization_token='synthetic-opaque-token')

    def tearDown(self):
        self.fixture.tearDown()

    def reserve(self, request=None, reference='original_reference'):
        return self.reservation.reserve(self.request if request is None else request, self.scope, self.fixture.body(), reference)

    def test_every_protected_scope_dimension_must_match(self):
        for field in self.scope:
            with self.subTest(field=field), self.assertRaises(PermissionError):
                self.reserve(dict(self.request, **{field:'wrong'}))
        self.assertEqual(self.center.db.execute("SELECT count(*) FROM events WHERE channel='COMMUNITY_AUTHORIZATION_CONSUMPTION'").fetchone()[0], 0)

    def test_browser_session_or_extra_fields_rejected(self):
        for field in ('session', 'csrf', 'store_id', 'store_authorized'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.reserve(dict(self.request, **{field:'forbidden'}))

    def test_expired_future_and_overlong_times_rejected(self):
        now = self.center.now()
        for issued, expires in [(now-20,now),(now+1,now+20),(now,now+31),(True,now+1)]:
            with self.assertRaises(PermissionError):
                self.reserve(dict(self.request, issued_unix=issued, expires_unix=expires))

    def test_reservation_records_unknown_without_raw_token(self):
        result = self.reserve()
        self.assertEqual(result['state'], 'UNKNOWN_QUERY_EXISTING_ONLY')
        row = self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_AUTHORIZATION_CONSUMPTION'").fetchone()
        data = self.center.decrypt(row[0], 'COMMUNITY_AUTHORIZATION_CONSUMPTION')
        self.assertNotIn(self.request['authorization_token'].encode(), data)
        self.assertEqual(json.loads(data)['reference'], 'original_reference')

    def test_request_and_reference_cannot_be_replayed_after_reconstruction(self):
        self.reserve()
        self.reservation = ConsumptionReservation(self.center)
        with self.assertRaises(ConsumptionUnknown):
            self.reserve(reference='different_reference')
        with self.assertRaises(ConsumptionUnknown):
            self.reserve(dict(self.request, request_id='new_request'))

    def test_unknown_survives_actual_database_reopen(self):
        self.reserve()
        self.fixture.fx.reopen()
        self.center = self.fixture.fx.center
        self.reservation = ConsumptionReservation(self.center)
        with self.assertRaises(ConsumptionUnknown):
            self.reserve()

    def test_audit_failure_rolls_back_both_markers(self):
        with patch.object(self.center, 'audit', side_effect=RuntimeError('synthetic audit failure')):
            with self.assertRaises(RuntimeError):
                self.reserve()
        self.assertEqual(self.center.db.execute("SELECT count(*) FROM events WHERE channel='COMMUNITY_AUTHORIZATION_CONSUMPTION'").fetchone()[0], 0)
        self.reserve()

    def test_no_business_route_without_exact_contract_adapter(self):
        with patch.object(self.fixture.fx.stage.api, 'dispatch') as dispatch:
            with self.assertRaisesRegex(PermissionError, 'EXACT_PR122_CONTRACT_ADAPTER_NOT_BOUND'):
                self.reservation.dispatch(self.request)
            dispatch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
