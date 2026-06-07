# RE DCF Workbench v3.1 Context

## Purpose
v3.1 adds real formula traceability on top of the working real estate DCF engine and v3 local persistence layer.

## Important
This version does not change core financial math. It adds a trace layer in `debug_workbench_app.py` that reads the existing engine outputs and explains how each major KPI/output was produced.

## Verified Baseline
- Existing test suite: 43 passed.
- Prior fixed engine issues retained:
  - IRR numerical underflow guardrails.
  - Unlevered IRR includes terminal sale proceeds.

## New v3.1 Features
- `cashflow_trace_table(...)`: builds month-level bridge rows from actual engine output.
- `build_formula_trace(...)`: creates live trace nodes for:
  - Levered IRR
  - Unlevered IRR
  - Equity CF
  - NOI
  - Exit Value
  - Refi Proceeds
  - DSCR Stabilized
  - Yield on Cost
- Formula Trace Drawer now shows:
  - Current value
  - Formula
  - Source function
  - Source file
  - Dependencies
  - Warnings
  - Bridge rows
  - Month-level trace table
- Formula Trace Explorer nodes route to the live trace drawer.
- Local SQLite persistence from v3 remains:
  - assumption metadata
  - scenario results
  - deal versions
  - audit log

## Run
```bash
python3 -m pytest tests -v
python3 -m streamlit run debug_workbench_app.py
```

## Notes
This is still a diagnostic workbench, not the final production UX.
