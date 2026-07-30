"""
sensitivity.py
==============
Sensitivity-analysis engine for the EAF model.

Provides reusable functions to:
  * sweep a single parameter and collect chosen output metrics
    (``sweep_static`` / ``sweep_dynamic``),
  * collect full dynamic trajectories over a parameter
    (``sweep_dynamic_trajectories``),
  * build 2-D response grids for heatmaps
    (``grid_static`` / ``grid_dynamic``),
  * rank parameters by influence (``tornado``).

These are consumed by ``sensitivity_analysis.py`` (which draws all the plots)
and by the GUI. No plotting here -> no backend assumptions.
"""

from __future__ import annotations

from .parameters import default_parameters
from .static_model import StaticEAFModel
from .dynamic_model import DynamicEAFModel


# --------------------------------------------------------------------------- #
#  Metric extractors                                                           #
# --------------------------------------------------------------------------- #
STATIC_METRICS = {
    "elec_kwh_t":  ("Specific electrical energy", "kWh/t"),
    "total_kwh_t": ("Total specific energy", "kWh/t"),
    "chem_kwh":    ("Chemical energy", "kWh"),
    "yield_pct":   ("Metallic yield", "%"),
    "basicity":    ("Slag basicity B2", "-"),
    "feo_pct":     ("Slag FeO", "%"),
    "slag_kg":     ("Slag mass", "kg"),
    "steel_t":     ("Liquid steel", "t"),
    "o2_nm3":      ("Oxygen demand", "Nm3"),
    "taptap_min":  ("Tap-to-tap time", "min"),
}

DYNAMIC_METRICS = {
    "elec_kwh_t":   ("Specific electrical energy", "kWh/t"),
    "chem_kwh":     ("Chemical energy", "kWh"),
    "o2_nm3":       ("Oxygen used", "Nm3"),
    "taptap_min":   ("Tap-to-tap time", "min"),
    "power_on_min": ("Power-on time", "min"),
    "tap_T":        ("Tap temperature", "degC"),
    "tap_C":        ("Tap carbon", "wt-%"),
    "foam":         ("Foaming index (final)", "-"),
    "feo_pct":      ("Slag FeO (final)", "%"),
    "basicity":     ("Slag basicity (final)", "-"),
    "reached":      ("Endpoint reached", "0/1"),
}


def static_metric(res, name):
    if name == "elec_kwh_t":  return res.electrical_energy_specific
    if name == "total_kwh_t": return res.total_energy_specific
    if name == "chem_kwh":    return res.chemical_energy_kWh
    if name == "yield_pct":   return res.metallic_yield * 100
    if name == "basicity":    return res.basicity_B2
    if name == "feo_pct":     return (res.slag["FeO"] / res.slag_mass * 100
                                      if res.slag_mass else 0.0)
    if name == "slag_kg":     return res.slag_mass
    if name == "steel_t":     return res.steel_mass / 1000
    if name == "o2_nm3":      return res.oxygen_required
    if name == "taptap_min":  return res.tap_to_tap_min
    raise KeyError(name)


def dynamic_metric(res, name):
    st = res.final
    if name == "elec_kwh_t":   return st.E_elec_MJ / 3.6 / (st.m_lSc / 1000)
    if name == "chem_kwh":     return st.E_chem_MJ / 3.6
    if name == "o2_nm3":       return st.O2_used_Nm3
    if name == "taptap_min":   return res.tap_to_tap_min
    if name == "power_on_min": return st.power_on_s / 60
    if name == "tap_T":        return st.T_lSc - 273.15
    if name == "tap_C":        return st.pct["C"]
    if name == "foam":         return st.foam_index
    if name == "feo_pct":      return st.feo_pct
    if name == "basicity":     return st.basicity
    if name == "reached":      return 1.0 if res.reached_endpoint else 0.0
    raise KeyError(name)


# --------------------------------------------------------------------------- #
#  1-D sweeps                                                                   #
# --------------------------------------------------------------------------- #
def sweep_static(param, values, metrics, base=None):
    """Vary one parameter; return {metric: [values...]} for the static model."""
    base = base or default_parameters
    out = {m: [] for m in metrics}
    for v in values:
        reg = base()
        reg.set(param, v)
        res = StaticEAFModel(reg).solve()
        for m in metrics:
            out[m].append(static_metric(res, m))
    return out


def sweep_dynamic(param, values, metrics, base=None, max_time_min=120):
    """Vary one parameter; return {metric: [values...]} for the dynamic model."""
    base = base or default_parameters
    out = {m: [] for m in metrics}
    for v in values:
        reg = base()
        reg.set(param, v)
        res = DynamicEAFModel(reg).simulate(mode="endpoint",
                                            max_time_min=max_time_min)
        for m in metrics:
            out[m].append(dynamic_metric(res, m))
    return out


def sweep_dynamic_trajectories(param, values, base=None, max_time_min=120):
    """Return [(value, history, result), ...] for overlaying trajectories."""
    base = base or default_parameters
    out = []
    for v in values:
        reg = base()
        reg.set(param, v)
        res = DynamicEAFModel(reg).simulate(mode="endpoint",
                                            max_time_min=max_time_min)
        out.append((v, res.history, res))
    return out


# --------------------------------------------------------------------------- #
#  2-D response grids (for heatmaps)                                            #
# --------------------------------------------------------------------------- #
def grid_static(px, xvals, py, yvals, metric, base=None):
    """Return Z[j][i] over (x=px, y=py) for the static model."""
    base = base or default_parameters
    Z = []
    for yv in yvals:
        row = []
        for xv in xvals:
            reg = base()
            reg.set(px, xv)
            reg.set(py, yv)
            row.append(static_metric(StaticEAFModel(reg).solve(), metric))
        Z.append(row)
    return Z


def grid_dynamic(px, xvals, py, yvals, metric, base=None, max_time_min=120):
    """Return Z[j][i] over (x=px, y=py) for the dynamic model."""
    base = base or default_parameters
    Z = []
    for yv in yvals:
        row = []
        for xv in xvals:
            reg = base()
            reg.set(px, xv)
            reg.set(py, yv)
            res = DynamicEAFModel(reg).simulate(mode="endpoint",
                                                max_time_min=max_time_min)
            row.append(dynamic_metric(res, metric))
        Z.append(row)
    return Z


# --------------------------------------------------------------------------- #
#  Tornado (one-at-a-time ranking)                                             #
# --------------------------------------------------------------------------- #
def tornado(kind, params, metric, base=None, pct=0.20, max_time_min=120):
    """
    Perturb each parameter by +/- ``pct`` and measure the change in ``metric``.

    Returns (rows, base_value) where rows is a list of
    (param, metric_low, metric_high, base_value) sorted by |high-low| desc.
    """
    base = base or default_parameters

    def evaluate(reg):
        if kind == "static":
            return static_metric(StaticEAFModel(reg).solve(), metric)
        return dynamic_metric(
            DynamicEAFModel(reg).simulate(mode="endpoint",
                                          max_time_min=max_time_min), metric)

    base_val = evaluate(base())
    rows = []
    for p in params:
        p0 = base().get(p)
        reg_lo = base(); reg_lo.set(p, p0 * (1 - pct))
        reg_hi = base(); reg_hi.set(p, p0 * (1 + pct))
        rows.append((p, evaluate(reg_lo), evaluate(reg_hi), base_val))
    rows.sort(key=lambda r: abs(r[2] - r[1]), reverse=True)
    return rows, base_val
