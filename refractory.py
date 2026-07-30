"""
refractory.py
=============
Coupled conduction / convection / radiation heat loss through the furnace wall.

The furnace wall is treated as a series of plane layers (working lining, safety
lining, insulation, steel shell). Heat conducts through the layers in series
from the hot face (bath / slag temperature) to the outer shell surface, which
then loses heat to the surroundings by BOTH natural/forced convection AND
thermal radiation:

    hot face  ──►  [working][safety][insulation][shell]  ──►  shell surface
                     (series conduction, R_wall)              │
                                                              ├─ convection  h·A·(Ts−Ta)
                                                              └─ radiation   εσA·(Ts⁴−Ta⁴)

At steady state the conducted flux equals the externally rejected flux; the
outer-shell temperature Ts is unknown and is solved iteratively (the radiation
term makes the balance non-linear). The module returns the wall heat-loss rate,
the shell temperature and every interface temperature (for the schematic).

All temperatures are handled in kelvin internally and reported in deg C.
"""

from __future__ import annotations
from dataclasses import dataclass, field

SIGMA = 5.670374e-8   # Stefan–Boltzmann constant, W/(m^2 K^4)


@dataclass
class Layer:
    """One refractory / shell layer."""
    name: str
    thickness_mm: float
    k: float             # thermal conductivity, W/(m.K)

    @property
    def thickness_m(self) -> float:
        return self.thickness_mm / 1000.0

    @property
    def resistance_per_area(self) -> float:
        return self.thickness_m / self.k     # (m^2.K)/W


@dataclass
class WallResult:
    q_watts: float = 0.0                 # total wall heat loss, W
    q_flux: float = 0.0                  # W/m^2
    shell_temp_C: float = 0.0            # outer shell surface temperature
    interface_temps_C: list = field(default_factory=list)  # hot face -> cold face
    conv_fraction: float = 0.0           # share of external loss by convection
    rad_fraction: float = 0.0            # share by radiation


def wall_heat_loss(T_hot_C: float, T_amb_C: float, layers: list,
                   area_m2: float, h_conv: float = 15.0,
                   emissivity: float = 0.80) -> WallResult:
    """
    Steady-state multi-layer wall heat loss with coupled convection+radiation.

    Parameters
    ----------
    T_hot_C : hot-face (inner refractory) temperature, deg C
    T_amb_C : ambient / surroundings temperature, deg C
    layers  : list of Layer (hot face first, shell last)
    area_m2 : heat-transfer area of this wall section, m^2
    h_conv  : external convective coefficient, W/(m^2.K)
    emissivity : outer-shell emissivity (-)
    """
    T_hot = T_hot_C + 273.15
    T_amb = T_amb_C + 273.15
    if T_hot <= T_amb or area_m2 <= 0:
        return WallResult(0.0, 0.0, T_amb_C, [T_hot_C], 0.0, 0.0)

    R_wall_area = sum(L.resistance_per_area for L in layers)   # (m^2.K)/W
    R_wall = R_wall_area / area_m2                             # K/W

    # iterate on shell temperature (radiation makes it non-linear)
    T_s = T_amb + 0.20 * (T_hot - T_amb)
    q = 0.0
    for _ in range(80):
        h_rad = emissivity * SIGMA * (T_s * T_s + T_amb * T_amb) * (T_s + T_amb)
        h_ext = h_conv + h_rad
        R_ext = 1.0 / (h_ext * area_m2)
        q = (T_hot - T_amb) / (R_wall + R_ext)
        T_s_new = T_amb + q * R_ext
        if abs(T_s_new - T_s) < 0.05:
            T_s = T_s_new
            break
        T_s = 0.5 * T_s + 0.5 * T_s_new

    # external split (convection vs radiation) at the converged shell temp
    q_conv = h_conv * area_m2 * (T_s - T_amb)
    h_rad = emissivity * SIGMA * (T_s * T_s + T_amb * T_amb) * (T_s + T_amb)
    q_rad = h_rad * area_m2 * (T_s - T_amb)
    q_ext = q_conv + q_rad if (q_conv + q_rad) > 0 else 1.0

    # interface temperatures, hot face -> cold face
    temps = [T_hot]
    T = T_hot
    for L in layers:
        T = T - q * (L.resistance_per_area / area_m2)
        temps.append(T)

    return WallResult(
        q_watts=q, q_flux=q / area_m2, shell_temp_C=T_s - 273.15,
        interface_temps_C=[t - 273.15 for t in temps],
        conv_fraction=q_conv / q_ext, rad_fraction=q_rad / q_ext,
    )


def default_wall_layers() -> list:
    """Representative EAF lower-vessel wall build-up (hot face first)."""
    return [
        Layer("Working lining (MgO-C)", 250.0, 12.0),
        Layer("Safety lining (burnt magnesia)", 120.0, 3.5),
        Layer("Insulation board", 40.0, 0.25),
        Layer("Steel shell", 40.0, 45.0),
    ]
