"""
diagnostics.py
==============
Process diagnostics and operator guidance ("decision support").

This module turns raw model output into **actionable advice**: it compares the
predicted heat against the operator's targets and against typical benchmark
ranges, flags problems, explains the likely cause, and recommends a concrete
set-point change.  This is the "guiding tool for the operator" layer, in the
spirit of a model-based decision-support system
("Model-Based Decision Support System for EAF Online Monitoring and Control").

Each check returns a :class:`Check` with a status:
    OK    – within target / benchmark
    WATCH – marginal; worth attention
    ACT   – out of range; a specific corrective action is suggested

Benchmark bands are conservative, plant-independent defaults; edit
:data:`BENCHMARKS` (or pass your own) to match your shop.
"""

from __future__ import annotations

from dataclasses import dataclass

# Typical modern scrap-based AC-EAF benchmark bands (edit for your plant) ----- #
BENCHMARKS = {
    "spec_electrical_kwh_t": (330.0, 430.0),   # kWh/t liquid
    "spec_total_kwh_t":      (550.0, 680.0),   # kWh/t liquid (elec + chem)
    "metallic_yield":        (0.90, 0.96),
    "basicity_B2":           (1.8, 2.6),
    "slag_FeO_pct":          (18.0, 32.0),     # % FeO in slag
    "tap_to_tap_min":        (40.0, 60.0),
    "oxygen_Nm3_t":          (25.0, 45.0),
    "electrode_kg_t":        (1.0, 2.5),
}

_ICON = {"OK": "[ OK ]", "WATCH": "[WATCH]", "ACT": "[ ACT ]"}


@dataclass
class Check:
    name: str
    status: str          # OK | WATCH | ACT
    value: str
    message: str
    recommendation: str = ""

    def __str__(self):
        s = f"{_ICON[self.status]} {self.name}: {self.value}\n        {self.message}"
        if self.recommendation:
            s += f"\n        -> {self.recommendation}"
        return s


class Diagnostics:
    """Evaluate a static and/or dynamic result and emit operator guidance."""

    def __init__(self, registry, benchmarks: dict | None = None):
        self.reg = registry
        self.bm = benchmarks or BENCHMARKS

    # ------------------------------------------------------------------ #
    def _band(self, key):
        return self.bm[key]

    def _in(self, x, key):
        lo, hi = self._band(key)
        return lo <= x <= hi

    # ================================================================== #
    #  STATIC-result diagnostics                                          #
    # ================================================================== #
    def from_static(self, res) -> list:
        p = self.reg.get
        checks: list[Check] = []
        lo, hi = self._band("spec_electrical_kwh_t")
        e = res.electrical_energy_specific
        if e > hi:
            checks.append(Check(
                "Specific electrical energy", "ACT", f"{e:.0f} kWh/t",
                "Above the typical band — the heat is 'electricity-heavy'.",
                "Add chemical energy (more O2/carbon or burners), improve slag "
                "foaming to raise arc-transfer efficiency, and cut power-off "
                "time. ~10 Nm3/t of O2 offsets roughly 30-40 kWh/t."))
        elif e < lo:
            checks.append(Check(
                "Specific electrical energy", "WATCH", f"{e:.0f} kWh/t",
                "Below the typical band — check that chemical inputs are not "
                "over-stated or the tap weight over-estimated.", ""))
        else:
            checks.append(Check("Specific electrical energy", "OK",
                                f"{e:.0f} kWh/t", "Within the typical band."))

        # yield
        y = res.metallic_yield
        if not self._in(y, "metallic_yield"):
            st = "ACT" if y < self._band("metallic_yield")[0] else "WATCH"
            checks.append(Check(
                "Metallic yield", st, f"{y*100:.1f} %",
                "Yield is off the typical band; the dominant lever is iron lost "
                "to slag as FeO.",
                "Reduce over-oxidation: trim lance O2 at low carbon, inject "
                "carbon to reduce slag FeO, and avoid over-shooting tap "
                "temperature."))
        else:
            checks.append(Check("Metallic yield", "OK", f"{y*100:.1f} %",
                                "Healthy yield."))

        # basicity
        B = res.basicity_B2
        if not self._in(B, "basicity_B2"):
            if B < self._band("basicity_B2")[0]:
                checks.append(Check(
                    "Slag basicity B2", "ACT", f"{B:.2f}",
                    "Basicity is low — acid slag attacks the lining and removes "
                    "phosphorus poorly.",
                    f"Add lime. To reach B2=2.2 you need about "
                    f"{res.lime_required_for_target:.0f} kg of lime."))
            else:
                checks.append(Check(
                    "Slag basicity B2", "WATCH", f"{B:.2f}",
                    "Basicity is high — slag may be viscous and foam poorly.",
                    "Reduce lime, or add fluidiser (e.g. a little fluorspar / "
                    "keep MgO saturation), and ensure enough FeO for fluidity."))
        else:
            checks.append(Check("Slag basicity B2", "OK", f"{B:.2f}",
                                "Basicity in range for good refining."))

        # slag FeO
        feo = res.slag.get("FeO", 0.0) / res.slag_mass * 100 if res.slag_mass else 0
        if feo > self._band("slag_FeO_pct")[1]:
            checks.append(Check(
                "Slag FeO", "ACT", f"{feo:.1f} %",
                "High FeO means the bath is over-oxidised: lost iron, higher "
                "consumption of ferroalloys at tap.",
                "Cut oxygen once carbon is near aim and inject carbon to reduce "
                "FeO and foam the slag."))
        elif feo < self._band("slag_FeO_pct")[0]:
            checks.append(Check(
                "Slag FeO", "WATCH", f"{feo:.1f} %",
                "Low FeO can make the slag hard to foam and slow "
                "dephosphorisation.", "A little more oxygen / hotter bath will "
                "raise FeO to a foamable level."))
        else:
            checks.append(Check("Slag FeO", "OK", f"{feo:.1f} %",
                                "FeO suitable for foaming and P removal."))

        # oxygen intensity
        o2t = res.oxygen_required / (res.steel_mass / 1000.0)
        checks.append(self._range_check(
            "Oxygen use", o2t, "Nm3/t", "oxygen_Nm3_t",
            act_hi="Very high O2 — expect high FeO and yield loss; verify the "
                   "carbon/energy strategy.",
            watch_lo="Low O2 — the heat leans on electricity; more O2 could cut "
                     "kWh/t."))

        # tap-to-tap
        checks.append(self._range_check(
            "Tap-to-tap time", res.tap_to_tap_min, "min", "tap_to_tap_min",
            act_hi="Long tap-to-tap hurts productivity and raises fixed energy "
                   "losses.",
            watch_lo=""))

        # phosphorus feasibility
        Ptap = res.tap_composition.get("P", 0)
        if Ptap > 0.02 and B < 2.0:
            checks.append(Check(
                "Dephosphorisation", "ACT", f"P={Ptap:.3f} %, B2={B:.2f}",
                "Tap phosphorus is high while basicity is low — P removal is "
                "thermodynamically limited.",
                "Raise basicity (lime) and keep enough FeO; a cooler, more "
                "oxidising, basic slag removes P best."))

        for n in res.notes:
            checks.append(Check("Model note", "WATCH", "-", n))
        return checks

    # ================================================================== #
    #  DYNAMIC-result diagnostics                                         #
    # ================================================================== #
    def from_dynamic(self, res) -> list:
        p = self.reg.get
        st = res.final
        checks: list[Check] = []

        # endpoint reached?
        if not res.reached_endpoint:
            checks.append(Check(
                "Endpoint", "ACT", "not reached",
                "Aim temperature and/or carbon not met in the simulated time.",
                "Increase arc power or oxygen in the flat-bath stage, or accept "
                "a longer power-on time."))
        else:
            checks.append(Check("Endpoint", "OK", "reached",
                                "Aim temperature and carbon met."))

        # temperature vs target
        Ttap = st.T_lSc - 273.15
        Ttar = p("target_tap_temperature")
        dT = Ttap - Ttar
        if abs(dT) > 15:
            st_s = "ACT" if abs(dT) > 30 else "WATCH"
            checks.append(Check(
                "Tap temperature", st_s, f"{Ttap:.0f} degC ({dT:+.0f})",
                "Bath temperature is off the aim.",
                "Overheated: reduce final-stage power / tap earlier. "
                "Too cold: extend power-on or raise final-stage power."
                if dT > 0 else
                "Too cold: extend power-on or raise final-stage power; check "
                "foaming and losses."))
        else:
            checks.append(Check("Tap temperature", "OK",
                                f"{Ttap:.0f} degC ({dT:+.0f})",
                                "On aim."))

        # carbon vs target
        Cpct = st.pct["C"]
        Ctar = p("target_carbon")
        if Cpct > Ctar + 0.02:
            checks.append(Check(
                "Tap carbon", "WATCH", f"{Cpct:.3f} %",
                "Carbon above aim — under-refined.",
                "Extend oxygen blowing at flat bath (watch FeO/yield)."))
        elif Cpct < max(Ctar - 0.02, 0.005):
            checks.append(Check(
                "Tap carbon", "WATCH", f"{Cpct:.3f} %",
                "Carbon below aim — over-blown; expect high FeO and low yield.",
                "Reduce oxygen earlier and/or inject recarburiser; add carbon "
                "to reduce slag FeO."))
        else:
            checks.append(Check("Tap carbon", "OK", f"{Cpct:.3f} %",
                                "On aim."))

        # specific electrical energy
        spec = st.E_elec_MJ / 3.6 / (st.m_lSc / 1000.0)
        checks.append(self._range_check(
            "Specific electrical energy", spec, "kWh/t",
            "spec_electrical_kwh_t",
            act_hi="Electricity-heavy heat: improve foaming, add chemical "
                   "energy, cut power-off time.",
            watch_lo="Low kWh/t — verify inputs."))

        # foaming
        foam = st.foam_index
        if foam < 0.4:
            checks.append(Check(
                "Slag foaming", "ACT", f"index {foam:.2f}",
                "Poor foam — the arc is exposed, wasting energy to the panels "
                "and stressing the lining.",
                "Increase carbon injection and keep FeO in the foamable band; "
                "check O2/carbon balance and basicity (<2.6)."))
        elif foam < 0.7:
            checks.append(Check(
                "Slag foaming", "WATCH", f"index {foam:.2f}",
                "Foam is moderate.", "Fine-tune carbon injection for a fuller "
                "foam and better arc coverage."))
        else:
            checks.append(Check("Slag foaming", "OK", f"index {foam:.2f}",
                                "Good foam — arc well covered."))

        # basicity & FeO
        checks.append(self._range_check(
            "Slag basicity B2", st.basicity, "", "basicity_B2",
            act_hi="High basicity — slag may be pasty; foam suffers.",
            watch_lo="Low basicity — add lime for P removal and lining "
                     "protection."))
        checks.append(self._range_check(
            "Slag FeO", st.feo_pct, "%", "slag_FeO_pct",
            act_hi="High FeO — over-oxidised bath, yield loss; inject carbon.",
            watch_lo="Low FeO — slag hard to foam; a little more O2 helps."))

        # productivity
        checks.append(self._range_check(
            "Tap-to-tap time", res.tap_to_tap_min, "min", "tap_to_tap_min",
            act_hi="Long heat — raise melt-in power or reduce delays.",
            watch_lo=""))

        for n in res.notes:
            checks.append(Check("Model note", "WATCH", "-", n))
        return checks

    # ------------------------------------------------------------------ #
    def _range_check(self, name, value, unit, key,
                     act_hi="", watch_lo="") -> Check:
        lo, hi = self._band(key)
        v = f"{value:.1f} {unit}".strip()
        if value > hi:
            return Check(name, "ACT", v,
                         f"Above the typical band ({lo:g}-{hi:g}).", act_hi)
        if value < lo:
            return Check(name, "WATCH", v,
                         f"Below the typical band ({lo:g}-{hi:g}).", watch_lo)
        return Check(name, "OK", v, f"Within the typical band ({lo:g}-{hi:g}).")

    # ------------------------------------------------------------------ #
    @staticmethod
    def render(checks: list) -> str:
        n_act = sum(c.status == "ACT" for c in checks)
        n_watch = sum(c.status == "WATCH" for c in checks)
        head = ("=" * 66 + "\n OPERATOR GUIDANCE  "
                f"({n_act} action(s), {n_watch} watch item(s))\n" + "=" * 66)
        return head + "\n" + "\n".join(str(c) for c in checks) + "\n" + "=" * 66
