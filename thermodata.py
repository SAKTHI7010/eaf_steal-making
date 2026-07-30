"""
thermodata.py
=============
Thermophysical and thermochemical reference data for the EAF model.

All values are collected in one place so they are easy to audit and to
*re-calibrate* against plant data or the reference documents.  Where a value is
a modelling simplification (e.g. an "effective" mean heat capacity that lumps
solid-state phase transformations into a single number) this is stated in the
comment next to it.

Sign convention for reaction enthalpies
----------------------------------------
The dictionaries below store the **magnitude of the energy released** by each
exothermic oxidation reaction, expressed **per kilogram of the element (or gas)
that is oxidised**, in kJ/kg.  They are therefore *positive* numbers that are
added on the "source" side of the energy balance.

>>> CHEM_ENERGY["C_to_CO"]      # kJ per kg of carbon burned to CO
9200.0

Typical literature ranges are given so a user can see whether a re-calibrated
value is still physically sensible.

NOTE ON CALIBRATION
-------------------
Numbers marked with  # [CALIBRATE] are the ones most worth replacing with data
from your own furnace / the shared reference material, because model output is
most sensitive to them.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# 1. Molar masses  (g/mol)                                                     #
# --------------------------------------------------------------------------- #
MOLAR_MASS = {
    "C": 12.011, "O": 15.999, "O2": 31.998, "N2": 28.014,
    "Si": 28.085, "Mn": 54.938, "Fe": 55.845, "P": 30.974,
    "S": 32.060, "Ca": 40.078, "Mg": 24.305, "Al": 26.982,
    # oxides / gases
    "CaO": 56.077, "MgO": 40.304, "SiO2": 60.083, "MnO": 70.937,
    "FeO": 71.844, "Fe2O3": 159.687, "P2O5": 141.944, "Al2O3": 101.961,
    "CO": 28.010, "CO2": 44.009, "CaCO3": 100.086,
}

# Stoichiometric mass ratios that show up all the time -----------------------
# kg of element oxidised per kg of O2 consumed (useful for O2-balance):
#   C + 1/2 O2 -> CO      : 12 kg C  needs 16 kg O2  -> 0.750 kg C / kg O2
#   C +     O2 -> CO2     : 12 kg C  needs 32 kg O2  -> 0.375 kg C / kg O2
#   Si +    O2 -> SiO2    : 28 kg Si needs 32 kg O2  -> 0.878 kg Si / kg O2
#   Mn + 1/2 O2 -> MnO    : 55 kg Mn needs 16 kg O2  -> 3.433 kg Mn / kg O2
#   Fe + 1/2 O2 -> FeO    : 56 kg Fe needs 16 kg O2  -> 3.490 kg Fe / kg O2
O2_TO_ELEMENT = {
    "C_to_CO":  MOLAR_MASS["C"]  / (0.5 * MOLAR_MASS["O2"]),   # 0.750
    "C_to_CO2": MOLAR_MASS["C"]  / (1.0 * MOLAR_MASS["O2"]),   # 0.375
    "Si":       MOLAR_MASS["Si"] / (1.0 * MOLAR_MASS["O2"]),   # 0.878
    "Mn":       MOLAR_MASS["Mn"] / (0.5 * MOLAR_MASS["O2"]),   # 3.433
    "Fe":       MOLAR_MASS["Fe"] / (0.5 * MOLAR_MASS["O2"]),   # 3.490
}

# --------------------------------------------------------------------------- #
# 2. Oxidation (chemical) energy   (kJ per kg of element / gas oxidised)        #
#    Derived from standard enthalpies of formation at 298 K.                    #
# --------------------------------------------------------------------------- #
#   dHf(CO)   = -110.5 kJ/mol   -> /12.011  = 9.20 MJ/kg C
#   dHf(CO2)  = -393.5 kJ/mol   -> /12.011  = 32.76 MJ/kg C
#   CO->CO2   = -283.0 kJ/mol   -> /28.010  = 10.10 MJ/kg CO   (post-combustion)
#   dHf(SiO2) = -910.7 kJ/mol   -> /28.085  = 32.43 MJ/kg Si
#   dHf(MnO)  = -385.2 kJ/mol   -> /54.938  = 7.01 MJ/kg Mn
#   dHf(FeO)  = -266.3 kJ/mol   -> /55.845  = 4.77 MJ/kg Fe
#   dHf(P2O5) = -1492 kJ/mol    -> /(2*30.974) = 24.09 MJ/kg P
#   dHf(Al2O3)= -1675.7 kJ/mol  -> /(2*26.982) = 31.05 MJ/kg Al
CHEM_ENERGY = {                    # kJ / kg element (or kg CO for post-comb.)
    "C_to_CO":   9_200.0,          # carbon -> CO      (bath reaction)
    "C_to_CO2": 32_762.0,          # carbon -> CO2     (full combustion)
    "CO_to_CO2": 10_103.0,         # CO -> CO2         (freeboard post-combustion, per kg CO)
    "Si":       32_435.0,          # [CALIBRATE-able] Si -> SiO2
    "Mn":        7_011.0,          # Mn -> MnO
    "Fe":        5_025.0,          # Fe -> FeO   (~5025 kJ/kg Fe; = yield loss)
    "P":        24_090.0,          # P  -> P2O5
    "Al":       31_050.0,          # Al -> Al2O3 (deox / chemical heat)
}

# --------------------------------------------------------------------------- #
# 3. Heat capacities & latent heats                                            #
#    Effective values suitable for a lumped energy balance.                    #
# --------------------------------------------------------------------------- #
# Steel ---------------------------------------------------------------------- #
CP_SOLID_STEEL   = 0.70    # kJ/(kg.K)  [CALIBRATE] effective 25 C -> solidus,
                           #            lumps alpha/gamma transformation heats.
                           #            Literature effective range 0.65-0.75.
CP_LIQUID_STEEL  = 0.82    # kJ/(kg.K)  liquid iron/steel
L_FUSION_STEEL   = 272.0   # kJ/kg      latent heat of fusion of steel
# Cross-check: 0.70*(1536-25) + 272 + 0.82*(1650-1536)
#            = 1057.7 + 272 + 93.5  = 1423 kJ/kg = 395 kWh/t  (theoretical, OK)

# Slag ----------------------------------------------------------------------- #
CP_SLAG          = 1.25    # kJ/(kg.K)  liquid EAF slag (approx.)
L_FUSION_SLAG    = 209.0   # kJ/kg      lumped slag fusion / formation allowance

# Scrap / DRI as charged (solid, before melting) ----------------------------- #
CP_SCRAP         = 0.70    # kJ/(kg.K)  ~ solid steel
CP_DRI           = 0.75    # kJ/(kg.K)  DRI/HBI solid

# Fluxes --------------------------------------------------------------------- #
CP_LIME          = 1.00    # kJ/(kg.K)  CaO (burnt lime)
CP_DOLOMITE      = 1.05    # kJ/(kg.K)  dolomitic lime
# Calcination of limestone / raw dolomite is endothermic; if RAW carbonate is
# charged instead of burnt lime, subtract this per kg of carbonate:
H_CALCINATION_CACO3 = 1660.0   # kJ/kg CaCO3  (CaCO3 -> CaO + CO2, endothermic)

# --------------------------------------------------------------------------- #
# 4. Off-gas heat capacities  (kJ/(kg.K), high-temperature effective)          #
# --------------------------------------------------------------------------- #
CP_GAS = {
    "CO":  1.30,
    "CO2": 1.25,
    "N2":  1.30,
    "O2":  1.10,
    "H2O": 2.20,
}

# --------------------------------------------------------------------------- #
# 5. Reference temperatures                                                    #
# --------------------------------------------------------------------------- #
T_AMBIENT_C   = 25.0       # deg C  reference / charge temperature

# --------------------------------------------------------------------------- #
# 6. Liquidus estimate                                                         #
# --------------------------------------------------------------------------- #
# Linear liquidus-depression coefficients (deg C per wt-%) for plain / low
# alloy steel.  T_liq = T_pure_iron - sum(k_i * %i).   [CALIBRATE for your grades]
T_PURE_IRON_C = 1538.0
LIQUIDUS_DEPRESSION = {     # deg C lost per 1 wt-% of element
    "C":  80.0,
    "Si": 13.0,
    "Mn":  4.9,
    "P":  30.0,
    "S":  25.0,
    "Cu":  5.0,
    "Ni":  3.5,
    "Cr":  1.5,
}


def liquidus_temperature_c(composition_pct: dict) -> float:
    """
    Estimate the liquidus temperature (deg C) from bath composition.

    Parameters
    ----------
    composition_pct : dict
        Weight-percent of alloying elements, e.g. {"C": 0.06, "Mn": 0.4}.
        Elements not in the coefficient table are ignored.

    Returns
    -------
    float
        Liquidus temperature in deg C.
    """
    depression = sum(
        LIQUIDUS_DEPRESSION.get(el, 0.0) * pct
        for el, pct in composition_pct.items()
    )
    return T_PURE_IRON_C - depression


# --------------------------------------------------------------------------- #
# 7. Handy unit conversions                                                    #
# --------------------------------------------------------------------------- #
KWH_PER_MJ = 1.0 / 3.6          # 1 MJ  = 0.2778 kWh
MJ_PER_KWH = 3.6               # 1 kWh = 3.6 MJ
KJ_PER_KWH = 3600.0

# Density of O2 at normal conditions (0 deg C, 1 atm) to convert Nm3 <-> kg
O2_DENSITY_NM3 = 1.429          # kg / Nm3
NG_DENSITY_NM3 = 0.717          # kg / Nm3 (approx. natural gas ~ methane)
NG_LHV = 50_000.0               # kJ/kg  lower heating value of natural gas (~50 MJ/kg)


def mj_to_kwh(mj: float) -> float:
    return mj * KWH_PER_MJ


def kwh_to_mj(kwh: float) -> float:
    return kwh * MJ_PER_KWH
