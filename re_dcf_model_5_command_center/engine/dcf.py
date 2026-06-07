"""
dcf.py — NPV, IRR (Newton-Raphson), levered & unlevered cash flows.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
import math


@dataclass
class CashFlowMonth:
    month: int
    egi: float
    noi: float
    debt_service: float
    capex_equity: float        # equity-funded reno draws + ongoing capex
    ncfbt: float               # net cash flow before tax (NOI - DS - CapEx)
    refi_proceeds: float
    sale_proceeds: float       # net after payoff and selling costs
    equity_cf: float           # ncfbt + refi + sale (the IRR input stream)
    unlevered_cf: float        # NOI - total capex (property level, no debt)
    cumulative_equity_cf: float


def build_cash_flows(
    revenue_months,    # List[RevenueMonth]
    opex_months,       # List[OpExMonth]
    capex_months,      # List[CapExMonth]
    debt_months,       # List[DebtMonth]
    a,                 # Assumptions
    stabilization_month: int,
) -> List[CashFlowMonth]:
    """Assemble the full monthly cash flow stream."""

    exit_m = a.exit.exit_month
    exit_cap = a.exit.exit_cap_rate
    selling_cost = a.exit.selling_cost_pct

    # Equity invested at Month 0
    pp       = a.acquisition.purchase_price
    acq_costs = a.acquisition.total_closing_costs
    acq_loan_amt = pp * a.acq_loan.ltv_or_ltc if a.acq_loan.include else 0.0
    gp_fee   = pp * a.waterfall.gp_acquisition_fee_pct

    results: List[CashFlowMonth] = []
    cum_equity = 0.0

    for m in range(len(revenue_months)):
        rev  = revenue_months[m]
        opex = opex_months[m]
        cx   = capex_months[m]
        debt = debt_months[m]

        egi = rev.egi
        noi = opex.noi

        # Debt service: scheduled loan payments (payoffs excluded — in sale_proc)
        ds = debt.total_debt_service

        # Ongoing capex (reserves post-stabilization, equity-funded)
        ongoing = cx.ongoing_capex

        # Operating net cash flow
        ncfbt = noi - ds - ongoing

        # Refi proceeds (positive inflow in refi month)
        refi_proc = debt.refi_net_proceeds

        # Exit / sale proceeds
        sale_proc = 0.0
        if m == exit_m:
            exit_noi_annual = noi * 12
            exit_value      = exit_noi_annual / exit_cap if exit_cap > 0 else 0.0
            loan_payoff     = debt.payoff_amount        # remaining balance at exit
            gross_proceeds  = exit_value * (1 - selling_cost)
            disp_fee        = exit_value * a.waterfall.gp_disposition_fee_pct
            sale_proc       = gross_proceeds - loan_payoff - disp_fee

        # GP asset management fee (monthly, taken before distribution)
        gp_mgmt_fee = egi * a.waterfall.gp_asset_mgmt_fee_pct / 12.0

        # Equity reno draws (funded by equity, not loan) — cash out during reno
        equity_reno = cx.equity_reno_draw

        # Month 0: initial equity investment (down payment + closing costs + GP fee)
        initial_equity_out = 0.0
        if m == 0:
            initial_equity_out = (pp - acq_loan_amt) + acq_costs + gp_fee

        # Equity cash flow
        equity_cf = (ncfbt
                     + refi_proc
                     + sale_proc
                     - gp_mgmt_fee
                     - equity_reno
                     - initial_equity_out)

        # Unlevered cash flow (property level, no debt)
        unlevered_sale_proc = 0.0
        if m == exit_m:
            # Unlevered exit proceeds exclude debt payoff.
            unlevered_sale_proc = gross_proceeds - disp_fee

        unlevered_cf = noi - cx.total_reno_draw - ongoing + unlevered_sale_proc
        if m == 0:
            unlevered_cf -= (pp + acq_costs)

        # Capex_equity for reporting (reno equity draw + ongoing + initial)
        equity_capex = equity_reno + ongoing + initial_equity_out

        cum_equity += equity_cf

        results.append(CashFlowMonth(
            month=m,
            egi=egi,
            noi=noi,
            debt_service=ds,
            capex_equity=equity_capex,
            ncfbt=ncfbt,
            refi_proceeds=refi_proc,
            sale_proceeds=sale_proc,
            equity_cf=equity_cf,
            unlevered_cf=unlevered_cf,
            cumulative_equity_cf=cum_equity,
        ))

    return results


# ---------------------------------------------------------------------------
# IRR — Newton-Raphson with bisection fallback
# ---------------------------------------------------------------------------

def _npv_at_rate(cfs: List[float], monthly_rate: float) -> float:
    """NPV at monthly rate with numeric guardrails for IRR search."""
    base = 1.0 + monthly_rate
    if base <= 0.0:
        return float("inf")
    total = 0.0
    for t, cf in enumerate(cfs):
        try:
            denom = base ** t
            if denom == 0.0:
                return float("inf") if cf >= 0 else float("-inf")
            total += cf / denom
        except (OverflowError, ZeroDivisionError):
            return float("inf") if cf >= 0 else float("-inf")
    return total


def _dnpv_at_rate(cfs: List[float], monthly_rate: float) -> float:
    """Derivative of NPV w.r.t. monthly_rate with numeric guardrails."""
    base = 1.0 + monthly_rate
    if base <= 0.0:
        return float("inf")
    total = 0.0
    for t, cf in enumerate(cfs):
        try:
            denom = base ** (t + 1)
            if denom == 0.0:
                return float("inf") if cf <= 0 else float("-inf")
            total += -t * cf / denom
        except (OverflowError, ZeroDivisionError):
            return float("inf") if cf <= 0 else float("-inf")
    return total


def compute_irr(cfs: List[float], tol: float = 1e-8, max_iter: int = 500) -> Optional[float]:
    """
    Compute monthly IRR via bracket scan + bisection + Newton-Raphson refinement.
    Returns annualized IRR, or None if no stable solution is found.
    """
    has_neg = any(c < 0 for c in cfs)
    has_pos = any(c > 0 for c in cfs)
    if not (has_neg and has_pos):
        return None

    bracket_found = False
    lo = hi = None
    scan_points = [(-0.95 + i * 0.005) for i in range(int((1.0 - (-0.95)) / 0.005) + 1)]
    prev_r = scan_points[0]
    prev_f = _npv_at_rate(cfs, prev_r)

    for r_scan in scan_points[1:]:
        curr_f = _npv_at_rate(cfs, r_scan)
        if curr_f in (float("inf"), float("-inf")) or prev_f in (float("inf"), float("-inf")):
            prev_r, prev_f = r_scan, curr_f
            continue
        if prev_f * curr_f < 0:
            lo, hi = prev_r, r_scan
            bracket_found = True
            break
        prev_r, prev_f = r_scan, curr_f

    if not bracket_found or lo is None or hi is None:
        return None

    f_lo = _npv_at_rate(cfs, lo)
    for _ in range(100):
        mid = (lo + hi) / 2.0
        f_mid = _npv_at_rate(cfs, mid)
        if abs(f_mid) < tol or (hi - lo) < tol:
            lo = hi = mid
            break
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo = mid
            f_lo = f_mid

    r = (lo + hi) / 2.0
    for _ in range(max_iter):
        f = _npv_at_rate(cfs, r)
        df = _dnpv_at_rate(cfs, r)
        if df in (float("inf"), float("-inf")) or abs(df) < 1e-15:
            break
        r_new = r - f / df
        r_new = max(-0.95, min(r_new, 1.0))
        if abs(r_new - r) < tol:
            r = r_new
            break
        r = r_new

    residual = _npv_at_rate(cfs, r)
    if abs(residual) > 1.0:
        return None
    return (1 + r) ** 12 - 1


def compute_npv(cfs: List[float], annual_discount_rate: float) -> float:
    monthly_rate = annual_discount_rate / 12.0
    return _npv_at_rate(cfs, monthly_rate)
