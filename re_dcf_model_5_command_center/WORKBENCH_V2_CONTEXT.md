# RE DCF Workbench v2 Context

Date: 2026-06-07
Status: Latest working diagnostic build

## Confirmed Baseline
- Original engine test suite: 43 passed.
- IRR underflow crash fixed in `engine/dcf.py`.
- Unlevered IRR bug fixed by adding unlevered terminal sale proceeds to `unlevered_cf` at exit month.
- Verified reference deal after fix:
  - Levered IRR: approximately 13.96%
  - Unlevered IRR: approximately 9.58%
  - Tests: 43 passed

## Purpose
Workbench v2 is not final UX. It is a professional diagnostic interface designed to expose:
- assumptions
- formula lineage
- KPI bridges
- cash flow streams
- source paths
- scenario recipes
- assumption impact

## Main Workbench v2 Features
1. Formula Drawer
   - Select major KPI/output.
   - Shows definition, formula, engine source path, source inputs, bridge table, and cash flow stream preview.

2. Command Center
   - Shows high-level bridges from Revenue to NOI, NOI to Exit Value, Debt to Refi, Exit to IRR, and Property to Unlevered IRR.

3. Formula Explorer
   - Text lineage tree for Levered IRR and major drivers.

4. Assumption Intelligence
   - One-variable shocks on key assumptions.
   - Shows levered IRR impact and impact class.

5. Scenario Recipes
   - Base
   - Exit Cap Expansion
   - Cost Overrun
   - Lease-Up Delay
   - Refi Failure
   - Rate Shock
   - Rent Recession

6. Engine Tables
   - Revenue
   - Unit Cohorts
   - OpEx
   - CapEx
   - Debt
   - DCF

## Run Instructions
From the project folder:

```bash
python3 -m pip install -r requirements_debug.txt
python3 -m streamlit run debug_workbench_app.py
```

## Current Development Rule
Do not build final production UX yet. Use this workbench to pressure-test engine behavior and trace formulas first.

## Next Build Targets
1. Clickable formula explorer nodes.
2. Editable assumption source/confidence tags.
3. Saved local scenario database.
4. Deal versioning and audit log.
5. Upgrade waterfall to monthly preferred return and capital-account logic.
