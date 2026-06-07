# RE DCF Workbench v3.3 Stable Clickable Trace

Fixes the Formula Trace Explorer interaction bug where buttons could disappear after click because `st.rerun()` was called inside the render path.

Changes:
- App version banner: v3.3 Stable Clickable Trace.
- Formula node buttons use Streamlit `on_click` callbacks.
- Removed manual `st.rerun()` from node button render flow.
- Added clickable dependency-tree trace buttons.
- No engine math changes.
- Expected test suite: 43 passed.
