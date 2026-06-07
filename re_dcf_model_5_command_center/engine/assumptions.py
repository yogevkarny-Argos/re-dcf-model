"""
assumptions.py — All input dataclasses for the RE Acquisition & DCF Engine.
Every assumption that drives the model lives here. No calculations.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AbsorptionCurve(str, Enum):
    S_CURVE = "s_curve"      # 3t²-2t³  — default, most realistic
    CONCAVE = "concave"      # 1-e^(-kt) — fast fill, slow tail
    LINEAR  = "linear"       # straight line


class AssetType(str, Enum):
    MULTIFAMILY = "multifamily"
    MIXED_USE   = "mixed_use"
    STUDENT     = "student"
    SENIOR      = "senior"


class LoanType(str, Enum):
    FIXED       = "fixed"
    FLOATING    = "floating"


# ---------------------------------------------------------------------------
# Unit Type Assumptions  (one per bedroom type: studio/1BR/2BR/3BR)
# ---------------------------------------------------------------------------

@dataclass
class UnitTypeAssumptions:
    label: str                          # e.g. "1BR"
    count: int                          # number of units of this type
    avg_sf: float                       # average SF per unit
    in_place_rent: float                # current monthly rent $
    market_rent: float                  # current market/pro-forma rent $
    # Rent growth: key = year (1-based), value = annual growth rate
    # If year not present, uses default_rent_growth
    rent_growth_by_year: Dict[int, float] = field(default_factory=dict)
    default_rent_growth: float = 0.03  # 3% default annual

    # Market rent resets: override market_rent at a specific year
    market_rent_reset_by_year: Dict[int, float] = field(default_factory=dict)

    # Lease-up
    absorption_curve: AbsorptionCurve = AbsorptionCurve.S_CURVE
    absorption_period_months: int = 12          # months to reach stabilized occ
    absorption_speed_k: float = 0.30            # concave curve only
    in_place_occupancy: float = 0.92
    stabilized_occupancy: float = 0.94
    reno_displacement_rate: float = 0.05        # occ hit on units being renovated
    reno_start_month: int = 1                   # month renovation begins for this type
    reno_pace_units_per_month: float = 5.0      # units renovated per month

    # Concessions
    concession_weeks: float = 4.0               # weeks free rent at lease signing
    concession_burn_months: int = 18            # months over which concessions phase out

    # Loss-to-lease
    lease_term_months: int = 12
    turnover_rate_monthly: float = 0.05         # fraction of units turning per month

    # Other income (per occupied unit per month)
    parking_income: float = 0.0
    storage_income: float = 0.0
    pet_income: float = 0.0
    laundry_income: float = 0.0
    other_income: float = 0.0


# ---------------------------------------------------------------------------
# Property Assumptions
# ---------------------------------------------------------------------------

@dataclass
class PropertyAssumptions:
    name: str = "Subject Property"
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    county: str = ""
    asset_type: AssetType = AssetType.MULTIFAMILY
    year_built: int = 2000
    num_buildings: int = 1
    num_stories: int = 4
    total_site_acres: float = 4.5
    gross_building_area_sf: float = 0.0         # computed if 0
    structured_parking_spaces: int = 0
    surface_parking_spaces: int = 0

    # Unit types — list drives all revenue calculations
    unit_types: List[UnitTypeAssumptions] = field(default_factory=list)

    @property
    def total_units(self) -> int:
        return sum(u.count for u in self.unit_types)

    @property
    def total_sf(self) -> float:
        return sum(u.count * u.avg_sf for u in self.unit_types)

    @property
    def total_parking(self) -> int:
        return self.structured_parking_spaces + self.surface_parking_spaces


# ---------------------------------------------------------------------------
# Market Assumptions  (research inputs)
# ---------------------------------------------------------------------------

@dataclass
class MarketComparable:
    name: str
    address: str = ""
    units: int = 0
    year_built: int = 0
    avg_rent_per_unit: float = 0.0
    avg_rent_per_sf: float = 0.0
    occupancy: float = 0.0
    sale_price_per_unit: float = 0.0
    cap_rate: float = 0.0
    notes: str = ""


@dataclass
class MarketAssumptions:
    market_vacancy_rate: float = 0.06
    market_cap_rate_going_in: float = 0.055
    market_cap_rate_exit: float = 0.060
    cap_rate_drift_per_year: float = 0.0        # + compresses, - expands per year post-stab
    construction_cost_per_sf_hard: float = 150.0
    construction_cost_soft_pct: float = 0.18    # % of hard costs
    land_cost_per_sf: float = 0.0               # if ground-up
    vacancy_drift_by_year: Dict[int, float] = field(default_factory=dict)
    comparables: List[MarketComparable] = field(default_factory=list)
    market_notes: str = ""


# ---------------------------------------------------------------------------
# Renovation Assumptions
# ---------------------------------------------------------------------------

@dataclass
class RenovationAssumptions:
    include_renovation: bool = True
    # Hard costs
    hard_cost_per_unit: float = 15000.0
    contingency_pct: float = 0.10               # % of hard costs
    # Soft costs
    architecture_pct: float = 0.05             # % of hard costs
    permits_pct: float = 0.02
    engineering_pct: float = 0.02
    other_soft_pct: float = 0.01
    # Common area / exterior (lump sum)
    common_area_cost: float = 0.0
    exterior_cost: float = 0.0
    # Draw schedule uses S-curve over reno_period_months
    reno_period_months: int = 24               # total renovation program length

    @property
    def total_hard_cost(self) -> float:
        # Computed externally using unit counts; this gives per-unit base
        return self.hard_cost_per_unit  # placeholder; engine multiplies by units

    @property
    def soft_cost_pct(self) -> float:
        return (self.architecture_pct + self.permits_pct +
                self.engineering_pct + self.other_soft_pct)


# ---------------------------------------------------------------------------
# Acquisition Cost Assumptions
# ---------------------------------------------------------------------------

@dataclass
class AcquisitionAssumptions:
    purchase_price: float = 65_000_000.0
    closing_cost_pct: float = 0.01             # % of purchase price
    transfer_tax_pct: float = 0.005
    legal_fees: float = 75_000.0
    title_insurance_pct: float = 0.003
    broker_fee_pct: float = 0.0                # acquisition broker %
    due_diligence_cost: float = 50_000.0
    other_acquisition_costs: float = 0.0

    @property
    def total_closing_costs(self) -> float:
        pp = self.purchase_price
        return (pp * self.closing_cost_pct +
                pp * self.transfer_tax_pct +
                self.legal_fees +
                pp * self.title_insurance_pct +
                pp * self.broker_fee_pct +
                self.due_diligence_cost +
                self.other_acquisition_costs)


# ---------------------------------------------------------------------------
# OpEx Line Item
# ---------------------------------------------------------------------------

@dataclass
class OpExLine:
    label: str
    cost_per_unit_per_year: float       # base annual cost per unit
    annual_escalator: float = 0.03      # 3% default
    is_pct_of_egi: bool = False         # True for mgmt fee
    pct_of_egi: float = 0.0             # used if is_pct_of_egi=True
    is_tax_line: bool = False           # True for property tax (separate logic)


@dataclass
class OpExAssumptions:
    # Standard lines (all $/unit/yr unless flagged)
    repairs_maintenance: OpExLine = field(default_factory=lambda: OpExLine("Repairs & Maintenance", 800))
    payroll: OpExLine = field(default_factory=lambda: OpExLine("Payroll", 1500))
    general_admin: OpExLine = field(default_factory=lambda: OpExLine("General & Administrative", 300))
    marketing: OpExLine = field(default_factory=lambda: OpExLine("Marketing", 200))
    utilities: OpExLine = field(default_factory=lambda: OpExLine("Utilities", 400))
    contract_services: OpExLine = field(default_factory=lambda: OpExLine("Contract Services", 200))
    make_ready: OpExLine = field(default_factory=lambda: OpExLine("Make Ready", 300))
    management_fee: OpExLine = field(default_factory=lambda: OpExLine(
        "Management Fee", 0, is_pct_of_egi=True, pct_of_egi=0.03))
    insurance: OpExLine = field(default_factory=lambda: OpExLine("Insurance", 400))
    property_tax: OpExLine = field(default_factory=lambda: OpExLine(
        "Property Tax", 1800, is_tax_line=True))
    reserves: OpExLine = field(default_factory=lambda: OpExLine("Reserves for Replacement", 250))
    # Property tax special inputs
    assessed_value_at_purchase: float = 0.0    # if 0, use purchase price
    tax_rate: float = 0.012                    # effective tax rate
    tax_assessment_lag_months: int = 12        # months before reassessment takes effect

    def all_lines(self) -> List[OpExLine]:
        return [
            self.repairs_maintenance, self.payroll, self.general_admin,
            self.marketing, self.utilities, self.contract_services,
            self.make_ready, self.management_fee, self.insurance,
            self.property_tax, self.reserves
        ]


# ---------------------------------------------------------------------------
# Loan Assumptions
# ---------------------------------------------------------------------------

@dataclass
class LoanAssumptions:
    include: bool = True
    loan_type: LoanType = LoanType.FIXED
    ltv_or_ltc: float = 0.60               # LTV for acq; LTC for construction
    interest_rate: float = 0.065           # annual
    term_months: int = 60
    io_period_months: int = 24             # interest-only months
    amortization_years: int = 30
    origination_fee_pct: float = 0.01
    exit_fee_pct: float = 0.0
    min_dscr: float = 1.20                 # covenant (informational)
    # Floating rate spread (if loan_type=FLOATING)
    spread_over_sofr: float = 0.0
    sofr_rate: float = 0.0                 # user inputs current SOFR
    rate_cap_pct: Optional[float] = None  # if hedged


@dataclass
class ConstructionLoanAssumptions:
    include: bool = True
    max_commitment_pct_of_cost: float = 0.70  # LTC
    interest_rate: float = 0.075
    term_months: int = 24
    origination_fee_pct: float = 0.01
    interest_reserve_months: int = 6       # months of interest capitalized upfront
    draw_on_s_curve: bool = True           # False = user-defined draw schedule
    custom_draw_schedule: Dict[int, float] = field(default_factory=dict)  # month→cumulative pct


@dataclass
class RefiAssumptions:
    include: bool = True
    trigger_month: Optional[int] = None    # None = auto at stabilization_month
    ltv: float = 0.65
    interest_rate: float = 0.060
    term_months: int = 84
    io_period_months: int = 0
    amortization_years: int = 30
    origination_fee_pct: float = 0.01
    refi_costs_fixed: float = 50_000.0


# ---------------------------------------------------------------------------
# Exit Assumptions
# ---------------------------------------------------------------------------

@dataclass
class ExitAssumptions:
    exit_month: int = 60                   # month of sale
    exit_cap_rate: float = 0.060
    selling_cost_pct: float = 0.02         # broker + legal
    # Optional: alternate exit scenarios (for scenario engine)
    alt_exit_cap_rates: Dict[str, float] = field(default_factory=dict)
    alt_exit_months: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Waterfall / Partnership Assumptions
# ---------------------------------------------------------------------------

@dataclass
class WaterfallTier:
    irr_hurdle: float                      # IRR threshold for this tier
    lp_split: float                        # LP share above this hurdle
    gp_split: float                        # GP share (= 1 - lp_split)


@dataclass
class WaterfallAssumptions:
    gp_equity_pct: float = 0.05            # GP's % of total equity
    lp_equity_pct: float = 0.95
    preferred_return: float = 0.08         # annual pref return to LP
    gp_asset_mgmt_fee_pct: float = 0.015  # % of EGI per year
    gp_acquisition_fee_pct: float = 0.01  # % of purchase price at close
    gp_disposition_fee_pct: float = 0.01  # % of sale price at exit
    # Promote tiers (applied to returns above preferred_return)
    tiers: List[WaterfallTier] = field(default_factory=lambda: [
        WaterfallTier(irr_hurdle=0.08, lp_split=0.80, gp_split=0.20),
        WaterfallTier(irr_hurdle=0.12, lp_split=0.70, gp_split=0.30),
        WaterfallTier(irr_hurdle=0.16, lp_split=0.60, gp_split=0.40),
        WaterfallTier(irr_hurdle=float('inf'), lp_split=0.50, gp_split=0.50),
    ])


# ---------------------------------------------------------------------------
# Timeline Assumptions
# ---------------------------------------------------------------------------

@dataclass
class TimelineAssumptions:
    analysis_start_month: int = 0          # month index of Month 0 (close)
    hold_months: int = 60                  # total analysis horizon
    # Stabilization trigger — engine computes dynamically, but can be forced
    force_stabilization_month: Optional[int] = None
    stabilized_occ_threshold: float = 0.93
    stability_confirmation_months: int = 2  # consecutive months above threshold


# ---------------------------------------------------------------------------
# Master Assumptions Object
# ---------------------------------------------------------------------------

@dataclass
class Assumptions:
    property: PropertyAssumptions = field(default_factory=PropertyAssumptions)
    market: MarketAssumptions = field(default_factory=MarketAssumptions)
    acquisition: AcquisitionAssumptions = field(default_factory=AcquisitionAssumptions)
    renovation: RenovationAssumptions = field(default_factory=RenovationAssumptions)
    opex: OpExAssumptions = field(default_factory=OpExAssumptions)
    acq_loan: LoanAssumptions = field(default_factory=LoanAssumptions)
    const_loan: ConstructionLoanAssumptions = field(default_factory=ConstructionLoanAssumptions)
    refi: RefiAssumptions = field(default_factory=RefiAssumptions)
    exit: ExitAssumptions = field(default_factory=ExitAssumptions)
    waterfall: WaterfallAssumptions = field(default_factory=WaterfallAssumptions)
    timeline: TimelineAssumptions = field(default_factory=TimelineAssumptions)
    discount_rate: float = 0.08            # equity discount rate for NPV

    def override(self, overrides: dict) -> "Assumptions":
        """Return a shallow-merged copy with scalar overrides applied (dot-path keys)."""
        import copy
        clone = copy.deepcopy(self)
        for key, val in overrides.items():
            parts = key.split(".")
            obj = clone
            for p in parts[:-1]:
                obj = getattr(obj, p)
            setattr(obj, parts[-1], val)
        return clone
