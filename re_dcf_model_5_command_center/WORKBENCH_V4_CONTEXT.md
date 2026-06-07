# RE DCF Workbench v4.0 — Underwriting OS

Date: 2026-06-07
Status: Local proof-of-concept UX transformation. Engine math unchanged.

## Purpose
Transform the project from a diagnostic Streamlit workbench into a local underwriting operating system proof of concept.

## Stack
- Streamlit UI
- Existing Python real estate DCF engine
- SQLite local database
- Local rule-based AI Copilot shell
- No cloud deployment
- No live market data feeds

## Verified
- 43 engine tests passing
- debug_workbench_app.py compiles
- Engine math unchanged from v3.8 base

## New v4.0 UX Concepts

### Electric Blue Light Theme
- Primary electric blue: #1E88FF
- Deep navy: #0B1F3A
- Sky blue: #5CC8FF
- Light background: #F8FAFC
- White cards with clean borders

### Workspace Navigation
Sidebar now includes workspace navigation:
- Executive Dashboard
- Cash Flow Timeline
- Deal Workspace
- Scenario Lab
- Monte Carlo
- AI Copilot
- Versions / Audit
- Engine Lab

### Executive Dashboard
Adds underwriting-oriented KPI cards and deal summary:
- Levered IRR
- Unlevered IRR
- Equity Multiple
- NPV
- DSCR
- Yield on Cost
- Risk
- Confidence

Includes cash flow snapshot and risk register.

### Cash Flow Timeline
A dedicated time-axis workspace. It keeps the old real estate cash flow standard central while wrapping it in a modern interface.

Layers:
- Occupancy
- EGI
- NOI
- Debt Service
- Equity CF
- Cumulative Equity CF

### Deal Workspace
Organizes assumptions by underwriting sections:
- Acquisition
- Revenue
- Operations
- Renovation
- Financing
- Exit

Each section summarizes assumptions, impact class, and related trace node.

### Scenario Lab
Keeps saved scenario workflow and adds a more IC-style workflow:
- Recipe scenario table
- Save recipe scenario results
- Saved scenario table
- Scenario comparison by saved IDs

### Monte Carlo Command Center
Preserves Monte Carlo and reframes it as a dedicated command center.

### AI Copilot Shell
Adds local POC "Ask the Deal" panel. This is not yet connected to OpenAI. It uses current model context, selected trace node, and clicked cell context to produce rule-based explanations.

Features:
- Ask input
- Rule-based explanation for IRR, DSCR, risk, and optimization topics
- Save as insight
- Mark as garbage
- Audit log writeback

### Persistent Explain Drawer
Right-side drawer remains central:
- Selected trace node
- Formula
- Source function/file
- Dependencies
- Formula bridge
- Selected cell context
- AI Copilot

## Next Phase
v4.1 should add the local AI optimization layer:
- Structured intent parser
- Bounded grid-search optimizer
- Constraints: DSCR floor, LTV cap, max variables changed
- Top feasible scenarios
- Apply as new saved scenario only

## Market Data Layer
Not activated yet. Future hooks should support:
- SOFR
- Treasury rates
- bond yields
- regional cap rates
- regional rent growth
- market vacancy

Do not connect live feeds until UX and workflow stabilize.
