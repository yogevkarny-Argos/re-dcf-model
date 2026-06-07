# RE DCF Engine Debug Workbench

This is a temporary local interface for testing Claude's real estate DCF engine before building the production UX and database.

## Purpose

It lets you enter core assumptions and inspect what each engine produces:

- Revenue
- OpEx
- CapEx
- Debt
- DCF
- Waterfall
- KPIs
- Full assumptions object

This is **not** the final product UI. It is a design/test area.

## Run

From the `re_dcf_model` folder:

```bash
python -m pip install -r requirements_debug.txt
streamlit run debug_workbench_app.py
```

Or on Mac/Linux:

```bash
./run_debug_workbench.sh
```

## What to review first

1. Change purchase price, hard cost/unit, exit cap, refi month, LTV, and rent growth.
2. Open each engine tab and check the monthly numbers.
3. Focus on formulas shown above each table.
4. Review the DCF tab carefully, especially sale proceeds, refi proceeds, equity CF, and unlevered CF.

## Known audit item

The current engine may not include unlevered terminal sale proceeds in `unlevered_cf`. If the intended definition of unlevered IRR is property-level acquisition-to-sale return, that should be fixed before productization.
