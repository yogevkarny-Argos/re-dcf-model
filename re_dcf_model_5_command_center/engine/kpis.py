"""
kpis.py — All 15 industry KPIs computed from engine outputs.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .assumptions import Assumptions

from .dcf import compute_irr, compute_npv


@dataclass
class KPIs:
    # Returns
    levered_irr: Optional[float]
    unlevered_irr: Optional[float]
    equity_multiple: float
    cash_on_cash_year1: float
    cash_on_cash_stabilized: float
    npv: float

    # Valuation
    going_in_cap_rate: float
    stabilized_cap_rate: float
    exit_cap_rate: float
    yield_on_cost: float
    development_spread_bps: float
    profit_on_cost: float

    # Debt
    dscr_stabilized: float
    ltv_at_purchase: float
    ltv_at_refi: Optional[float]

    # Timing
    payback_month: Optional[int]
    stabilization_month: int
    break_even_occupancy: float


def compute_kpis(
    cashflows,          # List[CashFlowMonth]
    debt_months,        # List[DebtMonth]
    opex_months,        # List[OpExMonth]
    revenue_months,     # List[RevenueMonth]
    a,                  # Assumptions
    stabilization_month: int,
    waterfall_result,   # WaterfallResult
) -> KPIs:
    from .dcf import compute_irr, compute_npv

    equity_cfs    = [cf.equity_cf for cf in cashflows]
    unlevered_cfs = [cf.unlevered_cf for cf in cashflows]

    lev_irr   = compute_irr(equity_cfs)
    unlev_irr = compute_irr(unlevered_cfs)
    npv       = compute_npv(equity_cfs, a.discount_rate)

    total_in  = sum(-c for c in equity_cfs if c < 0)
    total_out = sum(c  for c in equity_cfs if c > 0)
    em        = total_out / total_in if total_in > 0 else 0.0

    # Cash-on-cash Year 1
    year1_ncfbt = sum(cf.ncfbt for cf in cashflows[1:13])
    coc_yr1     = year1_ncfbt / total_in if total_in > 0 else 0.0

    # Cash-on-cash stabilized year
    stab_start = stabilization_month
    stab_end   = min(stab_start + 12, len(cashflows))
    stab_ncfbt = sum(cf.ncfbt for cf in cashflows[stab_start:stab_end])
    coc_stab   = stab_ncfbt / total_in if total_in > 0 else 0.0

    # Cap rates
    pp = a.acquisition.purchase_price
    noi_yr1_annual = opex_months[1].noi * 12 if len(opex_months) > 1 else 0.0
    going_in_cap   = noi_yr1_annual / pp if pp > 0 else 0.0

    stab_noi_monthly = opex_months[stab_start].noi if stab_start < len(opex_months) else 0.0
    stab_noi_annual  = stab_noi_monthly * 12
    stab_cap         = stab_noi_annual / pp if pp > 0 else 0.0

    exit_cap = a.exit.exit_cap_rate

    # Yield on cost
    units = float(a.property.total_units)
    total_hard  = a.renovation.hard_cost_per_unit * units * (1 + a.renovation.contingency_pct)
    total_soft  = total_hard * a.renovation.soft_cost_pct
    total_common = a.renovation.common_area_cost + a.renovation.exterior_cost
    total_project_cost = pp + a.acquisition.total_closing_costs + total_hard + total_soft + total_common
    yoc = stab_noi_annual / total_project_cost if total_project_cost > 0 else 0.0

    # Development spread
    market_cap = a.market.market_cap_rate_going_in
    dev_spread_bps = (yoc - market_cap) * 10_000

    # Profit on cost
    exit_m  = a.exit.exit_month
    exit_noi = opex_months[exit_m].noi * 12 if exit_m < len(opex_months) else stab_noi_annual
    exit_value = exit_noi / exit_cap if exit_cap > 0 else 0.0
    poc = (exit_value - total_project_cost) / total_project_cost if total_project_cost > 0 else 0.0

    # DSCR at stabilization
    stab_ds = debt_months[stab_start].total_debt_service * 12 if stab_start < len(debt_months) else 1.0
    dscr    = stab_noi_annual / stab_ds if stab_ds > 0 else 0.0

    # LTV at purchase
    acq_loan_amt = pp * a.acq_loan.ltv_or_ltc if a.acq_loan.include else 0.0
    ltv_purchase = acq_loan_amt / pp if pp > 0 else 0.0

    # LTV at refi
    ltv_refi = None
    if a.refi.include:
        refi_m = a.refi.trigger_month or stabilization_month
        if refi_m < len(debt_months):
            refi_bal = debt_months[refi_m].refi_loan.ending_balance
            refi_val = stab_noi_annual / market_cap if market_cap > 0 else 1.0
            ltv_refi = refi_bal / refi_val if refi_val > 0 else 0.0

    # Payback month
    payback = next(
        (cf.month for cf in cashflows if cf.cumulative_equity_cf >= 0),
        None
    )

    # Break-even occupancy
    # BE occ = fixed OpEx / (avg rent per unit × 12)
    avg_rent = (sum(ut.market_rent for ut in a.property.unit_types) /
                len(a.property.unit_types)) if a.property.unit_types else 0.0
    fixed_opex_annual = opex_months[stab_start].total * 12 if stab_start < len(opex_months) else 0.0
    gpr_at_100_occ = avg_rent * 12 * units
    be_occ = fixed_opex_annual / gpr_at_100_occ if gpr_at_100_occ > 0 else 0.0

    return KPIs(
        levered_irr=lev_irr,
        unlevered_irr=unlev_irr,
        equity_multiple=em,
        cash_on_cash_year1=coc_yr1,
        cash_on_cash_stabilized=coc_stab,
        npv=npv,
        going_in_cap_rate=going_in_cap,
        stabilized_cap_rate=stab_cap,
        exit_cap_rate=exit_cap,
        yield_on_cost=yoc,
        development_spread_bps=dev_spread_bps,
        profit_on_cost=poc,
        dscr_stabilized=dscr,
        ltv_at_purchase=ltv_purchase,
        ltv_at_refi=ltv_refi,
        payback_month=payback,
        stabilization_month=stabilization_month,
        break_even_occupancy=be_occ,
    )
