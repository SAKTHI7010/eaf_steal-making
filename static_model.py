"""
static_model.py
===============
Static (per-heat) mass- and energy-balance model for the EAF.

The static model answers the planning questions an operator or process engineer
asks *before* the heat:

    * How much liquid steel will I tap from this charge?  (yield)
    * How much slag will I make, and how much lime do I need to hit my
      target basicity?
    * How much oxygen and carbon do I need?
    * How much electrical energy will the heat take, and where does the
      energy go?  (a full energy balance / "Sankey")

It is an algebraic balance (no time), solved with a short fixed-point iteration
because the tapped-steel mass and the amounts of oxide formed depend on each
other.

Method
------
Mass balance  : elemental book-keeping of Fe, C, Si, Mn, P (+ inert Cu/S) from
                scrap / DRI / hot metal, with oxidation to slag and off-gas.
Energy balance: sinks (heat steel, heat slag, heat off-gas, calcine flux,
                losses) minus non-electrical sources (oxidation chemical
                energy, CO post-combustion, burners, hot-metal sensible heat)
                gives the required electrical energy.

References for the balance structure: standard EAF energy/mass-balance practice
(e.g. Kirschen et al.; and the energy-stream decomposition in
"Modeling and Energy Efficiency Analysis of the Steelmaking Process in an EAF").
Thermochemical data are in ``thermodata.py``.

All energies are handled in MJ internally and reported in kWh (and kWh/t).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import math

from . import thermodata as td


# --------------------------------------------------------------------------- #
#  Result container                                                            #
# --------------------------------------------------------------------------- #
@dataclass
class StaticResult:
    """Everything the static balance computes, in tidy attributes."""
    # masses (kg) --------------------------------------------------------- #
    steel_mass: float = 0.0
    slag_mass: float = 0.0
    offgas_mass: float = 0.0
    dust_mass: float = 0.0
    metallic_yield: float = 0.0            # steel_out / metallic_in (fraction)

    slag: dict = field(default_factory=dict)          # oxide -> kg
    offgas: dict = field(default_factory=dict)         # gas   -> kg
    tap_composition: dict = field(default_factory=dict)  # element -> wt-%

    basicity_B2: float = 0.0               # CaO/SiO2
    basicity_B3: float = 0.0               # (CaO+MgO)/SiO2
    lime_required_for_target: float = 0.0  # kg to hit target basicity
    oxygen_required: float = 0.0           # Nm3 (chemistry demand)

    # energy (kWh) -------------------------------------------------------- #
    energy_sinks: dict = field(default_factory=dict)    # MJ by sink
    energy_sources: dict = field(default_factory=dict)  # MJ by non-electrical source
    electrical_energy_kWh: float = 0.0
    electrical_energy_specific: float = 0.0   # kWh/t liquid steel
    chemical_energy_kWh: float = 0.0
    total_energy_specific: float = 0.0        # kWh/t (electrical + chemical + burner)

    tap_to_tap_min: float = 0.0
    electrode_consumption_kg: float = 0.0
    notes: list = field(default_factory=list)

    # convenience --------------------------------------------------------- #
    def summary(self) -> str:
        s = self.slag
        lines = [
            "=" * 66,
            " STATIC EAF MASS & ENERGY BALANCE",
            "=" * 66,
            f" Liquid steel tapped        : {self.steel_mass/1000:8.2f} t",
            f" Metallic yield             : {self.metallic_yield*100:8.2f} %",
            f" Slag mass                  : {self.slag_mass:8.0f} kg "
            f"({self.slag_mass/self.steel_mass*1000:5.1f} kg/t)",
            f" Off-gas mass               : {self.offgas_mass:8.0f} kg",
            f" Dust                       : {self.dust_mass:8.0f} kg",
            "-" * 66,
            " TAP CHEMISTRY (wt-%)",
            "   " + "  ".join(f"{el}:{v:.3f}" for el, v in
                              self.tap_composition.items()),
            f" Slag basicity  B2=CaO/SiO2 : {self.basicity_B2:8.2f}",
            f"                B3          : {self.basicity_B3:8.2f}",
            f" Lime to hit target B2      : {self.lime_required_for_target:8.0f} kg",
            f" Oxygen (chemistry demand)  : {self.oxygen_required:8.0f} Nm3 "
            f"({self.oxygen_required/(self.steel_mass/1000):5.1f} Nm3/t)",
            "-" * 66,
            " ENERGY BALANCE",
            f"   Electrical energy        : {self.electrical_energy_kWh:8.0f} kWh "
            f"({self.electrical_energy_specific:6.1f} kWh/t)",
            f"   Chemical energy          : {self.chemical_energy_kWh:8.0f} kWh",
            f"   Total input (spec.)      : {self.total_energy_specific:8.1f} kWh/t",
            f"   Est. tap-to-tap time     : {self.tap_to_tap_min:8.1f} min",
            f"   Electrode consumption    : {self.electrode_consumption_kg:8.0f} kg",
            "=" * 66,
        ]
        return "\n".join(lines)

    def energy_breakdown(self) -> str:
        """Human-readable energy 'Sankey' (where the energy goes / comes from)."""
        tot_sink = sum(self.energy_sinks.values())
        lines = ["ENERGY DEMAND (sinks):"]
        for k, v in sorted(self.energy_sinks.items(),
                           key=lambda kv: -kv[1]):
            lines.append(f"   {k:<28}{v/3.6:8.0f} kWh   "
                         f"{100*v/tot_sink:5.1f}%")
        lines.append(f"   {'TOTAL DEMAND':<28}{tot_sink/3.6:8.0f} kWh")
        lines.append("")
        tot_src = sum(self.energy_sources.values())
        lines.append("NON-ELECTRICAL SUPPLY (sources):")
        for k, v in sorted(self.energy_sources.items(), key=lambda kv: -kv[1]):
            lines.append(f"   {k:<28}{v/3.6:8.0f} kWh")
        lines.append(f"   {'TOTAL NON-ELECTRICAL':<28}{tot_src/3.6:8.0f} kWh")
        lines.append("")
        lines.append(f"   => ELECTRICAL ENERGY NEEDED  {self.electrical_energy_kWh:8.0f} kWh")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  The model                                                                   #
# --------------------------------------------------------------------------- #
class StaticEAFModel:
    """
    Static mass/energy balance driven by a :class:`ParameterRegistry`.

    Usage
    -----
    >>> from eaf_control_model import default_parameters, StaticEAFModel
    >>> reg = default_parameters()
    >>> res = StaticEAFModel(reg).solve()
    >>> print(res.summary())
    """

    def __init__(self, registry):
        self.reg = registry

    # -- helpers ------------------------------------------------------------ #
    def _p(self, name):
        return self.reg.get(name)

    # -- main solve -------------------------------------------------------- #
    def solve(self, *, size_lime_to_target: bool = False) -> StaticResult:
        """
        Run the static balance.

        Parameters
        ----------
        size_lime_to_target : bool
            If True, the CaO charged is *computed* from 'target_basicity'
            (the model tells you how much lime to add).  If False, the lime
            you entered in 'lime_charged' is used and the resulting basicity
            is reported.
        """
        p = self._p
        r = StaticResult()

        Tamb = p("ambient_temperature")
        Ttap = p("target_tap_temperature")

        # ---------------------------------------------------------------- #
        # 1. Gather metallic inputs and their element masses (kg)          #
        # ---------------------------------------------------------------- #
        m_scrap = p("scrap_charge_mass") * 1000.0          # kg
        comp = p("scrap_composition")                       # wt-%
        # scrap element masses
        el_in = {e: m_scrap * comp.get(e, 0.0) / 100.0
                 for e in ("C", "Si", "Mn", "P", "S", "Cu")}
        fe_scrap = m_scrap - sum(el_in.values())            # Fe balance

        # DRI ------------------------------------------------------------- #
        m_dri = p("dri_mass") * 1000.0
        dri_metal = p("dri_metallization") / 100.0
        dri_C = p("dri_carbon") / 100.0
        dri_gangue = p("dri_gangue") / 100.0
        # In DRI, total Fe ~ (1 - gangue - C); metallic part is dri_metal of it,
        # the rest is FeO that must be reduced (consumes C/energy).
        fe_total_dri = m_dri * (1.0 - dri_gangue - dri_C)
        fe_metal_dri = fe_total_dri * dri_metal
        feo_in_dri = (fe_total_dri - fe_metal_dri) / td.MOLAR_MASS["Fe"] * \
            td.MOLAR_MASS["FeO"]                            # kg FeO charged
        c_dri = m_dri * dri_C
        gangue_dri = m_dri * dri_gangue                     # ~ SiO2 + Al2O3
        el_in["C"] += c_dri

        # Hot metal ------------------------------------------------------- #
        m_hm = p("hot_metal_mass") * 1000.0
        hm_C = p("hot_metal_carbon") / 100.0
        hm_Si = 0.006                                        # typical 0.6% Si
        hm_Mn = 0.003
        fe_hm = m_hm * (1 - hm_C - hm_Si - hm_Mn)
        el_in["C"] += m_hm * hm_C
        el_in["Si"] += m_hm * hm_Si
        el_in["Mn"] += m_hm * hm_Mn

        fe_metallic_in = fe_scrap + fe_metal_dri + fe_hm
        metallic_in = fe_metallic_in + sum(el_in.values())  # kg metal charged

        # ---------------------------------------------------------------- #
        # 2. Refining: decide what is removed / oxidised                   #
        #    (fixed-point on steel mass because C_removed depends on it)   #
        # ---------------------------------------------------------------- #
        C_target = p("target_carbon") / 100.0
        mn_part = p("mn_slag_partition")
        fe_ox_frac = p("iron_oxidation_fraction")
        dust_rate = p("dust_rate")                           # kg/t

        # Si: assume essentially all Si oxidises to slag (strong affinity)
        si_removed = el_in["Si"] * 0.98
        # Mn: partition fraction oxidises to slag
        mn_removed = el_in["Mn"] * mn_part
        # P: aim for good dephosphorisation; fraction removed depends on
        #    basicity feasibility -- assume 0.75 if basic slag maintained.
        p_removed = el_in["P"] * 0.75
        # Fe lost to slag as FeO (yield loss)
        fe_to_slag = fe_metallic_in * fe_ox_frac

        # Charge (bucket) + injected carbon are additional carbon that is
        # oxidised (to CO) in the bath -> extra chemical energy AND extra oxygen
        # demand. (A static approximation: all non-steel carbon burns to CO;
        # the small endothermic FeO-reduction path is not separated out.)
        c_extra = p("charge_carbon") + p("injected_carbon")

        # iterate steel mass -> carbon to remove -> off-gas
        steel_mass = metallic_in * 0.90     # first guess
        for _ in range(25):
            C_final = C_target * steel_mass
            c_removed = max(el_in["C"] + c_extra - C_final, 0.0)  # kg C oxidised
            dust = dust_rate * (steel_mass / 1000.0)         # kg
            # steel = metallic in - Fe to slag - dust(mostly Fe) - removed alloys
            new_steel = (fe_metallic_in - fe_to_slag - dust * 0.7) + \
                (el_in["Mn"] - mn_removed) + \
                (el_in["Si"] - si_removed) + \
                (el_in["P"] - p_removed) + \
                C_final + el_in["Cu"]        # Cu stays in steel (tramp)
            if abs(new_steel - steel_mass) < 1.0:
                steel_mass = new_steel
                break
            steel_mass = new_steel

        C_final = C_target * steel_mass
        c_removed = max(el_in["C"] + c_extra - C_final, 0.0)
        dust = dust_rate * (steel_mass / 1000.0)

        # ---------------------------------------------------------------- #
        # 3. Off-gas (decarburisation products) & oxygen demand           #
        # ---------------------------------------------------------------- #
        # Split carbon removal between CO and CO2 at the reaction site.
        # Most bath decarburisation makes CO; a fraction makes CO2 directly.
        frac_CO2_direct = 0.10
        c_to_CO = c_removed * (1 - frac_CO2_direct)
        c_to_CO2 = c_removed * frac_CO2_direct
        mass_CO = c_to_CO / td.MOLAR_MASS["C"] * td.MOLAR_MASS["CO"]
        mass_CO2_direct = c_to_CO2 / td.MOLAR_MASS["C"] * td.MOLAR_MASS["CO2"]

        # Post-combustion of part of the CO in the freeboard (CO -> CO2)
        pcr = p("post_combustion_ratio")
        co_postcombusted = mass_CO * pcr
        mass_CO_out = mass_CO - co_postcombusted
        mass_CO2_out = mass_CO2_direct + \
            co_postcombusted / td.MOLAR_MASS["CO"] * td.MOLAR_MASS["CO2"]

        # Oxygen demand (Nm3): O2 to oxidise C(to CO/CO2), Si, Mn, Fe, P
        o2_kg = (
            c_to_CO / td.O2_TO_ELEMENT["C_to_CO"] +
            c_to_CO2 / td.O2_TO_ELEMENT["C_to_CO2"] +
            si_removed / td.O2_TO_ELEMENT["Si"] +
            mn_removed / td.O2_TO_ELEMENT["Mn"] +
            fe_to_slag / td.O2_TO_ELEMENT["Fe"]
        )
        # extra O2 for post-combustion (CO + 1/2 O2 -> CO2)
        o2_kg += co_postcombusted * 0.5 * td.MOLAR_MASS["O2"] / td.MOLAR_MASS["CO"]
        r.oxygen_required = o2_kg / td.O2_DENSITY_NM3       # Nm3

        offgas = {
            "CO": mass_CO_out,
            "CO2": mass_CO2_out,
            "N2": 0.02 * (mass_CO_out + mass_CO2_out),      # small leak/carrier
        }
        r.offgas = offgas
        r.offgas_mass = sum(offgas.values())

        # ---------------------------------------------------------------- #
        # 4. Slag build-up                                                 #
        # ---------------------------------------------------------------- #
        dirt_SiO2 = p("dirt_silica") * (m_scrap / 1000.0) * 0.85   # kg SiO2
        dirt_Al2O3 = p("dirt_silica") * (m_scrap / 1000.0) * 0.15  # kg Al2O3
        SiO2 = si_removed / td.MOLAR_MASS["Si"] * td.MOLAR_MASS["SiO2"] \
            + gangue_dri * 0.6 \
            + dirt_SiO2                                     # DRI gangue + scrap dirt
        MnO = mn_removed / td.MOLAR_MASS["Mn"] * td.MOLAR_MASS["MnO"]
        P2O5 = p_removed / td.MOLAR_MASS["P"] / 2 * td.MOLAR_MASS["P2O5"]
        FeO = fe_to_slag / td.MOLAR_MASS["Fe"] * td.MOLAR_MASS["FeO"] \
            + feo_in_dri * (1 - 0.8)                        # unreduced DRI FeO
        Al2O3 = gangue_dri * 0.4 + dirt_Al2O3              # DRI gangue + dirt

        # Fluxes
        lime = p("lime_charged")
        dolo = p("dolomite_charged")
        CaO_lime = lime * 0.90            # ~90% available CaO in burnt lime
        MgO_dolo = dolo * 0.38
        CaO_dolo = dolo * 0.55

        CaO = CaO_lime + CaO_dolo
        MgO = MgO_dolo

        # optionally size lime to hit target basicity
        B_target = p("target_basicity")
        CaO_needed = B_target * SiO2
        lime_needed = max(CaO_needed - CaO_dolo, 0.0) / 0.90
        r.lime_required_for_target = lime_needed
        if size_lime_to_target:
            lime = lime_needed
            CaO_lime = lime * 0.90
            CaO = CaO_lime + CaO_dolo
            r.notes.append(
                f"Lime sized to target B2={B_target:.2f}: {lime:.0f} kg charged.")

        slag = {"CaO": CaO, "MgO": MgO, "SiO2": SiO2, "MnO": MnO,
                "FeO": FeO, "P2O5": P2O5, "Al2O3": Al2O3}
        r.slag = slag
        r.slag_mass = sum(slag.values())
        r.basicity_B2 = CaO / SiO2 if SiO2 > 0 else float("inf")
        r.basicity_B3 = (CaO + MgO) / SiO2 if SiO2 > 0 else float("inf")

        # ---------------------------------------------------------------- #
        # 5. Final steel and tap chemistry                                #
        # ---------------------------------------------------------------- #
        r.steel_mass = steel_mass
        r.dust_mass = dust
        r.metallic_yield = steel_mass / metallic_in
        r.tap_composition = {
            "C":  100 * C_final / steel_mass,
            "Si": 100 * (el_in["Si"] - si_removed) / steel_mass,
            "Mn": 100 * (el_in["Mn"] - mn_removed) / steel_mass,
            "P":  100 * (el_in["P"] - p_removed) / steel_mass,
            "S":  100 * el_in["S"] / steel_mass,
            "Cu": 100 * el_in["Cu"] / steel_mass,
        }

        # ================================================================ #
        # 6. ENERGY BALANCE                                                #
        # ================================================================ #
        # ---- sinks (MJ) ------------------------------------------------ #
        q_steel = steel_mass * (
            td.CP_SOLID_STEEL * (td.T_PURE_IRON_C - Tamb) +
            td.L_FUSION_STEEL +
            td.CP_LIQUID_STEEL * (Ttap - td.T_PURE_IRON_C)
        ) / 1000.0
        q_slag = r.slag_mass * (
            td.CP_SLAG * (Ttap - Tamb) + td.L_FUSION_SLAG
        ) / 1000.0
        # off-gas sensible heat carried out (loss)
        Tog = p("offgas_temperature")
        q_offgas = sum(
            m * td.CP_GAS.get(g, 1.2) * (Tog - Tamb)
            for g, m in offgas.items()
        ) / 1000.0
        # dust sensible (leaves hot)
        q_dust = dust * 0.7 * (Ttap - Tamb) / 1000.0
        # continuous shell/cooling loss over the whole tap-to-tap time
        ton = p("power_on_time")
        toff = p("power_off_time")
        tap_to_tap = ton + toff
        q_cooling = p("panel_heat_loss") * 1000.0 * (tap_to_tap * 60.0) / 1000.0
        #                MW->kW           * seconds  -> kJ -> MJ

        # Reducing the residual FeO charged with DRI is endothermic
        # (FeO + C -> Fe + CO, ~800 kWh per tonne FeO reduced). ~80% of the DRI
        # FeO is reduced back to iron; the rest reports to slag.
        q_dri_reduction = feo_in_dri * 0.8 * 2880.0 / 1000.0    # MJ

        sinks = {
            "heat_steel": q_steel,
            "heat_slag": q_slag,
            "offgas_sensible_loss": q_offgas,
            "dust_loss": q_dust,
            "shell_cooling_loss": q_cooling,
        }
        if q_dri_reduction > 0:
            sinks["dri_feo_reduction"] = q_dri_reduction
        r.energy_sinks = sinks
        total_sink = sum(sinks.values())

        # ---- non-electrical sources (MJ) ------------------------------- #
        e_C = (c_to_CO * td.CHEM_ENERGY["C_to_CO"] +
               c_to_CO2 * td.CHEM_ENERGY["C_to_CO2"]) / 1000.0
        e_Si = si_removed * td.CHEM_ENERGY["Si"] / 1000.0
        e_Mn = mn_removed * td.CHEM_ENERGY["Mn"] / 1000.0
        e_Fe = fe_to_slag * td.CHEM_ENERGY["Fe"] / 1000.0
        e_P = p_removed * td.CHEM_ENERGY["P"] / 1000.0
        # post-combustion energy actually returned to the bath
        e_postcomb = (co_postcombusted * td.CHEM_ENERGY["CO_to_CO2"]
                      * p("post_combustion_efficiency")) / 1000.0
        # burners
        ng_kg = p("natural_gas") * td.NG_DENSITY_NM3
        e_burner = ng_kg * td.NG_LHV * 0.70 / 1000.0        # 70% to bath
        # hot-metal sensible heat credit
        e_hm = m_hm * (
            td.CP_LIQUID_STEEL * (p("hot_metal_temperature") - Tamb)
        ) / 1000.0 if m_hm > 0 else 0.0

        sources = {
            "chem_C_oxidation": e_C,
            "chem_Si_oxidation": e_Si,
            "chem_Mn_oxidation": e_Mn,
            "chem_Fe_oxidation": e_Fe,
            "chem_P_oxidation": e_P,
            "CO_post_combustion": e_postcomb,
            "oxy_fuel_burners": e_burner,
            "hot_metal_sensible": e_hm,
        }
        r.energy_sources = sources
        chem_total = e_C + e_Si + e_Mn + e_Fe + e_P + e_postcomb
        nonelec_total = sum(sources.values())

        # ---- close the balance for electrical energy ------------------- #
        # Electrical energy that must reach the *process* = demand - supply.
        # Grid electrical energy = that / electrical_efficiency (I2R losses),
        # and only arc_transfer_efficiency of arc energy reaches the charge.
        eta_elec = p("electrical_efficiency")
        eta_arc = p("arc_transfer_efficiency")
        process_deficit_MJ = max(total_sink - nonelec_total, 0.0)
        # energy the arc must deliver to the charge, accounting arc transfer:
        arc_energy_MJ = process_deficit_MJ / eta_arc
        grid_energy_MJ = arc_energy_MJ / eta_elec

        r.chemical_energy_kWh = chem_total / 3.6
        r.electrical_energy_kWh = grid_energy_MJ / 3.6
        r.electrical_energy_specific = r.electrical_energy_kWh / (steel_mass / 1000.0)
        r.total_energy_specific = (
            (grid_energy_MJ + chem_total + e_burner) / 3.6
        ) / (steel_mass / 1000.0)

        # tap-to-tap & electrodes
        r.tap_to_tap_min = tap_to_tap
        r.electrode_consumption_kg = p("electrode_consumption_rate") * \
            (steel_mass / 1000.0)

        # sanity notes
        if r.metallic_yield < 0.86:
            r.notes.append("Low metallic yield (<86%): check Fe-to-slag and "
                           "dust assumptions / over-oxidation.")
        if r.electrical_energy_specific > 480:
            r.notes.append("High specific electrical energy (>480 kWh/t): "
                           "consider more chemical energy, shorter power-off, "
                           "or better foaming.")
        return r
