'use strict';
function makeClient(transport) {
  let generation = 0;
  let reference = null;
  const call = async (operation, params) => {
    const reply = await transport({operation, params, at: 0});
    if (!reply || reply.offline_only !== true || !reply.result) throw Error('UNTRUSTED_REPLY');
    return reply.result;
  };
  return {
    async storefront() { return call('community.storefront', {}); },
    reset() { generation++; reference = null; },
    async checkout(amount, orderReference, context='mini') {
      if (!/^[1-9][0-9]{0,8}$/.test(amount) || Number(amount) > 100000000 ||
          !/^[A-Za-z0-9_-]{1,64}$/.test(orderReference)) throw Error('INVALID_AMOUNT_OR_REFERENCE');
      const version = ++generation;
      reference = null;
      const {token} = await call('community.qr', {context});
      if (version !== generation) throw Error('STALE_CHECKOUT');
      const order = await call('community.checkout', {context, token, reference:orderReference, amount_minor:Number(amount)});
      if (version !== generation) throw Error('STALE_CHECKOUT');
      if (order.state !== 'PENDING' || order.provider_payment_started !== false ||
          order.provider_settlement_verified !== false || order.reference !== orderReference)
        throw Error('UNTRUSTED_ORDER');
      reference = orderReference;
      return order;
    },
    async receipt() {
      if (!reference) throw Error('CHECKOUT_REQUIRED');
      const version = generation;
      const result = await call('community.receipt', {reference});
      if (version !== generation) throw Error('STALE_RECEIPT');
      if (result.simulation_only !== true || result.provider_settlement_verified !== false ||
          result.financial_receipt_issued !== false || result.finance_effect !== 'NONE' ||
          result.order.reference !== reference || result.order.provider_settlement_verified !== false)
        throw Error('UNTRUSTED_RECEIPT');
      if (result.ads.AD_SLOT_PAYMENT_SUCCESS !== null &&
          (result.payment_state !== 'MOCK_PAID_SIMULATED' || result.order.state !== 'SUCCESS'))
        throw Error('UNTRUSTED_SUCCESS_AD');
      return result;
    }
  };
}
module.exports = {makeClient};
