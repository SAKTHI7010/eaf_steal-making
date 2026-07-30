"""
dynamic_model.py
================
Dynamic (time-resolved) simulation of an EAF heat.

The dynamic model integrates the state of the furnace through the melt, so an
operator can see *how* temperature, chemistry, slag and energy evolve — and can
test "what-if" changes to power, oxygen, carbon and timing.

Modelling framework
-------------------
The structure follows the control-oriented, zone-based dynamic EAF model of
**Logar, Dovzan & Skrjanc, ISIJ International 52 (2012) 402 (Part 1, heat & mass
transfer) and 413 (Part 2, thermo-chemistry)** — the model those authors built
specifically for "optimisation of energy consumption and development of an
operator-training simulator", which is exactly this tool's purpose.

Retained faithfully from that work:
  * separate zones — solid scrap, liquid steel, slag, gas — each with its own
    energy balance and temperature (Part 1, Eqs. 33-37);
  * the melting-split relation (Part 1, Eqs. 42-43):
        m_dot_melt = Q_solid * (T_solid/T_melt) / (L_fus + Cp*(T_melt-T_solid))
    with the complementary heating factor (1 - T_solid/T_melt) capping the
    solid temperature at the melting point;
  * mass re-averaging of temperature when material is added (Part 1, Eq. 38);
  * CO post-combustion energy return (Part 1, Eq. 1 via K_post);
  * temperature-dependent oxy-fuel burner efficiency (Part 1, Eq. 3).

Deliberately reduced for usability and calibratability: the full geometric
view-factor radiation network of Part 1 (Section 2.2.1) is replaced by a
lumped arc-transfer efficiency that swings between a "bare-arc" and a
"foamed-slag" value with the slag-foaming index, plus a quasi-steady panel
cooling loss. The reaction set of Part 2 (Fe/FeO, C, Si, Mn, P) is kept but
expressed as first-order rate laws toward equilibrium rather than the full
equilibrium-constant formulation, so every rate is a single, physically
interpretable, calibratable constant in the parameter registry. Each of these
simplifications is marked in the code and can be swapped for the full treatment.

Temperatures are kept in KELVIN internally (the melting-split needs absolute
temperature ratios) and reported in deg C.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional
import math

import thermodata as td
import refractory as rf


K = 273.15   # deg C -> K offset


# --------------------------------------------------------------------------- #
#  State                                                                       #
# --------------------------------------------------------------------------- #
@dataclass
class State:
    """Instantaneous furnace state (SI: kg, K, s)."""
    t: float = 0.0                       # s

    m_sSc: float = 0.0                   # solid scrap mass, kg
    T_sSc: float = 298.15                # solid scrap temperature, K
    m_lSc: float = 0.0                   # liquid steel mass, kg
    T_lSc: float = 1809.0                # liquid steel temperature, K

    # bath (liquid steel) element masses, kg
    m_C: float = 0.0
    m_Si: float = 0.0
    m_Mn: float = 0.0
    m_P: float = 0.0
    m_Fe: float = 0.0

    # slag oxide masses, kg
    slag: dict = field(default_factory=lambda: {
        "CaO": 0.0, "MgO": 0.0, "SiO2": 0.0, "MnO": 0.0,
        "FeO": 0.0, "P2O5": 0.0, "Al2O3": 0.0})
    T_sl: float = 1809.0                 # slag temperature, K

    # cumulative tallies
    E_elec_MJ: float = 0.0               # grid electrical energy
    E_chem_MJ: float = 0.0               # chemical energy released
    m_o2_cum: float = 0.0                # cumulative oxygen blown, kg
    co_out_cum: float = 0.0              # cumulative CO leaving (post-combustion) kg
    co2_cum: float = 0.0                # cumulative CO2 formed, kg
    c_inj_cum: float = 0.0              # cumulative injected/charge carbon used, kg
    O2_used_Nm3: float = 0.0
    C_charge_left: float = 0.0           # bucket carbon not yet reacted, kg
    C_inj_left: float = 0.0              # injected carbon present in slag, kg
    c_inj_budget_left: float = 0.0       # foaming carbon not yet injected, kg
    m_lime_undissolved: float = 0.0      # charged lime not yet dissolved, kg
    offgas: dict = field(default_factory=lambda: {"CO": 0.0, "CO2": 0.0, "N2": 0.0})
    electrode_kg: float = 0.0
    power_on_s: float = 0.0

    # diagnostics of the moment
    foam_index: float = 0.0
    eta_transfer: float = 0.0
    P_chem_kW: float = 0.0
    wall_loss_kW: float = 0.0            # refractory conduction/conv/rad loss
    panel_loss_kW: float = 0.0          # water-cooled panel/roof loss
    offgas_loss_kW: float = 0.0         # sensible heat in off-gas
    shell_temp_C: float = 0.0           # outer-shell temperature

    # ---- derived quantities ------------------------------------------------ #
    @property
    def m_liquid_total(self) -> float:
        return max(self.m_lSc, 1e-6)

    @property
    def pct(self) -> dict:
        m = self.m_liquid_total
        return {
            "C": 100 * self.m_C / m,
            "Si": 100 * self.m_Si / m,
            "Mn": 100 * self.m_Mn / m,
            "P": 100 * self.m_P / m,
        }

    @property
    def slag_mass(self) -> float:
        return sum(self.slag.values())

    @property
    def basicity(self) -> float:
        s = self.slag["SiO2"]
        return self.slag["CaO"] / s if s > 1e-6 else 0.0

    @property
    def feo_pct(self) -> float:
        sm = self.slag_mass
        return 100 * self.slag["FeO"] / sm if sm > 1e-6 else 0.0

    @property
    def solid_fraction(self) -> float:
        tot = self.m_sSc + self.m_lSc
        return self.m_sSc / tot if tot > 1e-6 else 0.0


# --------------------------------------------------------------------------- #
#  Charge bucket                                                               #
# --------------------------------------------------------------------------- #
@dataclass
class Charge:
    """A scrap/DRI bucket dropped into the furnace at time ``t_add`` (s)."""
    t_add: float
    mass: float                          # kg metallic
    composition: dict                    # wt-% of C,Si,Mn,P,... (Fe = balance)
    temperature_C: float = 25.0
    carbon_extra: float = 0.0            # bucket (charge) carbon, kg
    lime: float = 0.0                    # kg CaO-bearing flux
    dolomite: float = 0.0                # kg


# --------------------------------------------------------------------------- #
#  Operating schedule (power / oxygen / carbon / burners vs. melt progress)     #
# --------------------------------------------------------------------------- #
class Schedule:
    """
    Returns the set-points (arc power, O2 rate, carbon-injection rate, burner
    power) as a function of the current state.  The default schedule is
    *progress-driven* (keyed to how much scrap is still solid), which is more
    robust than fixed clock times and mirrors real practice:

        bore-in   (solid > 70%) : reduced power, burners on, no lancing
        main melt (5-70% solid) : full power, burners off, moderate O2
        flat bath (<5% solid)   : power for superheat, high O2, carbon foaming
    """

    def __init__(self, registry):
        self.reg = registry

    def setpoints(self, st: State) -> dict:
        p = self.reg.get
        P_max = p("transformer_power")           # MW
        O2_max = p("oxygen_flow_rate")           # Nm3/h
        sf = st.solid_fraction

        if sf > 0.70:                             # bore-in
            return dict(P_arc=0.65 * P_max, O2=0.15 * O2_max,
                        C_inj=0.3, burner=0.9 * p("natural_gas") / 60.0)
        elif sf > 0.05:                           # main melt
            return dict(P_arc=1.00 * P_max, O2=0.50 * O2_max,
                        C_inj=0.6, burner=0.2 * p("natural_gas") / 60.0)
        else:                                     # flat bath / refining
            over = st.T_lSc - (p("target_tap_temperature") + K)
            Cnow = st.pct["C"]
            Ctar = p("target_carbon")
            # Keep blowing while decarburising OR while foaming carbon is still
            # available to burn (chemical energy + CO foam); trim only when both
            # are done, to avoid over-oxidising the bath.
            foam_active = (st.C_inj_left > 30.0 or st.c_inj_budget_left > 30.0)
            O2 = 1.00 * O2_max if (Cnow > Ctar or foam_active) else 0.15 * O2_max
            if over > 0 and Cnow <= Ctar:
                # only once the aim carbon is made does the operator trim the
                # lance; while still decarburising the blow continues and the
                # bath temperature is held down with the arc instead.
                O2 = min(O2, 0.40 * O2_max)
            # Foaming carbon is injected during the carbon boil and stopped as
            # the bath approaches aim carbon: the slag must then be allowed to
            # oxidise (FeO up) so that [C]_eq = K_CO/(%FeO) falls below the aim
            # and the final decarburisation can finish. This is standard
            # practice and is what sets the high tap-slag FeO.
            C_inj = 1.2 if Cnow > 1.6 * Ctar else 0.0
            # power: taper progressively as the bath approaches tap temperature
            # so the heat lands on aim instead of overshooting.
            if over > 0:
                P = 0.0                 # at aim: arc off, refine on O2 (time still counts)
            elif over > -15:
                P = 0.20 * P_max
            elif over > -30:
                P = 0.35 * P_max
            elif over > -70:
                P = 0.60 * P_max
            else:
                P = 0.85 * P_max
            return dict(P_arc=P, O2=O2, C_inj=C_inj, burner=0.0)


# --------------------------------------------------------------------------- #
#  Result / history                                                            #
# --------------------------------------------------------------------------- #
@dataclass
class DynamicResult:
    history: dict = field(default_factory=dict)
    final: Optional[State] = None
    tap_to_tap_min: float = 0.0
    reached_endpoint: bool = False
    notes: list = field(default_factory=list)
    events: list = field(default_factory=list)   # [{t, phase, event, detail}]

    def summary(self) -> str:
        st = self.final
        pct = st.pct
        lines = [
            "=" * 66,
            " DYNAMIC EAF SIMULATION RESULT",
            "=" * 66,
            f" Power-on time              : {st.power_on_s/60:8.1f} min",
            f" Tap-to-tap (incl. off-time): {self.tap_to_tap_min:8.1f} min",
            f" Endpoint reached           : {self.reached_endpoint}",
            "-" * 66,
            f" Liquid steel               : {st.m_lSc/1000:8.2f} t",
            f" Remaining solid scrap      : {st.m_sSc/1000:8.3f} t",
            f" Bath temperature           : {st.T_lSc-K:8.1f} degC",
            f" Tap chemistry  C / Si / Mn / P (wt-%):",
            f"                {pct['C']:.3f} / {pct['Si']:.3f} / "
            f"{pct['Mn']:.3f} / {pct['P']:.4f}",
            "-" * 66,
            f" Slag mass                  : {st.slag_mass:8.0f} kg",
            f" Slag basicity B2           : {st.basicity:8.2f}",
            f" Slag FeO                   : {st.feo_pct:8.1f} %",
            f" Foaming index (final)      : {st.foam_index:8.2f}",
            "-" * 66,
            f" Electrical energy          : {st.E_elec_MJ/3.6:8.0f} kWh "
            f"({st.E_elec_MJ/3.6/(st.m_lSc/1000):6.1f} kWh/t)",
            f" Chemical energy released   : {st.E_chem_MJ/3.6:8.0f} kWh",
            f" Oxygen used                : {st.O2_used_Nm3:8.0f} Nm3",
            f" Electrode consumption      : {st.electrode_kg:8.0f} kg",
            "=" * 66,
        ]
        return "\n".join(lines)

    # -- plotting ----------------------------------------------------------- #
    def figure(self, figsize=(18, 10.5)):
        """Build and return a comprehensive 12-panel Figure of the heat."""
        import math as _m
        from matplotlib.figure import Figure

        h = self.history
        t = [x / 60 for x in h["t"]]            # minutes

        def wpct(key):                          # oxide as wt-% of total slag
            return [100.0 * a / b if b > 1e-6 else 0.0
                    for a, b in zip(h[key], h["m_slag"])]

        fig = Figure(figsize=figsize)
        ax = fig.subplots(3, 4)

        # (1) masses -- steel in t on left, slag in t on right (UNIT-CORRECT)
        a = ax[0, 0]
        a.plot(t, h["m_sSc"], label="solid scrap", color="#8c564b")
        a.plot(t, h["m_lSc"], label="liquid steel", color="#1f77b4")
        a.set_ylabel("steel mass (t)"); a.set_xlabel("time (min)")
        ar = a.twinx()
        ar.plot([x for x in t], [m / 1000.0 for m in h["m_slag"]],
                color="#2ca02c", ls="-.", label="slag")
        ar.set_ylabel("slag mass (t)", color="#2ca02c"); ar.set_ylim(bottom=0)
        a.set_title("Masses: melting & slag build-up")
        a.legend(fontsize=7, loc="center left"); a.grid(alpha=0.3)

        # (2) phase fractions of the metallic charge (stacked area)
        a = ax[0, 1]
        tot = [max(s + l, 1e-9) for s, l in zip(h["m_sSc"], h["m_lSc"])]
        fsol = [100 * s / tt for s, tt in zip(h["m_sSc"], tot)]
        fliq = [100 * l / tt for l, tt in zip(h["m_lSc"], tot)]
        a.stackplot(t, fsol, fliq, labels=["solid scrap", "liquid steel"],
                    colors=["#8c564b", "#4a90d9"], alpha=0.9)
        a.set_ylim(0, 100); a.set_xlim(min(t), max(t))
        a.set_ylabel("metal phase (%)"); a.set_xlabel("time (min)")
        a.set_title("Solid \u2192 liquid conversion"); a.legend(fontsize=7, loc="center right")

        # (3) temperatures incl. shell
        a = ax[0, 2]
        a.plot(t, h["T_lSc"], color="tab:red", label="bath")
        a.plot(t, h["T_sSc"], color="tab:orange", ls="--", label="solid")
        a.axhline(self._target_T, color="k", ls=":", lw=1, label="tap aim")
        a.set_ylabel("temperature (\u00b0C)"); a.set_xlabel("time (min)")
        ar = a.twinx(); ar.plot(t, h["T_shell"], color="tab:gray", ls="-.", label="shell")
        ar.set_ylabel("shell (\u00b0C)", color="tab:gray")
        a.set_title("Temperatures"); a.legend(fontsize=7, loc="lower right"); a.grid(alpha=0.3)

        # (4) bath chemistry
        a = ax[0, 3]
        a.plot(t, h["C"], label="C"); a.plot(t, h["Si"], label="Si")
        a.plot(t, h["Mn"], label="Mn"); a.plot(t, h["P"], label="P \u00d710")
        a.set_ylabel("bath content (wt-%)"); a.set_xlabel("time (min)")
        a.set_title("Bath chemistry"); a.legend(fontsize=7); a.grid(alpha=0.3)

        # (5) slag composition (wt-%) -- stacked area
        a = ax[1, 0]
        series = [wpct(k) for k in ("slag_CaO", "slag_SiO2", "slag_FeO",
                                    "slag_MgO", "slag_MnO", "slag_P2O5")]
        other = [max(100 - sum(v[i] for v in series), 0) for i in range(len(t))]
        a.stackplot(t, *series, other,
                    labels=["CaO", "SiO2", "FeO", "MgO", "MnO", "P2O5", "Al2O3/oth"],
                    colors=["#1f77b4", "#ff7f0e", "#d62728", "#2ca02c",
                            "#9467bd", "#17becf", "#b0b0b0"], alpha=0.9)
        a.set_ylim(0, 100); a.set_xlim(min(t), max(t))
        a.set_ylabel("slag composition (wt-%)"); a.set_xlabel("time (min)")
        a.set_title("Slag composition (wt-%)"); a.legend(fontsize=6, ncol=2, loc="upper right")

        # (6) slag oxide masses (kg) + basicity
        a = ax[1, 1]
        for k, lab, c in [("slag_CaO", "CaO", "#1f77b4"), ("slag_SiO2", "SiO2", "#ff7f0e"),
                          ("slag_FeO", "FeO", "#d62728"), ("slag_MgO", "MgO", "#2ca02c"),
                          ("slag_MnO", "MnO", "#9467bd")]:
            a.plot(t, h[k], label=lab, color=c)
        a.set_ylabel("mass (kg)"); a.set_xlabel("time (min)")
        ar = a.twinx(); ar.plot(t, h["basicity"], color="k", ls=":", label="B2")
        ar.set_ylabel("basicity B2")
        a.set_title("Slag oxide masses"); a.legend(fontsize=6, loc="upper left"); a.grid(alpha=0.3)

        # (7) carbon-FeO coupling vs Turkdogan equilibrium
        a = ax[1, 2]
        Cs = [c for c in h["C"]]; Fs = [f for f in h["FeO"]]
        Cg = [0.02 + i * 0.003 for i in range(200)]
        Ttap = self._target_T + 273.15
        for Tc, col in [(1500, "#c6dbef"), (1600, "#6baed6"), (1700, "#2171b5")]:
            K = _m.exp(12325.0 / (Tc + 273.15) - 6.357)
            a.plot(Cg, [min(K / c, 45) for c in Cg], color=col, lw=1.3,
                   label=f"eqm {Tc}\u00b0C")
        a.plot(Cs, Fs, color="#d62728", lw=1.6, label="trajectory")
        a.axhspan(17, 23, color="#c8e6c9", alpha=0.4)
        a.set_xlim(0, 0.6); a.set_ylim(0, 45)
        a.set_xlabel("bath carbon (wt-%)"); a.set_ylabel("slag FeO (wt-%)")
        a.set_title("C\u2013FeO coupling vs Turkdogan"); a.legend(fontsize=6); a.grid(alpha=0.3)

        # (8) foaming index + FeO
        a = ax[1, 3]
        a.plot(t, h["FeO"], color="#d62728", label="slag FeO (wt-%)")
        a.axhspan(17, 23, color="#c8e6c9", alpha=0.4)
        a.set_ylabel("slag FeO (wt-%)", color="#d62728"); a.set_xlabel("time (min)")
        ar = a.twinx(); ar.plot(t, h["foam"], color="#7b3294", ls="--", label="foam index")
        ar.set_ylabel("foam index", color="#7b3294")
        a.set_title("Foaming & FeO (foaming window shaded)"); a.grid(alpha=0.3)

        # (9) cumulative energy + specific energy
        a = ax[2, 0]
        Etot = [e + c for e, c in zip(h["E_elec"], h["E_chem"])]
        a.plot(t, h["E_elec"], color="tab:blue", label="electrical")
        a.plot(t, h["E_chem"], color="tab:green", label="chemical")
        a.plot(t, Etot, color="k", ls="-", lw=1.2, label="total")
        a.set_ylabel("cumulative energy (kWh)"); a.set_xlabel("time (min)")
        ar = a.twinx(); ar.plot(t, h["spec_energy"], color="#e8930c", ls=":", label="kWh/t")
        ar.set_ylabel("specific energy (kWh/t)", color="#e8930c"); ar.set_ylim(bottom=0)
        a.set_title("Energy: cumulative & specific"); a.legend(fontsize=7, loc="upper left"); a.grid(alpha=0.3)

        # (10) power in / heat loss breakdown
        a = ax[2, 1]
        for k, lab, c in [("P_arc_bath", "arc\u2192bath", "#1f77b4"), ("P_chem", "chemical", "#2ca02c"),
                          ("P_panel", "panel loss", "#ff7f0e"), ("P_offgas", "off-gas loss", "#d62728"),
                          ("P_wall", "wall loss", "#8c564b")]:
            a.plot(t, h[k], label=lab, color=c)
        a.set_ylabel("power (MW)"); a.set_xlabel("time (min)")
        a.set_title("Power in / heat loss"); a.legend(fontsize=6); a.grid(alpha=0.3)

        # (11) off-gas: cumulative CO / CO2 + O2 use
        a = ax[2, 2]
        a.plot(t, h["CO_out"], color="#636363", label="CO out (kg)")
        a.plot(t, h["CO2_out"], color="#3182bd", label="CO2 (kg)")
        a.set_ylabel("cumulative gas (kg)"); a.set_xlabel("time (min)")
        ar = a.twinx(); ar.plot(t, h["O2_cum"], color="#31a354", ls="--", label="O2 (Nm3/t)")
        ar.set_ylabel("O2 use (Nm\u00b3/t)", color="#31a354")
        a.set_title("Off-gas (CO/CO2) & oxygen"); a.legend(fontsize=6, loc="upper left"); a.grid(alpha=0.3)

        # (12) basicity B2/B3 + lime dissolution (dephosphorisation context)
        a = ax[2, 3]
        a.plot(t, h["basicity"], color="#1f77b4", label="B2 = CaO/SiO2")
        a.plot(t, h["B3"], color="#9467bd", ls="--", label="B3 = CaO/(SiO2+Al2O3)")
        a.axhspan(1.8, 2.4, color="#c8e6c9", alpha=0.35)
        a.set_ylabel("basicity"); a.set_xlabel("time (min)")
        ar = a.twinx(); ar.plot(t, h["lime_undissolved"], color="#e8930c", ls=":", label="undissolved lime (kg)")
        ar.set_ylabel("undissolved lime (kg)", color="#e8930c"); ar.set_ylim(bottom=0)
        a.set_title("Basicity & lime dissolution"); a.legend(fontsize=6, loc="center right"); a.grid(alpha=0.3)

        fig.tight_layout()
        return fig

    def plot(self, path: str = "eaf_dynamic.png"):
        """Save the heat plot to ``path``. Requires matplotlib."""
        import matplotlib
        matplotlib.use("Agg")
        fig = self.figure()
        fig.savefig(path, dpi=110)
        return path


# --------------------------------------------------------------------------- #
#  The dynamic model                                                           #
# --------------------------------------------------------------------------- #
class DynamicEAFModel:
    """
    Time-stepping EAF simulator.

    Usage
    -----
    >>> from eaf_control_model import default_parameters, DynamicEAFModel
    >>> reg = default_parameters()
    >>> model = DynamicEAFModel(reg)
    >>> result = model.simulate(mode="endpoint")
    >>> print(result.summary())
    >>> result.plot("heat.png")
    """

    def __init__(self, registry, charges: Optional[list] = None,
                 schedule: Optional[Schedule] = None):
        self.reg = registry
        self.schedule = schedule or Schedule(registry)
        self.charges = charges if charges is not None else self._default_charges()

        # constants derived once
        comp = registry.get("scrap_composition")
        self.T_melt = td.liquidus_temperature_c(comp) + K       # K
        self.scrap_comp = comp
        self.total_charge_mass = max(sum(c.mass for c in self.charges), 1.0)
        r = registry.get
        self._wall_layers = [
            rf.Layer("Working lining", r("working_lining_thickness"), r("working_lining_k")),
            rf.Layer("Safety lining", r("safety_lining_thickness"), r("safety_lining_k")),
            rf.Layer("Insulation", r("insulation_thickness"), r("insulation_k")),
            rf.Layer("Steel shell", r("shell_thickness"), r("shell_k")),
        ]

    # -- default single-bucket charge from the registry -------------------- #
    def _default_charges(self) -> list:
        p = self.reg.get
        return [Charge(
            t_add=0.0,
            mass=p("scrap_charge_mass") * 1000.0,
            composition=p("scrap_composition"),
            temperature_C=p("ambient_temperature"),
            carbon_extra=p("charge_carbon"),
            lime=p("lime_charged") * 0.90,          # available CaO
            dolomite=p("dolomite_charged"),
        )]

    # ---------------------------------------------------------------------- #
    #  Chemistry sub-step  (returns energy to bath, gas produced, etc.)       #
    # ---------------------------------------------------------------------- #
    def _chemistry(self, st: State, o2_kg: float, c_inj_kg: float, dt: float):
        """
        Advance the refining reactions by one step.

        Grounded in Logar Part 2 reaction set (Fe/FeO, C, Si, Mn, P); expressed
        as first-order rates toward equilibrium with a simple oxygen allocation.
        Returns a dict with chemical energy (kJ), CO/CO2 generated (kg) and the
        instantaneous CO generation rate (kg/s) used for foaming.
        """
        p = self.reg.get
        M = st.m_liquid_total
        st.C_inj_left += c_inj_kg                  # newly injected foaming carbon
        chem_kJ = 0.0
        co_kg = 0.0
        co2_kg = 0.0
        o2_left = o2_kg * 0.97                     # ~97% oxygen utilisation

        # --- 1. Silicon: fast, strong affinity, gets oxygen first --------- #
        si_eq = 0.005 / 100 * M                    # ~0.005% equilibrium
        dSi = min(max(st.m_Si - si_eq, 0.0) * p("si_removal_rate") * dt,
                  o2_left * td.O2_TO_ELEMENT["Si"])
        if dSi > 0:
            o2_left -= dSi / td.O2_TO_ELEMENT["Si"]
            st.m_Si -= dSi
            st.slag["SiO2"] += dSi / td.MOLAR_MASS["Si"] * td.MOLAR_MASS["SiO2"]
            chem_kJ += dSi * td.CHEM_ENERGY["Si"]

        # --- 2. Manganese: partition toward equilibrium ------------------- #
        mn_eq = (1 - p("mn_slag_partition")) * st.m_Mn   # crude equilibrium target
        dMn = min(max(st.m_Mn - mn_eq, 0.0) * p("mn_removal_rate") * dt,
                  o2_left * td.O2_TO_ELEMENT["Mn"])
        if dMn > 0:
            o2_left -= dMn / td.O2_TO_ELEMENT["Mn"]
            st.m_Mn -= dMn
            st.slag["MnO"] += dMn / td.MOLAR_MASS["Mn"] * td.MOLAR_MASS["MnO"]
            chem_kJ += dMn * td.CHEM_ENERGY["Mn"]

        # --- 3. Phosphorus: favoured by high B, high FeO, lower T --------- #
        B = st.basicity
        feo = st.feo_pct
        T_factor = max(0.0, (1900.0 - st.T_lSc) / 300.0)      # cooler -> better
        favour = min(B / 2.0, 1.5) * min(feo / 20.0, 1.0) * T_factor
        dP = max(st.m_P, 0.0) * p("p_removal_rate") * favour * dt
        dP = min(dP, o2_left * td.O2_TO_ELEMENT.get("Fe", 3.49) * 0.2)
        if dP > 0:
            st.m_P -= dP
            st.slag["P2O5"] += dP / td.MOLAR_MASS["P"] / 2 * td.MOLAR_MASS["P2O5"]
            chem_kJ += dP * td.CHEM_ENERGY["P"]

        # --- 4. (Injected/charge carbon does NOT burn directly on the lance;
        #     it foams the slag by reducing FeO in section 7. The lanced oxygen
        #     therefore goes to Si, Mn, bath decarburisation and iron. Routing
        #     carbon through FeO formation+reduction conserves energy exactly:
        #     Fe+1/2O2->FeO (exo) then FeO+C->Fe+CO (endo) == C+1/2O2->CO.) ---

        # --- 5. Decarburisation, two-regime (Turkdogan) ------------------ #
        #   [C]+(FeO)->Fe+CO / [C]+1/2 O2->CO. Above the critical carbon
        #   (~0.30 wt%, Turkdogan) the rate is oxygen-supply limited and ~zero
        #   order in C; below it, carbon-mass-transfer limited and first order:
        #     d[%C]/dt = -(A rho_m k_C / 100 W)([%C]-[%C]_eq),  k_C~2-4e-3 m/s,
        #   folded into decarb_mass_transfer_coeff (a lumped 1/s constant,
        #   Bekker/Logar style). The equilibrium carbon is set by the slag FeO
        #   through the Turkdogan carbon-oxygen product  (%FeO)(%C) = K_CO(T),
        #   fitted to K_CO = 1.8/1.25/0.89 at 1500/1600/1700 C.
        Cpct = 100 * st.m_C / M
        C_crit = p("decarb_critical_carbon")
        eta_max = p("decarb_o2_efficiency_max")
        K_CO = p("feo_equilibrium_factor") * math.exp(12325.0 / st.T_lSc - 6.357)
        if Cpct > C_crit:
            # oxygen-limited: carbon takes most (eta_max) of the oxygen
            dC = min(o2_left * eta_max * td.O2_TO_ELEMENT["C_to_CO"],
                     max(st.m_C - C_crit / 100 * M, 0.0))
        else:
            # carbon-mass-transfer limited; [C]_eq in equilibrium with slag FeO
            C_eq = K_CO / max(st.feo_pct, 1.0)
            k = p("decarb_mass_transfer_coeff")
            dC_mt = max(Cpct - C_eq, 0.0) / 100 * M * k * dt
            dC = min(dC_mt, o2_left * td.O2_TO_ELEMENT["C_to_CO"])
        if dC > 0:
            o2_left -= dC / td.O2_TO_ELEMENT["C_to_CO"]
            st.m_C -= dC
            co_kg += dC / td.MOLAR_MASS["C"] * td.MOLAR_MASS["CO"]
            chem_kJ += dC * td.CHEM_ENERGY["C_to_CO"]

        # --- 6. Iron oxidation: remaining lanced O2 makes FeO ------------- #
        #     Fe + 1/2 O2 -> FeO.  As [C] falls the carbon cannot take all the
        #     oxygen, so FeO formation accelerates toward tap -> tap-slag FeO
        #     climbs to ~20-30 wt-%, as observed in plant slags (Kirschen).
        if o2_left > 0:
            dFe = min(o2_left * td.O2_TO_ELEMENT["Fe"], st.m_Fe * 0.5)
            st.m_Fe -= dFe
            st.slag["FeO"] += dFe / td.MOLAR_MASS["Fe"] * td.MOLAR_MASS["FeO"]
            chem_kJ += dFe * td.CHEM_ENERGY["Fe"]
            o2_left = 0.0

        # --- 7. FeO reduction by injected carbon toward the Turkdogan ----- #
        #     carbon-FeO equilibrium.  (FeO)+C(s)->Fe+CO, slag-side FeO mass-
        #     transfer controlled (k_FeO ~ 1e-5 m/s): rate = k_red m_C,slag m_FeO.
        #     Reduction only proceeds while slag FeO exceeds the value set by the
        #     bath carbon via the SAME product used for decarburisation:
        #         (%FeO)_eq = K_CO(T) / [%C]      (capped at slag_feo_max)
        #     -> a low, foaming-window FeO during the carbon boil and a higher
        #     FeO at tap.  Net endothermic (CO gain minus the Fe-O bond).
        FeO_pct = st.feo_pct
        FeO_eq = min(K_CO / max(Cpct, 0.02), p("slag_feo_max"))
        c_avail = st.C_inj_left                     # injected/slag foaming carbon
        if FeO_pct > FeO_eq and c_avail > 0 and st.slag["FeO"] > 0:
            sm = st.slag_mass
            reducible = (FeO_pct - FeO_eq) / 100.0 * sm          # kg FeO above eqm
            k_red = p("feo_reduction_rate")
            dFeO = k_red * c_avail * st.slag["FeO"] * dt         # slag-side MT rate
            dFeO = min(dFeO, reducible, st.slag["FeO"],
                       c_avail * td.MOLAR_MASS["FeO"] / td.MOLAR_MASS["C"])
            if dFeO > 0:
                dC_red = dFeO * td.MOLAR_MASS["C"] / td.MOLAR_MASS["FeO"]
                st.C_inj_left -= dC_red
                st.slag["FeO"] -= dFeO
                st.m_Fe += dFeO / td.MOLAR_MASS["FeO"] * td.MOLAR_MASS["Fe"]
                co_kg += dC_red / td.MOLAR_MASS["C"] * td.MOLAR_MASS["CO"]
                fe_per_c = td.MOLAR_MASS["Fe"] / td.MOLAR_MASS["C"]
                chem_kJ += dC_red * (td.CHEM_ENERGY["C_to_CO"]
                                     - fe_per_c * td.CHEM_ENERGY["Fe"])

        # (charge carbon is added to the FeO-reduction / CO-boil pool at
        #  charging time in _apply_charge, so there is no separate bath
        #  dissolution term here.)

        # --- 7. CO post-combustion in freeboard -------------------------- #
        pcr = p("post_combustion_ratio")
        pce = p("post_combustion_efficiency")
        co_burned = co_kg * pcr
        pc_energy_to_bath = co_burned * td.CHEM_ENERGY["CO_to_CO2"] * pce
        chem_kJ += pc_energy_to_bath
        co2_kg += co_burned / td.MOLAR_MASS["CO"] * td.MOLAR_MASS["CO2"]
        co_out = co_kg - co_burned

        # tally off-gas & oxygen
        st.offgas["CO"] += co_out
        st.offgas["CO2"] += co2_kg
        st.O2_used_Nm3 += (o2_kg - 0) / td.O2_DENSITY_NM3 * 0  # (tracked in caller)

        co_rate = co_kg / dt if dt > 0 else 0.0
        return dict(chem_kJ=chem_kJ, co_out=co_out, co2=co2_kg, co_rate=co_rate)

    # ---------------------------------------------------------------------- #
    #  Foaming index                                                          #
    # ---------------------------------------------------------------------- #
    def _foam_index(self, st: State, co_rate: float) -> float:
        p = self.reg.get
        ref = p("foaming_co_reference")
        base = min(co_rate / ref, 1.0)
        # Foam is driven by CO generation (from decarburisation, injected-carbon
        # combustion and FeO reduction). A very high FeO makes the slag too
        # fluid to hold foam, and a very high basicity makes it pasty; moderate
        # conditions foam best. Low FeO is NOT penalised as long as CO is
        # evolving (carbon+O2 supplies the bubbles).
        feo = st.feo_pct
        g_feo = 1.0 if feo < 35 else max(0.3, 1 - (feo - 35) / 30)
        B = st.basicity
        g_B = 1.0 if B < 2.8 else max(0.4, 1 - (B - 2.8) / 2.0)
        return max(0.0, min(1.0, base * g_feo * g_B))

    # ---------------------------------------------------------------------- #
    #  Add a charge bucket                                                    #
    # ---------------------------------------------------------------------- #
    def _apply_charge(self, st: State, ch: Charge):
        comp = ch.composition
        el = {e: ch.mass * comp.get(e, 0.0) / 100.0
              for e in ("C", "Si", "Mn", "P")}
        fe = ch.mass - sum(el.values())
        st.m_sSc += ch.mass
        # solid scrap temperature re-averaged (Logar Eq. 38)
        T_add = ch.temperature_C + K
        st.T_sSc = ((st.T_sSc * (st.m_sSc - ch.mass) + T_add * ch.mass)
                    / st.m_sSc) if st.m_sSc > 0 else T_add
        # element inventory carried by the (still solid) scrap is realised as it
        # melts; we stage it via a per-bucket composition on the solid mass.
        # For simplicity the whole furnace solid uses the latest bucket blend:
        self.scrap_comp = comp
        # charge (bucket) carbon mainly burns / reduces FeO (CO boil), so route
        # it to the carbon-available pool rather than dumping it as dissolved C.
        st.C_inj_left += ch.carbon_extra
        # lime dissolves into the slag over time (dissolution kinetics), so it is
        # held as an undissolved pool rather than counted as basicity at once.
        st.m_lime_undissolved += ch.lime
        st.slag["CaO"] += ch.dolomite * 0.55
        st.slag["MgO"] += ch.dolomite * 0.38
        # dirt / rust / sand / ash carried in on the scrap -> slag SiO2 + Al2O3
        ds = self.reg.get("dirt_silica") * ch.mass / 1000.0
        st.slag["SiO2"] += ds * 0.85
        st.slag["Al2O3"] += ds * 0.15
        # Rust / mill-scale / oxide skin on the scrap reports straight to the
        # slag as FeO. This is why plant slags show HIGH FeO at meltdown
        # (Kirschen; Morales), which carbon injection then pulls back down
        # during the boil before it rises again toward tap.
        st.slag["FeO"] += self.reg.get("scrap_rust_feo") * ch.mass / 1000.0

    # ---------------------------------------------------------------------- #
    #  Main integration loop                                                  #
    # ---------------------------------------------------------------------- #
    def simulate(self, mode: str = "endpoint",
                 max_time_min: float = 90.0,
                 record_every_s: float = 10.0) -> DynamicResult:
        """
        Integrate a heat.

        Parameters
        ----------
        mode : {"endpoint", "fixed"}
            "endpoint" runs until the aim temperature AND aim carbon are met
            (or ``max_time_min``).  "fixed" runs for the planned power-on time
            from the registry and reports the state reached.
        max_time_min : float
            Safety cap on simulated power-on time.
        record_every_s : float
            History sampling interval.
        """
        p = self.reg.get
        dt = p("sim_timestep")
        st = State()

        # small hot heel (previous tap) keeps the liquid-zone maths well posed
        heel = 0.005 * p("furnace_capacity") * 1000.0
        st.m_lSc = heel
        st.m_Fe = heel
        st.T_lSc = self.T_melt + 20.0
        st.T_sl = self.T_melt

        # bucket 1 (and any at t=0)
        pending = sorted(self.charges, key=lambda c: c.t_add)
        i_charge = 0
        while i_charge < len(pending) and pending[i_charge].t_add <= 0.0:
            self._apply_charge(st, pending[i_charge]); i_charge += 1
        st.c_inj_budget_left = p("injected_carbon")   # fed gradually while foaming

        T_target = p("target_tap_temperature")
        C_target = p("target_carbon")
        planned_on = p("power_on_time") * 60.0

        # history buffers (extended)
        H = {k: [] for k in (
            "t", "m_sSc", "m_lSc", "m_slag", "T_sSc", "T_lSc", "T_slag", "T_shell",
            "C", "Si", "Mn", "P",
            "slag_CaO", "slag_SiO2", "slag_FeO", "slag_MnO", "slag_MgO", "slag_P2O5",
            "basicity", "FeO", "foam", "lime_undissolved",
            "E_elec", "E_chem",
            "P_arc_bath", "P_chem", "P_wall", "P_panel", "P_offgas", "P_loss_total",
            "O2_cum", "CO_out", "CO2_out", "spec_energy", "yield_pct", "B3")}
        next_record = 0.0
        result = DynamicResult()
        result._target_T = T_target                          # for the plot

        # ---- event log ---------------------------------------------------- #
        events = []
        def log(phase, event, detail=""):
            events.append({"t": st.t, "phase": phase, "event": event,
                           "detail": detail})
        for ch in self.charges:
            if ch.t_add <= 0.0:
                comp = ", ".join(f"{k} {v:.2f}%" for k, v in ch.composition.items())
                log("Charge", f"Bucket charged: {ch.mass/1000:.1f} t scrap",
                    f"{ch.temperature_C:.0f} degC; {comp}")
        _lime0 = sum(c.lime for c in self.charges if c.t_add <= 0.0)
        if _lime0 > 0:
            log("Charge", f"Lime charged: {_lime0:.0f} kg", "dissolving into slag")
        if p("charge_carbon") > 0:
            log("Charge", f"Charge carbon: {p('charge_carbon'):.0f} kg", "")
        log("Bore-in", "Arc energised — melt-down begins",
            f"transformer {p('transformer_power'):.0f} MW")
        phase_prev = "Bore-in"
        lime_done = False
        o2_started = False
        cinj_started = False

        max_time_s = max_time_min * 60.0
        eta_elec = p("electrical_efficiency")
        eta_foam = p("arc_transfer_efficiency")
        eta_bare = p("arc_transfer_bare")
        Cp_sSc = td.CP_SCRAP
        Cp_lSc = td.CP_LIQUID_STEEL
        Cp_sl = td.CP_SLAG
        Tamb = p("ambient_temperature") + K

        while st.t < max_time_s:
            # add any due charge buckets
            while i_charge < len(pending) and pending[i_charge].t_add <= st.t:
                self._apply_charge(st, pending[i_charge]); i_charge += 1

            # --- dissolution kinetics: lime -> slag, carbon -> bath ------- #
            if st.m_lime_undissolved > 0:
                d_lime = min(p("lime_dissolution_rate") * st.m_lime_undissolved * dt,
                             st.m_lime_undissolved)
                st.m_lime_undissolved -= d_lime
                st.slag["CaO"] += d_lime
                if st.m_lime_undissolved < 1.0 and not lime_done:
                    lime_done = True
                    log(phase_prev, "Lime fully dissolved",
                        f"slag basicity B2 = {st.basicity:.2f}")
            if (p("carbon_dissolution_rate") > 0 and st.C_inj_left > 0
                    and st.m_lSc > 500):
                d_cd = min(p("carbon_dissolution_rate") * st.C_inj_left * dt,
                           st.C_inj_left)
                st.C_inj_left -= d_cd
                st.m_C += d_cd

            # --- phase-transition event ---------------------------------- #
            sf_now = st.solid_fraction
            phase_now = ("Bore-in" if sf_now > 0.70 else
                         ("Melt-down" if sf_now > 0.05 else "Flat bath / refining"))
            if phase_now != phase_prev:
                log(phase_now, f"Phase -> {phase_now}",
                    f"bath {st.T_lSc-K:.0f} degC, C {st.pct['C']:.3f}%, "
                    f"{st.m_lSc/1000:.1f} t liquid")
                phase_prev = phase_now

            sp = self.schedule.setpoints(st)
            P_arc_kW = sp["P_arc"] * 1000.0
            o2_kg = sp["O2"] / 3600.0 * dt * td.O2_DENSITY_NM3   # kg this step
            burner_MW = sp["burner"]

            # ----- chemistry first (gives CO rate for foaming) ----------- #
            feed_C = min(sp["C_inj"] * dt, st.c_inj_budget_left)
            st.c_inj_budget_left -= feed_C
            if not o2_started and sp["O2"] > 0:
                o2_started = True
                log(phase_prev, "Oxygen lancing on", f"{sp['O2']:.0f} Nm3/h")
            if not cinj_started and feed_C > 0:
                cinj_started = True
                log(phase_prev, "Carbon injection on (slag foaming)", "")
            chem = self._chemistry(st, o2_kg, feed_C, dt)
            st.O2_used_Nm3 += sp["O2"] / 3600.0 * dt
            st.E_chem_MJ += chem["chem_kJ"] / 1000.0
            st.m_o2_cum += o2_kg
            st.co_out_cum += chem["co_out"]
            st.co2_cum += chem["co2"]
            st.P_chem_kW = chem["chem_kJ"] / dt
            foam = self._foam_index(st, chem["co_rate"])
            st.foam_index = foam
            # The arc couples efficiently when it is SHIELDED -- by surrounding
            # scrap during melt-in, or by FOAMING slag at flat bath. Only the
            # exposed open arc (little scrap, poor foam) is inefficient and
            # radiates to the panels.
            shield = max(foam, min(1.0, st.solid_fraction / 0.30))
            eta_tr = eta_bare + shield * (eta_foam - eta_bare)
            st.eta_transfer = eta_tr

            # ----- arc power distribution -------------------------------- #
            arc_to_charge_kW = eta_elec * P_arc_kW * eta_tr
            # Exposure (Logar KsSc-lSc idea): while solid scrap is present the
            # electrodes bore into it, so almost all arc energy melts solid; the
            # split shifts to the liquid only near the flat bath. This keeps the
            # bath near the melting point during melt-in rather than overheating.
            sf = st.solid_fraction
            exposure_solid = min(1.0, sf / 0.06)
            Q_arc_sSc = arc_to_charge_kW * exposure_solid
            Q_arc_lSc = arc_to_charge_kW * (1.0 - exposure_solid)

            # burner energy to solid scrap (temperature-dependent efficiency,
            # Logar Eq. 3) --------------------------------------------------- #
            if burner_MW > 0 and st.m_sSc > 0:
                eff_b = 0.35 + 0.65 * math.tanh(1300.0 / max(st.T_sSc, 1.0) - 1.0)
                eff_b = max(0.1, min(eff_b, 1.0))
                Q_burner = burner_MW * 1000.0 * 0.7 * eff_b
            else:
                Q_burner = 0.0

            # chemical energy to zones: mostly to liquid bath -------------- #
            P_chem_kW = chem["chem_kJ"] / dt
            Q_chem_lSc = P_chem_kW * 0.85
            Q_chem_sSc = P_chem_kW * 0.15 if st.m_sSc > 0 else 0.0
            Q_chem_lSc += 0.0 if st.m_sSc > 0 else P_chem_kW * 0.15

            # ----- losses ------------------------------------------------- #
            hot = 1.0 - math.exp(-st.m_lSc / (0.3 * p("furnace_capacity") * 1000.0))
            Q_panel = p("panel_heat_loss") * 1000.0 * hot        # kW
            # off-gas sensible heat carried out of the bath (loss)
            Tog = p("offgas_temperature") + K
            gas_step = chem["co_out"] + chem["co2"]
            Q_offgas = (chem["co_out"] * td.CP_GAS["CO"] +
                        chem["co2"] * td.CP_GAS["CO2"]) * (Tog - Tamb) / dt

            # refractory wall loss (coupled conduction + convection + radiation)
            wall = rf.wall_heat_loss(
                st.T_sl - K, p("ambient_temperature"), self._wall_layers,
                p("refractory_area"), p("convection_coefficient"),
                p("shell_emissivity"))
            Q_wall = wall.q_watts / 1000.0        # kW
            st.wall_loss_kW = Q_wall
            st.shell_temp_C = wall.shell_temp_C
            st.panel_loss_kW = Q_panel
            st.offgas_loss_kW = Q_offgas

            # distribute panel + off-gas + wall losses across liquid & solid
            m_tot = st.m_sSc + st.m_lSc
            fS = st.m_sSc / m_tot if m_tot > 0 else 0.0
            fL = 1 - fS
            Q_sSc_loss = Q_panel * fS
            Q_lSc_loss = Q_panel * fL + Q_offgas + Q_wall

            # Immersion melting: a superheated bath melts the remaining solid by
            # direct contact (Logar liquid->solid conduction). This both melts
            # scrap AND cools the bath, preventing thermal runaway while solid
            # remains. Contact area scales ~ (solid mass)^(2/3).
            if st.m_sSc > 1.0 and st.T_lSc > self.T_melt:
                htc = p("scrap_melt_htc") * \
                    (st.m_sSc / self.total_charge_mass) ** 0.667
                Q_immersion = htc * (st.T_lSc - self.T_melt)         # kW
            else:
                Q_immersion = 0.0

            # ----- net zone powers (kW) ---------------------------------- #
            Q_sSc = Q_arc_sSc + Q_burner + Q_chem_sSc - Q_sSc_loss + Q_immersion
            Q_lSc = Q_arc_lSc + Q_chem_lSc - Q_lSc_loss - Q_immersion

            # ============================================================= #
            #  SOLID SCRAP: heat + melt  (Logar Eqs. 33, 42-43)             #
            # ============================================================= #
            if st.m_sSc > 1e-3:
                ratio = min(st.T_sSc / self.T_melt, 1.0)
                heat_factor = max(0.0, 1.0 - ratio)
                melt_factor = ratio
                # heating
                dT_sSc = (Q_sSc * heat_factor) / (st.m_sSc * Cp_sSc) * dt
                st.T_sSc += dT_sSc
                st.T_sSc = min(st.T_sSc, self.T_melt)      # cannot exceed melt pt
                # melting (only the melting share, and only if net power +ve)
                denom = td.L_FUSION_STEEL + Cp_sSc * max(self.T_melt - st.T_sSc, 0.0)
                mdot = max(Q_sSc, 0.0) * melt_factor / denom       # kg/s
                dm = min(mdot * dt, st.m_sSc)
                # transfer melted metal (with its element content) to the bath
                comp = self.scrap_comp
                add = {e: dm * comp.get(e, 0.0) / 100.0
                       for e in ("C", "Si", "Mn", "P")}
                add_Fe = dm - sum(add.values())
                # re-average bath temperature for incoming metal at T_melt
                if st.m_lSc + dm > 0:
                    st.T_lSc = (st.T_lSc * st.m_lSc + self.T_melt * dm) / (st.m_lSc + dm)
                st.m_sSc -= dm
                st.m_lSc += dm
                st.m_C += add["C"]; st.m_Si += add["Si"]
                st.m_Mn += add["Mn"]; st.m_P += add["P"]; st.m_Fe += add_Fe
            else:
                st.m_sSc = 0.0

            # Keep the liquid-steel mass equal to the sum of its dissolved
            # components, so iron oxidised to slag (FeO) and carbon lost as CO
            # actually reduce the tapped weight -> correct metallic yield.
            st.m_lSc = st.m_Fe + st.m_C + st.m_Si + st.m_Mn + st.m_P

            # ============================================================= #
            #  LIQUID STEEL temperature (Logar Eq. 34)                      #
            # ============================================================= #
            if st.m_lSc > 1e-3:
                dT_lSc = Q_lSc / (st.m_lSc * Cp_lSc) * dt
                st.T_lSc += dT_lSc

            # slag temperature tracks bath (simplified single slag zone) ---- #
            st.T_sl = st.T_lSc

            # ----- energy tallies ---------------------------------------- #
            st.E_elec_MJ += P_arc_kW * dt / 1000.0     # grid energy (MW basis)
            st.power_on_s += dt if P_arc_kW > 0 else 0.0
            st.t += dt

            # ----- record -------------------------------------------------- #
            if st.t >= next_record:
                pc = st.pct
                H["t"].append(st.t)
                H["m_sSc"].append(st.m_sSc / 1000.0)
                H["m_lSc"].append(st.m_lSc / 1000.0)
                H["m_slag"].append(st.slag_mass)
                H["T_sSc"].append(st.T_sSc - K)
                H["T_lSc"].append(st.T_lSc - K)
                H["T_slag"].append(st.T_sl - K)
                H["T_shell"].append(st.shell_temp_C)
                H["C"].append(pc["C"])
                H["Si"].append(pc["Si"])
                H["Mn"].append(pc["Mn"])
                H["P"].append(pc["P"] * 10)            # x10 for visibility
                H["slag_CaO"].append(st.slag["CaO"])
                H["slag_SiO2"].append(st.slag["SiO2"])
                H["slag_FeO"].append(st.slag["FeO"])
                H["slag_MnO"].append(st.slag["MnO"])
                H["slag_MgO"].append(st.slag["MgO"])
                H["slag_P2O5"].append(st.slag["P2O5"])
                H["basicity"].append(st.basicity)
                H["FeO"].append(st.feo_pct)
                H["foam"].append(st.foam_index)
                H["lime_undissolved"].append(st.m_lime_undissolved)
                H["E_elec"].append(st.E_elec_MJ / 3.6)
                H["E_chem"].append(st.E_chem_MJ / 3.6)
                H["P_arc_bath"].append(arc_to_charge_kW / 1000.0)   # MW
                H["P_chem"].append(P_chem_kW / 1000.0)
                H["P_wall"].append(Q_wall / 1000.0)
                H["P_panel"].append(Q_panel / 1000.0)
                H["P_offgas"].append(Q_offgas / 1000.0)
                H["P_loss_total"].append((Q_wall + Q_panel + Q_offgas) / 1000.0)
                H["O2_cum"].append(st.m_o2_cum / td.O2_DENSITY_NM3 / (st.m_lSc / 1000.0)
                                   if st.m_lSc > 20e3 else 0.0)          # Nm3/t
                H["CO_out"].append(st.co_out_cum)                        # kg cumulative
                H["CO2_out"].append(st.co2_cum)                          # kg cumulative
                H["spec_energy"].append((st.E_elec_MJ + st.E_chem_MJ) / 3.6
                                        / (self.total_charge_mass / 1000.0))
                H["yield_pct"].append(100.0 * st.m_lSc
                                      / (self.total_charge_mass + 1e-9))
                B3d = st.slag["SiO2"] + st.slag["Al2O3"]
                H["B3"].append(st.slag["CaO"] / B3d if B3d > 1e-6 else 0.0)
                next_record += record_every_s

            # ----- termination ------------------------------------------- #
            if mode == "endpoint":
                if (st.m_sSc < 1e-2 and st.T_lSc >= T_target + K
                        and 100 * st.m_C / st.m_liquid_total <= C_target):
                    result.reached_endpoint = True
                    log("Flat bath / refining", "Endpoint reached — ready to tap",
                        f"{st.T_lSc-K:.0f} degC, C {st.pct['C']:.3f}%, "
                        f"B2 {st.basicity:.2f}")
                    break
            elif mode == "fixed":
                if st.power_on_s >= planned_on:
                    break

        # electrode consumption estimate
        st.electrode_kg = p("electrode_consumption_rate") * (st.m_lSc / 1000.0)
        log(phase_prev, "TAP", f"{st.m_lSc/1000:.1f} t steel at {st.T_lSc-K:.0f} degC")

        result.history = H
        result.final = st
        result.events = events
        result.tap_to_tap_min = st.t / 60.0 + p("power_off_time")
        result.power_on_min = st.power_on_s / 60.0
        if not result.reached_endpoint and mode == "endpoint":
            result.notes.append(
                f"Endpoint NOT reached within {max_time_min:.0f} min — "
                f"bath {st.T_lSc-K:.0f} degC, C {100*st.m_C/st.m_liquid_total:.3f}%. "
                "Increase power/oxygen or extend time.")
        return result
