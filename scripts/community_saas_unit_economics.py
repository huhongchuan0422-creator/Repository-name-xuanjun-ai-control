"""Reusable SaaS feature unit economics, separate up-front R&D from per-customer marginal cost.

All inputs are evidence-based or explicitly projections. Calculation is
informational: not settled revenue, profit recognition or payment authority.
"""
def _money(value):
    if type(value) is not int or value < 0:
        raise ValueError("INVALID_MONEY_MINOR")
    return value

def project_unit_economics(development_cost_minor, sale_price_minor,
                          marginal_cost_minor, expected_buyers,
                          realized_buyers=0, recurring_commitment_minor=0):
    for value in (development_cost_minor,sale_price_minor,marginal_cost_minor,
                  recurring_commitment_minor):
        _money(value)
    if type(expected_buyers) is not int or expected_buyers < 1 or (
       type(realized_buyers) is not int or realized_buyers < 0):
        raise ValueError("INVALID_BUYER_COUNT")
    # Recurring obligation is for the compared sale/service period only.
    variable_per_sale=marginal_cost_minor+recurring_commitment_minor
    unit_contribution=sale_price_minor-variable_per_sale
    return {
        "upfront_development_cost_minor": development_cost_minor,
        "unit_sale_price_minor": sale_price_minor,
        "unit_variable_cost_minor":variable_per_sale,
        "unit_contribution_before_rnd_minor":unit_contribution,
        "projected_buyers":expected_buyers,
        "projected_sales_minor":sale_price_minor*expected_buyers,
        "projected_contribution_after_rnd_minor":unit_contribution*expected_buyers-development_cost_minor,
        "realized_buyers":realized_buyers,
        "realized_sales_minor":None,
        "rnd_recovered_by_verified_sales":False,
        "requires_subsidy_approval":unit_contribution<0,
        "provider_payment_executed":False,
        "financial_profit_recognized":False
    }
