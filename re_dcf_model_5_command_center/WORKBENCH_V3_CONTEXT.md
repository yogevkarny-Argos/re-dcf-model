# RE DCF Workbench v3 Context

## Status
Workbench v3 builds on the stabilized v2 engine baseline.

Verified:
- 43 tests passed.
- IRR numerical underflow guard remains in place.
- Unlevered IRR now includes terminal unlevered sale proceeds.
- Workbench v3 adds local persistence and diagnostic UX features without changing core engine math.

## New Features

### 1. Clickable Formula Explorer Nodes
The Formula Explorer now has clickable buttons for:
- Levered IRR
- Unlevered IRR
- DSCR Stabilized
- Exit Value
- Refi Proceeds

Clicking a node routes the selected item into the right-side Formula Drawer.

### 2. Editable Assumption Source / Confidence Tags
Assumption metadata is stored in local SQLite and can be edited in the Assumption Intelligence tab.

Fields:
- field_key
- display_name
- source
- confidence
- note
- updated_at

This metadata does not alter engine calculations. It provides input provenance and audit support.

### 3. Local Scenario Results Database
Scenario Recipes tab can save scenario runs to SQLite.

Stored fields include:
- run_id
- deal_name
- scenario_name
- levered_irr
- unlevered_irr
- npv
- equity_multiple
- irr_delta
- assumptions_json
- kpis_json
- created_at

### 4. Deal Versioning and Audit Log
Audit Notes tab is now Deal Versioning & Audit Log.

It supports:
- Save current deal version
- Store assumptions JSON
- Store KPI JSON
- Display recent deal versions
- Display local audit events

### 5. Local SQLite Database
Database file:

```text
workbench_local.db
```

Created automatically in the working folder when the app launches.

## Run

```bash
python3 -m pip install -r requirements_debug.txt
python3 -m pytest tests -v
python3 -m streamlit run debug_workbench_app.py
```

## Important Limitations
- This is still a diagnostic workbench, not production UX.
- SQLite is local-only.
- No authentication or multi-user permissions.
- No cloud database.
- No external market data feeds yet.
- Formula Explorer nodes are click-based, not true hover-card UX.

## Next Suggested Build
1. Add source links from formula drawer to exact engine table rows.
2. Add scenario comparison charts.
3. Add import/export for deal JSON.
4. Add proper project folder naming and Git repo.
5. Later migrate SQLite schema to PostgreSQL for production.
