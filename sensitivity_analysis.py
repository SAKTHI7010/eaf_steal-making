"""
sensitivity_analysis.py
=======================
Generate a full sensitivity analysis of the EAF model and save all plots.

Run:
    python sensitivity_analysis.py [output_dir]

Produces (into ./sensitivity_plots/ by default):
  STATIC
    1_static_energy_sweeps.png     specific electrical energy vs 6 operating inputs
    2_static_metallurgy_sweeps.png yield / FeO / basicity / slag vs their drivers
    3_static_heatmaps.png          2-parameter response surfaces (energy, basicity, yield)
    4_static_tornado.png           ranked influence on specific electrical energy
  DYNAMIC
    5_dynamic_trajectories.png     overlaid heat trajectories (T, C, melting, energy)
    6_dynamic_scalar_sweeps.png    tap-to-tap / energy / foam vs 6 operating inputs
    7_dynamic_heatmaps.png         tap-to-tap & energy vs (power x oxygen)
    8_dynamic_tornado.png          ranked influence on energy and tap-to-tap
"""

import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from eaf_control_model import sensitivity as S

OUT = sys.argv[1] if len(sys.argv) > 1 else "sensitivity_plots"
os.makedirs(OUT, exist_ok=True)


def lin(a, b, n):
    return list(np.linspace(a, b, n))


def _tornado_plot(ax, rows, base_val, unit, title):
    """Horizontal tornado bars centred on the baseline value."""
    names = [r[0] for r in rows][::-1]
    los = [r[1] for r in rows][::-1]
    his = [r[2] for r in rows][::-1]
    y = np.arange(len(names))
    for i, (lo, hi) in enumerate(zip(los, his)):
        left, right = sorted([lo, hi])
        ax.barh(i, right - left, left=left, height=0.6,
                color="#4C78A8", edgecolor="k", alpha=0.85)
    ax.axvline(base_val, color="crimson", lw=2, label=f"baseline = {base_val:.1f}")
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel(unit)
    ax.set_title(title)
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.3)


# ======================================================================= #
#  STATIC 1: specific electrical energy vs operating inputs               #
# ======================================================================= #
def fig1():
    print("  [1/8] static energy sweeps ...")
    sweeps = [
        ("scrap_charge_mass", lin(70, 120, 10), "Scrap charge (t)"),
        ("hot_metal_mass",    lin(0, 40, 10), "Hot metal charge (t)"),
        ("charge_carbon",     lin(0, 3000, 10), "Charge carbon (kg)"),
        ("natural_gas",       lin(0, 1500, 10), "Natural gas (Nm3)"),
        ("power_off_time",    lin(0, 30, 10), "Power-off time (min)"),
        ("target_tap_temperature", lin(1560, 1700, 10), "Tap temperature (degC)"),
    ]
    fig, axs = plt.subplots(2, 3, figsize=(13, 8))
    for ax, (p, vals, lab) in zip(axs.ravel(), sweeps):
        r = S.sweep_static(p, vals, ["elec_kwh_t"])
        ax.plot(vals, r["elec_kwh_t"], "o-", color="#1f77b4")
        ax.set_xlabel(lab)
        ax.set_ylabel("elec. energy (kWh/t)")
        ax.grid(alpha=0.3)
    fig.suptitle("STATIC sensitivity — specific electrical energy vs operating inputs",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(f"{OUT}/1_static_energy_sweeps.png", dpi=110)
    plt.close(fig)


# ======================================================================= #
#  STATIC 2: metallurgy sweeps                                            #
# ======================================================================= #
def fig2():
    print("  [2/8] static metallurgy sweeps ...")
    fig, axs = plt.subplots(2, 3, figsize=(13, 8))

    fe = lin(0.005, 0.06, 10)
    r = S.sweep_static("iron_oxidation_fraction", fe, ["yield_pct", "feo_pct"])
    axs[0, 0].plot([x*100 for x in fe], r["yield_pct"], "o-", color="#2ca02c")
    axs[0, 0].set_xlabel("Fe->slag fraction (%)"); axs[0, 0].set_ylabel("metallic yield (%)")
    axs[0, 1].plot([x*100 for x in fe], r["feo_pct"], "o-", color="#d62728")
    axs[0, 1].set_xlabel("Fe->slag fraction (%)"); axs[0, 1].set_ylabel("slag FeO (%)")

    lime = lin(500, 4000, 10)
    r = S.sweep_static("lime_charged", lime, ["basicity"])
    axs[0, 2].plot(lime, r["basicity"], "o-", color="#9467bd")
    axs[0, 2].axhspan(1.8, 2.6, color="green", alpha=0.1, label="target band")
    axs[0, 2].set_xlabel("lime charged (kg)"); axs[0, 2].set_ylabel("basicity B2")
    axs[0, 2].legend(fontsize=8)

    dirt = lin(0, 20, 10)
    r = S.sweep_static("dirt_silica", dirt, ["basicity", "slag_kg"])
    axs[1, 0].plot(dirt, r["basicity"], "o-", color="#9467bd")
    axs[1, 0].set_xlabel("dirt silica (kg/t)"); axs[1, 0].set_ylabel("basicity B2")
    axs[1, 1].plot(dirt, r["slag_kg"], "o-", color="#8c564b")
    axs[1, 1].set_xlabel("dirt silica (kg/t)"); axs[1, 1].set_ylabel("slag mass (kg)")

    pcr = lin(0.0, 0.6, 10)
    r = S.sweep_static("post_combustion_ratio", pcr, ["total_kwh_t", "elec_kwh_t"])
    axs[1, 2].plot(pcr, r["elec_kwh_t"], "o-", label="electrical", color="#1f77b4")
    axs[1, 2].plot(pcr, r["total_kwh_t"], "s--", label="total", color="#ff7f0e")
    axs[1, 2].set_xlabel("post-combustion ratio"); axs[1, 2].set_ylabel("energy (kWh/t)")
    axs[1, 2].legend(fontsize=8)

    for ax in axs.ravel():
        ax.grid(alpha=0.3)
    fig.suptitle("STATIC sensitivity — yield, slag chemistry & energy drivers",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(f"{OUT}/2_static_metallurgy_sweeps.png", dpi=110)
    plt.close(fig)


# ======================================================================= #
#  STATIC 3: heatmaps (2-parameter response surfaces)                     #
# ======================================================================= #
def _heatmap(ax, Z, xvals, yvals, xlab, ylab, title, cmap, fig):
    Z = np.array(Z)
    im = ax.imshow(Z, origin="lower", aspect="auto", cmap=cmap,
                   extent=[min(xvals), max(xvals), min(yvals), max(yvals)])
    ax.set_xlabel(xlab); ax.set_ylabel(ylab); ax.set_title(title)
    fig.colorbar(im, ax=ax, shrink=0.85)


def fig3():
    print("  [3/8] static heatmaps ...")
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))

    xo = lin(0, 3000, 12); yc = lin(0, 40, 12)
    Z = S.grid_static("charge_carbon", xo, "hot_metal_mass", yc, "elec_kwh_t")
    _heatmap(axs[0], Z, xo, yc, "charge carbon (kg)", "hot metal (t)",
             "Electrical energy (kWh/t)", "viridis", fig)

    xl = lin(500, 4000, 12); yd = lin(0, 20, 12)
    Z = S.grid_static("lime_charged", xl, "dirt_silica", yd, "basicity")
    _heatmap(axs[1], Z, xl, yd, "lime charged (kg)", "dirt silica (kg/t)",
             "Slag basicity B2", "plasma", fig)

    xf = lin(0.005, 0.06, 12); yu = lin(5, 30, 12)
    Z = S.grid_static("iron_oxidation_fraction", xf, "dust_rate", yu, "yield_pct")
    _heatmap(axs[2], Z, [x*100 for x in xf], yu,
             "Fe->slag fraction (%)", "dust rate (kg/t)",
             "Metallic yield (%)", "cividis", fig)

    fig.suptitle("STATIC sensitivity — 2-parameter response surfaces",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(f"{OUT}/3_static_heatmaps.png", dpi=110)
    plt.close(fig)


# ======================================================================= #
#  STATIC 4: tornado                                                      #
# ======================================================================= #
def fig4():
    print("  [4/8] static tornado ...")
    params = ["scrap_charge_mass", "hot_metal_mass", "charge_carbon", "natural_gas",
              "lime_charged", "iron_oxidation_fraction", "power_off_time",
              "target_tap_temperature", "electrical_efficiency",
              "arc_transfer_efficiency", "post_combustion_ratio", "panel_heat_loss"]
    rows, base = S.tornado("static", params, "elec_kwh_t", pct=0.20)
    fig, ax = plt.subplots(figsize=(9, 6))
    _tornado_plot(ax, rows, base, "electrical energy (kWh/t)",
                  "STATIC tornado — influence on specific electrical energy (+/-20%)")
    fig.tight_layout()
    fig.savefig(f"{OUT}/4_static_tornado.png", dpi=110)
    plt.close(fig)


# ======================================================================= #
#  DYNAMIC 5: trajectory overlays                                         #
# ======================================================================= #
def fig5():
    print("  [5/8] dynamic trajectory overlays ...")
    fig, axs = plt.subplots(2, 2, figsize=(13, 8.5))

    # (a) bath temperature vs transformer power
    for v, h, res in S.sweep_dynamic_trajectories(
            "transformer_power", [50, 65, 80, 95, 110]):
        axs[0, 0].plot(np.array(h["t"])/60, h["T_lSc"], label=f"{v:.0f} MW")
    axs[0, 0].axhline(1620, color="k", ls=":", lw=1)
    axs[0, 0].set_title("Bath temperature vs transformer power")
    axs[0, 0].set_xlabel("time (min)"); axs[0, 0].set_ylabel("bath T (degC)")
    axs[0, 0].legend(fontsize=8, title="power")

    # (b) bath carbon vs oxygen flow
    for v, h, res in S.sweep_dynamic_trajectories(
            "oxygen_flow_rate", [1500, 2500, 3500, 4500]):
        axs[0, 1].plot(np.array(h["t"])/60, h["C"], label=f"{v:.0f} Nm3/h")
    axs[0, 1].set_title("Bath carbon vs oxygen flow")
    axs[0, 1].set_xlabel("time (min)"); axs[0, 1].set_ylabel("C (wt-%)")
    axs[0, 1].legend(fontsize=8, title="O2 flow")

    # (c) melting (solid mass) vs melting HTC
    for v, h, res in S.sweep_dynamic_trajectories(
            "scrap_melt_htc", [120, 250, 400]):
        axs[1, 0].plot(np.array(h["t"])/60, h["m_sSc"], label=f"{v:.0f} kW/K")
    axs[1, 0].set_title("Solid scrap (melting) vs melt HTC")
    axs[1, 0].set_xlabel("time (min)"); axs[1, 0].set_ylabel("solid scrap (t)")
    axs[1, 0].legend(fontsize=8, title="h*A")

    # (d) cumulative electrical energy vs arc-transfer efficiency
    for v, h, res in S.sweep_dynamic_trajectories(
            "arc_transfer_efficiency", [0.60, 0.70, 0.80, 0.90]):
        axs[1, 1].plot(np.array(h["t"])/60, h["E_elec"], label=f"{v:.2f}")
    axs[1, 1].set_title("Cumulative electrical energy vs arc efficiency")
    axs[1, 1].set_xlabel("time (min)"); axs[1, 1].set_ylabel("energy (kWh)")
    axs[1, 1].legend(fontsize=8, title="eta_arc")

    for ax in axs.ravel():
        ax.grid(alpha=0.3)
    fig.suptitle("DYNAMIC sensitivity — overlaid heat trajectories",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(f"{OUT}/5_dynamic_trajectories.png", dpi=110)
    plt.close(fig)


# ======================================================================= #
#  DYNAMIC 6: scalar sweeps                                               #
# ======================================================================= #
def fig6():
    print("  [6/8] dynamic scalar sweeps ...")
    fig, axs = plt.subplots(2, 3, figsize=(13, 8))

    v = lin(50, 120, 8)
    r = S.sweep_dynamic("transformer_power", v, ["taptap_min"])
    axs[0, 0].plot(v, r["taptap_min"], "o-", color="#1f77b4")
    axs[0, 0].set_xlabel("transformer power (MW)"); axs[0, 0].set_ylabel("tap-to-tap (min)")

    v = lin(1500, 5000, 8)
    r = S.sweep_dynamic("oxygen_flow_rate", v, ["elec_kwh_t"])
    axs[0, 1].plot(v, r["elec_kwh_t"], "o-", color="#ff7f0e")
    axs[0, 1].set_xlabel("oxygen flow (Nm3/h)"); axs[0, 1].set_ylabel("elec. energy (kWh/t)")

    v = lin(0, 30, 8)
    r = S.sweep_dynamic("power_off_time", v, ["elec_kwh_t"])
    axs[0, 2].plot(v, r["elec_kwh_t"], "o-", color="#2ca02c")
    axs[0, 2].set_xlabel("power-off time (min)"); axs[0, 2].set_ylabel("elec. energy (kWh/t)")

    v = lin(0, 2500, 8)
    r = S.sweep_dynamic("injected_carbon", v, ["chem_kwh"])
    axs[1, 0].plot(v, r["chem_kwh"], "o-", color="#d62728")
    axs[1, 0].set_xlabel("injected carbon (kg)"); axs[1, 0].set_ylabel("chemical energy (kWh)")

    v = lin(0.2, 1.5, 8)
    r = S.sweep_dynamic("foaming_co_reference", v, ["foam"])
    axs[1, 1].plot(v, r["foam"], "o-", color="#9467bd")
    axs[1, 1].set_xlabel("foaming CO reference (kg/s)"); axs[1, 1].set_ylabel("foam index (final)")

    v = lin(100, 500, 8)
    r = S.sweep_dynamic("scrap_melt_htc", v, ["power_on_min"])
    axs[1, 2].plot(v, r["power_on_min"], "o-", color="#8c564b")
    axs[1, 2].set_xlabel("scrap melt HTC (kW/K)"); axs[1, 2].set_ylabel("power-on time (min)")

    for ax in axs.ravel():
        ax.grid(alpha=0.3)
    fig.suptitle("DYNAMIC sensitivity — heat outcomes vs operating inputs",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(f"{OUT}/6_dynamic_scalar_sweeps.png", dpi=110)
    plt.close(fig)


# ======================================================================= #
#  DYNAMIC 7: heatmaps                                                    #
# ======================================================================= #
def fig7():
    print("  [7/8] dynamic heatmaps (this one runs the most simulations) ...")
    fig, axs = plt.subplots(1, 2, figsize=(12, 5))
    xp = lin(55, 115, 8); yo = lin(1500, 4500, 8)

    Z = S.grid_dynamic("transformer_power", xp, "oxygen_flow_rate", yo, "taptap_min")
    _heatmap(axs[0], Z, xp, yo, "transformer power (MW)", "oxygen flow (Nm3/h)",
             "Tap-to-tap time (min)", "viridis_r", fig)

    Z = S.grid_dynamic("transformer_power", xp, "oxygen_flow_rate", yo, "elec_kwh_t")
    _heatmap(axs[1], Z, xp, yo, "transformer power (MW)", "oxygen flow (Nm3/h)",
             "Electrical energy (kWh/t)", "magma", fig)

    fig.suptitle("DYNAMIC sensitivity — power x oxygen response surfaces",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(f"{OUT}/7_dynamic_heatmaps.png", dpi=110)
    plt.close(fig)


# ======================================================================= #
#  DYNAMIC 8: tornado (energy + tap-to-tap)                               #
# ======================================================================= #
def fig8():
    print("  [8/8] dynamic tornado ...")
    params = ["transformer_power", "oxygen_flow_rate", "injected_carbon",
              "charge_carbon", "arc_transfer_efficiency", "electrical_efficiency",
              "panel_heat_loss", "power_off_time", "scrap_melt_htc",
              "post_combustion_ratio", "natural_gas"]
    fig, axs = plt.subplots(1, 2, figsize=(15, 6))
    rows, base = S.tornado("dynamic", params, "elec_kwh_t", pct=0.20)
    _tornado_plot(axs[0], rows, base, "electrical energy (kWh/t)",
                  "Influence on specific electrical energy (+/-20%)")
    rows, base = S.tornado("dynamic", params, "taptap_min", pct=0.20)
    _tornado_plot(axs[1], rows, base, "tap-to-tap (min)",
                  "Influence on tap-to-tap time (+/-20%)")
    fig.suptitle("DYNAMIC tornado — parameter influence",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(f"{OUT}/8_dynamic_tornado.png", dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    import time
    t0 = time.time()
    print(f"Generating sensitivity plots into '{OUT}/' ...")
    fig1(); fig2(); fig3(); fig4(); fig5(); fig6(); fig7(); fig8()
    print(f"Done in {time.time()-t0:.0f} s. {len(os.listdir(OUT))} figures in '{OUT}/'.")
