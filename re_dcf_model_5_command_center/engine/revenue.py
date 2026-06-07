"""
revenue.py — Dual-cohort per-unit-type lease-up, absorption curves,
concessions, loss-to-lease, and plateau revenue engine.

Outputs a monthly revenue array across the full analysis horizon.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .assumptions import Assumptions, UnitTypeAssumptions, AbsorptionCurve


# ---------------------------------------------------------------------------
# Monthly snapshot for a single unit type
# ---------------------------------------------------------------------------

@dataclass
class UnitTypeMonthly:
    month: int
    unit_type: str
    # Cohort A — unrenovated
    unreno_units: float
    unreno_occupied: float
    unreno_rent: float
    # Cohort B — renovated
    reno_units: float
    reno_occupied: float
    reno_rent: float           # after concessions
    reno_market_rent: float    # before concessions
    concession_rate: float
    # Aggregates
    total_occupied: float
    total_units: float
    occupancy_rate: float
    gpr: float                 # gross potential rent (occupied units × rent)
    other_income: float
    pgi: float                 # gpr + other_income


# ---------------------------------------------------------------------------
# Monthly revenue totals
# ---------------------------------------------------------------------------

@dataclass
class RevenueMonth:
    month: int
    unit_type_detail: List[UnitTypeMonthly]
    gpr: float
    other_income: float
    pgi: float
    vacancy_loss: float
    credit_loss: float
    egi: float
    occupancy_rate: float      # blended across all types
    stabilized: bool           # True once stabilization trigger fires


# ---------------------------------------------------------------------------
# Absorption curve functions
# ---------------------------------------------------------------------------

def _s_curve(t: float) -> float:
    """Smoothstep S-curve. t in [0,1]. Returns occupancy fraction in [0,1]."""
    t = max(0.0, min(1.0, t))
    return 3 * t**2 - 2 * t**3


def _concave(t: float, k: float) -> float:
    """Concave (exponential) absorption. t in [0,∞]. k = speed parameter."""
    t = max(0.0, t)
    return 1.0 - math.exp(-k * t)


def _linear(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t


def absorption_occupancy(
    months_since_available: float,
    absorption_period: int,
    curve_type: "AbsorptionCurve",
    speed_k: float,
    in_place_occ: float,
    stabilized_occ: float,
) -> float:
    """
    Returns occupancy fraction for renovated cohort at `months_since_available`.
    Interpolates from in_place_occ → stabilized_occ using chosen curve.
    """
    from .assumptions import AbsorptionCurve
    if absorption_period <= 0:
        return stabilized_occ

    t_norm = months_since_available / absorption_period  # 0 → 1 over absorption_period

    if curve_type == AbsorptionCurve.S_CURVE:
        frac = _s_curve(t_norm)
    elif curve_type == AbsorptionCurve.CONCAVE:
        # normalize: at t_norm=1 we want ~stabilized_occ
        # use t_norm * absorption_period as raw t input
        frac = _concave(months_since_available, speed_k / absorption_period)
        frac = min(frac, 1.0)
    else:  # LINEAR
        frac = _linear(t_norm)

    return in_place_occ + (stabilized_occ - in_place_occ) * frac


# ---------------------------------------------------------------------------
# Per-unit-type monthly state
# ---------------------------------------------------------------------------

def _compute_unit_type_month(
    ut: "UnitTypeAssumptions",
    m: int,
    reno_complete: bool,
) -> UnitTypeMonthly:
    """
    Compute cohort A (unrenovated) and cohort B (renovated) state for unit type
    at month m.
    """
    from .assumptions import AbsorptionCurve

    total = float(ut.count)

    # --- Renovated unit count (cumulative, capped at total) ---
    if m < ut.reno_start_month:
        reno_units = 0.0
    else:
        months_reno_active = m - ut.reno_start_month + 1
        reno_units = min(ut.reno_pace_units_per_month * months_reno_active, total)
    unreno_units = total - reno_units

    # --- Market rent with growth ---
    annual_growth = ut.rent_growth_by_year.get((m // 12) + 1, ut.default_rent_growth)
    # Apply monthly compounding from month 0
    growth_factor = (1 + annual_growth / 12) ** m
    # Market rent reset override
    base_market = ut.market_rent
    year = (m // 12) + 1
    if ut.market_rent_reset_by_year:
        for reset_year in sorted(ut.market_rent_reset_by_year):
            if year >= reset_year:
                base_market = ut.market_rent_reset_by_year[reset_year]
    market_rent = base_market * growth_factor

    # --- In-place rent with growth (unrenovated cohort) ---
    inplace_growth = ut.rent_growth_by_year.get((m // 12) + 1, ut.default_rent_growth)
    inplace_growth_factor = (1 + inplace_growth / 12) ** m

    # Loss-to-lease: fraction of unrenovated units at market rent
    if ut.lease_term_months > 0:
        at_market_pct = 1.0 - (1.0 - 1.0 / ut.lease_term_months) ** m
    else:
        at_market_pct = 1.0
    at_market_pct = max(0.0, min(1.0, at_market_pct))

    inplace_base = ut.in_place_rent * inplace_growth_factor
    market_unreno = ut.in_place_rent * inplace_growth_factor  # unreno units at in-place product level
    blended_unreno_rent = (
        inplace_base * (1 - at_market_pct) +
        market_unreno * at_market_pct
    )

    # --- Unrenovated occupancy ---
    # Slight displacement as active reno rolls through building
    occ_unreno = ut.in_place_occupancy
    if unreno_units > 0 and reno_units < total:
        # Units awaiting reno face a mild occ haircut
        occ_unreno = ut.in_place_occupancy * (1.0 - ut.reno_displacement_rate)
    unreno_occupied = unreno_units * occ_unreno

    # --- Renovated occupancy (absorption curve) ---
    if reno_units <= 0:
        occ_reno = 0.0
    else:
        months_reno_avail = max(0.0, m - ut.reno_start_month)
        occ_reno = absorption_occupancy(
            months_since_available=months_reno_avail,
            absorption_period=ut.absorption_period_months,
            curve_type=ut.absorption_curve,
            speed_k=ut.absorption_speed_k,
            in_place_occ=ut.in_place_occupancy,
            stabilized_occ=ut.stabilized_occupancy,
        )
    reno_occupied = reno_units * occ_reno

    # --- Concessions on renovated units ---
    if ut.concession_burn_months > 0:
        concession_rate = (
            (ut.concession_weeks / 52.0) *
            max(0.0, 1.0 - months_reno_avail / ut.concession_burn_months)
            if reno_units > 0 else 0.0
        )
    else:
        concession_rate = 0.0
    effective_reno_rent = market_rent * (1.0 - concession_rate)

    # --- GPR ---
    gpr_unreno = unreno_occupied * blended_unreno_rent
    gpr_reno   = reno_occupied   * effective_reno_rent
    gpr        = gpr_unreno + gpr_reno

    # --- Other income (per occupied unit per month) ---
    total_occupied = unreno_occupied + reno_occupied
    other = total_occupied * (
        ut.parking_income + ut.storage_income +
        ut.pet_income + ut.laundry_income + ut.other_income
    )

    pgi = gpr + other
    occ_rate = total_occupied / total if total > 0 else 0.0

    return UnitTypeMonthly(
        month=m,
        unit_type=ut.label,
        unreno_units=unreno_units,
        unreno_occupied=unreno_occupied,
        unreno_rent=blended_unreno_rent,
        reno_units=reno_units,
        reno_occupied=reno_occupied,
        reno_rent=effective_reno_rent,
        reno_market_rent=market_rent,
        concession_rate=concession_rate,
        total_occupied=total_occupied,
        total_units=total,
        occupancy_rate=occ_rate,
        gpr=gpr,
        other_income=other,
        pgi=pgi,
    )


# ---------------------------------------------------------------------------
# Stabilization detection
# ---------------------------------------------------------------------------

def _check_stabilization(
    occupancy_history: List[float],
    threshold: float,
    confirmation_months: int,
    force_month: Optional[int],
    current_month: int,
) -> bool:
    if force_month is not None:
        return current_month >= force_month
    if len(occupancy_history) < confirmation_months:
        return False
    recent = occupancy_history[-confirmation_months:]
    return all(o >= threshold for o in recent)


# ---------------------------------------------------------------------------
# Main revenue engine
# ---------------------------------------------------------------------------

def compute_revenue(a: "Assumptions") -> List[RevenueMonth]:
    """
    Compute monthly revenue from Month 0 through Month (hold_months).
    Returns list of RevenueMonth.
    """
    from .assumptions import AbsorptionCurve

    months = a.timeline.hold_months + 1  # inclusive of month 0
    unit_types = a.property.unit_types
    tl = a.timeline
    credit_loss_rate = a.market.market_vacancy_rate * 0.10  # ~10% of vacancy as credit loss

    occupancy_history: List[float] = []
    stabilized_flag = False
    results: List[RevenueMonth] = []

    for m in range(months):
        reno_complete = (m >= a.renovation.reno_period_months) if a.renovation.include_renovation else True

        # Per-unit-type monthly calculation
        ut_months: List[UnitTypeMonthly] = []
        for ut in unit_types:
            utm = _compute_unit_type_month(ut, m, reno_complete)
            ut_months.append(utm)

        # Totals
        total_units = sum(u.total_units for u in ut_months)
        total_occupied = sum(u.total_occupied for u in ut_months)
        gpr = sum(u.gpr for u in ut_months)
        other = sum(u.other_income for u in ut_months)
        pgi = gpr + other
        blended_occ = total_occupied / total_units if total_units > 0 else 0.0

        # Vacancy: market vacancy rate compresses as occ ramps (already baked
        # into cohort occupancy, so we apply only residual credit loss here)
        # vacancy_loss = PGI × (1 - blended_occ)  — already embedded in GPR
        # We still apply a separate credit loss on collected EGR
        vacancy_loss = pgi * (1.0 - blended_occ)   # structural (in addition to occupancy)
        # Note: occupancy IS the primary vacancy mechanism; this adds a small
        # additional credit/concession haircut on top
        vacancy_loss = 0.0   # occupancy already drives vacancy; set to 0 to avoid double-count

        # Market vacancy drift (post-stabilization)
        year = (m // 12) + 1
        vacancy_drift = a.market.vacancy_drift_by_year.get(year, 0.0)
        credit_loss = pgi * (credit_loss_rate + vacancy_drift)

        egi = pgi - credit_loss

        # Stabilization check
        occupancy_history.append(blended_occ)
        if not stabilized_flag:
            stabilized_flag = _check_stabilization(
                occupancy_history=occupancy_history,
                threshold=tl.stabilized_occ_threshold,
                confirmation_months=tl.stability_confirmation_months,
                force_month=tl.force_stabilization_month,
                current_month=m,
            )

        results.append(RevenueMonth(
            month=m,
            unit_type_detail=ut_months,
            gpr=gpr,
            other_income=other,
            pgi=pgi,
            vacancy_loss=vacancy_loss,
            credit_loss=credit_loss,
            egi=egi,
            occupancy_rate=blended_occ,
            stabilized=stabilized_flag,
        ))

    return results


def get_stabilization_month(revenue: List[RevenueMonth]) -> int:
    """Return the first month where stabilized=True, or last month if never."""
    for r in revenue:
        if r.stabilized:
            return r.month
    return revenue[-1].month
