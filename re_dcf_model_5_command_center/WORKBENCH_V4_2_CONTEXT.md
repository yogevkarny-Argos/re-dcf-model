# RE DCF Workbench v4.2 - Contextual Navigation + Filtered Live Editor

## Status
- Built from v4.1 Contextual UX package.
- Engine math unchanged.
- Test suite verified: 43 passed.

## Main UX Changes
1. Replaced fixed workspace radio list with hierarchical sidebar navigation.
2. Deal Workspace now opens as a submenu with section buttons:
   - Acquisition
   - Revenue
   - Operations
   - Renovation
   - Financing
   - Exit
3. Sidebar live editor is now filtered to the active workspace/submenu.
4. Removed the extra contextual summary panel from the sidebar to avoid clutter.
5. Deal Workspace text now explicitly says the sidebar editor is filtered to the selected section only.

## Design Intent
The sidebar should behave like a contextual editor, not a global Excel-style input dump.
The selected workspace controls which assumptions are editable.
Hidden assumptions preserve their prior Streamlit state so model runs remain stable.

## Verified
- python3 -m pytest tests -q
- Result: 43 passed
