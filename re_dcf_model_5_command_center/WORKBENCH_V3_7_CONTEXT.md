# RE DCF Workbench v3.7 Context Cells + Monte Carlo

Date: 2026-06-07

## Status
- Based on v3.6 Scenario Manager.
- Engine math unchanged.
- Python compile check passed.
- Test suite: 43 passed.

## Added in v3.7

### Context-enabled table cells
- Added a selected cell context section to the Formula Trace Drawer.
- Added clickable compact tables for smaller diagnostic lists.
- Added fallback cell inspectors for larger/wider engine tables.
- Clicking or selecting a cell sends the table name, row label, column, value, source, and context into the right drawer.

### Monte Carlo Risk Layer
- Added local Monte Carlo simulation tab.
- Perturbs current active assumptions across:
  - exit cap rate
  - rent growth
  - hard cost per unit
  - debt rates
  - stabilized occupancy
- Outputs:
  - IRR P10 / median / P90
  - NPV P10
  - failure rate under an 8% levered IRR threshold
  - IRR histogram
  - simulation result table
  - driver correlations to levered IRR

## Notes
- The Monte Carlo uses simple independent normal shocks for diagnostic testing.
- It is not a production risk model yet.
- Future work should support saved MC runs, user-defined distributions, covariance, market data feeds, and scenario-linked simulations.
