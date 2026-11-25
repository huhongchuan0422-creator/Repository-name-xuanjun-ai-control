"""Review entry: original gateway/Center/temp SQLite; synthetic WeChat subjects only."""
import unittest
from scripts.pr122_customer_core import canonical
from scripts.community_wechat_registration import CONSUMER
import test_community_public_directory as public_fixture


class RecommendationReviewEntry(unittest.TestCase):
    def test_new_wechat_consumer_reads_only_published_authorized_store_and_rechecks_revoke(self):
        fx = public_fixture.PublicDirectory()
        fx.setUp()
        self.addCleanup(fx.doCleanups)
        fx.publish()
        inner = fx.inner
        center, identity, gateway = inner.center, inner.identity, inner.gateway
        realm = dict(kind="COMMUNITY_PLATFORM_REALM", title="Synthetic review platform",
                     requirements=[], source="OWNER_APPROVED_FIRST_INSTALL", authority_ref="test_realm")
        center.db.execute("UPDATE projects SET authority_ref='test_realm',payload=? WHERE id='project1'",
                          (center.encrypt(canonical(realm), "project:project1"),))
        identity.configure_registration(["shop1"])
        inner.provider.exchange.return_value = dict(appid=identity.appid, openid="new_synthetic_reviewer")
        token = gateway.login({"code": "synthetic_review_code"})["session_token"]
        uid = center.session(token)
        self.assertEqual(center.db.execute("SELECT count(*) FROM members WHERE user_id=?", (uid,)).fetchone()[0], 0)

        def read(operation="customer.directory", params=None, credential=token):
            return gateway.dispatch(credential, dict(scene="", operation=operation, params={} if params is None else params))

        changes = (center.db.total_changes, fx.fx.db.total_changes)
        rows = read()["records"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(read("customer.store", {"id": rows[0]["id"]}), rows[0])
        self.assertNotIn("contact", rows[0])
        self.assertNotIn("scope", rows[0])
        self.assertEqual(changes, (center.db.total_changes, fx.fx.db.total_changes))
        with self.assertRaises(PermissionError):
            read(credential="")
        with self.assertRaises(ValueError):
            read("customer.store", {"id": "../invalid"})
        with self.assertRaises(PermissionError):
            read("customer.store", {"id": "b" * 64})
        with self.assertRaises(ValueError):
            read(params={"tenant": "foreign"})
        fx.publish(1, False)
        self.assertEqual(read()["records"], [])
        with self.assertRaises(PermissionError):
            read("customer.store", {"id": rows[0]["id"]})
        center.db.execute("UPDATE links SET active=0 WHERE channel=? AND user_id=?", (CONSUMER, uid))
        self.assertEqual(read()["records"], [])
        with self.assertRaises(PermissionError):
            read("customer.store", {"id": rows[0]["id"]})


if __name__ == "__main__":
    unittest.main()
