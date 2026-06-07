"""
capex.py — Renovation draw schedule (S-curve) and ongoing CapEx/reserves.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .assumptions import Assumptions


@dataclass
class CapExMonth:
    month: int
    hard_cost_draw: float
    soft_cost_draw: float
    common_area_draw: float
    total_reno_draw: float        # hard + soft + common area
    equity_reno_draw: float       # portion funded by equity (not const loan)
    const_loan_draw: float        # portion funded by construction loan
    ongoing_capex: float          # reserves post-stabilization
    total: float                  # reno_draw + ongoing_capex


def _s_curve_cumulative(t: float) -> float:
    """Smoothstep: t in [0,1], returns cumulative fraction [0,1]."""
    t = max(0.0, min(1.0, t))
    return 3 * t**2 - 2 * t**3


def compute_capex(
    a: "Assumptions",
    stabilization_month: int,
) -> List[CapExMonth]:
    """
    Compute monthly CapEx across hold_months+1 months.
    stabilization_month: first month where property is stabilized.
    """
    months = a.timeline.hold_months + 1
    reno  = a.renovation
    units = float(a.property.total_units)

    if reno.include_renovation:
        total_hard  = reno.hard_cost_per_unit * units * (1 + reno.contingency_pct)
        total_soft  = total_hard * reno.soft_cost_pct
        total_common = reno.common_area_cost + reno.exterior_cost
        reno_period = max(1, reno.reno_period_months)
    else:
        total_hard = total_soft = total_common = 0.0
        reno_period = 1

    const = a.const_loan
    # LTC applied to total reno cost
    total_reno_cost = total_hard + total_soft + total_common
    max_const_draw  = total_reno_cost * const.max_commitment_pct_of_cost if const.include else 0.0

    results: List[CapExMonth] = []
    prev_cumulative_pct = 0.0

    for m in range(months):
        if not reno.include_renovation or m == 0:
            hard_draw = soft_draw = common_draw = 0.0
        elif m > reno_period:
            hard_draw = soft_draw = common_draw = 0.0
        else:
            t_now  = m / reno_period
            t_prev = (m - 1) / reno_period

            if const.draw_on_s_curve:
                cum_now  = _s_curve_cumulative(t_now)
                cum_prev = _s_curve_cumulative(t_prev)
            else:
                # Custom draw schedule: month → cumulative pct
                cum_now  = const.custom_draw_schedule.get(m,   t_now)
                cum_prev = const.custom_draw_schedule.get(m-1, t_prev)

            increment = max(0.0, cum_now - cum_prev)
            hard_draw   = total_hard   * increment
            soft_draw   = total_soft   * increment
            common_draw = total_common * increment

        reno_draw = hard_draw + soft_draw + common_draw

        # Construction loan funding vs equity funding
        if total_reno_cost > 0:
            loan_frac = min(max_const_draw / total_reno_cost, 1.0) if const.include else 0.0
        else:
            loan_frac = 0.0
        const_draw  = reno_draw * loan_frac
        equity_draw = reno_draw * (1.0 - loan_frac)

        # Ongoing CapEx (reserves) — active post-stabilization
        ongoing = (a.opex.reserves.cost_per_unit_per_year * units / 12.0
                   if m >= stabilization_month else 0.0)
        # Note: reserves are also in opex.py — set one to zero in config to avoid double-count.
        # By default reserves OpEx line = 0 and this module carries them.

        results.append(CapExMonth(
            month=m,
            hard_cost_draw=hard_draw,
            soft_cost_draw=soft_draw,
            common_area_draw=common_draw,
            total_reno_draw=reno_draw,
            equity_reno_draw=equity_draw,
            const_loan_draw=const_draw,
            ongoing_capex=ongoing,
            total=reno_draw + ongoing,
        ))

    return results
