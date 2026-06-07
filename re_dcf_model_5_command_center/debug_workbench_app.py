"""
RE DCF Model 5 - Investor Command Center

Purpose:
- Experimental investor-lens UX sitting on top of the existing underwriting engine.
- Engine math remains unchanged.
- V4.2 Analyst Workbench preserved as analyst_workbench_v4_2.py.

Run:
    python3 -m pip install -r requirements_debug.txt
    python3 -m streamlit run debug_workbench_app.py
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any, Dict, List, Tuple

import pandas as pd
import streamlit as st

from tests.fixtures import make_test_deal
from engine.revenue import compute_revenue, get_stabilization_month
from engine.opex import compute_opex
from engine.capex import compute_capex
from engine.debt import compute_debt
from engine.dcf import build_cash_flows, compute_irr
from engine.waterfall import allocate_waterfall
from engine.kpis import compute_kpis

APP_VERSION = "Model 5.0 - Investor Command Center Experiment"

# =============================================================================
# Page / style
# =============================================================================

st.set_page_config(
    page_title="RE DCF Command Center",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root{
        --blue:#1E88FF;
        --sky:#5CC8FF;
        --navy:#0B1F3A;
        --bg:#F8FAFC;
        --card:#FFFFFF;
        --line:#D8E7F7;
        --muted:#64748B;
        --good:#16A34A;
        --warn:#F59E0B;
        --bad:#DC2626;
      }
      .block-container {padding-top: 1.0rem; padding-bottom: 2rem; max-width: 1500px;}
      [data-testid="stSidebar"] {background: #F3F8FF; border-right: 1px solid #D8E7F7;}
      .v5-banner {border:1px solid #BFDFFF; background:linear-gradient(90deg,#EAF5FF,#FFFFFF); border-radius:14px; padding:10px 14px; color:#0B1F3A; font-weight:700; margin-bottom:10px;}
      .deal-header {border:1px solid #D8E7F7; background:#FFFFFF; border-radius:18px; padding:18px 20px; box-shadow: 0 2px 10px rgba(30,136,255,.07); margin-bottom:12px;}
      .deal-title {font-size:28px; color:#0B1F3A; font-weight:800; margin-bottom:2px;}
      .deal-subtitle {font-size:14px; color:#64748B;}
      .metric-card {border:1px solid #D8E7F7; background:#FFFFFF; border-radius:16px; padding:14px 16px; box-shadow: 0 2px 8px rgba(30,136,255,.06); min-height:104px;}
      .metric-label {font-size:12px; color:#64748B; text-transform:uppercase; letter-spacing:.06em; font-weight:700;}
      .metric-value {font-size:28px; color:#0B1F3A; font-weight:800; margin-top:4px;}
      .metric-sub {font-size:12px; color:#64748B; margin-top:2px;}
      .lens-card {border:1px solid #D8E7F7; background:#FFFFFF; border-radius:16px; padding:14px 16px; margin-bottom:10px;}
      .panel-title {font-size:17px; color:#0B1F3A; font-weight:800; margin-bottom:6px;}
      .small-muted {font-size:12px; color:#64748B;}
      .risk-low {color:#16A34A; font-weight:800;}
      .risk-med {color:#F59E0B; font-weight:800;}
      .risk-high {color:#DC2626; font-weight:800;}
      .thesis-box {border:1px solid #BFDFFF; background:#F8FBFF; border-radius:16px; padding:14px 16px; margin-bottom:12px;}
      .section-chip {display:inline-block; padding:5px 10px; border:1px solid #BFDFFF; color:#0B1F3A; background:#EAF5FF; border-radius:999px; font-size:12px; font-weight:700; margin-right:6px; margin-bottom:6px;}
      .warning-box {border-left:4px solid #F59E0B; background:#FFFBEB; padding:10px 12px; border-radius:10px; margin-bottom:8px; color:#0B1F3A;}
      .good-box {border-left:4px solid #16A34A; background:#F0FDF4; padding:10px 12px; border-radius:10px; margin-bottom:8px; color:#0B1F3A;}
      .bad-box {border-left:4px solid #DC2626; background:#FEF2F2; padding:10px 12px; border-radius:10px; margin-bottom:8px; color:#0B1F3A;}
    </style>
    """,
    unsafe_allow_html=True,
)

# =============================================================================
# Formatting
# =============================================================================

def money(x: Any) -> str:
    try:
        v = float(x)
    except Exception:
        return "—"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000:
        return f"{sign}${v/1_000_000:,.2f}M"
    if v >= 1_000:
        return f"{sign}${v/1_000:,.0f}K"
    return f"{sign}${v:,.0f}"


def pct(x: Any) -> str:
    try:
        return f"{float(x)*100:,.2f}%"
    except Exception:
        return "—"


def xmult(x: Any) -> str:
    try:
        return f"{float(x):,.2f}x"
    except Exception:
        return "—"


def card(label: str, value: str, sub: str = "") -> str:
    return f"""
    <div class="metric-card">
      <div class="metric-label">{label}</div>
      <div class="metric-value">{value}</div>
      <div class="metric-sub">{sub}</div>
    </div>
    """


def safe(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default

# =============================================================================
# Engine run
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


if "base_assumptions" not in st.session_state:
    st.session_state.base_assumptions = make_test_deal()

if "selected_context" not in st.session_state:
    st.session_state.selected_context = {
        "title": "Deal Overview",
        "body": "Select a KPI, chart, or table row to inspect it here.",
        "formula": "",
        "source": "Command Center",
    }


def set_context(title: str, body: str, formula: str = "", source: str = "") -> None:
    st.session_state.selected_context = {
        "title": title,
        "body": body,
        "formula": formula,
        "source": source,
    }


# =============================================================================
# Assumption editing by active lens
# =============================================================================

def build_assumptions_for_lens(lens: str):
    a = deepcopy(st.session_state.base_assumptions)
    st.sidebar.markdown(f"### Live Editor")
    st.sidebar.caption(f"Filtered to current lens: {lens}")

    # Always visible deal selector, minimal.
    with st.sidebar.expander("Deal identity", expanded=False):
        a.property.name = st.text_input("Deal name", a.property.name)
        a.property.city = st.text_input("City", a.property.city)
        a.property.state = st.text_input("State", a.property.state)

    if lens == "Returns":
        with st.sidebar.expander("Return drivers", expanded=True):
            a.acquisition.purchase_price = st.number_input("Purchase price", value=float(a.acquisition.purchase_price), step=250_000.0)
            a.exit.exit_month = int(st.slider("Hold period / exit month", 24, 120, int(a.exit.exit_month), 6))
            a.exit.exit_cap_rate = st.slider("Exit cap rate", 0.035, 0.085, float(a.exit.exit_cap_rate), 0.001)
            for u in a.property.unit_types:
                u.default_rent_growth = st.slider(f"{u.label} rent growth", 0.0, 0.08, float(u.default_rent_growth), 0.0025)
        with st.sidebar.expander("Refi return impact", expanded=False):
            a.refi.ltv = st.slider("Refi LTV", 0.40, 0.80, float(a.refi.ltv), 0.01)
            a.refi.interest_rate = st.slider("Refi rate", 0.03, 0.10, float(a.refi.interest_rate), 0.001)

    elif lens == "Risk":
        with st.sidebar.expander("Risk variables", expanded=True):
            a.exit.exit_cap_rate = st.slider("Exit cap rate", 0.035, 0.085, float(a.exit.exit_cap_rate), 0.001)
            a.market.market_vacancy_rate = st.slider("Market vacancy", 0.02, 0.15, float(a.market.market_vacancy_rate), 0.005)
            a.acq_loan.interest_rate = st.slider("Acquisition loan rate", 0.03, 0.11, float(a.acq_loan.interest_rate), 0.001)
            a.refi.interest_rate = st.slider("Refi rate", 0.03, 0.11, float(a.refi.interest_rate), 0.001)
        with st.sidebar.expander("Cost overrun assumptions", expanded=False):
            a.renovation.hard_cost_per_unit = st.number_input("Hard cost / unit", value=float(a.renovation.hard_cost_per_unit), step=500.0)
            a.renovation.contingency_pct = st.slider("Contingency", 0.0, 0.35, float(a.renovation.contingency_pct), 0.01)

    elif lens == "Capital":
        with st.sidebar.expander("Acquisition debt", expanded=True):
            a.acq_loan.ltv_or_ltc = st.slider("Acquisition LTV", 0.35, 0.80, float(a.acq_loan.ltv_or_ltc), 0.01)
            a.acq_loan.interest_rate = st.slider("Acquisition loan rate", 0.03, 0.11, float(a.acq_loan.interest_rate), 0.001)
            a.acq_loan.interest_only_months = int(st.slider("IO period", 0, 60, int(a.acq_loan.interest_only_months), 1))
        with st.sidebar.expander("Refinance", expanded=True):
            a.refi.ltv = st.slider("Refi LTV", 0.40, 0.80, float(a.refi.ltv), 0.01)
            a.refi.interest_rate = st.slider("Refi rate", 0.03, 0.11, float(a.refi.interest_rate), 0.001)
            a.refi.trigger_month = int(st.slider("Refi trigger month", 12, 72, int(a.refi.trigger_month or 24), 1))

    elif lens == "Operations":
        with st.sidebar.expander("Revenue / occupancy", expanded=True):
            for u in a.property.unit_types:
                u.in_place_occupancy = st.slider(f"{u.label} in-place occ", 0.70, 1.00, float(u.in_place_occupancy), 0.005)
                u.stabilized_occupancy = st.slider(f"{u.label} stabilized occ", 0.80, 1.00, float(u.stabilized_occupancy), 0.005)
                u.market_rent = st.number_input(f"{u.label} market rent", value=float(u.market_rent), step=25.0)
        with st.sidebar.expander("Operating expenses", expanded=False):
            a.opex.repairs_maintenance.cost_per_unit_per_year = st.number_input("R&M / unit / yr", value=float(a.opex.repairs_maintenance.cost_per_unit_per_year), step=25.0)
            a.opex.payroll.cost_per_unit_per_year = st.number_input("Payroll / unit / yr", value=float(a.opex.payroll.cost_per_unit_per_year), step=25.0)
            a.opex.property_tax.cost_per_unit_per_year = st.number_input("Property tax / unit / yr", value=float(a.opex.property_tax.cost_per_unit_per_year), step=25.0)
            a.opex.management_fee.pct_of_egi = st.slider("Management fee", 0.0, 0.08, float(a.opex.management_fee.pct_of_egi), 0.0025)

    elif lens == "Exit":
        with st.sidebar.expander("Exit assumptions", expanded=True):
            a.exit.exit_month = int(st.slider("Exit month", 24, 120, int(a.exit.exit_month), 6))
            a.exit.exit_cap_rate = st.slider("Exit cap rate", 0.035, 0.085, float(a.exit.exit_cap_rate), 0.001)
            a.exit.selling_cost_pct = st.slider("Selling costs", 0.0, 0.06, float(a.exit.selling_cost_pct), 0.0025)
            a.waterfall.gp_disposition_fee_pct = st.slider("Disposition fee", 0.0, 0.04, float(a.waterfall.gp_disposition_fee_pct), 0.0025)
        with st.sidebar.expander("Exit market lens", expanded=False):
            a.market.market_cap_rate_exit = st.slider("Market exit cap benchmark", 0.035, 0.085, float(a.market.market_cap_rate_exit), 0.001)

    elif lens == "Market":
        with st.sidebar.expander("Market assumptions", expanded=True):
            a.market.market_vacancy_rate = st.slider("Market vacancy", 0.02, 0.15, float(a.market.market_vacancy_rate), 0.005)
            a.market.market_cap_rate_going_in = st.slider("Going-in market cap", 0.035, 0.085, float(a.market.market_cap_rate_going_in), 0.001)
            a.market.market_cap_rate_exit = st.slider("Exit market cap", 0.035, 0.085, float(a.market.market_cap_rate_exit), 0.001)
            a.market.construction_cost_per_sf_hard = st.number_input("Construction cost / sf hard", value=float(a.market.construction_cost_per_sf_hard), step=5.0)
        st.sidebar.info("Market data hooks only. No live data feed is active yet.")

    return a

# =============================================================================
# Derived tables and thesis
# =============================================================================

def cashflow_df(cfs) -> pd.DataFrame:
    rows = []
    for cf in cfs:
        rows.append({
            "Month": cf.month,
            "NOI": cf.noi,
            "Debt Service": cf.debt_service,
            "NCFBT": cf.ncfbt,
            "Refi Proceeds": cf.refi_proceeds,
            "Sale Proceeds": cf.sale_proceeds,
            "Equity CF": cf.equity_cf,
            "Unlevered CF": cf.unlevered_cf,
            "Cumulative Equity CF": cf.cumulative_equity_cf,
        })
    return pd.DataFrame(rows)


def summarize_risk(kpis, a) -> Tuple[str, List[str]]:
    flags: List[str] = []
    risk_score = 0
    if kpis.levered_irr is not None and kpis.levered_irr < 0.12:
        flags.append("Levered IRR below 12% target range.")
        risk_score += 2
    if kpis.dscr_stabilized < 1.35:
        flags.append("Stabilized DSCR is tight.")
        risk_score += 2
    if a.exit.exit_cap_rate < a.market.market_cap_rate_going_in:
        flags.append("Exit cap is below going-in market cap, implying cap-rate compression.")
        risk_score += 1
    if a.renovation.contingency_pct < 0.08:
        flags.append("Renovation contingency is light for value-add execution.")
        risk_score += 1
    if a.refi.ltv > 0.70:
        flags.append("Refi LTV is aggressive.")
        risk_score += 1
    if not flags:
        flags.append("No major mechanical risk flag triggered by current rule set.")
    if risk_score >= 4:
        return "High", flags
    if risk_score >= 2:
        return "Medium", flags
    return "Low", flags


def deal_score(kpis, risk_level: str) -> int:
    score = 70
    if kpis.levered_irr is not None:
        score += int(max(-15, min(20, (kpis.levered_irr - 0.12) * 100)))
    if kpis.equity_multiple > 1.6:
        score += 5
    if kpis.dscr_stabilized > 1.5:
        score += 5
    if risk_level == "High":
        score -= 15
    elif risk_level == "Medium":
        score -= 5
    return max(0, min(100, score))


def thesis_text(kpis, risk_level: str, flags: List[str], a) -> str:
    main_return = "exit value and refinance proceeds" if a.refi.include else "NOI growth and exit value"
    return (
        f"Current thesis: value-add multifamily acquisition in {a.property.city}, {a.property.state}. "
        f"The deal produces {pct(kpis.levered_irr)} levered IRR and {xmult(kpis.equity_multiple)} equity multiple under the active assumptions. "
        f"Returns are mainly driven by {main_return}. Risk is currently classified as {risk_level.lower()}. "
        f"Primary attention point: {flags[0]}"
    )


def show_context_drawer():
    ctx = st.session_state.selected_context
    st.markdown("<div class='thesis-box'>", unsafe_allow_html=True)
    st.markdown("### Explain This Number")
    st.markdown(f"**{ctx.get('title','')}**")
    st.write(ctx.get("body", ""))
    if ctx.get("formula"):
        st.code(ctx["formula"], language="text")
    if ctx.get("source"):
        st.caption(f"Source: {ctx['source']}")
    st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# Main app
# =============================================================================

st.markdown(f"<div class='v5-banner'>{APP_VERSION} | Engine unchanged | V4 Analyst Workbench archived as analyst_workbench_v4_2.py</div>", unsafe_allow_html=True)

lens = st.radio(
    "Investment lens",
    ["Returns", "Risk", "Capital", "Operations", "Exit", "Market"],
    horizontal=True,
    label_visibility="collapsed",
)

assumptions = build_assumptions_for_lens(lens)
rev, stab_m, opex, capex, debt, cfs, wf, kpis = run_all_engines(assumptions)
cfdf = cashflow_df(cfs)
risk_level, risk_flags = summarize_risk(kpis, assumptions)
score = deal_score(kpis, risk_level)
thesis = thesis_text(kpis, risk_level, risk_flags, assumptions)

# Deal header
st.markdown(
    f"""
    <div class="deal-header">
      <div class="deal-title">{assumptions.property.name}</div>
      <div class="deal-subtitle">{assumptions.property.city}, {assumptions.property.state} · {assumptions.property.total_units:,} units · Version: V5 experiment · Status: Under Review</div>
      <div style="margin-top:10px;">
        <span class="section-chip">Deal Score: {score}/100</span>
        <span class="section-chip">Risk: {risk_level}</span>
        <span class="section-chip">Stabilization: Month {stab_m}</span>
        <span class="section-chip">Exit: Month {assumptions.exit.exit_month}</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Primary KPIs
k1, k2, k3, k4, k5, k6 = st.columns(6)
with k1:
    if st.button("Inspect IRR", use_container_width=True):
        set_context("Levered IRR", "IRR is calculated from the monthly equity cash-flow stream, including operating cash flow, refi proceeds, sale proceeds, fees, renovation equity draws, and initial equity investment.", "IRR(equity_cash_flows)", "engine/kpis.py → compute_kpis; engine/dcf.py → compute_irr")
    st.markdown(card("Levered IRR", pct(kpis.levered_irr), "equity return"), unsafe_allow_html=True)
with k2:
    if st.button("Inspect EM", use_container_width=True):
        set_context("Equity Multiple", "Equity multiple compares total positive equity distributions to total negative equity contributions.", "sum(positive equity CF) / abs(sum(negative equity CF))", "engine/kpis.py")
    st.markdown(card("Equity Multiple", xmult(kpis.equity_multiple), "total out / total in"), unsafe_allow_html=True)
with k3:
    if st.button("Inspect NPV", use_container_width=True):
        set_context("NPV", "NPV discounts equity cash flows at the model discount rate.", "NPV(equity_cash_flows, discount_rate)", "engine/kpis.py; engine/dcf.py")
    st.markdown(card("NPV", money(kpis.npv), f"discount rate {pct(assumptions.discount_rate)}"), unsafe_allow_html=True)
with k4:
    if st.button("Inspect DSCR", use_container_width=True):
        set_context("DSCR Stabilized", "DSCR compares stabilized annual NOI to annual debt service at stabilization.", "Stabilized NOI / Stabilized Debt Service", "engine/kpis.py")
    st.markdown(card("DSCR", xmult(kpis.dscr_stabilized), "stabilized"), unsafe_allow_html=True)
with k5:
    if st.button("Inspect YoC", use_container_width=True):
        set_context("Yield on Cost", "Yield on cost compares stabilized NOI to total project cost.", "Stabilized NOI / Total Project Cost", "engine/kpis.py")
    st.markdown(card("Yield on Cost", pct(kpis.yield_on_cost), f"spread {kpis.development_spread_bps:,.0f} bps"), unsafe_allow_html=True)
with k6:
    st.markdown(card("Risk", risk_level, "rules-based v5 score"), unsafe_allow_html=True)

main, side = st.columns([2.4, 1.0], gap="large")

with side:
    st.markdown("<div class='thesis-box'>", unsafe_allow_html=True)
    st.markdown("### Investment Thesis")
    st.write(thesis)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='thesis-box'>", unsafe_allow_html=True)
    st.markdown("### AI Copilot")
    st.caption("Local POC shell. No API calls yet.")
    ask = st.text_input("Ask about this deal", placeholder="Why is IRR at this level?")
    if st.button("Ask", use_container_width=True):
        if ask:
            set_context("AI Copilot Draft Answer", f"Question: {ask}\n\nDraft local answer: under the current {lens} lens, the main observable drivers are IRR {pct(kpis.levered_irr)}, exit cap {pct(assumptions.exit.exit_cap_rate)}, DSCR {xmult(kpis.dscr_stabilized)}, and risk level {risk_level}. Full AI integration will use this selected context plus model traces.", "Context-aware answer = selected lens + KPI outputs + trace nodes + saved scenarios", "V5 AI Copilot shell")
        else:
            set_context("AI Copilot", "Enter a question first.", "", "V5 AI Copilot shell")
    st.markdown("</div>", unsafe_allow_html=True)

    show_context_drawer()

with main:
    if lens == "Returns":
        st.markdown("<div class='lens-card'>", unsafe_allow_html=True)
        st.markdown("### Returns Lens")
        c1, c2, c3 = st.columns(3)
        c1.metric("Cash-on-cash year 1", pct(kpis.cash_on_cash_year1))
        c2.metric("Cash-on-cash stabilized", pct(kpis.cash_on_cash_stabilized))
        c3.metric("Payback month", kpis.payback_month if kpis.payback_month is not None else "—")
        st.markdown("#### Equity cash-flow timeline")
        chart_df = cfdf[["Month", "Equity CF", "Cumulative Equity CF"]].set_index("Month")
        st.line_chart(chart_df, height=260)
        st.markdown("#### Return bridge")
        bridge = pd.DataFrame([
            {"Driver": "Exit sale proceeds", "Value": cfdf["Sale Proceeds"].sum(), "Relevance": "Primary terminal value driver"},
            {"Driver": "Refi proceeds", "Value": cfdf["Refi Proceeds"].sum(), "Relevance": "Mid-hold equity return enhancer"},
            {"Driver": "Operating NCFBT", "Value": cfdf["NCFBT"].sum(), "Relevance": "Recurring cash-flow driver"},
            {"Driver": "Initial equity", "Value": min(cfdf["Equity CF"]), "Relevance": "Initial capital burden"},
        ])
        st.dataframe(bridge, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    elif lens == "Risk":
        st.markdown("<div class='lens-card'>", unsafe_allow_html=True)
        st.markdown("### Risk Lens")
        for flag in risk_flags:
            klass = "bad-box" if risk_level == "High" else "warning-box" if risk_level == "Medium" else "good-box"
            st.markdown(f"<div class='{klass}'>{flag}</div>", unsafe_allow_html=True)
        st.markdown("#### Downside sensitivity snapshot")
        base_irr = kpis.levered_irr
        rows = []
        shocks = [
            ("Exit cap +50 bps", {"exit_cap": assumptions.exit.exit_cap_rate + 0.005}),
            ("Rent growth -100 bps", {"rent_growth_delta": -0.01}),
            ("Refi rate +100 bps", {"refi_rate": assumptions.refi.interest_rate + 0.01}),
            ("Hard cost +15%", {"hard_cost": assumptions.renovation.hard_cost_per_unit * 1.15}),
        ]
        for name, change in shocks:
            aa = deepcopy(assumptions)
            if "exit_cap" in change:
                aa.exit.exit_cap_rate = change["exit_cap"]
            if "rent_growth_delta" in change:
                for u in aa.property.unit_types:
                    u.default_rent_growth = max(0.0, u.default_rent_growth + change["rent_growth_delta"])
            if "refi_rate" in change:
                aa.refi.interest_rate = change["refi_rate"]
            if "hard_cost" in change:
                aa.renovation.hard_cost_per_unit = change["hard_cost"]
            kk = run_all_engines(aa)[-1]
            rows.append({"Shock": name, "IRR": kk.levered_irr, "Delta vs base": (kk.levered_irr or 0) - (base_irr or 0), "DSCR": kk.dscr_stabilized})
        st.dataframe(pd.DataFrame(rows).style.format({"IRR": "{:.2%}", "Delta vs base": "{:.2%}", "DSCR": "{:.2f}x"}), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    elif lens == "Capital":
        st.markdown("<div class='lens-card'>", unsafe_allow_html=True)
        st.markdown("### Capital Lens")
        acq_debt = assumptions.acquisition.purchase_price * assumptions.acq_loan.ltv_or_ltc if assumptions.acq_loan.include else 0
        initial_equity = assumptions.acquisition.purchase_price - acq_debt + assumptions.acquisition.total_closing_costs + assumptions.acquisition.purchase_price * assumptions.waterfall.gp_acquisition_fee_pct
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Purchase price", money(assumptions.acquisition.purchase_price))
        c2.metric("Acquisition debt", money(acq_debt))
        c3.metric("Initial equity", money(initial_equity))
        c4.metric("LTV at refi", pct(kpis.ltv_at_refi))
        debt_rows = []
        for d in debt:
            debt_rows.append({
                "Month": d.month,
                "Debt Service": d.total_debt_service,
                "Debt Balance": d.total_balance,
                "Refi Proceeds": d.refi_net_proceeds,
                "Payoff Amount": d.payoff_amount,
            })
        st.line_chart(pd.DataFrame(debt_rows).set_index("Month")[["Debt Balance", "Debt Service", "Refi Proceeds"]], height=280)
        st.dataframe(pd.DataFrame(debt_rows).head(72), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    elif lens == "Operations":
        st.markdown("<div class='lens-card'>", unsafe_allow_html=True)
        st.markdown("### Operations Lens")
        ops_df = pd.DataFrame({
            "Month": [r.month for r in rev],
            "Occupancy": [r.occupancy_rate for r in rev],
            "EGI": [r.egi for r in rev],
            "NOI": [o.noi for o in opex],
            "OpEx": [o.total for o in opex],
        })
        c1, c2, c3 = st.columns(3)
        c1.metric("Month 0 occupancy", pct(ops_df.loc[0, "Occupancy"]))
        c2.metric("Stabilized month", stab_m)
        c3.metric("Stabilized NOI", money(ops_df.loc[stab_m, "NOI"] * 12))
        st.line_chart(ops_df.set_index("Month")[["EGI", "NOI", "OpEx"]], height=280)
        st.dataframe(ops_df.head(72).style.format({"Occupancy": "{:.2%}", "EGI": "${:,.0f}", "NOI": "${:,.0f}", "OpEx": "${:,.0f}"}), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    elif lens == "Exit":
        st.markdown("<div class='lens-card'>", unsafe_allow_html=True)
        st.markdown("### Exit Lens")
        exit_m = assumptions.exit.exit_month
        exit_noi = opex[exit_m].noi * 12 if exit_m < len(opex) else opex[-1].noi * 12
        exit_value = exit_noi / assumptions.exit.exit_cap_rate if assumptions.exit.exit_cap_rate else 0
        gross_after_selling = exit_value * (1 - assumptions.exit.selling_cost_pct)
        payoff = debt[exit_m].payoff_amount if exit_m < len(debt) else 0
        disp_fee = exit_value * assumptions.waterfall.gp_disposition_fee_pct
        net_sale = gross_after_selling - payoff - disp_fee
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Exit NOI", money(exit_noi))
        c2.metric("Exit value", money(exit_value))
        c3.metric("Debt payoff", money(payoff))
        c4.metric("Net sale proceeds", money(net_sale))
        exit_bridge = pd.DataFrame([
            {"Component": "Exit NOI", "Value": exit_noi, "Formula": "NOI at exit month × 12"},
            {"Component": "Exit Value", "Value": exit_value, "Formula": "Exit NOI / Exit Cap"},
            {"Component": "Gross After Selling Costs", "Value": gross_after_selling, "Formula": "Exit Value × (1 - selling cost)"},
            {"Component": "Debt Payoff", "Value": -payoff, "Formula": "Remaining debt balance at exit"},
            {"Component": "Disposition Fee", "Value": -disp_fee, "Formula": "Exit Value × GP disposition fee"},
            {"Component": "Net Sale Proceeds", "Value": net_sale, "Formula": "Gross after costs - payoff - disposition fee"},
        ])
        st.dataframe(exit_bridge, use_container_width=True)
        if st.button("Explain exit bridge", use_container_width=True):
            set_context("Exit Bridge", "Exit value is the terminal valuation of the property. Net sale proceeds are after selling costs, debt payoff, and GP disposition fee.", "Exit Value = Exit NOI / Exit Cap", "engine/dcf.py")
        st.markdown("</div>", unsafe_allow_html=True)

    elif lens == "Market":
        st.markdown("<div class='lens-card'>", unsafe_allow_html=True)
        st.markdown("### Market Lens")
        st.info("Market data integrations are intentionally inactive. This screen is the future home for regional assumptions, cap-rate benchmarks, soft rates, bond rates, SOFR, and market-validation flags.")
        market_rows = pd.DataFrame([
            {"Assumption": "Market vacancy", "Current": pct(assumptions.market.market_vacancy_rate), "Source": "Manual", "Future Data Hook": "Regional market data"},
            {"Assumption": "Going-in market cap", "Current": pct(assumptions.market.market_cap_rate_going_in), "Source": "Manual", "Future Data Hook": "Regional cap-rate comps"},
            {"Assumption": "Exit market cap", "Current": pct(assumptions.market.market_cap_rate_exit), "Source": "Manual", "Future Data Hook": "Forward cap-rate benchmark"},
            {"Assumption": "Construction cost / sf", "Current": money(assumptions.market.construction_cost_per_sf_hard), "Source": "Manual", "Future Data Hook": "Construction cost index"},
        ])
        st.dataframe(market_rows, use_container_width=True)
        st.markdown("#### Planned external data")
        st.markdown("<span class='section-chip'>Treasuries</span><span class='section-chip'>SOFR</span><span class='section-chip'>Agency Debt</span><span class='section-chip'>Regional Cap Rates</span><span class='section-chip'>Rent Growth</span><span class='section-chip'>Vacancy</span>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# Bottom cashflow timeline, always available but compact.
st.markdown("---")
st.markdown("### Cash Flow Timeline - Golden Standard View")
st.caption("Persistent timeline across all lenses. Use it as the canonical month-by-month deal spine.")
st.area_chart(cfdf.set_index("Month")[["NOI", "Equity CF", "Cumulative Equity CF"]], height=240)

with st.expander("Raw monthly cash-flow table", expanded=False):
    st.dataframe(cfdf, use_container_width=True)
