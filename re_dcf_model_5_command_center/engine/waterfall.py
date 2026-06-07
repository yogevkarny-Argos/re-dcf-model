"""
waterfall.py — GP/LP promote and preferred return waterfall.
Operates on the equity cash flow stream (monthly), allocates between GP and LP.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .assumptions import Assumptions, WaterfallAssumptions


@dataclass
class WaterfallResult:
    total_equity_in: float
    total_distributions: float
    gp_equity_in: float
    lp_equity_in: float
    gp_distributions: float
    lp_distributions: float
    gp_net_irr: float
    lp_net_irr: float
    gp_em: float
    lp_em: float


def allocate_waterfall(
    equity_cfs: List[float],   # monthly: negative = equity in, positive = distributions
    a: "Assumptions",
) -> WaterfallResult:
    """
    Two-step waterfall:
    1. Return of capital to LP and GP (pro-rata by equity pct)
    2. Preferred return to LP
    3. Promote tiers split residual above pref
    """
    from .dcf import compute_irr
    wf = a.waterfall

    total_in  = sum(-cf for cf in equity_cfs if cf < 0)
    total_out = sum(cf  for cf in equity_cfs if cf > 0)

    gp_equity_pct = wf.gp_equity_pct
    lp_equity_pct = wf.lp_equity_pct

    gp_in = total_in * gp_equity_pct
    lp_in = total_in * lp_equity_pct

    # Preferred return: LP gets pref on unreturned capital, compounding annually
    # Simplified: compute pref as total_in × pref_rate × hold_years
    hold_years = a.timeline.hold_months / 12.0
    lp_pref_amount = lp_in * wf.preferred_return * hold_years

    # Residual after return of capital and pref
    lp_roe_and_pref = lp_in + lp_pref_amount
    gp_roe          = gp_in

    residual = total_out - lp_roe_and_pref - gp_roe
    residual = max(0.0, residual)

    # Promote tiers — split residual
    gp_promote = 0.0
    lp_promote = 0.0
    remaining  = residual

    for tier in wf.tiers:
        if remaining <= 0:
            break
        # Determine how much residual belongs to this tier
        # (simplified: all residual above pref flows through tiers)
        tier_slice  = remaining  # entire remaining goes to final tier
        lp_promote += tier_slice * tier.lp_split
        gp_promote += tier_slice * tier.gp_split
        remaining   = 0.0

    gp_total = gp_roe + gp_promote
    lp_total = lp_roe_and_pref + lp_promote

    # Compute GP and LP IRR from their respective cash flow streams
    # GP cash flows: -gp_in at m=0, pro-rata share of positive cash flows
    gp_cfs = []
    lp_cfs = []
    gp_frac = gp_total / total_out if total_out > 0 else gp_equity_pct
    lp_frac = lp_total / total_out if total_out > 0 else lp_equity_pct

    for cf in equity_cfs:
        if cf < 0:
            gp_cfs.append(cf * gp_equity_pct)
            lp_cfs.append(cf * lp_equity_pct)
        else:
            gp_cfs.append(cf * gp_frac)
            lp_cfs.append(cf * lp_frac)

    gp_irr = compute_irr(gp_cfs) or 0.0
    lp_irr = compute_irr(lp_cfs) or 0.0
    gp_em  = gp_total / gp_in if gp_in > 0 else 0.0
    lp_em  = lp_total / lp_in if lp_in > 0 else 0.0

    return WaterfallResult(
        total_equity_in=total_in,
        total_distributions=total_out,
        gp_equity_in=gp_in,
        lp_equity_in=lp_in,
        gp_distributions=gp_total,
        lp_distributions=lp_total,
        gp_net_irr=gp_irr,
        lp_net_irr=lp_irr,
        gp_em=gp_em,
        lp_em=lp_em,
    )
