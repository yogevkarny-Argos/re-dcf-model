# RE DCF Model 5 - Investor Command Center Experiment

Date: 2026-06-07

## Purpose

Model 5 is a UX branch, not an engine rewrite.

The goal is to test the investor command-center concept:

- Lens-based navigation
- Deal header
- Returns / Risk / Capital / Operations / Exit / Market lenses
- Investment Thesis side panel
- AI Copilot shell
- Persistent Explain This Number drawer
- Persistent cash-flow timeline

## Important

The engine is unchanged from the current tested model.

V4.2 Analyst Workbench was archived as:

`analyst_workbench_v4_2.py`

## Version Philosophy

V4 = Analyst Workbench
V5 = Investor Command Center

V5 should be judged by whether it feels like a professional investment workstation, not a wizard and not generic SaaS.

## Run

```bash
python3 -m pytest tests -v
python3 -m streamlit run debug_workbench_app.py
```

## Current Scope

Included:

- Deal header
- Lens bar
- Returns lens
- Risk lens
- Capital lens
- Operations lens
- Exit lens
- Market lens
- Investment thesis panel
- AI Copilot shell
- Cash-flow timeline
- Contextual sidebar editor filtered by active lens

Not included yet:

- Real AI calls
- Optimization engine
- Live market data
- Repository separation
- Production UI framework

## Next likely improvements

1. Better visual cash-flow timeline
2. True AI Copilot context package
3. Optimization lab
4. Scenario compare inside lens view
5. Full repo migration and module separation
