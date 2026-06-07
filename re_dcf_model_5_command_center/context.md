# RE Acquisition & DCF Model — Context File
**Date:** 2026-06-05  
**Status:** Engine + tests complete. UI/API/chart layers are stubs pending next phase.

---

## Reference Deal (Synthetic Test — 300-Unit Value-Add, Austin TX)
| KPI | Value |
|---|---|
| Levered IRR | 14.0% |
| Unlevered IRR | −32.0% (heavy leverage effect in construction period) |
| Equity Multiple | 1.68x |
| CoC Year 1 | 3.5% |
| CoC Stabilized | 3.6% |
| NPV (8% discount) | $6.03M |
| Going-in Cap | 4.98% |
| Stabilized Cap | 7.01% |
| Exit Cap | 6.00% |
| Yield on Cost | 6.36% |
| Development Spread | 86 bps |
| Profit on Cost | 20.6% |
| DSCR (stabilized) | 1.80x |
| LTV at Purchase | 60.0% |
| LTV at Refi | 67.1% |
| Stabilization Month | 22 |
| Break-even Occupancy | 29.7% |

---

## Project Structure

```
re_dcf_model/
├── engine/
│   ├── __init__.py
│   ├── assumptions.py   — All Pydantic-style dataclasses (master input object)
│   ├── revenue.py       — Dual-cohort lease-up + plateau engine
│   ├── opex.py          — Per-line expense stack with escalators
│   ├── capex.py         — S-curve reno draws + ongoing reserves
│   ├── debt.py          — Acq loan, const loan, refi, exit payoff
│   ├── dcf.py           — Monthly CF assembly, NPV, IRR (bisection+NR)
│   ├── waterfall.py     — GP/LP promote allocation
│   ├── kpis.py          — All 15 industry KPIs
│   └── scenario.py      — ScenarioEngine + 2-var sensitivity table
├── tests/
│   ├── __init__.py
│   ├── fixtures.py      — Canonical 300-unit test deal
│   └── test_engine.py   — 43 unit tests, all passing
├── ui/                  — PLACEHOLDER (not built)
│   ├── chart.html       — DCF interactive chart (Plotly)
│   └── kpi_dashboard.html
├── models.py            — PLACEHOLDER (data layer / DB schema)
├── api.py               — PLACEHOLDER (FastAPI stubs)
└── context.md           — This file
```

---

## Architecture Decisions

### Revenue Engine — Dual Cohort
Two cohorts tracked per unit type per month:
- **Cohort A (unrenovated):** in-place rents × blended occupancy with loss-to-lease burn-off
- **Cohort B (renovated):** market rents × absorption curve occupancy − concessions

Three absorption curve options per unit type: S-curve (default), Concave (1−e^−kt), Linear.

Stabilization is formula-triggered: first month where blended occupancy ≥ threshold for N consecutive months. Can be force-overridden via `force_stabilization_month`.

### Debt Stack
- **Acquisition loan:** standard amortizing with configurable IO period. Paid off at refi.
- **Construction loan:** interest capitalized into balance (drawn on S-curve). Paid off at refi.
- **Refi loan:** sized as `(stabilized NOI × 12 / market_cap_rate) × LTV`. Net proceeds flow into equity CF.
- **Exit:** loan payoff netted against gross sale proceeds in DCF. Not recorded as debt service (avoids double-count).

### IRR Solver
Bisection scan (−5% to +100% monthly) to find sign-change bracket, then Newton-Raphson refinement. Returns annualized rate: `(1 + r_monthly)^12 − 1`. Returns `None` if no sign change or no convergence.

### Scenario Engine
`ScenarioEngine.override()` uses dot-path keys (`"exit.exit_cap_rate"`, `"market.market_vacancy_rate"`) on a deep copy of `Assumptions`. 2-variable sensitivity table returns a 2D array of any KPI.

### Known Limitations / Next Phase Items
1. **Unlevered IRR** is negative in construction-heavy deals due to large upfront outflows and capitalized const interest — expected behavior; display note needed in UI.
2. **Waterfall** uses simplified pref calc (flat × years). Replace with month-by-month preferred accrual for precision.
3. **Floating rate** debt (SOFR + spread) modeled as fixed effective rate. Forward curve integration (Chatham) is a future input source.
4. **Tax / depreciation** not modeled (after-tax IRR is a future module).
5. **Ground-up / land cost** path exists in assumptions but capex engine only covers value-add renovation today.

---

## Key Formulas

### S-Curve (absorption + capex draws)
`f(t) = 3t² − 2t³`, t ∈ [0,1]

### Concave Absorption
`f(t) = 1 − e^(−k·t)`, normalized by absorption_period

### Amortizing Payment
`PMT = B × r(1+r)^n / ((1+r)^n − 1)`

### Exit Value
`Exit Value = NOI[exit_month] × 12 / exit_cap_rate`

### Refi Loan Sizing
`Refi Loan = (NOI[refi_month] × 12 / market_cap_rate) × refi_LTV`

### IRR (monthly → annual)
`IRR_annual = (1 + r_monthly)^12 − 1`

### Development Spread
`Dev Spread (bps) = (Yield on Cost − Market Cap Rate) × 10,000`

---

## Running Tests
```bash
cd re_dcf_model
python -m pytest tests/ -v -p no:cacheprovider
# Expected: 43 passed
```

## Running a Deal
```python
from engine.scenario import run_model
from tests.fixtures import make_test_deal

assumptions = make_test_deal()  # or build your own Assumptions object
kpis = run_model(assumptions)
print(f"Levered IRR: {kpis.levered_irr:.1%}")
print(f"Equity Multiple: {kpis.equity_multiple:.2f}x")
```

## Running Scenarios
```python
from engine.scenario import ScenarioEngine
from tests.fixtures import make_test_deal

engine = ScenarioEngine(make_test_deal())
engine.add_scenario("Bear", {"exit.exit_cap_rate": 0.070, "market.market_vacancy_rate": 0.10})
engine.add_scenario("Bull", {"exit.exit_cap_rate": 0.050, "market.market_vacancy_rate": 0.04})
results = engine.run_all()

# 2-variable sensitivity
table = engine.sensitivity(
    "exit.exit_cap_rate",         [0.050, 0.055, 0.060, 0.065, 0.070],
    "market.market_vacancy_rate", [0.04,  0.06,  0.08,  0.10],
    kpi="levered_irr"
)
```
