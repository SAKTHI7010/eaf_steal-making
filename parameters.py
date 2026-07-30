"""
parameters.py
=============
Central registry of every *operating* and *technical* parameter the EAF model
uses.  Each parameter carries:

    * a value (with a sensible default),
    * a unit,
    * a category  ("operating" | "technical"),
    * a plausible min/max range (used for validation + warnings),
    * a one-line summary and a longer help text (the "help file").

The registry is the single place an operator or engineer edits to drive the
model, and the ``help`` methods turn it into a self-documenting tool.

Typical use
-----------
>>> reg = default_parameters()
>>> reg.set("scrap_charge_mass", 92.0)          # change a value (validated)
>>> reg.help("oxygen_total")                     # print the help file for one param
>>> reg.list(category="operating")               # tabular listing
>>> reg.to_dict()                                # plain dict for the models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import textwrap


# --------------------------------------------------------------------------- #
#  Parameter object                                                            #
# --------------------------------------------------------------------------- #
@dataclass
class Parameter:
    """A single modifiable model parameter with its documentation."""
    name: str
    value: Any
    unit: str
    category: str                       # "operating" or "technical"
    summary: str                        # one-line description
    help: str                           # full "help file" text
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    default: Any = field(default=None)

    def __post_init__(self):
        if self.default is None:
            self.default = self.value

    # -- validation --------------------------------------------------------- #
    def validate(self, value: Any) -> list[str]:
        """Return a list of human-readable warnings (empty = OK)."""
        warnings: list[str] = []
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.minimum is not None and value < self.minimum:
                warnings.append(
                    f"'{self.name}' = {value} {self.unit} is below the "
                    f"expected minimum of {self.minimum} {self.unit}."
                )
            if self.maximum is not None and value > self.maximum:
                warnings.append(
                    f"'{self.name}' = {value} {self.unit} is above the "
                    f"expected maximum of {self.maximum} {self.unit}."
                )
        return warnings

    def reset(self) -> None:
        self.value = self.default


# --------------------------------------------------------------------------- #
#  Registry                                                                    #
# --------------------------------------------------------------------------- #
class ParameterRegistry:
    """A dictionary-like collection of :class:`Parameter` objects."""

    def __init__(self, parameters: list[Parameter]):
        self._params: dict[str, Parameter] = {p.name: p for p in parameters}

    # -- access ------------------------------------------------------------- #
    def __contains__(self, name: str) -> bool:
        return name in self._params

    def __getitem__(self, name: str) -> Parameter:
        return self._params[name]

    def get(self, name: str) -> Any:
        """Return the *value* of a parameter."""
        return self._params[name].value

    def set(self, name: str, value: Any, *, strict: bool = False) -> list[str]:
        """
        Update a parameter value, running range validation.

        Parameters
        ----------
        strict : bool
            If True, raise ValueError on any out-of-range value instead of just
            returning warnings.

        Returns
        -------
        list[str]
            Warning messages (empty if the value is within range).
        """
        if name not in self._params:
            raise KeyError(
                f"Unknown parameter '{name}'. Use .list() to see valid names."
            )
        p = self._params[name]
        warnings = p.validate(value)
        if warnings and strict:
            raise ValueError(" ".join(warnings))
        p.value = value
        return warnings

    def update(self, **kwargs) -> dict[str, list[str]]:
        """Bulk update; returns {name: [warnings]} for anything out of range."""
        all_warnings: dict[str, list[str]] = {}
        for name, value in kwargs.items():
            w = self.set(name, value)
            if w:
                all_warnings[name] = w
        return all_warnings

    def reset_all(self) -> None:
        for p in self._params.values():
            p.reset()

    # -- export ------------------------------------------------------------- #
    def to_dict(self) -> dict[str, Any]:
        """Flat {name: value} mapping consumed by the model classes."""
        return {name: p.value for name, p in self._params.items()}

    def names(self, category: Optional[str] = None) -> list[str]:
        return [
            n for n, p in self._params.items()
            if category is None or p.category == category
        ]

    # -- documentation / help ---------------------------------------------- #
    def help(self, name: str) -> None:
        """Print the full help file for one parameter."""
        p = self._params[name]
        rng = ""
        if p.minimum is not None or p.maximum is not None:
            lo = "-inf" if p.minimum is None else p.minimum
            hi = "+inf" if p.maximum is None else p.maximum
            rng = f"    range     : {lo} .. {hi} {p.unit}\n"
        body = textwrap.fill(p.help, width=74,
                             initial_indent="    ", subsequent_indent="    ")
        print(
            f"\n=== {p.name}  ({p.category}) ===\n"
            f"    value     : {p.value} {p.unit}\n"
            f"    default   : {p.default} {p.unit}\n"
            f"{rng}"
            f"    summary   : {p.summary}\n\n"
            f"{body}\n"
        )

    def list(self, category: Optional[str] = None) -> None:
        """Print a compact table of parameters (optionally one category)."""
        cats = ([category] if category else ["operating", "technical"])
        for cat in cats:
            names = self.names(cat)
            if not names:
                continue
            print(f"\n----- {cat.upper()} PARAMETERS "
                  f"({len(names)}) -----")
            print(f"{'name':<28}{'value':>14}  {'unit':<12}summary")
            print("-" * 96)
            for n in names:
                p = self._params[n]
                val = p.value
                if isinstance(val, float):
                    val_s = f"{val:.4g}"
                elif isinstance(val, dict):
                    val_s = "{...}"
                else:
                    val_s = str(val)
                print(f"{p.name:<28}{val_s:>14}  {p.unit:<12}{p.summary}")
        print()

    def help_all(self, category: Optional[str] = None) -> None:
        """Print the full help file for every parameter."""
        for n in self.names(category):
            self.help(n)


# --------------------------------------------------------------------------- #
#  Default parameter set                                                        #
# --------------------------------------------------------------------------- #
def default_parameters() -> ParameterRegistry:
    """
    Build the registry pre-loaded with realistic defaults for a ~100 t,
    scrap-based AC EAF.  Every value can be overridden by the user.
    """
    P = Parameter
    params: list[Parameter] = [

        # ============================================================== #
        #  OPERATING PARAMETERS  (change heat-to-heat)                    #
        # ============================================================== #
        P("scrap_charge_mass", 140.0, "t", "operating",
          "Total metallic scrap charged (all buckets).",
          "Sum of all scrap charged across buckets, in tonnes. Drives the mass "
          "and energy balance directly. Together with the metallic yield it "
          "sets how much liquid steel you can tap. Increase to raise tap "
          "weight; watch that furnace volume and transformer power can cope."),

        P("scrap_composition", {"C": 0.25, "Si": 0.15, "Mn": 0.35,
                                 "P": 0.020, "S": 0.030, "Cu": 0.25},
          "wt-%", "operating",
          "Average scrap analysis (Fe is the balance).",
          "Weight-percent of the tramp/alloy elements in the scrap mix. Fe is "
          "assumed to be the balance. Higher C and Si increase available "
          "chemical energy but also increase the oxygen and lime you need. "
          "High P or Cu limit the grades you can make. Provide your own shop "
          "average or a per-bucket weighted analysis."),

        P("dri_mass", 0.0, "t", "operating",
          "DRI / HBI charged.",
          "Mass of Direct Reduced Iron or Hot Briquetted Iron charged, in "
          "tonnes. DRI dilutes tramp elements and stabilises chemistry, but "
          "its gangue (SiO2 + Al2O3) increases slag volume and lime demand, "
          "and its FeO must be reduced (costs energy/carbon). Set 0 for a "
          "pure-scrap heat."),

        P("dri_metallization", 94.0, "%", "operating",
          "Metallic-Fe fraction of total Fe in the DRI.",
          "Percentage of the iron in DRI that is already metallic (the rest is "
          "FeO). Lower metallization means more FeO to reduce in the bath, "
          "raising carbon and energy demand. Typical commercial DRI is "
          "92-96%.", 80.0, 99.0),

        P("dri_carbon", 2.0, "wt-%", "operating",
          "Carbon content of the DRI.",
          "Carbon combined in the DRI (as Fe3C / free C). This carbon helps "
          "reduce the DRI's own FeO and contributes chemical energy. Typical "
          "1.5-4.0%.", 0.0, 5.0),

        P("dri_gangue", 4.5, "wt-%", "operating",
          "Acid gangue (SiO2+Al2O3) in the DRI.",
          "Non-iron oxide gangue in the DRI, mostly SiO2 and Al2O3. Reports "
          "directly to the slag and must be fluxed with extra lime to keep "
          "basicity, so it raises slag mass and energy loss.", 0.0, 12.0),

        P("hot_metal_mass", 0.0, "t", "operating",
          "Hot metal (liquid pig iron) charged.",
          "Optional charge of liquid blast-furnace hot metal, in tonnes. Adds "
          "large sensible heat plus chemical energy from its high C and Si, "
          "cutting electricity demand, but increases oxygen and lime needs and "
          "can lengthen refining. Set 0 for a conventional EAF."),

        P("hot_metal_carbon", 4.3, "wt-%", "operating",
          "Carbon content of charged hot metal.",
          "Carbon in the charged hot metal. All of the excess over the aim "
          "carbon must be removed by oxygen blowing, which generates chemical "
          "energy but also off-gas and takes refining time.", 3.0, 5.0),

        P("hot_metal_temperature", 1350.0, "degC", "operating",
          "Temperature of charged hot metal.",
          "Delivery temperature of hot metal. Its sensible heat above ambient "
          "is credited to the energy balance.", 1200.0, 1500.0),

        P("lime_charged", 2900.0, "kg", "operating",
          "Burnt lime (CaO) added.",
          "Mass of burnt lime charged/injected, in kilograms. Lime neutralises "
          "the acid oxides (SiO2, P2O5) to form a basic, protective, "
          "P-removing slag. Too little lime -> low basicity, poor "
          "dephosphorisation and refractory attack; too much -> viscous slag, "
          "extra energy and cost. The static model can also SIZE the lime for "
          "you from 'target_basicity'."),

        P("dolomite_charged", 2400.0, "kg", "operating",
          "Dolomitic lime (CaO.MgO) added.",
          "Dolomitic lime supplies MgO to saturate the slag and protect the "
          "MgO-C refractory lining, reducing lining wear. Typical 8-15 kg/t.",
          0.0, 4000.0),

        P("dirt_silica", 12.0, "kg/t", "operating",
          "Silica (SiO2) entering with scrap dirt / rust / sand / ash.",
          "Non-metallic acid oxide brought in on the scrap surface (adhering "
          "sand, rust, refractory fines, charge-carbon ash), per tonne of "
          "scrap. It reports to the slag as SiO2 (plus a little Al2O3) and is "
          "usually a bigger silica source than the dissolved Si in clean "
          "scrap, so it strongly affects slag volume and the lime needed for "
          "basicity. Typical 5-12 kg/t; lower for clean prime scrap.",
          0.0, 25.0),

        P("charge_carbon", 1200.0, "kg", "operating",
          "Charge (bucket) carbon added.",
          "Carbon charged with the scrap (anthracite / char). Provides early "
          "chemical energy, helps reduce FeO, and builds the carbon boil for "
          "slag foaming. Distinct from injected carbon."),

        P("injected_carbon", 800.0, "kg", "operating",
          "Lanced / injected carbon for slag foaming.",
          "Carbon injected into the slag during the flat-bath / refining "
          "period. Reacts with FeO in the slag to generate CO, foaming the "
          "slag so it covers the arc. Good foaming raises electrical "
          "efficiency and cuts refractory and panel heat load."),

        P("oxygen_total", 4600.0, "Nm3", "operating",
          "Total oxygen blown per heat.",
          "Total gaseous oxygen (lance + burners) per heat, in normal cubic "
          "metres. Oxidises C, Si, Mn, Fe and P, releasing chemical energy and "
          "driving decarburisation. Too much oxygen over-oxidises the bath "
          "(high slag FeO, yield loss); too little leaves the heat cold and "
          "under-refined. Typical 25-45 Nm3/t."),

        P("oxygen_flow_rate", 3900.0, "Nm3/h", "operating",
          "Oxygen supply rate (dynamic model).",
          "Volumetric oxygen supply rate used by the DYNAMIC model to set the "
          "instantaneous decarburisation and chemical-power rate. Capped by "
          "lance capacity. Higher flow speeds refining but risks slopping and "
          "over-oxidation at low carbon.", 0.0, 6000.0),

        P("natural_gas", 250.0, "Nm3", "operating",
          "Natural gas burned in oxy-fuel burners.",
          "Natural gas fired through wall burners to cut cold spots and add "
          "chemical energy early in the melt, in normal cubic metres. Reduces "
          "electricity demand and flattens the bath faster. Set 0 if burners "
          "are not used.", 0.0, 2000.0),

        P("transformer_power", 110.0, "MW", "operating",
          "Active electrical power set-point.",
          "Active (real) power drawn on the working tap, in megawatts. The "
          "dynamic model integrates this over power-on time. Higher power "
          "shortens tap-to-tap but raises electrode consumption, flicker and "
          "panel heat load if the arc is not shielded by foaming slag.",
          0.0, 200.0),

        P("power_on_time", 48.0, "min", "operating",
          "Planned power-on (arc) time.",
          "Total time the arc is energised per heat, in minutes. With the "
          "power set-point this fixes the electrical energy input in a "
          "fixed-profile run. In endpoint mode the dynamic model computes the "
          "time needed to reach the aim temperature.", 20.0, 120.0),

        P("power_off_time", 8.0, "min", "operating",
          "Non-productive (power-off) time.",
          "Dead time per heat with the arc off: charging, tapping, "
          "electrode/roof swings, delays. Added to power-on time to give "
          "tap-to-tap time and to size continuous heat losses. Reducing this "
          "is often the cheapest productivity gain.", 0.0, 60.0),

        P("target_tap_temperature", 1630.0, "degC", "operating",
          "Aim steel temperature at tap.",
          "Target liquid-steel temperature at tap, in deg C. Must clear the "
          "liquidus plus enough superheat for ladle handling and casting. Too "
          "high wastes energy, oxidises the bath and wears the lining; too low "
          "risks skulls and nozzle freeze in casting.", 1550.0, 1700.0),

        P("target_carbon", 0.07, "wt-%", "operating",
          "Aim carbon at tap.",
          "Target dissolved carbon at tap, in weight-percent. Sets how far the "
          "heat must be decarburised and, with oxygen activity, the tap "
          "oxygen and alloy recovery. Low aim carbon means more oxygen, higher "
          "slag FeO and lower yield.", 0.01, 1.0),

        P("target_basicity", 2.0, "-", "operating",
          "Aim slag basicity B2 = CaO/SiO2.",
          "Target binary basicity (mass ratio CaO/SiO2). Used by the static "
          "model to size the lime addition. Higher basicity improves "
          "dephosphorisation and protects the lining but, if overdone, makes "
          "the slag pasty and hard to foam. Typical EAF aim 1.8-2.6.",
          1.0, 3.5),

        # ============================================================== #
        #  TECHNICAL PARAMETERS  (furnace / plant characteristics)        #
        # ============================================================== #
        P("furnace_capacity", 130.0, "t", "technical",
          "Nominal tap weight of the furnace.",
          "Design liquid-steel tap weight, in tonnes. Reference for "
          "specific (per-tonne) figures and for range checks on charge mass "
          "and power.", 5.0, 400.0),

        P("transformer_rating", 90.0, "MVA", "technical",
          "Transformer apparent-power rating.",
          "Nameplate apparent power of the furnace transformer. Caps the "
          "achievable active power once the power factor is accounted for.",
          5.0, 300.0),

        P("electrical_efficiency", 0.93, "-", "technical",
          "Electrical efficiency, grid -> arc.",
          "Fraction of active electrical power that reaches the arc after "
          "transformer, reactor, bus-tube, cable and electrode I2R losses. The "
          "remainder is lost as heat. Typical 0.90-0.95.", 0.80, 0.99),

        P("arc_transfer_efficiency", 0.90, "-", "technical",
          "Arc-to-bath heat-transfer efficiency (foamed).",
          "Fraction of arc energy actually absorbed by the bath/scrap rather "
          "than radiated to the water panels and roof, WITH a well-foamed "
          "slag. The dynamic model reduces this toward 'arc_transfer_bare' "
          "when the slag is not foaming. Typical foamed 0.75-0.90.",
          0.40, 0.95),

        P("arc_transfer_bare", 0.40, "-", "technical",
          "Arc-to-bath efficiency with a bare (un-foamed) arc.",
          "Heat-transfer efficiency when the arc is exposed (open bath, no "
          "foam). Much of the energy radiates to the panels, so covering the "
          "arc with foaming slag is worth a large efficiency gain.",
          0.30, 0.80),

        P("panel_heat_loss", 4.5, "MW", "technical",
          "Cooling-water heat extraction when hot.",
          "Quasi-steady heat removed by the water-cooled panels and roof once "
          "the furnace is hot, in megawatts. A continuous loss that penalises "
          "long power-off and long tap-to-tap times.", 0.5, 15.0),

        P("offgas_temperature", 1350.0, "degC", "technical",
          "Off-gas temperature leaving the furnace.",
          "Temperature at which CO/CO2/N2 leave the furnace, setting the "
          "sensible-heat loss in the off-gas. Higher off-gas temperature = "
          "bigger loss. Depends on post-combustion and the 4th-hole gap.",
          800.0, 1800.0),

        P("post_combustion_ratio", 0.25, "-", "technical",
          "Fraction of CO burned to CO2 inside the furnace.",
          "Share of evolved CO that combusts to CO2 in the freeboard (from "
          "in-leaked/injected O2). This recovers extra chemical energy; the "
          "rest of the CO leaves unburned and carries its heating value out as "
          "a loss.", 0.0, 0.8),

        P("post_combustion_efficiency", 0.60, "-", "technical",
          "Fraction of post-combustion heat returned to the bath.",
          "Of the energy released by CO->CO2 in the freeboard, the share "
          "actually transferred back to the bath/scrap (the rest heats the "
          "off-gas and panels). Typical 0.5-0.7.", 0.2, 0.9),

        P("electrode_consumption_rate", 1.6, "kg/t", "technical",
          "Graphite electrode consumption.",
          "Specific graphite electrode consumption (tip oxidation + sidewall + "
          "breakage), in kilograms per tonne of steel. Rises with power-on "
          "time, oxygen and poor foaming. Used to estimate electrode cost and "
          "the small carbon pick-up from electrode tips.", 0.8, 4.0),

        P("iron_oxidation_fraction", 0.015, "-", "technical",
          "Fraction of metallic Fe lost to slag as FeO.",
          "Share of metallic iron oxidised to FeO in the slag under normal "
          "operation. The dominant yield loss. Rises with over-blowing and low "
          "carbon at tap. Used in the static yield/slag calculation.",
          0.01, 0.15),

        P("dust_rate", 16.0, "kg/t", "technical",
          "Dust (fume) generation.",
          "Mass of dust captured in the baghouse per tonne of steel "
          "(vaporised Fe/Zn, fines). A yield and material loss; also an "
          "environmental output.", 5.0, 30.0),

        # ---- kinetic / thermochemical technical constants ----------------- #
        P("decarb_critical_carbon", 0.30, "wt-%", "technical",
          "Carbon at which decarburisation becomes mass-transfer limited.",
          "Below this carbon level the decarburisation rate is limited by "
          "carbon transport to the reaction sites rather than by oxygen "
          "supply, so it slows sharply and excess oxygen starts oxidising Fe "
          "instead. Typical 0.2-0.4%.", 0.1, 0.6),

        P("decarb_mass_transfer_coeff", 0.03, "1/s", "technical",
          "Rate constant for mass-transfer-limited decarburisation.",
          "First-order rate constant used below the critical carbon: "
          "dC/dt = -k*(C - C_eq). Larger k = faster low-carbon refining "
          "(better stirring / more reaction area). [CALIBRATE to your bath "
          "stirring].", 0.001, 0.1),

        P("scrap_melt_htc", 250.0, "kW/K", "technical",
          "Effective scrap-melting heat-transfer coefficient (h*A).",
          "Lumped heat-transfer coefficient times interfacial area governing "
          "how fast superheat in the bath melts the remaining solid scrap in "
          "the DYNAMIC model. Scales with the solid fraction as scrap shrinks. "
          "[CALIBRATE so that the modelled melt-in time matches your shop].",
          10.0, 500.0),

        P("mn_slag_partition", 0.55, "-", "technical",
          "Fraction of scrap Mn oxidised to slag.",
          "Share of the manganese input that ends up as MnO in the slag under "
          "oxidising EAF conditions (the rest stays in the steel). Used in the "
          "mass balance; the balance is recovered to the steel.", 0.2, 0.9),

        P("ambient_temperature", 25.0, "degC", "technical",
          "Reference / charge temperature.",
          "Ambient reference temperature for all sensible-heat calculations "
          "and the starting temperature of cold scrap. Raise it to represent "
          "scrap pre-heating (e.g. shaft/Consteel systems).", -20.0, 800.0),

        # ---- dynamic-model arc / foaming / kinetic constants -------------- #
        # (framework follows Logar, Dovzan & Skrjanc, ISIJ Int. 52 (2012) 402 &
        #  413 -- the zone energy-balance + melting-split dynamic EAF model)
        P("arc_conduction_fraction", 0.20, "-", "technical",
          "Fraction of arc power conducted directly to the metal.",
          "Share of total arc power delivered to the metal by conduction "
          "(the rest is radiated to surfaces or lost to gas/electrodes). Logar "
          "et al. use ~0.20; radiation ~0.75; gas/electrode ~0.05.",
          0.10, 0.35),

        P("arc_gas_fraction", 0.025, "-", "technical",
          "Fraction of arc power that heats the gas / is lost to electrodes.",
          "Small share of arc power absorbed by the freeboard gas and lost at "
          "the electrode tips; leaves the metal energy balance.", 0.0, 0.10),

        P("foaming_co_reference", 0.45, "kg/s", "technical",
          "CO evolution rate giving fully developed foam.",
          "CO generation rate (from decarburisation + FeO reduction) at which "
          "the slag foam is considered fully developed, so the arc-transfer "
          "efficiency reaches its 'foamed' value. Below this the efficiency is "
          "interpolated toward the bare-arc value. [CALIBRATE].", 0.1, 2.0),

        P("si_removal_rate", 0.020, "1/s", "technical",
          "First-order rate constant for Si oxidation.",
          "Silicon oxidises quickly and almost completely early in the melt. "
          "Modelled as dSi/dt = -k*(Si - Si_eq); larger k = faster/earlier "
          "desiliconisation. Grounded in the FeO+Si and Si+O2 reactions of "
          "Logar Part 2. [CALIBRATE].", 0.001, 0.2),

        P("mn_removal_rate", 0.010, "1/s", "technical",
          "First-order rate constant for Mn oxidation toward equilibrium.",
          "Manganese partitions between metal and slag. Modelled as "
          "dMn/dt = -k*(Mn - Mn_eq), with Mn_eq set by 'mn_slag_partition'. "
          "[CALIBRATE].", 0.001, 0.1),

        P("p_removal_rate", 0.006, "1/s", "technical",
          "First-order rate constant for dephosphorisation.",
          "Phosphorus removal to slag as P2O5, favoured by high basicity, high "
          "slag FeO and lower temperature. Modelled as dP/dt = -k*f(B,FeO,T)*P. "
          "Reverts (P returns to steel) if the slag/temperature turn "
          "unfavourable. [CALIBRATE].", 0.0, 0.05),

        P("feo_reduction_rate", 1.0e-6, "1/(kg.s)", "technical",
          "Rate constant for FeO reduction by injected carbon (foaming).",
          "Governs FeO(slag) + C -> Fe + CO, the reaction that both foams the "
          "slag and recovers iron. Rate ~ k * m_C_available * m_FeO. Higher "
          "values foam faster and recover more Fe but consume carbon quicker. "
          "[CALIBRATE].", 1e-7, 1e-4),

        P("sim_timestep", 0.5, "s", "technical",
          "Integration time step of the dynamic model.",
          "Fixed Euler time step for the dynamic simulation. Smaller = more "
          "accurate but slower. 0.2-1.0 s is a good compromise for a "
          "reduced-order thermal/chemical model; reduce it if the solution "
          "looks noisy.", 0.05, 2.0),

        # ---- refractory wall (coupled conduction/convection/radiation) ---- #
        P("refractory_area", 55.0, "m2", "technical",
          "Refractory-lined hot-face area (hearth + slag/metal line).",
          "Internal area of the refractory-lined lower vessel exposed to the "
          "bath/slag, used for the coupled conduction-convection-radiation "
          "wall heat-loss calculation. Scale with furnace size.", 5.0, 200.0),
        P("working_lining_thickness", 450.0, "mm", "technical",
          "Working-lining (hot face) thickness.",
          "Thickness of the consumable hot-face lining (typically MgO-C). "
          "Thicker lining lowers heat loss and lengthens campaign life but "
          "reduces working volume.", 80.0, 800.0),
        P("working_lining_k", 12.0, "W/mK", "technical",
          "Working-lining thermal conductivity.",
          "Effective thermal conductivity of the hot-face refractory (MgO-C is "
          "relatively conductive because of its graphite content). [CALIBRATE "
          "to your brand].", 2.0, 40.0),
        P("safety_lining_thickness", 200.0, "mm", "technical",
          "Safety/backup-lining thickness.",
          "Thickness of the permanent backup lining (e.g. burnt-magnesia "
          "brick) behind the working lining.", 40.0, 400.0),
        P("safety_lining_k", 3.5, "W/mK", "technical",
          "Safety-lining thermal conductivity.",
          "Thermal conductivity of the backup lining.", 1.0, 15.0),
        P("insulation_thickness", 40.0, "mm", "technical",
          "Insulation-layer thickness.",
          "Thickness of the low-conductivity insulating layer between backup "
          "lining and steel shell; the dominant thermal resistance.", 0.0, 200.0),
        P("insulation_k", 0.25, "W/mK", "technical",
          "Insulation thermal conductivity.",
          "Conductivity of the insulation board/felt (very low -> most of the "
          "temperature drop occurs here).", 0.05, 2.0),
        P("shell_thickness", 40.0, "mm", "technical",
          "Steel-shell thickness.",
          "Thickness of the outer steel shell.", 10.0, 120.0),
        P("shell_k", 45.0, "W/mK", "technical",
          "Steel-shell thermal conductivity.", "Conductivity of carbon-steel "
          "shell (~45 W/mK).", 20.0, 60.0),
        P("shell_emissivity", 0.80, "-", "technical",
          "Outer-shell emissivity for radiation loss.",
          "Radiative emissivity of the oxidised steel shell surface, used in "
          "the external radiation heat loss.", 0.1, 1.0),
        P("convection_coefficient", 15.0, "W/m2K", "technical",
          "External convective coefficient at the shell.",
          "Combined natural/forced-convection coefficient at the outer shell "
          "surface; higher with shop draughts or shell-cooling fans.",
          3.0, 60.0),

        # ---- dissolution kinetics ---------------------------------------- #
        P("lime_dissolution_rate", 0.004, "1/s", "technical",
          "First-order dissolution rate of lime into the slag.",
          "Governs how fast charged lime dissolves into the slag and raises "
          "basicity. Undissolved lime does not count toward basicity, so a low "
          "rate delays slag formation and dephosphorisation. Depends on lime "
          "reactivity, size, slag FeO and stirring. [CALIBRATE].", 0.0005, 0.05),
        # ---- FeO evolution / decarburisation oxygen efficiency ----------- #
        P("feo_equilibrium_factor", 1.4, "-", "technical",
          "Multiplier on the Turkdogan carbon-oxygen product K_CO(T).",
          "Slag FeO and bath carbon are coupled by the Turkdogan equilibrium "
          "product (%FeO)(%C) = K_CO(T), fitted to K_CO = 1.8 / 1.25 / 0.89 at "
          "1500 / 1600 / 1700 C. This single factor scales that product for a "
          "specific furnace: >1 gives a more oxidising slag (higher tap FeO at "
          "a given carbon), <1 a more reduced slag. [CALIBRATE]", 0.3, 3.0),
        P("slag_feo_max", 45.0, "%", "technical",
          "Cap on the equilibrium slag FeO (wt-%).",
          "Upper bound applied to (%FeO)_eq = K_CO/[%C] so the equilibrium stays "
          "finite as bath carbon approaches zero. Overblown low-carbon heats "
          "reach ~40-45% FeO in practice (Morales).", 25.0, 60.0),
        P("scrap_rust_feo", 14.0, "kg/t", "charge",
          "Rust / mill-scale (as FeO) carried in on the scrap.",
          "Oxide skin and rust on the scrap report directly to the slag as FeO "
          "at charge. This sets the HIGH slag FeO observed at meltdown, which "
          "carbon injection then reduces during the boil before FeO rises "
          "again toward tap (Kirschen; Morales). Clean/prime scrap ~5 kg/t, "
          "rusty shredded/obsolete scrap ~20-30 kg/t. [CALIBRATE]", 0.0, 40.0),
        P("decarb_o2_efficiency_max", 0.90, "-", "technical",
          "Maximum oxygen efficiency for decarburisation (above critical C).",
          "Fraction of lanced oxygen that reacts with carbon when the bath is "
          "carbon-rich. Below the critical carbon this efficiency falls in "
          "proportion to [C], so the remaining oxygen oxidises iron to FeO -- "
          "the mechanism that raises tap-slag FeO. Mass-transfer grounded.", 0.6, 1.0),
        P("carbon_dissolution_rate", 0.0, "1/s", "technical",
          "First-order dissolution rate of solid carbon into the bath.",
          "Rate at which charge/injected carbon dissolves into the liquid "
          "steel (recarburisation) rather than burning at the slag. Affects "
          "the bath-carbon trajectory. [CALIBRATE].", 0.0, 0.05),
    ]

    return ParameterRegistry(params)
