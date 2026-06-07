"""
fixtures.py — Canonical synthetic deal for unit testing.
300-unit value-add multifamily, mirrors colleague's model structure.
"""

from engine.assumptions import (
    Assumptions, PropertyAssumptions, UnitTypeAssumptions, AbsorptionCurve,
    MarketAssumptions, AcquisitionAssumptions, RenovationAssumptions,
    OpExAssumptions, OpExLine, LoanAssumptions, ConstructionLoanAssumptions,
    RefiAssumptions, ExitAssumptions, WaterfallAssumptions, WaterfallTier,
    TimelineAssumptions,
)


def make_test_deal() -> Assumptions:
    """
    300-unit value-add deal.
    Purchase: $65M, Reno: $4.5M hard, 24-month program, 36-month hold.
    Acq loan: 60% LTV, 6.5%, 24-month IO, 30yr amort.
    Refi at stabilization (month 24), exit month 60.
    """

    unit_types = [
        UnitTypeAssumptions(
            label="Studio",
            count=60,
            avg_sf=520,
            in_place_rent=1_200,
            market_rent=1_450,
            in_place_occupancy=0.90,
            stabilized_occupancy=0.94,
            absorption_curve=AbsorptionCurve.S_CURVE,
            absorption_period_months=12,
            reno_start_month=1,
            reno_pace_units_per_month=2.5,
            concession_weeks=4,
            concession_burn_months=18,
            lease_term_months=12,
            default_rent_growth=0.03,
            parking_income=0,
        ),
        UnitTypeAssumptions(
            label="1BR",
            count=150,
            avg_sf=750,
            in_place_rent=1_592,
            market_rent=1_831,
            in_place_occupancy=0.92,
            stabilized_occupancy=0.94,
            absorption_curve=AbsorptionCurve.S_CURVE,
            absorption_period_months=14,
            reno_start_month=1,
            reno_pace_units_per_month=6.25,
            concession_weeks=4,
            concession_burn_months=18,
            lease_term_months=12,
            default_rent_growth=0.03,
            parking_income=50,
        ),
        UnitTypeAssumptions(
            label="2BR",
            count=75,
            avg_sf=1_000,
            in_place_rent=1_950,
            market_rent=2_250,
            in_place_occupancy=0.93,
            stabilized_occupancy=0.95,
            absorption_curve=AbsorptionCurve.CONCAVE,
            absorption_period_months=16,
            absorption_speed_k=0.25,
            reno_start_month=1,
            reno_pace_units_per_month=3.125,
            concession_weeks=6,
            concession_burn_months=24,
            lease_term_months=12,
            default_rent_growth=0.03,
            parking_income=75,
        ),
        UnitTypeAssumptions(
            label="3BR",
            count=15,
            avg_sf=1_300,
            in_place_rent=2_300,
            market_rent=2_700,
            in_place_occupancy=0.95,
            stabilized_occupancy=0.96,
            absorption_curve=AbsorptionCurve.LINEAR,
            absorption_period_months=12,
            reno_start_month=3,
            reno_pace_units_per_month=0.625,
            concession_weeks=4,
            concession_burn_months=18,
            lease_term_months=12,
            default_rent_growth=0.03,
            parking_income=100,
        ),
    ]

    prop = PropertyAssumptions(
        name="300 Elm Apartments",
        address="300 Elm Street",
        city="Austin",
        state="TX",
        zip_code="78701",
        year_built=2002,
        num_buildings=1,
        num_stories=4,
        total_site_acres=4.5,
        structured_parking_spaces=285,
        surface_parking_spaces=55,
        unit_types=unit_types,
    )

    market = MarketAssumptions(
        market_vacancy_rate=0.06,
        market_cap_rate_going_in=0.055,
        market_cap_rate_exit=0.060,
        cap_rate_drift_per_year=0.0,
        construction_cost_per_sf_hard=150.0,
        construction_cost_soft_pct=0.18,
    )

    acq = AcquisitionAssumptions(
        purchase_price=65_325_000,
        closing_cost_pct=0.005,
        transfer_tax_pct=0.003,
        legal_fees=75_000,
        title_insurance_pct=0.002,
        broker_fee_pct=0.0,
        due_diligence_cost=50_000,
    )

    reno = RenovationAssumptions(
        include_renovation=True,
        hard_cost_per_unit=15_000,
        contingency_pct=0.10,
        architecture_pct=0.04,
        permits_pct=0.02,
        engineering_pct=0.02,
        other_soft_pct=0.01,
        common_area_cost=300_000,
        exterior_cost=200_000,
        reno_period_months=24,
    )

    opex = OpExAssumptions(
        repairs_maintenance=OpExLine("Repairs & Maintenance", 516, annual_escalator=0.03),
        payroll=OpExLine("Payroll", 1317, annual_escalator=0.03),
        general_admin=OpExLine("General & Administrative", 800, annual_escalator=0.03),
        marketing=OpExLine("Marketing", 433, annual_escalator=0.03),
        utilities=OpExLine("Utilities", 600, annual_escalator=0.03),
        contract_services=OpExLine("Contract Services", 200, annual_escalator=0.03),
        make_ready=OpExLine("Make Ready", 300, annual_escalator=0.03),
        management_fee=OpExLine("Management Fee", 0, is_pct_of_egi=True, pct_of_egi=0.03),
        insurance=OpExLine("Insurance", 400, annual_escalator=0.03),
        property_tax=OpExLine("Property Tax", 1_800, annual_escalator=0.02, is_tax_line=True),
        reserves=OpExLine("Reserves", 0),   # carried in capex.py
        assessed_value_at_purchase=65_325_000,
        tax_rate=0.0083,
        tax_assessment_lag_months=12,
    )

    acq_loan = LoanAssumptions(
        include=True,
        ltv_or_ltc=0.60,
        interest_rate=0.065,
        term_months=60,
        io_period_months=24,
        amortization_years=30,
        origination_fee_pct=0.01,
    )

    const_loan = ConstructionLoanAssumptions(
        include=True,
        max_commitment_pct_of_cost=0.70,
        interest_rate=0.075,
        term_months=24,
        origination_fee_pct=0.01,
        draw_on_s_curve=True,
    )

    refi = RefiAssumptions(
        include=True,
        trigger_month=24,
        ltv=0.65,
        interest_rate=0.060,
        term_months=84,
        io_period_months=0,
        amortization_years=30,
        origination_fee_pct=0.01,
        refi_costs_fixed=50_000,
    )

    exit_a = ExitAssumptions(
        exit_month=60,
        exit_cap_rate=0.060,
        selling_cost_pct=0.02,
    )

    waterfall = WaterfallAssumptions(
        gp_equity_pct=0.05,
        lp_equity_pct=0.95,
        preferred_return=0.08,
        gp_asset_mgmt_fee_pct=0.015,
        gp_acquisition_fee_pct=0.01,
        gp_disposition_fee_pct=0.01,
        tiers=[
            WaterfallTier(0.08, 0.80, 0.20),
            WaterfallTier(0.12, 0.70, 0.30),
            WaterfallTier(0.16, 0.60, 0.40),
            WaterfallTier(float('inf'), 0.50, 0.50),
        ],
    )

    timeline = TimelineAssumptions(
        hold_months=60,
        force_stabilization_month=None,
        stabilized_occ_threshold=0.93,
        stability_confirmation_months=2,
    )

    return Assumptions(
        property=prop,
        market=market,
        acquisition=acq,
        renovation=reno,
        opex=opex,
        acq_loan=acq_loan,
        const_loan=const_loan,
        refi=refi,
        exit=exit_a,
        waterfall=waterfall,
        timeline=timeline,
        discount_rate=0.08,
    )
