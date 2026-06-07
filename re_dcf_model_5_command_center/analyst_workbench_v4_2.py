"""
RE DCF Workbench v4.2

Purpose:
- Diagnostic underwriting interface, not client-facing UX.
- Exposes assumptions, formulas, source tags, dependency logic, cash-flow streams,
  scenario recipes, and KPI bridges.

Run:
    python3 -m pip install -r requirements_debug.txt
    python3 -m streamlit run debug_workbench_app.py
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime
import random
import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, get_origin, get_args, get_type_hints, Union
import json
import sqlite3

import pandas as pd
import streamlit as st

from tests.fixtures import make_test_deal
from engine.assumptions import AbsorptionCurve
from engine.revenue import compute_revenue, get_stabilization_month
from engine.opex import compute_opex
from engine.capex import compute_capex
from engine.debt import compute_debt
from engine.dcf import build_cash_flows, compute_irr, compute_npv
from engine.waterfall import allocate_waterfall
from engine.kpis import compute_kpis


# =============================================================================
# Formatting helpers
# =============================================================================

def money(x: Any) -> str:
    if x is None:
        return "—"
    try:
        x = float(x)
    except Exception:
        return str(x)
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1_000_000:
        return f"{sign}${x/1_000_000:,.2f}M"
    if x >= 1_000:
        return f"{sign}${x/1_000:,.0f}K"
    return f"{sign}${x:,.0f}"


def pct(x: Any) -> str:
    if x is None:
        return "—"
    try:
        return f"{float(x) * 100:,.2f}%"
    except Exception:
        return str(x)


def xmult(x: Any) -> str:
    if x is None:
        return "—"
    try:
        return f"{float(x):,.2f}x"
    except Exception:
        return str(x)


def safe_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None


def dataclass_rows(objs: List[Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for obj in objs:
        if is_dataclass(obj):
            rows.append(asdict(obj))
        elif isinstance(obj, dict):
            rows.append(obj)
        else:
            rows.append(getattr(obj, "__dict__", {"value": obj}))
    return pd.DataFrame(rows)


def flatten_unit_detail(revenue_months, max_month: int) -> pd.DataFrame:
    rows = []
    for r in revenue_months[: max_month + 1]:
        for d in r.unit_type_detail:
            row = asdict(d)
            row["month"] = r.month
            rows.append(row)
    return pd.DataFrame(rows)


# =============================================================================
# Engine runner
# =============================================================================

def run_all_engines(a):
    rev = compute_revenue(a)
    stab_m = get_stabilization_month(rev)
    egi_series = [r.egi for r in rev]
    opex = compute_opex(a, egi_series)
    noi_series = [o.noi for o in opex]
    capex = compute_capex(a, stabilization_month=stab_m)
    const_draws = [c.const_loan_draw for c in capex]
    debt = compute_debt(a, const_draws, stab_m, noi_series)
    cfs = build_cash_flows(rev, opex, capex, debt, a, stab_m)
    wf = allocate_waterfall([cf.equity_cf for cf in cfs], a)
    kpis = compute_kpis(cfs, debt, opex, rev, a, stab_m, wf)
    return rev, stab_m, opex, capex, debt, cfs, wf, kpis


def run_kpis_only(a):
    try:
        *_, kpis = run_all_engines(a)
        return kpis
    except Exception:
        return None


# =============================================================================
# Assumption editor
# =============================================================================

def build_assumptions_from_ui(workspace: str = "Executive Dashboard", deal_section: Optional[str] = None):
    """Context-aware sidebar editor.

    v4.2 principle: the sidebar is a true contextual live editor.
    Only assumptions relevant to the active workspace or submenu are rendered.
    Hidden fields keep their Streamlit state so the model remains stable.
    """
    a = make_test_deal()

    def visible(group: str) -> bool:
        # Strict contextual editor. No global assumption dump.
        # Each workspace/submenu exposes only the assumptions that directly drive it.
        if workspace == "Engine Lab":
            return True
        if workspace == "Executive Dashboard":
            return group in {"deal", "exit"}
        if workspace == "Cash Flow Timeline":
            return group in {"deal", "revenue", "debt"}
        if workspace == "Scenario Lab":
            return group in {"exit", "revenue", "debt", "renovation"}
        if workspace == "Monte Carlo":
            return group in {"exit", "revenue", "debt", "renovation", "opex"}
        if workspace == "AI Copilot":
            return group in {"deal"}
        if workspace == "Versions / Audit":
            return group in set()
        if workspace == "Deal Workspace":
            section_map = {
                "Acquisition": {"deal"},
                "Revenue": {"revenue"},
                "Operations": {"opex"},
                "Renovation": {"renovation"},
                "Financing": {"debt"},
                "Exit": {"exit"},
            }
            return group in section_map.get(deal_section or "Acquisition", {"deal"})
        return group in set()

    def ninput(key: str, label: str, minv: int, maxv: int, default: int, step: int, show: bool) -> int:
        if show:
            return int(st.sidebar.number_input(label, min_value=minv, max_value=maxv, value=int(st.session_state.get(key, default)), step=step, key=key))
        return int(st.session_state.get(key, default))

    def fslider(key: str, label: str, minv: float, maxv: float, default: float, step: float, show: bool) -> float:
        if show:
            return float(st.sidebar.slider(label, minv, maxv, float(st.session_state.get(key, default)), step, key=key))
        return float(st.session_state.get(key, default))

    def islider(key: str, label: str, minv: int, maxv: int, default: int, step: int, show: bool) -> int:
        if show:
            return int(st.sidebar.slider(label, minv, maxv, int(st.session_state.get(key, default)), step, key=key))
        return int(st.session_state.get(key, default))

    def check(key: str, label: str, default: bool, show: bool) -> bool:
        if show:
            return bool(st.sidebar.checkbox(label, bool(st.session_state.get(key, default)), key=key))
        return bool(st.session_state.get(key, default))

    if visible("deal"):
        st.sidebar.header("Live Editor: Deal")
        st.sidebar.caption(f"Context: {workspace}" + (f" / {deal_section}" if deal_section else ""))
    a.acquisition.purchase_price = ninput("assump_purchase_price", "Purchase price", 1_000_000, 500_000_000, int(a.acquisition.purchase_price), 250_000, visible("deal"))
    a.timeline.hold_months = islider("assump_hold_months", "Hold months", 12, 120, int(a.timeline.hold_months), 6, visible("deal"))
    a.exit.exit_month = a.timeline.hold_months
    a.discount_rate = fslider("assump_discount_rate", "Discount rate", 0.00, 0.25, float(a.discount_rate), 0.005, visible("deal"))

    if visible("revenue"):
        st.sidebar.header("Live Editor: Revenue / Lease-Up")
    rent_growth = fslider("assump_rent_growth", "Default rent growth", 0.00, 0.10, 0.03, 0.0025, visible("revenue"))
    stab_threshold = fslider("assump_stab_threshold", "Stabilization occupancy threshold", 0.70, 0.99, float(a.timeline.stabilized_occ_threshold), 0.01, visible("revenue"))
    a.timeline.stabilized_occ_threshold = stab_threshold
    a.timeline.stability_confirmation_months = islider("assump_stab_confirm", "Stability confirmation months", 1, 6, int(a.timeline.stability_confirmation_months), 1, visible("revenue"))
    curves = [c.value for c in AbsorptionCurve]
    if visible("revenue"):
        selected_curve = st.sidebar.selectbox("Default absorption curve", curves, index=curves.index(st.session_state.get("assump_abs_curve", curves[0])) if st.session_state.get("assump_abs_curve", curves[0]) in curves else 0, key="assump_abs_curve")
    else:
        selected_curve = st.session_state.get("assump_abs_curve", curves[0])
    for ut in a.property.unit_types:
        ut.default_rent_growth = rent_growth
        ut.absorption_curve = AbsorptionCurve(selected_curve)

    if visible("revenue"):
        with st.sidebar.expander("1BR quick edit", expanded=(workspace == "Deal Workspace" and deal_section == "Revenue")):
            one_br = next((u for u in a.property.unit_types if u.label == "1BR"), a.property.unit_types[0])
            one_br.in_place_rent = st.number_input("1BR in-place rent", 500, 5000, int(st.session_state.get("assump_1br_inplace_rent", one_br.in_place_rent)), 25, key="assump_1br_inplace_rent")
            one_br.market_rent = st.number_input("1BR market rent", 500, 6000, int(st.session_state.get("assump_1br_market_rent", one_br.market_rent)), 25, key="assump_1br_market_rent")
            one_br.in_place_occupancy = st.slider("1BR in-place occupancy", 0.50, 1.00, float(st.session_state.get("assump_1br_inplace_occ", one_br.in_place_occupancy)), 0.01, key="assump_1br_inplace_occ")
            one_br.stabilized_occupancy = st.slider("1BR stabilized occupancy", 0.50, 1.00, float(st.session_state.get("assump_1br_stab_occ", one_br.stabilized_occupancy)), 0.01, key="assump_1br_stab_occ")
            one_br.absorption_period_months = st.slider("1BR absorption months", 1, 48, int(st.session_state.get("assump_1br_abs_months", one_br.absorption_period_months)), 1, key="assump_1br_abs_months")
            one_br.concession_weeks = st.slider("1BR concession weeks", 0.0, 12.0, float(st.session_state.get("assump_1br_concession_weeks", float(one_br.concession_weeks))), 0.5, key="assump_1br_concession_weeks")
    else:
        one_br = next((u for u in a.property.unit_types if u.label == "1BR"), a.property.unit_types[0])
        one_br.in_place_rent = st.session_state.get("assump_1br_inplace_rent", one_br.in_place_rent)
        one_br.market_rent = st.session_state.get("assump_1br_market_rent", one_br.market_rent)
        one_br.in_place_occupancy = st.session_state.get("assump_1br_inplace_occ", one_br.in_place_occupancy)
        one_br.stabilized_occupancy = st.session_state.get("assump_1br_stab_occ", one_br.stabilized_occupancy)
        one_br.absorption_period_months = st.session_state.get("assump_1br_abs_months", one_br.absorption_period_months)
        one_br.concession_weeks = st.session_state.get("assump_1br_concession_weeks", one_br.concession_weeks)

    if visible("renovation"):
        st.sidebar.header("Live Editor: Renovation / CapEx")
    a.renovation.include_renovation = check("assump_include_reno", "Include renovation", a.renovation.include_renovation, visible("renovation"))
    a.renovation.hard_cost_per_unit = ninput("assump_hard_cost", "Hard cost / unit", 0, 100_000, int(a.renovation.hard_cost_per_unit), 500, visible("renovation"))
    a.renovation.contingency_pct = fslider("assump_contingency", "Contingency", 0.00, 0.40, float(a.renovation.contingency_pct), 0.01, visible("renovation"))
    a.renovation.reno_period_months = islider("assump_reno_period", "Reno period months", 1, 60, int(a.renovation.reno_period_months), 1, visible("renovation"))
    a.renovation.common_area_cost = ninput("assump_common_area", "Common area cost", 0, 10_000_000, int(a.renovation.common_area_cost), 50_000, visible("renovation"))
    a.renovation.exterior_cost = ninput("assump_exterior", "Exterior cost", 0, 10_000_000, int(a.renovation.exterior_cost), 50_000, visible("renovation"))

    if visible("debt"):
        st.sidebar.header("Live Editor: Debt / Financing")
    a.acq_loan.include = check("assump_acq_include", "Include acquisition loan", a.acq_loan.include, visible("debt"))
    a.acq_loan.ltv_or_ltc = fslider("assump_acq_ltv", "Acq loan LTV", 0.00, 0.90, float(a.acq_loan.ltv_or_ltc), 0.01, visible("debt"))
    a.acq_loan.interest_rate = fslider("assump_acq_rate", "Acq loan rate", 0.00, 0.15, float(a.acq_loan.interest_rate), 0.0025, visible("debt"))
    a.acq_loan.io_period_months = islider("assump_acq_io", "Acq IO months", 0, 60, int(a.acq_loan.io_period_months), 6, visible("debt"))
    a.const_loan.include = check("assump_const_include", "Include construction loan", a.const_loan.include, visible("debt"))
    a.const_loan.max_commitment_pct_of_cost = fslider("assump_const_ltc", "Construction LTC on reno cost", 0.00, 1.00, float(a.const_loan.max_commitment_pct_of_cost), 0.01, visible("debt"))
    a.const_loan.interest_rate = fslider("assump_const_rate", "Construction loan rate", 0.00, 0.18, float(a.const_loan.interest_rate), 0.0025, visible("debt"))
    a.refi.include = check("assump_refi_include", "Include refi", a.refi.include, visible("debt"))
    a.refi.trigger_month = islider("assump_refi_trigger", "Refi trigger month", 1, max(1, a.timeline.hold_months - 1), int(a.refi.trigger_month or 24), 1, visible("debt"))
    a.refi.ltv = fslider("assump_refi_ltv", "Refi LTV", 0.00, 0.85, float(a.refi.ltv), 0.01, visible("debt"))
    a.refi.interest_rate = fslider("assump_refi_rate", "Refi rate", 0.00, 0.15, float(a.refi.interest_rate), 0.0025, visible("debt"))

    if visible("exit"):
        st.sidebar.header("Live Editor: Exit / Market")
    a.exit.exit_cap_rate = fslider("assump_exit_cap", "Exit cap rate", 0.02, 0.12, float(a.exit.exit_cap_rate), 0.00125, visible("exit"))
    a.exit.selling_cost_pct = fslider("assump_selling_cost", "Selling cost", 0.00, 0.08, float(a.exit.selling_cost_pct), 0.0025, visible("exit"))
    a.market.market_cap_rate_going_in = fslider("assump_market_cap", "Market cap for refi sizing", 0.02, 0.12, float(a.market.market_cap_rate_going_in), 0.00125, visible("exit"))

    if visible("opex"):
        st.sidebar.header("Live Editor: Operations / OpEx")
    a.opex.repairs_maintenance.cost_per_unit_per_year = ninput("assump_rm", "R&M / unit / year", 0, 5000, int(a.opex.repairs_maintenance.cost_per_unit_per_year), 25, visible("opex"))
    a.opex.payroll.cost_per_unit_per_year = ninput("assump_payroll", "Payroll / unit / year", 0, 8000, int(a.opex.payroll.cost_per_unit_per_year), 25, visible("opex"))
    a.opex.property_tax.cost_per_unit_per_year = ninput("assump_tax", "Tax / unit / year", 0, 10000, int(a.opex.property_tax.cost_per_unit_per_year), 25, visible("opex"))
    a.opex.management_fee.pct_of_egi = fslider("assump_mgmt_fee", "Management fee % EGI", 0.00, 0.10, float(a.opex.management_fee.pct_of_egi), 0.0025, visible("opex"))
    a.opex.reserves.cost_per_unit_per_year = ninput("assump_reserves", "Reserves / unit / year", 0, 2000, int(a.opex.reserves.cost_per_unit_per_year), 25, visible("opex"))

    if not any(visible(g) for g in ["deal", "revenue", "renovation", "debt", "exit", "opex"]):
        st.sidebar.info("No live assumption fields for this workspace. Use Deal Workspace, Cash Flow Timeline, Scenario Lab, or Monte Carlo to edit drivers.")

    return a


# =============================================================================
# Formula / source intelligence
# =============================================================================

def kpi_values(kpis) -> Dict[str, Any]:
    return {
        "Levered IRR": kpis.levered_irr,
        "Unlevered IRR": kpis.unlevered_irr,
        "Equity Multiple": kpis.equity_multiple,
        "NPV": kpis.npv,
        "Yield on Cost": kpis.yield_on_cost,
        "Development Spread": kpis.development_spread_bps,
        "DSCR Stabilized": kpis.dscr_stabilized,
        "Stabilization Month": kpis.stabilization_month,
    }


def formula_dictionary(a, cashflows, debt, opex, kpis) -> Dict[str, Dict[str, Any]]:
    exit_m = a.exit.exit_month
    exit_cf = cashflows[exit_m]
    exit_noi = exit_cf.noi * 12
    gross_exit_value = exit_noi / a.exit.exit_cap_rate if a.exit.exit_cap_rate > 0 else 0.0
    levered_cfs = [cf.equity_cf for cf in cashflows]
    unlevered_cfs = [cf.unlevered_cf for cf in cashflows]

    total_in = sum(-c for c in levered_cfs if c < 0)
    total_out = sum(c for c in levered_cfs if c > 0)

    return {
        "Levered IRR": {
            "definition": "Annualized internal rate of return on the equity cash-flow stream.",
            "formula": "IRR([equity_cf_month_0 ... equity_cf_exit]) annualized as (1 + monthly_irr)^12 - 1",
            "source": "engine.kpis.compute_kpis → engine.dcf.compute_irr(equity_cfs)",
            "inputs": ["equity_cf", "NOI", "debt_service", "refi_proceeds", "sale_proceeds", "equity-funded capex", "initial equity"],
            "current": pct(kpis.levered_irr),
            "bridge": [
                {"Component": "Initial equity outflow", "Value": money(cashflows[0].equity_cf)},
                {"Component": "Total positive equity CF", "Value": money(total_out)},
                {"Component": "Total negative equity CF", "Value": money(-total_in)},
                {"Component": "Exit month equity CF", "Value": money(exit_cf.equity_cf)},
            ],
            "cashflows": levered_cfs,
        },
        "Unlevered IRR": {
            "definition": "Property-level IRR before debt. Includes acquisition, property NOI, total renovation draws, ongoing reserves, and unlevered terminal sale proceeds.",
            "formula": "IRR(NOI - total_reno_draw - ongoing_capex + unlevered_sale_proceeds - acquisition_outflow at month 0)",
            "source": "engine.dcf.build_cash_flows → CashFlowMonth.unlevered_cf → compute_irr",
            "inputs": ["purchase price", "closing costs", "NOI", "total renovation draw", "ongoing capex", "gross exit value", "selling cost", "disposition fee"],
            "current": pct(kpis.unlevered_irr),
            "bridge": [
                {"Component": "Month 0 unlevered CF", "Value": money(cashflows[0].unlevered_cf)},
                {"Component": "Exit month unlevered CF", "Value": money(exit_cf.unlevered_cf)},
                {"Component": "Total positive unlevered CF", "Value": money(sum(x for x in unlevered_cfs if x > 0))},
                {"Component": "Total negative unlevered CF", "Value": money(sum(x for x in unlevered_cfs if x < 0))},
            ],
            "cashflows": unlevered_cfs,
        },
        "Exit Value": {
            "definition": "Terminal property value before debt payoff, based on exit NOI and exit cap rate.",
            "formula": "Exit Value = Exit Month NOI × 12 / Exit Cap Rate",
            "source": "engine.dcf.build_cash_flows and engine.kpis.compute_kpis",
            "inputs": ["exit month NOI", "exit cap rate"],
            "current": money(gross_exit_value),
            "bridge": [
                {"Component": "Exit monthly NOI", "Value": money(exit_cf.noi)},
                {"Component": "Exit annualized NOI", "Value": money(exit_noi)},
                {"Component": "Exit cap rate", "Value": pct(a.exit.exit_cap_rate)},
                {"Component": "Gross exit value", "Value": money(gross_exit_value)},
                {"Component": "Levered net sale proceeds", "Value": money(exit_cf.sale_proceeds)},
            ],
            "cashflows": [],
        },
        "Refi Proceeds": {
            "definition": "Net cash proceeds from refinance after paying off acquisition/construction debt and refi costs.",
            "formula": "Refi Loan = Stabilized Value × Refi LTV; Net Proceeds = Refi Loan - Payoffs - Costs, floored at zero",
            "source": "engine.debt.compute_debt",
            "inputs": ["NOI at refi", "market cap rate", "refi LTV", "acquisition payoff", "construction payoff", "refi costs"],
            "current": money(sum(cf.refi_proceeds for cf in cashflows)),
            "bridge": [
                {"Component": "Total refi proceeds", "Value": money(sum(cf.refi_proceeds for cf in cashflows))},
                {"Component": "Refi LTV", "Value": pct(a.refi.ltv)},
                {"Component": "Market cap for sizing", "Value": pct(a.market.market_cap_rate_going_in)},
            ],
            "cashflows": [cf.refi_proceeds for cf in cashflows],
        },
        "DSCR Stabilized": {
            "definition": "Annualized NOI at stabilization divided by annualized debt service at stabilization.",
            "formula": "DSCR = Stabilized NOI × 12 / Stabilized Debt Service × 12",
            "source": "engine.kpis.compute_kpis",
            "inputs": ["stabilization month", "NOI", "total debt service"],
            "current": xmult(kpis.dscr_stabilized),
            "bridge": [
                {"Component": "Stabilization month", "Value": str(kpis.stabilization_month)},
                {"Component": "Monthly NOI at stabilization", "Value": money(opex[kpis.stabilization_month].noi)},
                {"Component": "Monthly debt service at stabilization", "Value": money(debt[kpis.stabilization_month].total_debt_service)},
                {"Component": "DSCR", "Value": xmult(kpis.dscr_stabilized)},
            ],
            "cashflows": [],
        },
    }



def cashflow_trace_table(cashflows, capex, debt, a) -> pd.DataFrame:
    """Month-level bridge that makes the DCF math inspectable."""
    rows = []
    pp = a.acquisition.purchase_price
    acq_costs = a.acquisition.total_closing_costs
    acq_loan_amt = pp * a.acq_loan.ltv_or_ltc if a.acq_loan.include else 0.0
    gp_fee = pp * a.waterfall.gp_acquisition_fee_pct
    exit_m = a.exit.exit_month

    for i, cf in enumerate(cashflows):
        cx = capex[i]
        dm = debt[i]
        initial_equity = (pp - acq_loan_amt) + acq_costs + gp_fee if cf.month == 0 else 0.0
        gp_mgmt_fee = cf.egi * a.waterfall.gp_asset_mgmt_fee_pct / 12.0
        total_reno_draw = getattr(cx, "total_reno_draw", 0.0)
        ongoing = getattr(cx, "ongoing_capex", 0.0)
        unlevered_sale = 0.0
        exit_value = 0.0
        gross_after_selling = 0.0
        disposition_fee = 0.0
        payoff = getattr(dm, "payoff_amount", 0.0)
        if cf.month == exit_m:
            exit_value = (cf.noi * 12.0) / a.exit.exit_cap_rate if a.exit.exit_cap_rate > 0 else 0.0
            gross_after_selling = exit_value * (1 - a.exit.selling_cost_pct)
            disposition_fee = exit_value * a.waterfall.gp_disposition_fee_pct
            unlevered_sale = gross_after_selling - disposition_fee
        rows.append({
            "month": cf.month,
            "EGI": cf.egi,
            "NOI": cf.noi,
            "Debt Service": cf.debt_service,
            "Ongoing CapEx": ongoing,
            "NCFBT = NOI - DS - Ongoing": cf.ncfbt,
            "Refi Proceeds": cf.refi_proceeds,
            "Exit Value": exit_value,
            "Gross After Selling Cost": gross_after_selling,
            "Loan Payoff": payoff,
            "Disposition Fee": disposition_fee,
            "Levered Sale Proceeds": cf.sale_proceeds,
            "GP Mgmt Fee": gp_mgmt_fee,
            "Equity Reno Draw": getattr(cx, "equity_reno_draw", 0.0),
            "Initial Equity Outflow": initial_equity,
            "Equity CF": cf.equity_cf,
            "Total Reno Draw": total_reno_draw,
            "Unlevered Sale Proceeds": unlevered_sale,
            "Unlevered CF": cf.unlevered_cf,
        })
    return pd.DataFrame(rows)


def build_formula_trace(a, revenue, opex, capex, debt, cashflows, kpis) -> Dict[str, Dict[str, Any]]:
    """Live trace layer. It does not change model math; it explains the math already produced."""
    trace_df = cashflow_trace_table(cashflows, capex, debt, a)
    exit_m = a.exit.exit_month
    stab_m = kpis.stabilization_month
    levered_cfs = [cf.equity_cf for cf in cashflows]
    unlevered_cfs = [cf.unlevered_cf for cf in cashflows]
    exit_row = trace_df.loc[trace_df["month"] == exit_m].iloc[0]
    stab_row = trace_df.loc[trace_df["month"] == stab_m].iloc[0]
    total_project_cost = (
        a.acquisition.purchase_price
        + a.acquisition.total_closing_costs
        + sum(getattr(c, "total_reno_draw", 0.0) for c in capex)
    )

    def bridge_rows(items):
        return pd.DataFrame([{"Component": k, "Value": v, "Formula Role": r} for k, v, r in items])

    return {
        "Levered IRR": {
            "value": pct(kpis.levered_irr),
            "source_function": "engine.kpis.compute_kpis → engine.dcf.compute_irr",
            "source_file": "engine/kpis.py lines around compute_kpis; engine/dcf.py compute_irr",
            "formula": "Levered IRR = annualized IRR(equity_cf[0:exit_month])",
            "dependencies": ["Equity CF", "NCFBT", "NOI", "Debt Service", "Refi Proceeds", "Levered Sale Proceeds", "Equity Reno Draw", "Initial Equity"],
            "bridge": bridge_rows([
                ("Month 0 Equity CF", money(levered_cfs[0]), "Initial equity outflow net of acquisition debt"),
                ("Total Positive Equity CF", money(sum(x for x in levered_cfs if x > 0)), "Cash returned before and at exit"),
                ("Total Negative Equity CF", money(sum(x for x in levered_cfs if x < 0)), "Equity invested and interim deficits"),
                ("Exit Month Equity CF", money(levered_cfs[exit_m]), "Terminal equity distribution"),
                ("Refi Proceeds", money(sum(cf.refi_proceeds for cf in cashflows)), "Mid-hold liquidity event"),
                ("Levered Sale Proceeds", money(exit_row["Levered Sale Proceeds"]), "Sale after debt payoff and fees"),
            ]),
            "month_detail": trace_df[["month", "NOI", "Debt Service", "NCFBT = NOI - DS - Ongoing", "Refi Proceeds", "Levered Sale Proceeds", "GP Mgmt Fee", "Equity Reno Draw", "Initial Equity Outflow", "Equity CF"]],
            "warnings": ["Multiple sign changes can create multiple IRR roots. Review the cash-flow stream if results look unintuitive."],
        },
        "Unlevered IRR": {
            "value": pct(kpis.unlevered_irr),
            "source_function": "engine.dcf.build_cash_flows → CashFlowMonth.unlevered_cf → engine.dcf.compute_irr",
            "source_file": "engine/dcf.py build_cash_flows and compute_irr",
            "formula": "Unlevered IRR = annualized IRR(NOI - total_reno_draw - ongoing_capex + unlevered_sale_proceeds - acquisition_outflow at m0)",
            "dependencies": ["Purchase Price", "Closing Costs", "NOI", "Total Reno Draw", "Ongoing CapEx", "Unlevered Sale Proceeds"],
            "bridge": bridge_rows([
                ("Month 0 Unlevered CF", money(unlevered_cfs[0]), "Purchase price + closing costs offset by month 0 NOI"),
                ("Total Positive Unlevered CF", money(sum(x for x in unlevered_cfs if x > 0)), "Operating cash flow and terminal property sale"),
                ("Total Negative Unlevered CF", money(sum(x for x in unlevered_cfs if x < 0)), "Acquisition and renovation draw periods"),
                ("Exit Month Unlevered CF", money(unlevered_cfs[exit_m]), "NOI plus unlevered sale proceeds"),
                ("Unlevered Sale Proceeds", money(exit_row["Unlevered Sale Proceeds"]), "Gross after selling cost less disposition fee, no debt payoff"),
            ]),
            "month_detail": trace_df[["month", "NOI", "Total Reno Draw", "Ongoing CapEx", "Unlevered Sale Proceeds", "Unlevered CF"]],
            "warnings": ["This metric must include terminal sale proceeds. Earlier build was fixed after this trace exposed the missing exit value."],
        },
        "Equity CF": {
            "value": money(sum(levered_cfs)),
            "source_function": "engine.dcf.build_cash_flows",
            "source_file": "engine/dcf.py CashFlowMonth.equity_cf",
            "formula": "Equity CF = NCFBT + refi proceeds + sale proceeds - GP mgmt fee - equity reno draw - initial equity outflow",
            "dependencies": ["NOI", "Debt Service", "Ongoing CapEx", "Refi Proceeds", "Sale Proceeds", "GP Fees", "Reno Equity", "Initial Equity"],
            "bridge": bridge_rows([
                ("NCFBT Total", money(sum(cf.ncfbt for cf in cashflows)), "NOI less debt service and ongoing capex"),
                ("Refi Proceeds", money(sum(cf.refi_proceeds for cf in cashflows)), "Refi cash inflow"),
                ("Levered Sale Proceeds", money(exit_row["Levered Sale Proceeds"]), "Terminal sale net of loan payoff"),
                ("Equity CF Net", money(sum(levered_cfs)), "Net sum of equity stream"),
            ]),
            "month_detail": trace_df[["month", "NCFBT = NOI - DS - Ongoing", "Refi Proceeds", "Levered Sale Proceeds", "GP Mgmt Fee", "Equity Reno Draw", "Initial Equity Outflow", "Equity CF"]],
            "warnings": [],
        },
        "NOI": {
            "value": money(stab_row["NOI"]),
            "source_function": "engine.opex.compute_opex",
            "source_file": "engine/opex.py compute_opex",
            "formula": "NOI = EGI - total operating expenses",
            "dependencies": ["Revenue", "Vacancy", "Credit Loss", "OpEx Lines", "Management Fee"],
            "bridge": bridge_rows([
                ("Stabilized EGI", money(stab_row["EGI"]), "Effective gross income at stabilization"),
                ("Stabilized NOI", money(stab_row["NOI"]), "Output after OpEx"),
                ("Annualized Stabilized NOI", money(stab_row["NOI"] * 12), "Used in cap rates and DSCR"),
            ]),
            "month_detail": pd.DataFrame([asdict(o) for o in opex]),
            "warnings": [],
        },
        "Exit Value": {
            "value": money(exit_row["Exit Value"]),
            "source_function": "engine.dcf.build_cash_flows; engine.kpis.compute_kpis",
            "source_file": "engine/dcf.py exit / sale proceeds block",
            "formula": "Exit Value = Exit Month NOI × 12 / Exit Cap Rate",
            "dependencies": ["Exit Month NOI", "Exit Cap Rate"],
            "bridge": bridge_rows([
                ("Exit Monthly NOI", money(exit_row["NOI"]), "Source NOI in exit month"),
                ("Exit Annual NOI", money(exit_row["NOI"] * 12), "Annualized terminal NOI"),
                ("Exit Cap Rate", pct(a.exit.exit_cap_rate), "Terminal valuation denominator"),
                ("Exit Value", money(exit_row["Exit Value"]), "Gross property value before costs"),
                ("Gross After Selling Cost", money(exit_row["Gross After Selling Cost"]), "Exit value less broker/selling costs"),
            ]),
            "month_detail": trace_df.loc[trace_df["month"].isin([max(0, exit_m-2), max(0, exit_m-1), exit_m]), ["month", "NOI", "Exit Value", "Gross After Selling Cost", "Loan Payoff", "Disposition Fee", "Levered Sale Proceeds"]],
            "warnings": ["Exit cap is typically one of the highest-impact assumptions."],
        },
        "Refi Proceeds": {
            "value": money(sum(cf.refi_proceeds for cf in cashflows)),
            "source_function": "engine.debt.compute_debt",
            "source_file": "engine/debt.py compute_debt",
            "formula": "Net Refi Proceeds = Refi Loan Amount - acquisition payoff - construction payoff - refi costs, floored at zero",
            "dependencies": ["Refi Month NOI", "Market Cap Rate", "Refi LTV", "Debt Payoffs", "Refi Costs"],
            "bridge": bridge_rows([
                ("Total Refi Proceeds", money(sum(cf.refi_proceeds for cf in cashflows)), "Cash released to equity at refi"),
                ("Refi LTV", pct(a.refi.ltv), "Debt sizing assumption"),
                ("Market Cap Rate", pct(a.market.market_cap_rate_going_in), "Valuation denominator for refi sizing"),
            ]),
            "month_detail": trace_df[["month", "NOI", "Debt Service", "Refi Proceeds", "Equity CF"]],
            "warnings": ["If refi proceeds are zero, check whether payoff amounts exceed available refi sizing."],
        },
        "DSCR Stabilized": {
            "value": xmult(kpis.dscr_stabilized),
            "source_function": "engine.kpis.compute_kpis",
            "source_file": "engine/kpis.py DSCR at stabilization block",
            "formula": "DSCR = stabilized NOI × 12 / stabilized debt service × 12",
            "dependencies": ["Stabilization Month", "NOI", "Debt Service"],
            "bridge": bridge_rows([
                ("Stabilization Month", str(stab_m), "First sustained occupancy threshold month"),
                ("Monthly NOI", money(stab_row["NOI"]), "Stabilized NOI"),
                ("Monthly Debt Service", money(stab_row["Debt Service"]), "Debt service at stabilization"),
                ("DSCR", xmult(kpis.dscr_stabilized), "NOI / debt service"),
            ]),
            "month_detail": trace_df[["month", "NOI", "Debt Service", "Equity CF"]],
            "warnings": [],
        },
        "Yield on Cost": {
            "value": pct(kpis.yield_on_cost),
            "source_function": "engine.kpis.compute_kpis",
            "source_file": "engine/kpis.py yield on cost block",
            "formula": "Yield on Cost = Stabilized Annual NOI / Total Project Cost",
            "dependencies": ["Stabilized NOI", "Purchase Price", "Closing Costs", "Renovation Costs"],
            "bridge": bridge_rows([
                ("Stabilized Annual NOI", money(stab_row["NOI"] * 12), "Numerator"),
                ("Total Project Cost", money(total_project_cost), "Denominator"),
                ("Yield on Cost", pct(kpis.yield_on_cost), "Output"),
            ]),
            "month_detail": trace_df[["month", "NOI", "Total Reno Draw", "Unlevered CF"]],
            "warnings": [],
        },
    }


def assumption_intelligence(a, base_kpis) -> pd.DataFrame:
    base_irr = safe_float(base_kpis.levered_irr) or 0.0
    rows = []

    def test_change(label: str, source: str, confidence: str, path: str, current: str, change_text: str, changer: Callable[[Any], None]):
        b = deepcopy(a)
        changer(b)
        k = run_kpis_only(b)
        new_irr = safe_float(k.levered_irr) if k else None
        delta = None if new_irr is None else new_irr - base_irr
        impact = "Unknown"
        if delta is not None:
            ad = abs(delta)
            if ad >= 0.015:
                impact = "Very High"
            elif ad >= 0.0075:
                impact = "High"
            elif ad >= 0.0025:
                impact = "Medium"
            else:
                impact = "Low"
        rows.append({
            "Assumption": label,
            "Current": current,
            "Source": source,
            "Confidence": confidence,
            "Tested Shock": change_text,
            "Levered IRR Impact": "—" if delta is None else f"{delta*100:+.2f} pts",
            "Impact Class": impact,
            "Model Path": path,
        })

    test_change(
        "Exit Cap Rate", "Manual / Market Comp", "Medium", "a.exit.exit_cap_rate", pct(a.exit.exit_cap_rate), "+25 bps",
        lambda b: setattr(b.exit, "exit_cap_rate", b.exit.exit_cap_rate + 0.0025),
    )
    test_change(
        "Rent Growth", "Manual / Market Rent Assumption", "Medium", "unit_type.default_rent_growth", pct(a.property.unit_types[0].default_rent_growth), "+50 bps",
        lambda b: [setattr(u, "default_rent_growth", u.default_rent_growth + 0.005) for u in b.property.unit_types],
    )
    test_change(
        "Hard Cost / Unit", "Manual / Renovation Budget", "Medium", "a.renovation.hard_cost_per_unit", money(a.renovation.hard_cost_per_unit), "+10%",
        lambda b: setattr(b.renovation, "hard_cost_per_unit", b.renovation.hard_cost_per_unit * 1.10),
    )
    test_change(
        "Refi Rate", "Manual / Debt Quote", "Medium", "a.refi.interest_rate", pct(a.refi.interest_rate), "+100 bps",
        lambda b: setattr(b.refi, "interest_rate", b.refi.interest_rate + 0.01),
    )
    test_change(
        "Refi LTV", "Manual / Debt Quote", "Low-Medium", "a.refi.ltv", pct(a.refi.ltv), "-5 pts",
        lambda b: setattr(b.refi, "ltv", max(0.0, b.refi.ltv - 0.05)),
    )
    return pd.DataFrame(rows)


def apply_scenario(a, recipe: str):
    b = deepcopy(a)
    if recipe == "Base":
        return b
    if recipe == "Exit Cap Expansion":
        b.exit.exit_cap_rate += 0.005
    elif recipe == "Cost Overrun":
        b.renovation.hard_cost_per_unit *= 1.15
        b.renovation.contingency_pct += 0.05
        b.renovation.reno_period_months += 3
    elif recipe == "Lease-Up Delay":
        for u in b.property.unit_types:
            u.absorption_period_months += 6
            u.concession_weeks += 2
    elif recipe == "Refi Failure":
        b.refi.include = False
    elif recipe == "Rate Shock":
        b.acq_loan.interest_rate += 0.01
        b.const_loan.interest_rate += 0.01
        b.refi.interest_rate += 0.01
    elif recipe == "Rent Recession":
        for u in b.property.unit_types:
            u.default_rent_growth = max(0.0, u.default_rent_growth - 0.015)
            u.stabilized_occupancy = max(0.80, u.stabilized_occupancy - 0.03)
    return b


# =============================================================================
# Local persistence: SQLite scenario results, deal versions, assumption metadata, audit log
# =============================================================================

DB_PATH = Path("workbench_local.db")


def json_default(obj):
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "value"):
        return obj.value
    try:
        return str(obj)
    except Exception:
        return None


def to_json(obj: Any) -> str:
    return json.dumps(obj, default=json_default, indent=2, sort_keys=True)


def dataclass_from_dict(cls, data):
    """Rehydrate nested dataclasses from JSON saved by asdict()."""
    from dataclasses import fields, is_dataclass
    from enum import Enum

    if data is None:
        return None

    origin = get_origin(cls)
    args = get_args(cls)

    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        return dataclass_from_dict(non_none[0], data) if non_none else data

    if origin in (list, List):
        item_type = args[0] if args else Any
        return [dataclass_from_dict(item_type, item) for item in data]

    if origin in (dict, Dict):
        return data

    try:
        if isinstance(cls, type) and issubclass(cls, Enum):
            return cls(data)
    except Exception:
        pass

    if is_dataclass(cls):
        hints = get_type_hints(cls)
        kwargs = {}
        for f in fields(cls):
            if isinstance(data, dict) and f.name in data:
                kwargs[f.name] = dataclass_from_dict(hints.get(f.name, f.type), data[f.name])
        return cls(**kwargs)

    return data


def assumptions_from_json(raw_json: str):
    from engine.assumptions import Assumptions
    return dataclass_from_dict(Assumptions, json.loads(raw_json))


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def db_conn():
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with db_conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS assumption_metadata (
                field_key TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence TEXT NOT NULL,
                note TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS scenario_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                deal_name TEXT NOT NULL,
                scenario_name TEXT NOT NULL,
                levered_irr REAL,
                unlevered_irr REAL,
                npv REAL,
                equity_multiple REAL,
                irr_delta REAL,
                assumptions_json TEXT NOT NULL,
                kpis_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS deal_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deal_name TEXT NOT NULL,
                version_label TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                kpis_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        con.commit()
    seed_assumption_metadata()


def append_audit(event_type: str, detail: str) -> None:
    with db_conn() as con:
        con.execute(
            "INSERT INTO audit_log(event_type, detail, created_at) VALUES (?, ?, ?)",
            (event_type, detail, now_iso()),
        )
        con.commit()


def default_assumption_metadata_rows() -> List[Dict[str, str]]:
    return [
        {"field_key": "acquisition.purchase_price", "display_name": "Purchase Price", "source": "Manual", "confidence": "Medium", "note": "Initial acquisition price assumption."},
        {"field_key": "timeline.hold_months", "display_name": "Hold Period", "source": "Manual", "confidence": "Medium", "note": "Investment hold period in months."},
        {"field_key": "exit.exit_cap_rate", "display_name": "Exit Cap Rate", "source": "Manual / Market Comp", "confidence": "Medium", "note": "High-impact terminal valuation assumption."},
        {"field_key": "market.market_cap_rate_going_in", "display_name": "Market Cap for Refi", "source": "Manual / Debt Sizing", "confidence": "Medium", "note": "Used to size stabilized/refi value."},
        {"field_key": "unit_type.default_rent_growth", "display_name": "Rent Growth", "source": "Manual / Market Assumption", "confidence": "Medium", "note": "Applied to unit types."},
        {"field_key": "timeline.stabilized_occ_threshold", "display_name": "Stabilization Occupancy", "source": "Manual", "confidence": "Medium", "note": "Used by stabilization detector."},
        {"field_key": "renovation.hard_cost_per_unit", "display_name": "Hard Cost / Unit", "source": "Manual / Budget", "confidence": "Medium", "note": "Reno budget driver."},
        {"field_key": "renovation.contingency_pct", "display_name": "Contingency", "source": "Manual / Budget", "confidence": "Medium", "note": "CapEx cushion."},
        {"field_key": "acq_loan.ltv_or_ltc", "display_name": "Acq Loan LTV", "source": "Manual / Debt Quote", "confidence": "Medium", "note": "Purchase debt sizing."},
        {"field_key": "acq_loan.interest_rate", "display_name": "Acq Loan Rate", "source": "Manual / Debt Quote", "confidence": "Medium", "note": "Debt-service driver."},
        {"field_key": "refi.ltv", "display_name": "Refi LTV", "source": "Manual / Debt Quote", "confidence": "Low-Medium", "note": "Refi proceeds driver."},
        {"field_key": "refi.interest_rate", "display_name": "Refi Rate", "source": "Manual / Debt Quote", "confidence": "Medium", "note": "Post-refi debt-service driver."},
        {"field_key": "opex.property_tax.cost_per_unit_per_year", "display_name": "Property Tax", "source": "Manual / Tax Data", "confidence": "Medium", "note": "Large OpEx line."},
        {"field_key": "opex.management_fee.pct_of_egi", "display_name": "Management Fee", "source": "Manual / Property Mgmt", "confidence": "High", "note": "Usually contract-based."},
    ]


def seed_assumption_metadata() -> None:
    with db_conn() as con:
        for row in default_assumption_metadata_rows():
            con.execute(
                """
                INSERT OR IGNORE INTO assumption_metadata(field_key, display_name, source, confidence, note, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (row["field_key"], row["display_name"], row["source"], row["confidence"], row["note"], now_iso()),
            )
        con.commit()


def load_assumption_metadata() -> pd.DataFrame:
    with db_conn() as con:
        df = pd.read_sql_query(
            "SELECT field_key, display_name, source, confidence, note, updated_at FROM assumption_metadata ORDER BY display_name",
            con,
        )
    return df


def save_assumption_metadata(df: pd.DataFrame) -> None:
    with db_conn() as con:
        for _, row in df.iterrows():
            con.execute(
                """
                INSERT INTO assumption_metadata(field_key, display_name, source, confidence, note, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(field_key) DO UPDATE SET
                    display_name=excluded.display_name,
                    source=excluded.source,
                    confidence=excluded.confidence,
                    note=excluded.note,
                    updated_at=excluded.updated_at
                """,
                (
                    str(row.get("field_key", "")),
                    str(row.get("display_name", "")),
                    str(row.get("source", "Manual")),
                    str(row.get("confidence", "Medium")),
                    str(row.get("note", "")),
                    now_iso(),
                ),
            )
        con.commit()
    append_audit("assumption_metadata_saved", f"Saved {len(df)} assumption metadata rows")


def save_deal_version(deal_name: str, version_label: str, assumptions: Any, kpis: Any) -> None:
    with db_conn() as con:
        con.execute(
            """
            INSERT INTO deal_versions(deal_name, version_label, assumptions_json, kpis_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (deal_name, version_label, to_json(assumptions), to_json(kpis), now_iso()),
        )
        con.commit()
    append_audit("deal_version_saved", f"Saved {deal_name} / {version_label}")


def load_deal_versions(limit: int = 20) -> pd.DataFrame:
    with db_conn() as con:
        return pd.read_sql_query(
            "SELECT id, deal_name, version_label, created_at FROM deal_versions ORDER BY id DESC LIMIT ?",
            con,
            params=(limit,),
        )


def save_scenario_results(deal_name: str, base_kpis: Any, scenario_rows: List[Dict[str, Any]], scenario_payloads: List[Tuple[str, Any, Any]]) -> str:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_irr = base_kpis.levered_irr if base_kpis and base_kpis.levered_irr is not None else None
    with db_conn() as con:
        for scenario_name, scenario_assumptions, scenario_kpis in scenario_payloads:
            irr_delta = None
            if base_irr is not None and scenario_kpis and scenario_kpis.levered_irr is not None:
                irr_delta = scenario_kpis.levered_irr - base_irr
            con.execute(
                """
                INSERT INTO scenario_results(
                    run_id, deal_name, scenario_name, levered_irr, unlevered_irr, npv,
                    equity_multiple, irr_delta, assumptions_json, kpis_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    deal_name,
                    scenario_name,
                    None if scenario_kpis is None else scenario_kpis.levered_irr,
                    None if scenario_kpis is None else scenario_kpis.unlevered_irr,
                    None if scenario_kpis is None else scenario_kpis.npv,
                    None if scenario_kpis is None else scenario_kpis.equity_multiple,
                    irr_delta,
                    to_json(scenario_assumptions),
                    to_json(scenario_kpis),
                    now_iso(),
                ),
            )
        con.commit()
    append_audit("scenario_results_saved", f"Saved scenario run {run_id} for {deal_name}")
    return run_id


def load_scenario_results(limit: int = 50) -> pd.DataFrame:
    with db_conn() as con:
        return pd.read_sql_query(
            """
            SELECT id, run_id, deal_name, scenario_name, levered_irr, unlevered_irr, npv,
                   equity_multiple, irr_delta, created_at
            FROM scenario_results
            ORDER BY id DESC
            LIMIT ?
            """,
            con,
            params=(limit,),
        )


def load_scenario_detail(scenario_id: int) -> Optional[Dict[str, Any]]:
    with db_conn() as con:
        cur = con.execute(
            """
            SELECT id, run_id, deal_name, scenario_name, assumptions_json, kpis_json, created_at
            FROM scenario_results
            WHERE id = ?
            """,
            (int(scenario_id),),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "run_id": row[1], "deal_name": row[2], "scenario_name": row[3],
        "assumptions_json": row[4], "kpis_json": row[5], "created_at": row[6],
    }


def delete_scenario_result(scenario_id: int) -> None:
    detail = load_scenario_detail(scenario_id)
    with db_conn() as con:
        con.execute("DELETE FROM scenario_results WHERE id = ?", (int(scenario_id),))
        con.commit()
    label = detail["scenario_name"] if detail else str(scenario_id)
    append_audit("scenario_deleted", f"Deleted saved scenario {label} / id={scenario_id}")


def load_scenario_ids(ids: List[int]) -> pd.DataFrame:
    if not ids:
        return pd.DataFrame()
    placeholders = ",".join("?" for _ in ids)
    with db_conn() as con:
        return pd.read_sql_query(
            f"""
            SELECT id, run_id, deal_name, scenario_name, levered_irr, unlevered_irr, npv,
                   equity_multiple, irr_delta, created_at
            FROM scenario_results
            WHERE id IN ({placeholders})
            ORDER BY id DESC
            """,
            con,
            params=tuple(int(x) for x in ids),
        )


def load_audit_log(limit: int = 50) -> pd.DataFrame:
    with db_conn() as con:
        return pd.read_sql_query(
            "SELECT id, event_type, detail, created_at FROM audit_log ORDER BY id DESC LIMIT ?",
            con,
            params=(limit,),
        )


def scenario_recipe_outputs(assumptions, kpis):
    recipes = ["Base", "Exit Cap Expansion", "Cost Overrun", "Lease-Up Delay", "Refi Failure", "Rate Shock", "Rent Recession"]
    rows = []
    payloads = []
    for recipe in recipes:
        aa = apply_scenario(assumptions, recipe)
        kk = run_kpis_only(aa)
        payloads.append((recipe, aa, kk))
        if kk is None:
            rows.append({"Scenario": recipe, "Levered IRR": "Error", "Unlevered IRR": "Error", "NPV": "Error", "Equity Multiple": "Error", "IRR Delta": "Error"})
            continue
        delta = (kk.levered_irr - kpis.levered_irr) if kk.levered_irr is not None and kpis.levered_irr is not None else None
        rows.append({
            "Scenario": recipe,
            "Levered IRR": pct(kk.levered_irr),
            "Unlevered IRR": pct(kk.unlevered_irr),
            "NPV": money(kk.npv),
            "Equity Multiple": xmult(kk.equity_multiple),
            "IRR Delta": "—" if delta is None else f"{delta*100:+.2f} pts",
        })
    return rows, payloads


def scenario_recipe_definitions() -> pd.DataFrame:
    """Human-readable scenario recipe definitions. These explain where the scenario lab figures come from."""
    return pd.DataFrame([
        {"Scenario": "Base", "How populated": "Current live sidebar assumptions", "Overrides": "None", "Purpose": "Current working underwriting case"},
        {"Scenario": "Exit Cap Expansion", "How populated": "Auto-run recipe", "Overrides": "+100 bps exit cap", "Purpose": "Terminal valuation stress"},
        {"Scenario": "Cost Overrun", "How populated": "Auto-run recipe", "Overrides": "+20% hard cost, +5% contingency", "Purpose": "Renovation execution stress"},
        {"Scenario": "Lease-Up Delay", "How populated": "Auto-run recipe", "Overrides": "+6 months absorption, lower initial occupancy", "Purpose": "Revenue ramp timing stress"},
        {"Scenario": "Refi Failure", "How populated": "Auto-run recipe", "Overrides": "Refi disabled", "Purpose": "Liquidity / refinance risk case"},
        {"Scenario": "Rate Shock", "How populated": "Auto-run recipe", "Overrides": "+150 bps debt/refi rates", "Purpose": "Financing cost stress"},
        {"Scenario": "Rent Recession", "How populated": "Auto-run recipe", "Overrides": "Rent growth reduced, vacancy higher", "Purpose": "Market revenue stress"},
    ])


def focused_sidebar_context(workspace: str, assumptions, kpis, deal_section: str = "Acquisition") -> None:
    """Contextual assumption summary for the active workspace.

    This does not replace the live editor yet. It gives the user a focused view
    of the assumptions most relevant to the current screen while preserving the
    full editor below for POC stability.
    """
    st.sidebar.markdown("### Relevant Assumptions")
    if workspace == "Deal Workspace":
        section = deal_section
    else:
        section = workspace

    rows = []
    if section in ["Executive Dashboard", "Cash Flow Timeline"]:
        rows = [
            ("Hold Months", assumptions.timeline.hold_months),
            ("Exit Cap", pct(assumptions.exit.exit_cap_rate)),
            ("Rent Growth", pct(assumptions.property.unit_types[0].default_rent_growth if assumptions.property.unit_types else 0)),
            ("Refi LTV", pct(assumptions.refi.ltv)),
        ]
    elif section == "Revenue":
        rows = [
            ("Rent Growth", pct(assumptions.property.unit_types[0].default_rent_growth if assumptions.property.unit_types else 0)),
            ("Stab Occ Threshold", pct(assumptions.timeline.stabilized_occ_threshold)),
            ("1BR Market Rent", money(next((u.market_rent for u in assumptions.property.unit_types if u.label == "1BR"), 0))),
            ("Absorption Curve", assumptions.property.unit_types[0].absorption_curve.value if assumptions.property.unit_types else "—"),
        ]
    elif section == "Operations":
        rows = [
            ("R&M / Unit", money(assumptions.opex.repairs_maintenance.cost_per_unit_per_year)),
            ("Payroll / Unit", money(assumptions.opex.payroll.cost_per_unit_per_year)),
            ("Tax / Unit", money(assumptions.opex.property_tax.cost_per_unit_per_year)),
            ("Mgmt Fee", pct(assumptions.opex.management_fee.pct_of_egi)),
        ]
    elif section == "Renovation":
        rows = [
            ("Include Reno", assumptions.renovation.include_renovation),
            ("Hard Cost / Unit", money(assumptions.renovation.hard_cost_per_unit)),
            ("Contingency", pct(assumptions.renovation.contingency_pct)),
            ("Reno Months", assumptions.renovation.reno_period_months),
        ]
    elif section == "Financing":
        rows = [
            ("Acq LTV", pct(assumptions.acq_loan.ltv_or_ltc)),
            ("Acq Rate", pct(assumptions.acq_loan.interest_rate)),
            ("Refi LTV", pct(assumptions.refi.ltv)),
            ("Refi Rate", pct(assumptions.refi.interest_rate)),
        ]
    elif section == "Exit":
        rows = [
            ("Exit Month", assumptions.exit.exit_month),
            ("Exit Cap", pct(assumptions.exit.exit_cap_rate)),
            ("Selling Cost", pct(assumptions.exit.selling_cost_pct)),
            ("Market Cap", pct(assumptions.market.market_cap_rate_going_in)),
        ]
    elif section == "Scenario Lab":
        rows = [("Base IRR", pct(kpis.levered_irr)), ("Base NPV", money(kpis.npv)), ("Exit Cap", pct(assumptions.exit.exit_cap_rate)), ("Rent Growth", pct(assumptions.property.unit_types[0].default_rent_growth if assumptions.property.unit_types else 0))]
    elif section == "Monte Carlo":
        rows = [("Base IRR", pct(kpis.levered_irr)), ("Exit Cap", pct(assumptions.exit.exit_cap_rate)), ("Rent Growth", pct(assumptions.property.unit_types[0].default_rent_growth if assumptions.property.unit_types else 0)), ("Hard Cost", money(assumptions.renovation.hard_cost_per_unit))]
    else:
        rows = [("Levered IRR", pct(kpis.levered_irr)), ("Unlevered IRR", pct(kpis.unlevered_irr)), ("DSCR", xmult(kpis.dscr_stabilized)), ("Risk", classify_deal_risk(kpis, assumptions))]

    for label, value in rows:
        st.sidebar.markdown(f"<div style='font-size:12px;color:#486581;margin-top:6px'>{label}</div><div style='font-size:16px;font-weight:700;color:#0B1F3A'>{value}</div>", unsafe_allow_html=True)



# -----------------------------------------------------------------------------
# Cell context layer - makes table/list values inspectable in the right drawer.
# -----------------------------------------------------------------------------

def set_cell_context(table_name: str, row_label: str, column_name: str, value: Any, source: str = "Workbench UI", formula: str = "See related formula trace node where applicable.") -> None:
    st.session_state["selected_cell_context"] = {
        "table": str(table_name),
        "row": str(row_label),
        "column": str(column_name),
        "value": value,
        "source": str(source),
        "formula": str(formula),
        "captured_at": now_iso(),
    }


def _short_cell_label(value: Any, max_len: int = 22) -> str:
    txt = "—" if value is None else str(value)
    txt = txt.replace("\n", " ")
    return txt if len(txt) <= max_len else txt[: max_len - 1] + "…"


def render_clickable_context_table(df: pd.DataFrame, table_name: str, source: str = "Workbench table", max_rows: int = 12) -> None:
    """Render a compact table where each visible cell is a Streamlit button.

    Streamlit's native dataframe does not expose per-cell click callbacks. This
    helper renders smaller diagnostic lists as button grids, so clicking a cell
    pushes exact cell context into the drawer.
    """
    if df is None or df.empty:
        st.info("No rows to display.")
        return

    visible = df.head(max_rows).copy()
    if len(df) > max_rows:
        st.caption(f"Showing first {max_rows} rows as clickable cells. Full table has {len(df)} rows.")

    cols = list(visible.columns)
    # Avoid unreadable wide button grids.
    if len(cols) > 8:
        st.dataframe(df, hide_index=True, width="stretch")
        render_cell_inspector(df, table_name, source=source)
        return

    header = st.columns(len(cols))
    for i, col in enumerate(cols):
        header[i].markdown(f"**{col}**")

    safe_name = ''.join(ch if ch.isalnum() else '_' for ch in table_name)
    for ridx, row in visible.iterrows():
        row_cols = st.columns(len(cols))
        row_label = row.get(cols[0], ridx)
        for cidx, col in enumerate(cols):
            val = row[col]
            key = f"cell_{safe_name}_{ridx}_{cidx}_{col}".replace(" ", "_")
            row_cols[cidx].button(
                _short_cell_label(val),
                key=key,
                width="stretch",
                help=f"Inspect {table_name} → row {ridx}, column {col}",
                on_click=set_cell_context,
                args=(table_name, row_label, col, val, source),
            )


def render_cell_inspector(df: pd.DataFrame, table_name: str, source: str = "Workbench table") -> None:
    """Fallback context selector for large/wide engine tables."""
    if df is None or df.empty:
        return
    with st.expander(f"Inspect a cell from {table_name}", expanded=False):
        max_index = len(df) - 1
        row_idx = st.number_input(f"{table_name} row index", min_value=0, max_value=max_index, value=0, step=1, key=f"inspect_row_{table_name}")
        col = st.selectbox(f"{table_name} column", list(df.columns), key=f"inspect_col_{table_name}")
        value = df.iloc[int(row_idx)][col]
        st.write("Selected value:", value)
        if st.button(f"Send {table_name} cell to drawer", key=f"inspect_btn_{table_name}"):
            set_cell_context(table_name, f"row {row_idx}", str(col), value, source)
            st.rerun()




def render_contextual_dataframe(df: pd.DataFrame, table_name: str, source: str = "Workbench table", formula: str = "Table values are generated by the live model run.", max_preview_rows: int = 6) -> None:
    """Display a dataframe and attach a reliable cell context inspector.

    Native Streamlit dataframes do not emit per-cell click events. This wrapper
    shows the dataframe normally, then provides a persistent row/column selector
    and, for small tables, a compact clickable preview. Both write into the same
    drawer context state.
    """
    if df is None or df.empty:
        st.info("No rows to display.")
        return
    st.dataframe(df, hide_index=True, width="stretch")
    with st.expander(f"Cell context for {table_name}", expanded=False):
        max_index = len(df) - 1
        c1, c2, c3 = st.columns([1, 2, 1])
        row_idx = c1.number_input("Row", min_value=0, max_value=max_index, value=0, step=1, key=f"ctx_row_{table_name}")
        col = c2.selectbox("Column", list(df.columns), key=f"ctx_col_{table_name}")
        value = df.iloc[int(row_idx)][col]
        c3.metric("Selected", _short_cell_label(value, 18))
        st.caption(f"Row {int(row_idx)} | Column `{col}` | Source: {source}")
        if st.button("Load selected cell into drawer", key=f"ctx_send_{table_name}", width="stretch"):
            set_cell_context(table_name, f"row {int(row_idx)}", str(col), value, source, formula)
            st.rerun()
        # Small clickable preview for compact tables only.
        if len(df) <= max_preview_rows and len(df.columns) <= 8:
            st.markdown("**Clickable preview**")
            render_clickable_context_table(df, f"{table_name} Preview", source=source, max_rows=max_preview_rows)


def render_chart_context(title: str, source: str, formula: str, data: Optional[pd.DataFrame] = None) -> None:
    """Attach chart-level and optional point-level context to the drawer."""
    with st.expander(f"Chart context: {title}", expanded=False):
        st.caption("Streamlit's built-in chart click events are limited, so this sends chart or selected data-point context to the drawer.")
        if st.button(f"Load {title} chart context into drawer", key=f"chart_ctx_{title}", width="stretch"):
            set_cell_context(title, "chart", "visualization", "Chart / visual output", source, formula)
            st.rerun()
        if data is not None and not data.empty:
            cols = list(data.columns)
            c1, c2 = st.columns(2)
            row_idx = c1.number_input("Data row", min_value=0, max_value=len(data)-1, value=0, step=1, key=f"chart_row_{title}")
            col = c2.selectbox("Data field", cols, key=f"chart_col_{title}")
            value = data.iloc[int(row_idx)][col]
            st.write("Selected chart data value:", value)
            if st.button(f"Load selected {title} data point", key=f"chart_point_{title}", width="stretch"):
                set_cell_context(title, f"chart data row {int(row_idx)}", str(col), value, source, formula)
                st.rerun()


# -----------------------------------------------------------------------------
# Monte Carlo risk layer
# -----------------------------------------------------------------------------

def monte_carlo_run(base_assumptions, n_sims: int, seed: int, exit_cap_bps: float, rent_growth_bps: float, hard_cost_pct: float, rate_bps: float, occ_pct: float) -> pd.DataFrame:
    rng = random.Random(int(seed))
    rows = []
    for i in range(int(n_sims)):
        a = deepcopy(base_assumptions)
        # Shock assumptions. Keep shocks simple, auditable, and bounded.
        exit_shock = rng.gauss(0.0, exit_cap_bps / 10000.0)
        rent_shock = rng.gauss(0.0, rent_growth_bps / 10000.0)
        hard_shock = rng.gauss(0.0, hard_cost_pct)
        rate_shock = rng.gauss(0.0, rate_bps / 10000.0)
        occ_shock = rng.gauss(0.0, occ_pct)

        a.exit.exit_cap_rate = max(0.02, min(0.15, a.exit.exit_cap_rate + exit_shock))
        a.renovation.hard_cost_per_unit = max(0.0, a.renovation.hard_cost_per_unit * (1.0 + hard_shock))
        a.acq_loan.interest_rate = max(0.0, min(0.20, a.acq_loan.interest_rate + rate_shock))
        a.const_loan.interest_rate = max(0.0, min(0.22, a.const_loan.interest_rate + rate_shock))
        a.refi.interest_rate = max(0.0, min(0.20, a.refi.interest_rate + rate_shock))
        for u in a.property.unit_types:
            u.default_rent_growth = max(-0.05, min(0.12, u.default_rent_growth + rent_shock))
            u.stabilized_occupancy = max(0.70, min(0.99, u.stabilized_occupancy + occ_shock))

        kk = run_kpis_only(a)
        rows.append({
            "sim": i + 1,
            "levered_irr": None if kk is None else kk.levered_irr,
            "unlevered_irr": None if kk is None else kk.unlevered_irr,
            "npv": None if kk is None else kk.npv,
            "equity_multiple": None if kk is None else kk.equity_multiple,
            "dscr": None if kk is None else kk.dscr_stabilized,
            "exit_cap_rate": a.exit.exit_cap_rate,
            "rent_growth": a.property.unit_types[0].default_rent_growth if a.property.unit_types else None,
            "hard_cost_per_unit": a.renovation.hard_cost_per_unit,
            "acq_rate": a.acq_loan.interest_rate,
            "avg_stab_occ": sum(u.stabilized_occupancy for u in a.property.unit_types) / len(a.property.unit_types) if a.property.unit_types else None,
        })
    return pd.DataFrame(rows)


def percentile(series: pd.Series, q: float) -> Optional[float]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    return float(s.quantile(q))


# =============================================================================
# Interaction helpers used by the v4 page
# =============================================================================

def select_formula_node(name: str) -> None:
    """Streamlit callback: set selected formula before rerun renders the drawer."""
    st.session_state.selected_formula = name


def dependency_tree_text(name: str) -> str:
    """Return a dynamic dependency tree for the currently selected trace node."""
    trees = {
        "Levered IRR": """Levered IRR
├── Equity CF
│   ├── NCFBT = NOI - Debt Service - Ongoing CapEx
│   │   ├── NOI
│   │   └── Debt Service
│   ├── Refi Proceeds
│   ├── Levered Sale Proceeds
│   │   ├── Exit Value
│   │   ├── Loan Payoff
│   │   └── Disposition Fee
│   ├── Equity Reno Draw
│   └── Initial Equity Outflow
└── compute_irr(equity_cfs)""",
        "Unlevered IRR": """Unlevered IRR
├── Unlevered CF
│   ├── NOI
│   ├── Total Reno Draw
│   ├── Ongoing CapEx
│   ├── Acquisition Outflow
│   └── Unlevered Sale Proceeds
│       └── Exit Value
└── compute_irr(unlevered_cfs)""",
        "Equity CF": """Equity CF
├── NCFBT
│   ├── NOI
│   ├── Debt Service
│   └── Ongoing CapEx
├── Refi Proceeds
├── Levered Sale Proceeds
│   └── Exit Value
├── GP Management Fee
├── Equity Reno Draw
└── Initial Equity Outflow""",
        "NOI": """NOI
├── EGI
│   ├── Gross Potential Rent
│   ├── Occupancy / Vacancy
│   ├── Concessions
│   └── Credit Loss
└── Operating Expenses
    ├── Repairs & Maintenance
    ├── Payroll
    ├── Utilities
    ├── Insurance
    ├── Property Tax
    └── Management Fee""",
        "Exit Value": """Exit Value
├── Exit Month NOI
├── Annualization × 12
└── Exit Cap Rate

Levered Sale Proceeds
├── Exit Value
├── Selling Costs
├── Loan Payoff
└── Disposition Fee""",
        "Refi Proceeds": """Refi Proceeds
├── Refi Value
│   ├── NOI at Refi / Stabilized NOI
│   └── Market Cap Rate
├── Refi LTV
├── Acquisition Loan Payoff
├── Construction Loan Payoff
└── Refi Costs""",
        "DSCR Stabilized": """DSCR Stabilized
├── Stabilized Annual NOI
│   └── Stabilized Monthly NOI × 12
└── Stabilized Annual Debt Service
    └── Stabilized Monthly Debt Service × 12""",
        "Yield on Cost": """Yield on Cost
├── Stabilized Annual NOI
└── Total Project Cost
    ├── Purchase Price
    ├── Closing Costs
    ├── Hard Costs
    ├── Soft Costs
    └── Common / Exterior Costs""",
    }
    return trees.get(name, f"{name}\n└── No dependency tree registered yet")


def render_trace_dependency_controls(trace: Dict[str, Dict[str, Any]]) -> None:
    """Show a dynamic dependency tree that follows the selected trace node."""
    selected = st.session_state.get("selected_formula", list(trace.keys())[0])
    fd = trace[selected]
    st.markdown(f"#### Dependency Tree: {selected}")
    st.code(dependency_tree_text(selected), language="text")
    st.caption("Click any available dependency below to jump the drawer and this tree to that node.")

    dependency_buttons = [d for d in fd.get("dependencies", []) if d in trace]
    if selected not in dependency_buttons and selected in trace:
        dependency_buttons = [selected] + dependency_buttons

    if dependency_buttons:
        cols = st.columns(min(4, len(dependency_buttons)))
        for i, dep in enumerate(dependency_buttons):
            cols[i % len(cols)].button(
                f"Trace: {dep}",
                key=f"dynamic_dep_{selected}_{dep}",
                width="stretch",
                on_click=select_formula_node,
                args=(dep,),
            )
    else:
        st.info("No clickable trace dependencies registered for this node yet.")




# -----------------------------------------------------------------------------
# Visual risk coloring layer
# -----------------------------------------------------------------------------

def risk_level_color(level: str) -> str:
    level = (level or "").lower()
    if "very high" in level or "critical" in level:
        return "#fee2e2"
    if "high" in level:
        return "#ffedd5"
    if "medium" in level or "low-medium" in level:
        return "#fef9c3"
    if "low" in level or "high" in level == False:
        return "#dcfce7"
    return "#f3f4f6"


def risk_text_color(level: str) -> str:
    level = (level or "").lower()
    if "very high" in level or "critical" in level:
        return "#991b1b"
    if "high" in level:
        return "#9a3412"
    if "medium" in level or "low-medium" in level:
        return "#854d0e"
    if "low" in level:
        return "#166534"
    return "#374151"


def risk_badge(label: str, level: str) -> str:
    bg = risk_level_color(level)
    fg = risk_text_color(level)
    return f"""
    <div style='border:1px solid {fg}; background:{bg}; color:{fg};
                padding:10px 12px; border-radius:10px; margin-bottom:8px;'>
        <div style='font-size:11px; opacity:.8; text-transform:uppercase; letter-spacing:.04em;'>{label}</div>
        <div style='font-size:18px; font-weight:700;'>{level}</div>
    </div>
    """


def kpi_risk_assessment(kpis, a) -> List[Dict[str, str]]:
    rows = []
    irr = safe_float(kpis.levered_irr)
    unirr = safe_float(kpis.unlevered_irr)
    dscr = safe_float(kpis.dscr_stabilized)
    spread = safe_float(kpis.development_spread_bps)
    em = safe_float(kpis.equity_multiple)

    rows.append({
        "Area": "Levered Return",
        "Metric": "Levered IRR",
        "Value": pct(irr),
        "Risk": "High" if irr is not None and irr < 0.12 else "Medium" if irr is not None and irr < 0.16 else "Low",
        "Reason": "Below 12% target" if irr is not None and irr < 0.12 else "Moderate return sensitivity" if irr is not None and irr < 0.16 else "Above basic return threshold",
    })
    rows.append({
        "Area": "Property Return",
        "Metric": "Unlevered IRR",
        "Value": pct(unirr),
        "Risk": "High" if unirr is not None and unirr < 0.075 else "Medium" if unirr is not None and unirr < 0.10 else "Low",
        "Reason": "Weak property-level return" if unirr is not None and unirr < 0.075 else "Acceptable but terminal-value sensitive" if unirr is not None and unirr < 0.10 else "Solid property-level return",
    })
    rows.append({
        "Area": "Debt Coverage",
        "Metric": "DSCR Stabilized",
        "Value": xmult(dscr or 0.0),
        "Risk": "Very High" if dscr is not None and dscr < 1.20 else "High" if dscr is not None and dscr < 1.35 else "Medium" if dscr is not None and dscr < 1.60 else "Low",
        "Reason": "Below lender floor" if dscr is not None and dscr < 1.20 else "Thin coverage" if dscr is not None and dscr < 1.35 else "Adequate cushion" if dscr is not None and dscr < 1.60 else "Strong debt cushion",
    })
    rows.append({
        "Area": "Development Spread",
        "Metric": "YoC - Market Cap",
        "Value": f"{spread:,.0f} bps" if spread is not None else "—",
        "Risk": "High" if spread is not None and spread < 50 else "Medium" if spread is not None and spread < 100 else "Low",
        "Reason": "Insufficient spread for execution risk" if spread is not None and spread < 50 else "Moderate value-add spread" if spread is not None and spread < 100 else "Good spread cushion",
    })
    rows.append({
        "Area": "Terminal Value",
        "Metric": "Exit Cap Rate",
        "Value": pct(a.exit.exit_cap_rate),
        "Risk": "High",
        "Reason": "High-sensitivity terminal valuation input",
    })
    rows.append({
        "Area": "Equity Multiple",
        "Metric": "Equity Multiple",
        "Value": xmult(em or 0.0),
        "Risk": "High" if em is not None and em < 1.35 else "Medium" if em is not None and em < 1.60 else "Low",
        "Reason": "Low absolute profit multiple" if em is not None and em < 1.35 else "Moderate equity profit" if em is not None and em < 1.60 else "Healthy absolute profit",
    })
    return rows


def style_risk_dataframe(df: pd.DataFrame):
    def row_style(row):
        level = str(row.get("Risk", row.get("Impact Class", "")))
        bg = risk_level_color(level)
        return [f"background-color: {bg}" for _ in row]
    return df.style.apply(row_style, axis=1)


# -----------------------------------------------------------------------------
# v4.0 Underwriting OS visual helpers
# -----------------------------------------------------------------------------

def os_kpi_card(label: str, value: str, sub: str = "", risk: str = "Low") -> str:
    risk = risk or "Low"
    accent = {
        "Low": "#1E88FF",
        "Medium": "#F59E0B",
        "High": "#DC2626",
        "Very High": "#991B1B",
    }.get(risk, "#1E88FF")
    return f"""
    <div class='os-card' style='border-top:4px solid {accent};'>
        <div class='os-card-label'>{label}</div>
        <div class='os-card-value'>{value}</div>
        <div class='os-card-sub'>{sub}</div>
    </div>
    """


def os_info_card(title: str, value: str, detail: str = "") -> str:
    return f"""
    <div class='os-info-card'>
        <div class='os-info-title'>{title}</div>
        <div class='os-info-value'>{value}</div>
        <div class='os-info-detail'>{detail}</div>
    </div>
    """


def classify_deal_risk(kpis, a) -> str:
    irr = safe_float(kpis.levered_irr)
    dscr = safe_float(kpis.dscr_stabilized)
    spread = safe_float(kpis.development_spread_bps)
    high = 0
    if irr is not None and irr < 0.12: high += 1
    if dscr is not None and dscr < 1.35: high += 1
    if spread is not None and spread < 75: high += 1
    if a.exit.exit_cap_rate < a.market.market_cap_rate_going_in: high += 1
    if high >= 3: return "High"
    if high >= 1: return "Medium"
    return "Low"


def confidence_score(assumptions, kpis, metadata_df: Optional[pd.DataFrame] = None) -> int:
    # POC confidence score: blend assumption metadata with model risk metrics.
    score = 82
    if metadata_df is not None and not metadata_df.empty and "confidence" in metadata_df.columns:
        lows = metadata_df[metadata_df["confidence"].astype(str).str.lower().isin(["low", "unknown"])].shape[0]
        score -= min(20, lows * 3)
    if safe_float(kpis.dscr_stabilized) is not None and kpis.dscr_stabilized < 1.35:
        score -= 10
    if safe_float(kpis.levered_irr) is not None and kpis.levered_irr < 0.12:
        score -= 10
    if safe_float(kpis.development_spread_bps) is not None and kpis.development_spread_bps < 75:
        score -= 7
    return max(0, min(100, score))


def build_timeline_df(cashflows, revenue, opex, debt) -> pd.DataFrame:
    rows = []
    for i, cf in enumerate(cashflows):
        rows.append({
            "Month": cf.month,
            "Occupancy": revenue[i].occupancy_rate if i < len(revenue) else None,
            "EGI": cf.egi,
            "NOI": cf.noi,
            "Debt Service": cf.debt_service,
            "Equity CF": cf.equity_cf,
            "Cumulative Equity CF": cf.cumulative_equity_cf,
        })
    return pd.DataFrame(rows)


def render_ai_copilot_panel(assumptions, kpis, trace, active_ctx):
    st.markdown("### Ask the Deal")
    st.caption("Local POC assistant. It uses current model context, selected trace/cell, and rule-based diagnostics. OpenAI integration comes later.")
    q = st.text_input("Ask me", placeholder="Why is IRR like that? What affects DSCR? Optimize exit cap?", key="ai_ask_input")
    if st.button("Ask", type="primary", width="stretch") and q:
        ql = q.lower()
        selected = st.session_state.get("selected_formula", "Levered IRR")
        answer = []
        answer.append(f"Context: active trace node is {selected}.")
        if active_ctx:
            answer.append(f"Selected cell: {active_ctx.get('table')} / {active_ctx.get('column')} = {active_ctx.get('value')}.")
        if "irr" in ql:
            answer.append(f"Levered IRR is {pct(kpis.levered_irr)} and unlevered IRR is {pct(kpis.unlevered_irr)}. The core path is equity cash flow, refi proceeds, sale proceeds, debt service, and terminal exit value.")
            answer.append("Primary practical drivers: exit cap rate, rent growth, renovation cost/timing, refi LTV/rate, and stabilization NOI.")
        elif "dscr" in ql:
            answer.append(f"DSCR at stabilization is {xmult(kpis.dscr_stabilized)}. Formula: stabilized annual NOI / stabilized annual debt service.")
        elif "risk" in ql:
            answer.append(f"Current overall risk classification: {classify_deal_risk(kpis, assumptions)}. Focus first on exit cap, DSCR cushion, development spread, and low-confidence assumptions.")
        elif "optimiz" in ql or "improve" in ql:
            answer.append("Optimization should be bounded. Suggested POC action: run grid search over exit cap, rent growth, and refi LTV while constraining DSCR > 1.50x and LTV <= 70%. Do not overwrite Base. Save as an optimization scenario.")
        else:
            fd = trace.get(selected, {})
            answer.append(f"{selected}: {fd.get('value', '—')}. Formula: {fd.get('formula', 'No formula registered.')}")
        st.session_state["last_ai_answer"] = "\n\n".join(answer)
        append_audit("ai_copilot_question", q)
    if st.session_state.get("last_ai_answer"):
        st.markdown("#### Answer")
        st.info(st.session_state["last_ai_answer"])
        c1, c2 = st.columns(2)
        if c1.button("Save as insight", width="stretch"):
            append_audit("ai_insight_saved", st.session_state["last_ai_answer"][:500])
            st.success("Insight saved to audit log.")
        if c2.button("Mark as garbage", width="stretch"):
            append_audit("ai_insight_rejected", st.session_state["last_ai_answer"][:500])
            st.warning("Marked as rejected feedback.")



# =============================================================================
# Sidebar navigation - v4.2 hierarchical menu
# =============================================================================

def _set_workspace(workspace_name: str, section_name: Optional[str] = None) -> None:
    st.session_state["current_workspace"] = workspace_name
    if section_name is not None:
        st.session_state["deal_workspace_section"] = section_name


def _nav_button(label: str, workspace_name: str, section_name: Optional[str] = None) -> None:
    active = st.session_state.get("current_workspace", "Executive Dashboard") == workspace_name
    if section_name is not None:
        active = active and st.session_state.get("deal_workspace_section", "Acquisition") == section_name
    prefix = "● " if active else "○ "
    st.sidebar.button(prefix + label, key=f"nav_{workspace_name}_{section_name or 'root'}", width="stretch", on_click=_set_workspace, args=(workspace_name, section_name))


def render_sidebar_navigation() -> Tuple[str, Optional[str]]:
    if "current_workspace" not in st.session_state:
        st.session_state["current_workspace"] = "Executive Dashboard"
    if "deal_workspace_section" not in st.session_state:
        st.session_state["deal_workspace_section"] = "Acquisition"

    st.sidebar.markdown("### Navigation")
    _nav_button("Executive Dashboard", "Executive Dashboard")
    _nav_button("Cash Flow Timeline", "Cash Flow Timeline")

    with st.sidebar.expander("Deal Workspace", expanded=st.session_state.get("current_workspace") == "Deal Workspace"):
        for sec in ["Acquisition", "Revenue", "Operations", "Renovation", "Financing", "Exit"]:
            _nav_button(sec, "Deal Workspace", sec)

    with st.sidebar.expander("Analysis", expanded=st.session_state.get("current_workspace") in {"Scenario Lab", "Monte Carlo"}):
        _nav_button("Scenario Lab", "Scenario Lab")
        _nav_button("Monte Carlo", "Monte Carlo")

    with st.sidebar.expander("System", expanded=st.session_state.get("current_workspace") in {"AI Copilot", "Versions / Audit", "Engine Lab"}):
        _nav_button("AI Copilot", "AI Copilot")
        _nav_button("Versions / Audit", "Versions / Audit")
        _nav_button("Engine Lab", "Engine Lab")

    workspace_name = st.session_state.get("current_workspace", "Executive Dashboard")
    deal_section_name = st.session_state.get("deal_workspace_section", "Acquisition") if workspace_name == "Deal Workspace" else None
    st.sidebar.caption("Active: " + workspace_name + ((" / " + deal_section_name) if deal_section_name else ""))
    st.sidebar.divider()
    return workspace_name, deal_section_name

# =============================================================================
# Page - v4.0 Underwriting OS
# =============================================================================

st.set_page_config(page_title="RE DCF Underwriting OS v4.2", layout="wide")
init_db()
APP_VERSION = "v4.2 Contextual Navigation + Filtered Live Editor"

st.markdown("""
<style>
:root {
  --electric:#1E88FF;
  --sky:#5CC8FF;
  --navy:#0B1F3A;
  --muted:#64748B;
  --bg:#F8FAFC;
  --card:#FFFFFF;
  --border:#D9E7F7;
}
.main .block-container {padding-top: 1.1rem; max-width: 1500px;}
.os-header {background: linear-gradient(90deg, #0B1F3A 0%, #123B70 50%, #1E88FF 100%); color:white; padding:18px 22px; border-radius:18px; margin-bottom:14px; box-shadow:0 8px 24px rgba(30,136,255,.15);}
.os-title {font-size:26px; font-weight:800; margin:0; letter-spacing:-.02em;}
.os-subtitle {font-size:13px; opacity:.88; margin-top:4px;}
.os-pill {display:inline-block; background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.3); padding:6px 10px; border-radius:999px; margin-left:8px; font-size:12px;}
.os-card {background:#FFFFFF; border:1px solid #D9E7F7; border-radius:16px; padding:16px 15px; min-height:105px; box-shadow:0 4px 18px rgba(11,31,58,.06);}
.os-card-label {font-size:11px; text-transform:uppercase; letter-spacing:.08em; color:#64748B; font-weight:700;}
.os-card-value {font-size:28px; color:#0B1F3A; font-weight:850; margin-top:5px;}
.os-card-sub {font-size:12px; color:#64748B; margin-top:2px;}
.os-info-card {background:#FFFFFF; border:1px solid #D9E7F7; border-radius:14px; padding:13px 14px; min-height:88px; box-shadow:0 3px 14px rgba(11,31,58,.05);}
.os-info-title {font-size:11px; color:#64748B; text-transform:uppercase; letter-spacing:.07em; font-weight:700;}
.os-info-value {font-size:21px; color:#0B1F3A; font-weight:800; margin-top:4px;}
.os-info-detail {font-size:12px; color:#64748B; margin-top:2px;}
.section-title {color:#0B1F3A; font-weight:800; font-size:18px; margin:10px 0 4px 0;}
.risk-chip {display:inline-block; padding:4px 9px; border-radius:999px; font-size:12px; font-weight:700; margin:2px 4px 2px 0;}
.risk-low {background:#E8F7FF; color:#075985; border:1px solid #5CC8FF;}
.risk-medium {background:#FEF9C3; color:#854D0E; border:1px solid #F59E0B;}
.risk-high {background:#FFE7DF; color:#9A3412; border:1px solid #FB923C;}
.risk-very-high {background:#FEE2E2; color:#991B1B; border:1px solid #DC2626;}
[data-testid="stSidebar"] {background:#F8FAFC; border-right:1px solid #D9E7F7;}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class='os-header'>
  <div class='os-title'>RE DCF Underwriting OS <span class='os-pill'>{APP_VERSION}</span><span class='os-pill'>Local POC</span></div>
  <div class='os-subtitle'>Electric-blue underwriting workspace: executive dashboard, cash-flow timeline, trace drawer, scenarios, Monte Carlo, and AI copilot shell.</div>
</div>
""", unsafe_allow_html=True)

# Sidebar navigation first, then the fully contextual assumption controls.
workspace, active_deal_section_for_sidebar = render_sidebar_navigation()

try:
    if st.session_state.get("active_assumptions_json"):
        st.sidebar.header("Loaded Scenario")
        st.sidebar.success(st.session_state.get("active_scenario_label", "Saved scenario loaded"))
        if st.sidebar.button("Return to live sidebar editor"):
            st.session_state.pop("active_assumptions_json", None)
            st.session_state.pop("active_scenario_label", None)
            st.rerun()
        assumptions = assumptions_from_json(st.session_state["active_assumptions_json"])
        st.warning(f"Loaded scenario active: {st.session_state.get('active_scenario_label', 'saved scenario')}. Sidebar editing is paused until you return to live editor.")
    else:
        assumptions = build_assumptions_from_ui(workspace, active_deal_section_for_sidebar)
    revenue, stab_month, opex, capex, debt, cashflows, waterfall, kpis = run_all_engines(assumptions)
except Exception as exc:
    st.error("Engine run failed.")
    st.exception(exc)
    st.stop()

trace = build_formula_trace(assumptions, revenue, opex, capex, debt, cashflows, kpis)

# v4.2: no separate global summary panel here. The live editor itself is filtered
# to the active workspace/submenu.
formula_keys = list(trace.keys())
if "selected_formula" not in st.session_state or st.session_state.selected_formula not in formula_keys:
    st.session_state.selected_formula = formula_keys[0]

metadata_df = load_assumption_metadata()
risk_rows = kpi_risk_assessment(kpis, assumptions)
risk_counts = pd.DataFrame(risk_rows)["Risk"].value_counts().to_dict()
deal_risk = classify_deal_risk(kpis, assumptions)
conf = confidence_score(assumptions, kpis, metadata_df)
timeline_df = build_timeline_df(cashflows, revenue, opex, debt)

# Persistent top KPI strip.
kcols = st.columns(8)
kpi_specs = [
    ("Levered IRR", pct(kpis.levered_irr), "equity return", "High" if (kpis.levered_irr or 0) < 0.12 else "Medium" if (kpis.levered_irr or 0) < 0.16 else "Low"),
    ("Unlevered IRR", pct(kpis.unlevered_irr), "property return", "Medium" if (kpis.unlevered_irr or 0) < 0.10 else "Low"),
    ("Equity Multiple", xmult(kpis.equity_multiple), "total out / in", "Medium" if kpis.equity_multiple < 1.6 else "Low"),
    ("NPV", money(kpis.npv), f"@ {pct(assumptions.discount_rate)}", "Low" if kpis.npv >= 0 else "High"),
    ("DSCR", xmult(kpis.dscr_stabilized), "stabilized", "High" if kpis.dscr_stabilized < 1.35 else "Medium" if kpis.dscr_stabilized < 1.6 else "Low"),
    ("YoC", pct(kpis.yield_on_cost), f"spread {kpis.development_spread_bps:,.0f} bps", "Medium" if kpis.development_spread_bps < 100 else "Low"),
    ("Risk", deal_risk, "model flags", deal_risk),
    ("Confidence", f"{conf}%", "POC score", "Low" if conf >= 75 else "Medium" if conf >= 55 else "High"),
]
for col, spec in zip(kcols, kpi_specs):
    col.markdown(os_kpi_card(*spec), unsafe_allow_html=True)

st.markdown(" ")

left, right = st.columns([2.35, 1.0], gap="large")

with right:
    st.markdown("### Explain This Number")
    active_ctx = st.session_state.get("selected_cell_context")
    if active_ctx:
        st.success(f"Clicked context: {active_ctx.get('table')} | {active_ctx.get('column')} = {active_ctx.get('value')}")
    selected_formula = st.selectbox(
        "Trace node",
        formula_keys,
        index=formula_keys.index(st.session_state.selected_formula),
        key="selected_formula",
    )
    fd = trace[st.session_state.selected_formula]
    st.markdown(f"#### {st.session_state.selected_formula}: {fd['value']}")
    st.code(fd["formula"], language="text")
    st.caption(f"Source: {fd['source_function']} | {fd['source_file']}")
    if fd.get("warnings"):
        for w in fd["warnings"]:
            st.warning(w)
    selected_risk = "High" if st.session_state.selected_formula in ["Levered IRR", "Exit Value", "Refi Proceeds"] else "Medium" if st.session_state.selected_formula in ["Unlevered IRR", "Yield on Cost", "DSCR Stabilized"] else "Low"
    st.markdown(risk_badge("Trace risk", selected_risk), unsafe_allow_html=True)
    st.markdown("**Dependencies**")
    deps = [d for d in fd.get("dependencies", []) if d in trace]
    if deps:
        dcols = st.columns(min(2, len(deps)))
        for i, dep in enumerate(deps):
            dcols[i % len(dcols)].button(dep, key=f"right_dep_{st.session_state.selected_formula}_{dep}", width="stretch", on_click=select_formula_node, args=(dep,))
    else:
        st.caption("No clickable dependencies registered.")
    st.markdown("**Bridge**")
    render_contextual_dataframe(fd["bridge"], f"Formula Bridge - {st.session_state.selected_formula}", source="Formula trace bridge", formula=fd["formula"], max_preview_rows=4)
    if active_ctx:
        st.divider()
        st.markdown("### Selected Cell Context")
        st.markdown(f"**Table:** `{active_ctx.get('table')}`")
        st.markdown(f"**Row:** `{active_ctx.get('row')}` | **Column:** `{active_ctx.get('column')}`")
        st.code(str(active_ctx.get("value")), language="text")
        st.caption(f"Source: {active_ctx.get('source')} | Captured: {active_ctx.get('captured_at')}")
    st.divider()
    render_ai_copilot_panel(assumptions, kpis, trace, active_ctx)

with left:
    if workspace == "Executive Dashboard":
        st.markdown("<div class='section-title'>Executive Dashboard</div>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(os_info_card("Exit Value", trace.get("Exit Value", {}).get("value", "—"), "Terminal valuation"), unsafe_allow_html=True)
        c2.markdown(os_info_card("Stabilization", f"Month {kpis.stabilization_month}", "Occupancy threshold achieved"), unsafe_allow_html=True)
        c3.markdown(os_info_card("LTV at Purchase", pct(kpis.ltv_at_purchase), "Acquisition leverage"), unsafe_allow_html=True)
        c4.markdown(os_info_card("Profit on Cost", pct(kpis.profit_on_cost), "Exit value vs project cost"), unsafe_allow_html=True)

        st.markdown("#### Cash Flow Snapshot")
        chart_df = timeline_df[["Month", "NOI", "Equity CF", "Cumulative Equity CF"]].set_index("Month")
        st.line_chart(chart_df, height=310)
        render_chart_context("Dashboard Cash Flow Snapshot", source="engine.dcf.build_cash_flows", formula="Timeline chart from NOI, Equity CF, and cumulative Equity CF.", data=timeline_df)

        st.markdown("#### Risk Register")
        risk_df = pd.DataFrame(risk_rows)
        st.dataframe(style_risk_dataframe(risk_df), hide_index=True, width="stretch")
        render_clickable_context_table(risk_df, "Dashboard Risk Register", source="kpi_risk_assessment")

    elif workspace == "Cash Flow Timeline":
        st.markdown("<div class='section-title'>Cash Flow Timeline</div>", unsafe_allow_html=True)
        st.caption("The old industry standard stays central: month-by-month cash flow on a time axis. Everything else explains the timeline.")
        metric = st.multiselect("Timeline layers", ["Occupancy", "EGI", "NOI", "Debt Service", "Equity CF", "Cumulative Equity CF"], default=["NOI", "Debt Service", "Equity CF", "Cumulative Equity CF"])
        if metric:
            plot_df = timeline_df[["Month"] + metric].set_index("Month")
            st.line_chart(plot_df, height=420)
            render_chart_context("Cash Flow Timeline", source="engine.dcf + revenue + debt", formula="Time-axis view of selected model outputs.", data=timeline_df)
        st.markdown("#### Month Inspector")
        month = st.slider("Select month", 0, assumptions.timeline.hold_months, min(assumptions.timeline.hold_months, kpis.stabilization_month), 1)
        row = timeline_df.loc[timeline_df["Month"] == month].iloc[0]
        mcols = st.columns(6)
        for c, label in zip(mcols, ["Occupancy", "EGI", "NOI", "Debt Service", "Equity CF", "Cumulative Equity CF"]):
            val = row[label]
            c.metric(label, pct(val) if label == "Occupancy" else money(val))
        render_contextual_dataframe(timeline_df, "Cash Flow Timeline Table", source="v4 timeline workspace", formula="Rows combine live model outputs by month.")

    elif workspace == "Deal Workspace":
        st.markdown("<div class='section-title'>Deal Workspace</div>", unsafe_allow_html=True)
        section = st.session_state.get("deal_workspace_section", "Acquisition")
        st.info(f"Current section: {section}. The sidebar live editor is filtered to this section only.")
        if section == "Acquisition":
            rows = pd.DataFrame([
                {"Assumption": "Purchase Price", "Value": money(assumptions.acquisition.purchase_price), "Trace": "Initial Equity Outflow", "Impact": "High"},
                {"Assumption": "Closing Costs", "Value": money(assumptions.acquisition.total_closing_costs), "Trace": "Unlevered CF", "Impact": "Medium"},
                {"Assumption": "Acq LTV", "Value": pct(assumptions.acq_loan.ltv_or_ltc), "Trace": "Equity CF", "Impact": "High"},
            ])
        elif section == "Revenue":
            rent_rows = []
            for u in assumptions.property.unit_types:
                rent_rows.append({
                    "Unit Type": getattr(u, "label", getattr(u, "name", "Unit")),
                    "Units": getattr(u, "unit_count", "—"),
                    "In-Place Rent": money(getattr(u, "in_place_rent", 0)),
                    "Market Rent": money(getattr(u, "market_rent", 0)),
                    "Rent Growth": pct(getattr(u, "default_rent_growth", 0)),
                    "Stab Occ": pct(getattr(u, "stabilized_occupancy", 0)),
                    "Absorption Months": getattr(u, "absorption_period_months", "—"),
                    "Trace": "NOI",
                    "Impact": "High",
                })
            rows = pd.DataFrame(rent_rows)
            st.markdown("#### Revenue Build")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Month 1 EGI", money(revenue[1].egi if len(revenue) > 1 else revenue[0].egi))
            r2.metric("Stabilized EGI", money(revenue[stab_month].egi if stab_month < len(revenue) else 0))
            r3.metric("Stabilization Month", stab_month)
            r4.metric("Stab Occupancy", pct(revenue[stab_month].occupancy_rate if stab_month < len(revenue) else 0))
        elif section == "Operations":
            rows = pd.DataFrame([
                {"Assumption": "R&M / unit", "Value": money(assumptions.opex.repairs_maintenance.cost_per_unit_per_year), "Trace": "NOI", "Impact": "Medium"},
                {"Assumption": "Payroll / unit", "Value": money(assumptions.opex.payroll.cost_per_unit_per_year), "Trace": "NOI", "Impact": "Medium"},
                {"Assumption": "Tax / unit", "Value": money(assumptions.opex.property_tax.cost_per_unit_per_year), "Trace": "NOI", "Impact": "High"},
            ])
        elif section == "Renovation":
            rows = pd.DataFrame([
                {"Assumption": "Hard Cost / Unit", "Value": money(assumptions.renovation.hard_cost_per_unit), "Trace": "Unlevered CF", "Impact": "High"},
                {"Assumption": "Reno Period", "Value": f"{assumptions.renovation.reno_period_months} months", "Trace": "Equity CF", "Impact": "Medium"},
            ])
        elif section == "Financing":
            rows = pd.DataFrame([
                {"Assumption": "Acq Rate", "Value": pct(assumptions.acq_loan.interest_rate), "Trace": "Debt Service", "Impact": "High"},
                {"Assumption": "Refi LTV", "Value": pct(assumptions.refi.ltv), "Trace": "Refi Proceeds", "Impact": "High"},
                {"Assumption": "Refi Rate", "Value": pct(assumptions.refi.interest_rate), "Trace": "Debt Service", "Impact": "High"},
            ])
        else:
            rows = pd.DataFrame([
                {"Assumption": "Exit Cap", "Value": pct(assumptions.exit.exit_cap_rate), "Trace": "Exit Value", "Impact": "Very High"},
                {"Assumption": "Selling Cost", "Value": pct(assumptions.exit.selling_cost_pct), "Trace": "Exit Value", "Impact": "Medium"},
            ])
        render_clickable_context_table(rows, f"{section} Workspace", source="v4 deal workspace")

    elif workspace == "Scenario Lab":
        st.markdown("<div class='section-title'>Scenario Lab</div>", unsafe_allow_html=True)
        st.caption("Scenario figures are auto-populated by applying preset recipe overrides to the current live deal assumptions. They are recalculated on every sidebar change. Saved scenarios are stored separately in SQLite below.")
        with st.expander("Where do these scenario figures come from?", expanded=False):
            render_clickable_context_table(scenario_recipe_definitions(), "Scenario Recipe Definitions", source="hardcoded scenario recipe definitions")
        rows, payloads = scenario_recipe_outputs(assumptions, kpis)
        scenario_df = pd.DataFrame(rows)
        render_clickable_context_table(scenario_df, "Scenario Recipe Cards", source="auto-generated scenario recipe runs from current assumptions")
        deal_name = st.text_input("Deal name for scenario save", value=assumptions.property.name or "Current Deal", key="v4_scenario_deal_name")
        if st.button("Save recipe scenario results", type="primary"):
            run_id = save_scenario_results(deal_name, kpis, rows, payloads)
            st.success(f"Saved scenarios under run {run_id}.")
        st.markdown("#### Saved scenarios")
        saved = load_scenario_results(limit=40)
        if saved.empty:
            st.info("No saved scenarios yet.")
        else:
            render_contextual_dataframe(saved, "Saved Scenario Results", source="SQLite scenario_results", formula="Saved scenario result table.")
            selected_ids = st.multiselect("Compare scenario IDs", saved["id"].tolist(), default=saved["id"].head(min(3, len(saved))).tolist())
            if selected_ids:
                comp = load_scenario_ids(selected_ids)
                render_contextual_dataframe(comp, "Scenario Compare", source="SQLite scenario comparison", formula="Loads saved scenario KPIs for side-by-side review.")

    elif workspace == "Monte Carlo":
        st.markdown("<div class='section-title'>Monte Carlo Command Center</div>", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        n_sims = m1.number_input("Simulations", min_value=50, max_value=2000, value=300, step=50)
        seed = m2.number_input("Random seed", min_value=1, max_value=999999, value=42, step=1)
        run_mc = m3.button("Run Monte Carlo", type="primary", width="stretch")
        c1, c2, c3, c4, c5 = st.columns(5)
        exit_cap_bps = c1.slider("Exit cap stdev", 0, 200, 50, 5)
        rent_growth_bps = c2.slider("Rent growth stdev", 0, 300, 75, 5)
        hard_cost_pct = c3.slider("Hard cost stdev", 0.00, 0.50, 0.10, 0.01)
        rate_bps = c4.slider("Debt rate stdev", 0, 300, 75, 5)
        occ_pct = c5.slider("Stab occ stdev", 0.00, 0.10, 0.02, 0.005)
        if run_mc:
            with st.spinner("Running Monte Carlo simulations..."):
                mc = monte_carlo_run(assumptions, int(n_sims), int(seed), float(exit_cap_bps), float(rent_growth_bps), float(hard_cost_pct), float(rate_bps), float(occ_pct))
            st.session_state["monte_carlo_results"] = mc
            append_audit("monte_carlo_run", f"Ran {int(n_sims)} simulations with seed {int(seed)}")
        mc = st.session_state.get("monte_carlo_results")
        if mc is None or mc.empty:
            st.info("Run the simulation to generate risk distributions.")
        else:
            clean = mc.dropna(subset=["levered_irr"]).copy()
            s1, s2, s3, s4, s5 = st.columns(5)
            s1.metric("IRR P10", pct(percentile(clean["levered_irr"], 0.10)))
            s2.metric("IRR Median", pct(percentile(clean["levered_irr"], 0.50)))
            s3.metric("IRR P90", pct(percentile(clean["levered_irr"], 0.90)))
            s4.metric("NPV P10", money(percentile(clean["npv"], 0.10)))
            s5.metric("Failure Rate", pct((clean["levered_irr"] < 0.08).mean() if not clean.empty else None))
            hist = clean["levered_irr"].mul(100).round(1).value_counts().sort_index().reset_index()
            hist.columns = ["Levered IRR %", "Count"]
            st.bar_chart(hist.set_index("Levered IRR %"), height=300)
            render_chart_context("Monte Carlo IRR Distribution", source="Monte Carlo", formula="Histogram of simulated levered IRR results.", data=hist)
            render_contextual_dataframe(mc, "Monte Carlo Raw Results", source="Monte Carlo simulation results", formula="Each row is one stochastic simulation.")

    elif workspace == "AI Copilot":
        st.markdown("<div class='section-title'>AI Copilot Workspace</div>", unsafe_allow_html=True)
        st.info("This is a local POC shell. It does not call OpenAI yet. Next version can wire this to an API key and structured model context.")
        render_ai_copilot_panel(assumptions, kpis, trace, st.session_state.get("selected_cell_context"))
        st.markdown("#### Planned optimization workflow")
        opt_df = pd.DataFrame([
            {"Step": 1, "Action": "User asks why a KPI is weak", "Guardrail": "Explain only"},
            {"Step": 2, "Action": "User requests optimization", "Guardrail": "Bound variables and constraints"},
            {"Step": 3, "Action": "Grid search optimizer runs", "Guardrail": "No more than 5 assumptions"},
            {"Step": 4, "Action": "Show before / after", "Guardrail": "Do not overwrite Base"},
            {"Step": 5, "Action": "User applies", "Guardrail": "Save as new scenario"},
        ])
        render_clickable_context_table(opt_df, "AI Optimization Workflow", source="v4 AI planning")

    elif workspace == "Versions / Audit":
        st.markdown("<div class='section-title'>Versions / Audit</div>", unsafe_allow_html=True)
        vcol1, vcol2 = st.columns(2)
        with vcol1:
            deal_name = st.text_input("Deal name", value=assumptions.property.name or "Test Deal", key="version_deal_name")
        with vcol2:
            version_label = st.text_input("Version label", value=f"v_{datetime.now().strftime('%Y%m%d_%H%M')}", key="version_label")
        if st.button("Save current deal version", type="primary"):
            save_deal_version(deal_name, version_label, assumptions, kpis)
            st.success("Deal version saved to local database.")
        st.markdown("#### Saved deal versions")
        versions = load_deal_versions(limit=25)
        render_contextual_dataframe(versions, "Saved Deal Versions", source="SQLite deal_versions", formula="Deal versions save assumption snapshots and KPI snapshots.") if not versions.empty else st.info("No saved versions yet.")
        st.markdown("#### Audit log")
        audit = load_audit_log(limit=75)
        render_contextual_dataframe(audit, "Audit Log", source="SQLite audit_log", formula="Audit rows are appended when saved/loaded/deleted actions occur.") if not audit.empty else st.info("No audit events yet.")

    else:
        st.markdown("<div class='section-title'>Engine Lab</div>", unsafe_allow_html=True)
        st.caption("This preserves the v3 diagnostic tables for continued engine testing.")
        max_month = st.slider("Display months", 12, assumptions.timeline.hold_months, min(36, assumptions.timeline.hold_months), 1)
        engine_tab_names = ["Revenue", "Unit Cohorts", "OpEx", "CapEx", "Debt", "DCF", "Formula Tree"]
        t_rev, t_unit, t_opex, t_capex, t_debt, t_dcf, t_tree = st.tabs(engine_tab_names)
        with t_rev:
            render_contextual_dataframe(dataclass_rows(revenue[: max_month + 1]).drop(columns=["unit_type_detail"], errors="ignore"), "Revenue Engine Table", source="engine.revenue.compute_revenue", formula="Revenue is computed by unit cohort rent, occupancy, concessions, other income, and credit loss.")
        with t_unit:
            render_contextual_dataframe(flatten_unit_detail(revenue, max_month), "Unit Cohort Detail", source="engine.revenue.compute_revenue", formula="Unit cohort detail splits renovated and unrenovated unit economics by month.")
        with t_opex:
            render_contextual_dataframe(dataclass_rows(opex[: max_month + 1]), "OpEx Engine Table", source="engine.opex.compute_opex", formula="NOI = EGI - total operating expenses.")
        with t_capex:
            render_contextual_dataframe(dataclass_rows(capex[: max_month + 1]), "CapEx Engine Table", source="engine.capex.compute_capex", formula="Renovation draws use an S-curve and split equity draw versus construction loan draw.")
        with t_debt:
            render_contextual_dataframe(dataclass_rows(debt[: max_month + 1]).drop(columns=["acq_loan", "const_loan", "refi_loan"], errors="ignore"), "Debt Engine Table", source="engine.debt.compute_debt", formula="Debt combines acquisition, construction, and refinance loan schedules.")
        with t_dcf:
            render_contextual_dataframe(dataclass_rows(cashflows[: max_month + 1]), "DCF Engine Table", source="engine.dcf.build_cash_flows", formula="Equity CF = NCFBT + refi proceeds + sale proceeds - GP fees - equity renovation - initial equity.")
        with t_tree:
            render_trace_dependency_controls(trace)

st.caption("v4.0 keeps all computation local: Streamlit UI, Python engine, SQLite storage. No cloud deployment or market data feeds are active yet.")
