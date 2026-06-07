# RE DCF Workbench v3.2 Trace Click Fix

## Status
- Based on v3.1 Formula Trace build.
- Core engine math unchanged.
- 43 tests passing.

## Fixes
1. Added visible app version banner at top: `v3.2 Trace Click Fix`.
2. Fixed Formula Trace Explorer node click behavior.
3. The right-side Formula Trace Drawer now uses `st.session_state.selected_formula` directly instead of a separate selectbox state key that was overwriting button clicks.

## Expected Behavior
- Clicking any node under Formula Trace Explorer changes the drawer on the right.
- The selectbox in the drawer and the node buttons now share the same session-state key.
- The app should clearly display the current version at top.
