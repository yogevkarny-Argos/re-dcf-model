"""
opex.py — Operating expense engine.
Per-line escalation, management fee (% of EGI), property tax with reassessment lag.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .assumptions import Assumptions, OpExLine


@dataclass
class OpExMonth:
    month: int
    repairs_maintenance: float
    payroll: float
    general_admin: float
    marketing: float
    utilities: float
    contract_services: float
    make_ready: float
    management_fee: float
    insurance: float
    property_tax: float
    reserves: float
    total: float
    noi: float


def _escalate(base: float, annual_escalator: float, month: int) -> float:
    """Compound monthly from base using annual escalator."""
    return base * (1 + annual_escalator / 12) ** month


def _line_cost(line: "OpExLine", units: float, month: int, egi: float) -> float:
    if line.is_pct_of_egi:
        return egi * line.pct_of_egi
    base_annual = line.cost_per_unit_per_year * units
    base_monthly = base_annual / 12.0
    return _escalate(base_monthly, line.annual_escalator, month)


def compute_opex(a: "Assumptions", egi_by_month: List[float]) -> List[OpExMonth]:
    """
    Compute monthly OpEx for all months.
    egi_by_month: list of EGI values from revenue engine (length = hold_months+1).
    """
    from .assumptions import OpExAssumptions
    units = float(a.property.total_units)
    opex_a = a.opex
    pp = a.acquisition.purchase_price
    assessed = opex_a.assessed_value_at_purchase if opex_a.assessed_value_at_purchase > 0 else pp
    tax_lag = opex_a.tax_assessment_lag_months

    results: List[OpExMonth] = []

    for m, egi in enumerate(egi_by_month):
        oa = opex_a

        rm    = _line_cost(oa.repairs_maintenance, units, m, egi)
        pay   = _line_cost(oa.payroll, units, m, egi)
        ga    = _line_cost(oa.general_admin, units, m, egi)
        mktg  = _line_cost(oa.marketing, units, m, egi)
        util  = _line_cost(oa.utilities, units, m, egi)
        cs    = _line_cost(oa.contract_services, units, m, egi)
        mr    = _line_cost(oa.make_ready, units, m, egi)
        mgmt  = _line_cost(oa.management_fee, units, m, egi)
        ins   = _line_cost(oa.insurance, units, m, egi)
        res   = _line_cost(oa.reserves, units, m, egi)

        # Property tax — reassessment kicks in after lag, then annual escalator
        if m < tax_lag:
            # Pre-reassessment: use historical / in-place tax (base rate on assessed)
            annual_tax = assessed * oa.tax_rate
        else:
            # Post-reassessment: escalate from year of reassessment
            months_since_reassess = m - tax_lag
            annual_tax = (assessed * oa.tax_rate *
                          (1 + oa.property_tax.annual_escalator / 12) ** months_since_reassess)
        tax = annual_tax / 12.0

        total = rm + pay + ga + mktg + util + cs + mr + mgmt + ins + tax + res
        noi   = egi - total

        results.append(OpExMonth(
            month=m,
            repairs_maintenance=rm,
            payroll=pay,
            general_admin=ga,
            marketing=mktg,
            utilities=util,
            contract_services=cs,
            make_ready=mr,
            management_fee=mgmt,
            insurance=ins,
            property_tax=tax,
            reserves=res,
            total=total,
            noi=noi,
        ))

    return results
