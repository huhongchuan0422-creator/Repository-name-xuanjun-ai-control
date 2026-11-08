import unittest
from unittest.mock import patch
from test_community_h5_recovery import H5Recovery
from scripts.community_h5 import OrderUnavailable
class OrderDenial(unittest.TestCase):
 def setUp(self):
  self.fx=H5Recovery();self.fx.setUp()
 def tearDown(self):self.fx.tearDown()
 def test_only_exact_original_operation_denials_are_public(self):
  h=self.fx.h
  cases=[('commerce.purchase_recover','OWNED_BASKET_RESERVATION_REQUIRED',True),('commerce.purchase_read','CUSTOMER_ORDER_DENIED',True),('commerce.purchase','OWNED_BASKET_RESERVATION_REQUIRED',False),('commerce.purchase_recover','PROJECT_PERMISSION_REQUIRED',False),('commerce.purchase_recover','ORIGINAL_BASKET_IDENTITY_CHANGED',False)]
  for op,code,typed in cases:
   with self.subTest(op=op,code=code),patch.object(h.gateway,'dispatch',side_effect=PermissionError(code)):
    with self.assertRaises(PermissionError) as e:h.dispatch('/h5/api',self.fx.headers,dict(scene='shop1',operation=op,params={'reference':'synthetic'}))
    self.assertEqual(type(e.exception) is OrderUnavailable,typed)
 def test_invalid_csrf_is_not_order_unavailable(self):
  h=self.fx.h;self.fx.headers.replace_header('X-CSRF-Token','invalid')
  with patch.object(h.gateway,'dispatch',side_effect=PermissionError('OWNED_BASKET_RESERVATION_REQUIRED')) as dispatch:
   with self.assertRaises(PermissionError) as e:h.dispatch('/h5/api',self.fx.headers,dict(scene='shop1',operation='commerce.purchase_recover',params={'reference':'synthetic'}))
   self.assertIsNot(type(e.exception),OrderUnavailable);dispatch.assert_not_called()
if __name__=='__main__':unittest.main()
