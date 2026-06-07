"""
scenario.py — Scenario engine: named overrides + 2-variable sensitivity table.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Any, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .assumptions import Assumptions
    from .kpis import KPIs


def run_model(a: "Assumptions") -> "KPIs":
    """Full model run — import here to avoid circular imports at module level."""
    from .revenue import compute_revenue, get_stabilization_month
    from .opex    import compute_opex
    from .capex   import compute_capex
    from .debt    import compute_debt
    from .dcf     import build_cash_flows
    from .waterfall import allocate_waterfall
    from .kpis    import compute_kpis

    rev    = compute_revenue(a)
    stab_m = get_stabilization_month(rev)
    egi_series = [r.egi for r in rev]
    noi_series_opex = compute_opex(a, egi_series)
    noi_series = [o.noi for o in noi_series_opex]
    cx     = compute_capex(a, stabilization_month=stab_m)
    const_draws = [c.const_loan_draw for c in cx]
    debt   = compute_debt(a, const_draws, stab_m, noi_series)
    cfs    = build_cash_flows(rev, noi_series_opex, cx, debt, a, stab_m)
    wf     = allocate_waterfall([cf.equity_cf for cf in cfs], a)
    kpis   = compute_kpis(cfs, debt, noi_series_opex, rev, a, stab_m, wf)
    return kpis


@dataclass
class ScenarioResult:
    name: str
    overrides: Dict[str, Any]
    kpis: "KPIs"


class ScenarioEngine:
    """
    Named scenario runner + 2-variable sensitivity table.

    Usage:
        engine = ScenarioEngine(base_assumptions)
        engine.add_scenario("Bear", {"exit.exit_cap_rate": 0.065, "market.market_cap_rate_going_in": 0.060})
        results = engine.run_all()
        table = engine.sensitivity("exit.exit_cap_rate", [0.055,0.060,0.065],
                                   "market.market_vacancy_rate", [0.05,0.07,0.10],
                                   kpi="levered_irr")
    """

    def __init__(self, base: "Assumptions"):
        self.base = base
        self._scenarios: Dict[str, Dict[str, Any]] = {}

    def add_scenario(self, name: str, overrides: Dict[str, Any]) -> None:
        self._scenarios[name] = overrides

    def run_scenario(self, name: str) -> ScenarioResult:
        overrides = self._scenarios.get(name, {})
        a = self.base.override(overrides)
        kpis = run_model(a)
        return ScenarioResult(name=name, overrides=overrides, kpis=kpis)

    def run_base(self) -> ScenarioResult:
        kpis = run_model(self.base)
        return ScenarioResult(name="Base", overrides={}, kpis=kpis)

    def run_all(self) -> List[ScenarioResult]:
        results = [self.run_base()]
        for name in self._scenarios:
            results.append(self.run_scenario(name))
        return results

    def sensitivity(
        self,
        var1_path: str,
        var1_values: List[Any],
        var2_path: str,
        var2_values: List[Any],
        kpi: str = "levered_irr",
    ) -> List[List[Optional[float]]]:
        """
        2-variable sensitivity table.
        Returns a 2D list: rows = var1_values, cols = var2_values.
        """
        table: List[List[Optional[float]]] = []
        for v1 in var1_values:
            row: List[Optional[float]] = []
            for v2 in var2_values:
                a = self.base.override({var1_path: v1, var2_path: v2})
                try:
                    k = run_model(a)
                    row.append(getattr(k, kpi))
                except Exception:
                    row.append(None)
            table.append(row)
        return table
