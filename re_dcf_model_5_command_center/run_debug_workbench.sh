#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python -m pip install -r requirements_debug.txt
streamlit run debug_workbench_app.py
