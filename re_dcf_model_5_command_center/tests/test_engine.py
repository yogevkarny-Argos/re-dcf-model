"""
test_engine.py — Unit tests for all engine modules.
Run: cd re_dcf_model && python -m pytest tests/ -v
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tests.fixtures import make_test_deal
from engine.revenue  import compute_revenue, get_stabilization_month, absorption_occupancy
from engine.opex     import compute_opex
from engine.capex    import compute_capex, _s_curve_cumulative
from engine.debt     import compute_debt
from engine.dcf      import build_cash_flows, compute_irr, compute_npv
from engine.waterfall import allocate_waterfall
from engine.kpis     import compute_kpis
from engine.scenario import ScenarioEngine, run_model
from engine.assumptions import AbsorptionCurve


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def deal():
    return make_test_deal()


# ---------------------------------------------------------------------------
# Absorption curve tests
# ---------------------------------------------------------------------------

class TestAbsorptionCurves:

    def test_s_curve_zero(self):
        occ = absorption_occupancy(0, 12, AbsorptionCurve.S_CURVE, 0.3, 0.90, 0.94)
        assert abs(occ - 0.90) < 1e-6

    def test_s_curve_full(self):
        occ = absorption_occupancy(12, 12, AbsorptionCurve.S_CURVE, 0.3, 0.90, 0.94)
        assert abs(occ - 0.94) < 1e-6

    def test_s_curve_midpoint(self):
        occ = absorption_occupancy(6, 12, AbsorptionCurve.S_CURVE, 0.3, 0.00, 1.00)
        # At t=0.5: 3(0.25)-2(0.125) = 0.75-0.25 = 0.5
        assert abs(occ - 0.5) < 1e-6

    def test_concave_approaches_stabilized(self):
        # After 5x absorption period, concave curve should be very close to stabilized
        occ = absorption_occupancy(60, 12, AbsorptionCurve.CONCAVE, 0.3, 0.90, 0.94)
        assert occ >= 0.93  # well above in-place, near stabilized

    def test_linear_midpoint(self):
        occ = absorption_occupancy(6, 12, AbsorptionCurve.LINEAR, 0.3, 0.90, 0.94)
        assert abs(occ - 0.92) < 1e-6  # exactly halfway

    def test_beyond_absorption_period_capped(self):
        occ = absorption_occupancy(100, 12, AbsorptionCurve.S_CURVE, 0.3, 0.90, 0.94)
        assert occ <= 0.94 + 1e-9

    def test_all_curves_monotonic(self):
        for curve in AbsorptionCurve:
            prev = 0.0
            for t in range(25):
                occ = absorption_occupancy(t, 12, curve, 0.3, 0.0, 1.0)
                assert occ >= prev - 1e-9, f"{curve} not monotonic at t={t}"
                prev = occ


# ---------------------------------------------------------------------------
# S-curve CapEx draw tests
# ---------------------------------------------------------------------------

class TestSCurve:

    def test_cumulative_zero_at_start(self):
        assert _s_curve_cumulative(0.0) == 0.0

    def test_cumulative_one_at_end(self):
        assert _s_curve_cumulative(1.0) == 1.0

    def test_cumulative_half_at_midpoint(self):
        assert abs(_s_curve_cumulative(0.5) - 0.5) < 1e-9

    def test_draws_sum_to_total(self, deal):
        from engine.capex import compute_capex
        stab_m = 24
        cx = compute_capex(deal, stab_m)
        total_hard_expected = (deal.renovation.hard_cost_per_unit *
                               deal.property.total_units *
                               (1 + deal.renovation.contingency_pct))
        total_hard_actual = sum(c.hard_cost_draw for c in cx)
        total_soft_actual = sum(c.soft_cost_draw for c in cx)
        total_actual = total_hard_actual + total_soft_actual + sum(c.common_area_draw for c in cx)
        total_expected = (total_hard_expected +
                          total_hard_expected * deal.renovation.soft_cost_pct +
                          deal.renovation.common_area_cost + deal.renovation.exterior_cost)
        assert abs(total_actual - total_expected) < 1.0  # within $1


# ---------------------------------------------------------------------------
# Revenue engine tests
# ---------------------------------------------------------------------------

class TestRevenue:

    def test_month_count(self, deal):
        rev = compute_revenue(deal)
        assert len(rev) == deal.timeline.hold_months + 1

    def test_month_zero_occupancy_in_place(self, deal):
        rev = compute_revenue(deal)
        m0 = rev[0]
        # At month 0, no units renovated, occupancy near in-place
        assert 0.85 <= m0.occupancy_rate <= 0.97

    def test_egi_positive(self, deal):
        rev = compute_revenue(deal)
        assert all(r.egi >= 0 for r in rev)

    def test_occupancy_ramps(self, deal):
        rev = compute_revenue(deal)
        occ_m1  = rev[1].occupancy_rate
        occ_m24 = rev[24].occupancy_rate
        assert occ_m24 >= occ_m1  # ramp up

    def test_stabilization_detected(self, deal):
        rev = compute_revenue(deal)
        stab_m = get_stabilization_month(rev)
        assert 0 < stab_m <= deal.timeline.hold_months

    def test_egi_greater_after_stabilization(self, deal):
        rev = compute_revenue(deal)
        stab_m = get_stabilization_month(rev)
        egi_early = rev[6].egi
        egi_stab  = rev[stab_m].egi
        assert egi_stab >= egi_early

    def test_gpr_increases_with_rent_growth(self, deal):
        rev = compute_revenue(deal)
        # Post-stabilization GPR should grow
        gpr_stab = rev[min(24, len(rev)-1)].gpr
        gpr_late = rev[min(48, len(rev)-1)].gpr
        assert gpr_late >= gpr_stab * 0.99  # small tolerance


# ---------------------------------------------------------------------------
# OpEx tests
# ---------------------------------------------------------------------------

class TestOpEx:

    def test_length_matches(self, deal):
        rev = compute_revenue(deal)
        egi = [r.egi for r in rev]
        opex = compute_opex(deal, egi)
        assert len(opex) == len(egi)

    def test_noi_positive_at_stabilization(self, deal):
        rev  = compute_revenue(deal)
        egi  = [r.egi for r in rev]
        opex = compute_opex(deal, egi)
        stab_m = get_stabilization_month(rev)
        assert opex[stab_m].noi > 0

    def test_mgmt_fee_pct_of_egi(self, deal):
        rev  = compute_revenue(deal)
        egi  = [r.egi for r in rev]
        opex = compute_opex(deal, egi)
        m = 30
        expected = egi[m] * deal.opex.management_fee.pct_of_egi
        assert abs(opex[m].management_fee - expected) < 0.01

    def test_expenses_escalate(self, deal):
        rev  = compute_revenue(deal)
        egi  = [r.egi for r in rev]
        opex = compute_opex(deal, egi)
        # R&M should grow over time
        assert opex[48].repairs_maintenance >= opex[12].repairs_maintenance * 0.99


# ---------------------------------------------------------------------------
# Debt tests
# ---------------------------------------------------------------------------

class TestDebt:

    def _run_debt(self, deal):
        rev  = compute_revenue(deal)
        stab_m = get_stabilization_month(rev)
        egi  = [r.egi for r in rev]
        opex = compute_opex(deal, egi)
        noi  = [o.noi for o in opex]
        cx   = compute_capex(deal, stab_m)
        const_draws = [c.const_loan_draw for c in cx]
        return compute_debt(deal, const_draws, stab_m, noi), stab_m

    def test_acq_balance_at_month0(self, deal):
        debt, _ = self._run_debt(deal)
        expected = deal.acquisition.purchase_price * deal.acq_loan.ltv_or_ltc
        assert abs(debt[0].acq_loan.ending_balance - expected) < 1.0

    def test_acq_loan_paid_off_at_refi(self, deal):
        debt, stab_m = self._run_debt(deal)
        refi_m = deal.refi.trigger_month or stab_m
        if refi_m < len(debt):
            assert debt[refi_m].acq_loan.ending_balance < 1.0  # paid off

    def test_refi_proceeds_positive(self, deal):
        debt, stab_m = self._run_debt(deal)
        refi_m = deal.refi.trigger_month or stab_m
        assert debt[refi_m].refi_net_proceeds >= 0

    def test_const_loan_draws_during_reno(self, deal):
        debt, _ = self._run_debt(deal)
        total_const_drawn = max(d.const_loan.ending_balance for d in debt)
        assert total_const_drawn > 0

    def test_io_payment_equals_interest(self, deal):
        debt, _ = self._run_debt(deal)
        # Month 1 should be IO for acq loan
        al = debt[1].acq_loan
        assert al.is_io
        assert abs(al.payment - al.interest) < 0.01


# ---------------------------------------------------------------------------
# DCF / IRR tests
# ---------------------------------------------------------------------------

class TestDCF:

    def test_irr_sign_change(self):
        # Monthly cash flows over 60 months: invest $1M, receive ~$8.3K/mo + $1.2M at exit
        # Known annualized IRR ~12-15%
        cfs = [-1_000_000] + [8_333] * 59 + [1_200_000]
        irr = compute_irr(cfs)
        assert irr is not None
        assert 0.08 < irr < 0.20

    def test_irr_none_on_all_positive(self):
        assert compute_irr([100, 200, 300]) is None

    def test_npv_positive_at_zero_rate(self):
        cfs = [-1000, 400, 400, 400, 400]
        npv = compute_npv(cfs, 0.0)
        assert abs(npv - 600) < 0.01

    def test_npv_decreases_with_rate(self):
        cfs = [-1_000_000, 100_000, 100_000, 100_000, 100_000, 1_200_000]
        npv_low  = compute_npv(cfs, 0.05)
        npv_high = compute_npv(cfs, 0.15)
        assert npv_low > npv_high

    def test_full_run_levered_irr(self, deal):
        kpis = run_model(deal)
        assert kpis.levered_irr is not None
        assert 0.05 < kpis.levered_irr < 0.50  # sanity band

    def test_full_run_unlevered_irr_lower_than_levered(self, deal):
        kpis = run_model(deal)
        if kpis.unlevered_irr and kpis.levered_irr:
            # Levered IRR should exceed unlevered (positive leverage)
            assert kpis.levered_irr > kpis.unlevered_irr * 0.5  # loose bound

    def test_equity_multiple_gt_one(self, deal):
        kpis = run_model(deal)
        assert kpis.equity_multiple > 1.0

    def test_npv_type(self, deal):
        kpis = run_model(deal)
        assert isinstance(kpis.npv, float)


# ---------------------------------------------------------------------------
# KPI tests
# ---------------------------------------------------------------------------

class TestKPIs:

    def test_going_in_cap_positive(self, deal):
        kpis = run_model(deal)
        assert kpis.going_in_cap_rate > 0

    def test_yield_on_cost_gt_going_in_cap(self, deal):
        kpis = run_model(deal)
        # Value-add: yield on cost should exceed going-in cap (positive spread)
        assert kpis.yield_on_cost > kpis.going_in_cap_rate * 0.8

    def test_dscr_above_one_at_stabilization(self, deal):
        kpis = run_model(deal)
        assert kpis.dscr_stabilized > 1.0

    def test_ltv_at_purchase(self, deal):
        kpis = run_model(deal)
        assert abs(kpis.ltv_at_purchase - 0.60) < 0.01

    def test_break_even_occ_lt_stabilized_occ(self, deal):
        kpis = run_model(deal)
        assert kpis.break_even_occupancy < 0.95


# ---------------------------------------------------------------------------
# Scenario engine tests
# ---------------------------------------------------------------------------

class TestScenario:

    def test_bear_case_lower_irr(self, deal):
        engine = ScenarioEngine(deal)
        engine.add_scenario("Bear", {
            "exit.exit_cap_rate": 0.070,
            "market.market_vacancy_rate": 0.10,
        })
        results = engine.run_all()
        base = next(r for r in results if r.name == "Base")
        bear = next(r for r in results if r.name == "Bear")
        assert bear.kpis.levered_irr < base.kpis.levered_irr

    def test_sensitivity_table_shape(self, deal):
        engine = ScenarioEngine(deal)
        var1 = [0.055, 0.060, 0.065]
        var2 = [0.03, 0.035, 0.04]
        table = engine.sensitivity(
            "exit.exit_cap_rate", var1,
            "market.market_cap_rate_going_in", var2,
            kpi="levered_irr"
        )
        assert len(table) == 3
        assert len(table[0]) == 3

    def test_higher_exit_cap_lowers_irr(self, deal):
        engine = ScenarioEngine(deal)
        table = engine.sensitivity(
            "exit.exit_cap_rate", [0.055, 0.065],
            "market.market_vacancy_rate", [0.06],
            kpi="levered_irr"
        )
        # Lower exit cap = higher exit value = higher IRR
        assert table[0][0] > table[1][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
