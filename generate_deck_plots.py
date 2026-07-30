"""
generate_deck_plots.py
======================
Generate the figure set for the SmartEAF deck:

  1_process_trajectory.png   full 12-panel dynamic heat dashboard
  2_validation.png           model KPIs vs. literature "tentative" bands + decarb curve + energy split
  3_mass_energy_balance.png  input/output masses, energy sources/sinks, slag composition
  4_refractory_thermal.png   through-wall temperature profile + heat-loss breakdown

The reference plant is anonymised as "Industry-X". Literature bands are typical
values compiled from the reviewed corpus (Logar et al. 2012; the EAF energy-
efficiency analysis; Conejo 2024) and are used for validation of the model.
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from eaf_control_model import default_parameters, StaticEAFModel, DynamicEAFModel
from eaf_control_model import refractory as rf

OUT = "deck_plots"
os.makedirs(OUT, exist_ok=True)

reg = default_parameters()
static = StaticEAFModel(reg).solve()
dyn = DynamicEAFModel(reg).simulate(mode="endpoint")
st = dyn.final
h = dyn.history
tt = np.array(h["t"]) / 60.0

# ----------------------------------------------------------------------- #
# 1. Process trajectory (reuse the model's rich 6-panel figure)
# ----------------------------------------------------------------------- #
fig = dyn.figure(figsize=(19, 11))
fig.suptitle("Industry-X EAF (modern ~130 t UHP, scrap baseline) — simulated process trajectory",
             fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.97])
fig.savefig(f"{OUT}/1_process_trajectory.png", dpi=115)
print("wrote 1_process_trajectory.png")

# ----------------------------------------------------------------------- #
# 2. Validation vs literature bands
# ----------------------------------------------------------------------- #
fig, axs = plt.subplots(2, 3, figsize=(18, 9))

# (a) KPI bars vs literature bands
kpis = [
    ("Elec. energy\n(kWh/t)", static.electrical_energy_specific, 350, 450),
    ("Total energy\n(kWh/t)", static.total_energy_specific, 560, 650),
    ("Tap-to-tap\n(min)", dyn.tap_to_tap_min, 40, 60),
    ("Tap temp\n(degC)", st.T_lSc - 273.15, 1600, 1660),
    ("Yield\n(%)", static.metallic_yield * 100, 90, 97),
    ("O2 use\n(Nm3/t)", static.oxygen_required / (static.steel_mass / 1000), 20, 40),
    ("Electrode\n(kg/t)", static.electrode_consumption_kg / (static.steel_mass / 1000), 1.3, 2.0),
    ("Slag basicity\nB2", static.basicity_B2, 1.8, 2.4),
]
ax = axs[0, 0]
x = np.arange(len(kpis))
for i, (lab, val, lo, hi) in enumerate(kpis):
    # normalise each KPI to its band for a common axis: plot band as [0,1], value scaled
    span = hi - lo
    ax.add_patch(plt.Rectangle((i - 0.35, 0), 0.7, 1, color="#c8e6c9", alpha=0.7))
    v_norm = (val - lo) / span
    ax.plot(i, np.clip(v_norm, -0.25, 1.25), "o", color="#c62828", ms=11, zorder=5)
    ax.text(i, 1.32, f"{val:.0f}" if val > 5 else f"{val:.2f}", ha="center",
            fontsize=8, fontweight="bold")
ax.axhline(0, color="gray", lw=0.8); ax.axhline(1, color="gray", lw=0.8)
ax.set_xticks(x); ax.set_xticklabels([k[0] for k in kpis], fontsize=7)
ax.set_ylim(-0.35, 1.5); ax.set_yticks([0, 1]); ax.set_yticklabels(["band low", "band high"])
ax.set_title("Model KPIs vs. literature-typical bands\n(green = literature range, red dot = model)", fontsize=10)

# (b) Decarburisation trajectory vs typical band
ax = axs[0, 1]
ax.plot(tt, h["C"], color="#1f77b4", lw=2, label="model bath [C]")
ax.axhspan(0.03, 0.10, color="#c8e6c9", alpha=0.6, label="typical tap [C] band")
ax.axhline(reg.get("target_carbon"), color="k", ls=":", label="aim C")
ax.set_xlabel("time (min)"); ax.set_ylabel("bath carbon (wt-%)")
ax.set_title("Decarburisation: carbon boil then refine to aim", fontsize=10)
ax.legend(fontsize=8); ax.grid(alpha=0.3)

# (c) Energy input split (electrical vs chemical) vs literature
ax = axs[1, 0]
e_elec = static.electrical_energy_kWh
e_chem = static.chemical_energy_kWh
tot = e_elec + e_chem
model_split = [100 * e_elec / tot, 100 * e_chem / tot]
lit_split = [62, 38]
xb = np.arange(2)
ax.bar(xb - 0.2, model_split, 0.4, label="model", color="#1f77b4")
ax.bar(xb + 0.2, lit_split, 0.4, label="literature typical", color="#9e9e9e")
ax.set_xticks(xb); ax.set_xticklabels(["Electrical", "Chemical"])
ax.set_ylabel("share of input energy (%)")
ax.set_title("Energy input split vs. literature", fontsize=10)
ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)

# (d) Energy sinks (where the energy goes)
ax = axs[1, 1]
sinks = static.energy_sinks
labels = [k.replace("_", " ") for k in sinks]
vals = [v / 3.6 for v in sinks.values()]
order = np.argsort(vals)[::-1]
labels = [labels[i] for i in order]; vals = [vals[i] for i in order]
ax.barh(labels, vals, color="#ef6c00")
ax.invert_yaxis()
ax.set_xlabel("energy (kWh)")
ax.set_title("Energy demand distribution (sinks)", fontsize=10)
ax.grid(axis="x", alpha=0.3)

fig.suptitle("Industry-X EAF model — validation against literature-typical data",
             fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.96])
# (e) slag composition (wt-%) vs research bands
ax = axs[0, 2]
sc = {k: 100 * static.slag[k] / static.slag_mass for k in ["FeO", "CaO", "SiO2", "MgO", "MnO"]}
bands = {"FeO": (20, 32), "CaO": (28, 40), "SiO2": (10, 18), "MgO": (6, 12), "MnO": (3, 7)}
xs = list(sc.keys()); xi = np.arange(len(xs))
for i, k in enumerate(xs):
    lo, hi = bands[k]; ax.add_patch(plt.Rectangle((i - 0.35, lo), 0.7, hi - lo, color="#c8e6c9", alpha=0.6, zorder=0))
ax.scatter(xi, [sc[k] for k in xs], color="#d62728", s=70, zorder=5)
for i, k in enumerate(xs): ax.text(i, sc[k] + 1.2, f"{sc[k]:.0f}", ha="center", fontsize=8)
ax.set_xticks(xi); ax.set_xticklabels(xs); ax.set_ylabel("wt-%")
ax.set_title("Tap-slag composition vs literature bands", fontsize=10); ax.set_ylim(0, 45); ax.grid(axis="y", alpha=0.3)

# (f) FeO evolution shape vs plant practice (meltdown / boil / tap)
ax = axs[1, 2]
hh = dyn.history; tmin = np.array(hh["t"]) / 60.0; feo = np.array(hh["FeO"])
ax.plot(tmin, feo, color="#d62728", lw=1.8, label="model FeO")
ax.axhspan(17, 23, color="#c8e6c9", alpha=0.4, label="foaming window")
pk = feo[tmin < 6].max(); dp = feo[(tmin > 8) & (tmin < 30)].min()
ax.annotate(f"meltdown peak ~{pk:.0f}%", (tmin[np.argmax(feo[tmin<6])], pk), fontsize=7.5,
            xytext=(tmin.max()*0.25, 40), arrowprops=dict(arrowstyle="->", lw=0.7))
ax.annotate(f"carbon-boil dip ~{dp:.0f}%", (tmin[(tmin>8)&(tmin<30)][np.argmin(feo[(tmin>8)&(tmin<30)])], dp),
            fontsize=7.5, xytext=(tmin.max()*0.3, 2), arrowprops=dict(arrowstyle="->", lw=0.7))
ax.annotate(f"tap ~{feo[-1]:.0f}%", (tmin[-1], feo[-1]), fontsize=7.5,
            xytext=(tmin.max()*0.62, 33), arrowprops=dict(arrowstyle="->", lw=0.7))
ax.set_xlabel("time (min)"); ax.set_ylabel("slag FeO (wt-%)"); ax.set_ylim(0, 45)
ax.set_title("FeO evolution vs plant shape (Kirschen/Morales)", fontsize=10); ax.legend(fontsize=7, loc="upper center"); ax.grid(alpha=0.3)

fig.savefig(f"{OUT}/2_validation.png", dpi=115)
print("wrote 2_validation.png")

# ----------------------------------------------------------------------- #
# 3. Mass & energy balance
# ----------------------------------------------------------------------- #
fig, axs = plt.subplots(2, 3, figsize=(18, 9))

# (a) input vs output masses
ax = axs[0, 0]
ins = {
    "Scrap": reg.get("scrap_charge_mass") * 1000,
    "Lime": reg.get("lime_charged"),
    "Dolomite": reg.get("dolomite_charged"),
    "Carbon": reg.get("charge_carbon") + reg.get("injected_carbon"),
    "Oxygen": static.oxygen_required * 1.429,
}
outs = {
    "Liquid steel": static.steel_mass,
    "Slag": static.slag_mass,
    "Off-gas": static.offgas_mass,
    "Dust": static.dust_mass,
}
ax.bar(list(ins.keys()), [v / 1000 for v in ins.values()], color="#1976d2")
ax.set_ylabel("mass (t)"); ax.set_title("Inputs (per heat)", fontsize=10)
ax.tick_params(axis="x", rotation=25); ax.grid(axis="y", alpha=0.3)

ax = axs[0, 1]
ax.bar(list(outs.keys()), [v / 1000 for v in outs.values()], color="#388e3c")
ax.set_ylabel("mass (t)"); ax.set_title("Outputs (per heat)", fontsize=10)
ax.tick_params(axis="x", rotation=20); ax.grid(axis="y", alpha=0.3)

# (c) tap steel composition
ax = axs[1, 0]
comp = static.tap_composition
ax.bar(list(comp.keys()), list(comp.values()), color="#5e35b1")
ax.set_ylabel("wt-%"); ax.set_title("Final tapped-steel composition", fontsize=10)
ax.grid(axis="y", alpha=0.3)
for i, (k, v) in enumerate(comp.items()):
    ax.text(i, v, f"{v:.3f}", ha="center", va="bottom", fontsize=7)

# (d) final slag composition (pie)
ax = axs[1, 1]
slag = {k: v for k, v in static.slag.items() if v > 1}
ax.pie(list(slag.values()), labels=list(slag.keys()), autopct="%1.0f%%",
       colors=plt.cm.tab20.colors, textprops={"fontsize": 8})
ax.set_title(f"Final slag composition (B2={static.basicity_B2:.2f})", fontsize=10)

fig.suptitle("Industry-X EAF — mass & energy balance (inputs, outputs, products)",
             fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(f"{OUT}/3_mass_energy_balance.png", dpi=115)
print("wrote 3_mass_energy_balance.png")

# ----------------------------------------------------------------------- #
# 4. Refractory thermal profile + heat-loss breakdown
# ----------------------------------------------------------------------- #
fig, axs = plt.subplots(1, 2, figsize=(13, 5.2))

layers = [
    rf.Layer("Working\nlining", reg.get("working_lining_thickness"), reg.get("working_lining_k")),
    rf.Layer("Safety\nlining", reg.get("safety_lining_thickness"), reg.get("safety_lining_k")),
    rf.Layer("Insul.", reg.get("insulation_thickness"), reg.get("insulation_k")),
    rf.Layer("Shell", reg.get("shell_thickness"), reg.get("shell_k")),
]
wall = rf.wall_heat_loss(st.T_lSc - 273.15, reg.get("ambient_temperature"),
                         layers, reg.get("refractory_area"),
                         reg.get("convection_coefficient"), reg.get("shell_emissivity"))
# temperature profile through the wall
ax = axs[0]
xpos = [0]
for L in layers:
    xpos.append(xpos[-1] + L.thickness_mm)
temps = wall.interface_temps_C
ax.plot(xpos, temps, "o-", color="#c62828", lw=2)
# shade layers
colors = ["#ffcc80", "#ffe0b2", "#b3e5fc", "#cfd8dc"]
for i, L in enumerate(layers):
    ax.axvspan(xpos[i], xpos[i + 1], color=colors[i], alpha=0.5)
    ax.text((xpos[i] + xpos[i + 1]) / 2, max(temps) * 0.9, L.name,
            ha="center", fontsize=8)
ax.set_xlabel("distance from hot face (mm)")
ax.set_ylabel("temperature (degC)")
ax.set_title(f"Through-wall temperature profile\n(hot face {temps[0]:.0f} degC -> shell {wall.shell_temp_C:.0f} degC, "
             f"loss {wall.q_watts/1000:.0f} kW)", fontsize=10)
ax.grid(alpha=0.3)

# heat-loss breakdown at tap
ax = axs[1]
losses = {
    "Off-gas\nsensible": st.offgas_loss_kW,
    "Water panels\n& roof": st.panel_loss_kW,
    "Refractory wall\n(cond+conv+rad)": st.wall_loss_kW,
}
ax.pie(list(losses.values()), labels=list(losses.keys()), autopct="%1.0f%%",
       colors=["#ef5350", "#42a5f5", "#8d6e63"], textprops={"fontsize": 9})
ax.set_title(f"Instantaneous heat-loss breakdown at tap\n(total {sum(losses.values()):.0f} kW)", fontsize=10)

fig.suptitle("Industry-X EAF — refractory heat transfer (coupled conduction / convection / radiation)",
             fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.93])
fig.savefig(f"{OUT}/4_refractory_thermal.png", dpi=115)
print("wrote 4_refractory_thermal.png")

print(f"\nAll deck plots written to '{OUT}/'.")

# ----------------------------------------------------------------------- #
# 5. India DRI energy penalty (validates the gangue/FeO recalibration)
# ----------------------------------------------------------------------- #
fig, axs = plt.subplots(1, 2, figsize=(13, 5.0))
dri_pct = list(range(0, 61, 6))
elec, total, slagm, yld = [], [], [], []
for d in dri_pct:
    r = default_parameters()
    dm = 140.0 * d / 100.0
    r.set("scrap_charge_mass", max(140.0 - dm, 55.0))
    r.set("dri_mass", dm); r.set("dri_metallization", 88); r.set("dri_gangue", 6.0)
    r.set("dri_carbon", 1.5); r.set("lime_charged", 3100 + d * 45)
    sx = StaticEAFModel(r).solve()
    elec.append(sx.electrical_energy_specific); total.append(sx.total_energy_specific)
    slagm.append(sx.slag_mass / (sx.steel_mass / 1000)); yld.append(sx.metallic_yield * 100)

ax = axs[0]
ax.axhspan(310, 640, color="#c8e6c9", alpha=0.5, label="DRI-melting band (lit. 310-640 kWh/t)")
ax.plot(dri_pct, elec, "o-", color="#1f77b4", label="electrical")
ax.plot(dri_pct, total, "s-", color="#d62728", label="total (elec+chem)")
ax.set_xlabel("DRI in charge (%)"); ax.set_ylabel("specific energy (kWh/t)")
ax.set_title("Energy vs DRI fraction\n(~+1.8 kWh/t per %DRI: gangue + endothermic FeO reduction)", fontsize=10)
ax.legend(fontsize=8); ax.grid(alpha=0.3)

ax = axs[1]
ax.plot(dri_pct, slagm, "o-", color="#8c564b", label="slag mass (kg/t)")
ax.set_xlabel("DRI in charge (%)"); ax.set_ylabel("slag mass (kg/t)", color="#8c564b")
ax.axhspan(100, 200, color="#efe0c8", alpha=0.5)
ax2 = ax.twinx()
ax2.plot(dri_pct, yld, "s--", color="#2ca02c", label="metallic yield (%)")
ax2.set_ylabel("metallic yield (%)", color="#2ca02c")
ax.set_title("Slag mass & yield vs DRI\n(coal-based DRI: metallisation 88%, gangue 6%)", fontsize=10)
ax.grid(alpha=0.3)

fig.suptitle("Industry-X EAF \u2014 India DRI/sponge-iron recalibration (coal-based DRI)",
             fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.93])
fig.savefig(f"{OUT}/5_dri_energy_penalty.png", dpi=115)
print("wrote 5_dri_energy_penalty.png")

# ----------------------------------------------------------------------- #
# 6. Slag composition in wt-% (trajectory + final) -- IMPORTANT
# ----------------------------------------------------------------------- #
h = dyn.history
tt2 = np.array(h["t"]) / 60.0
msl = np.array(h["m_slag"])
msl_safe = np.where(msl > 1e-6, msl, 1e-6)
comp_keys = [("slag_CaO", "CaO", "#1f77b4"), ("slag_SiO2", "SiO2", "#ff7f0e"),
             ("slag_FeO", "FeO", "#d62728"), ("slag_MgO", "MgO", "#2ca02c"),
             ("slag_MnO", "MnO", "#9467bd"), ("slag_P2O5", "P2O5", "#17becf")]
wt = {lab: 100.0 * np.array(h[k]) / msl_safe for k, lab, _ in comp_keys}
other = np.clip(100.0 - sum(wt.values()), 0, None)   # Al2O3 + remainder

fig, axs = plt.subplots(1, 2, figsize=(13, 5.2))

# (a) stacked-area wt-% trajectory
ax = axs[0]
labels = [lab for _, lab, _ in comp_keys] + ["Al2O3/other"]
colors = [c for _, _, c in comp_keys] + ["#b0b0b0"]
series = [wt[lab] for _, lab, _ in comp_keys] + [other]
ax.stackplot(tt2, *series, labels=labels, colors=colors, alpha=0.9)
ax.set_xlim(tt2.min(), tt2.max()); ax.set_ylim(0, 100)
ax.set_xlabel("time (min)"); ax.set_ylabel("slag composition (wt-%)")
ax.set_title("Slag composition trajectory (wt-%)", fontsize=11)
ax.legend(fontsize=8, loc="upper right", ncol=2)

# (b) final slag composition (wt-%) bar
ax = axs[1]
fin = {lab: 100.0 * static.slag[lab] / static.slag_mass
       for lab in ["CaO", "SiO2", "FeO", "MgO", "MnO", "P2O5", "Al2O3"]
       if static.slag.get(lab, 0) > 0}
order = sorted(fin, key=fin.get, reverse=True)
ax.barh(order, [fin[k] for k in order],
        color=["#1f77b4", "#ff7f0e", "#d62728", "#2ca02c", "#9467bd", "#17becf", "#b0b0b0"][:len(order)])
ax.invert_yaxis(); ax.set_xlabel("wt-%")
ax.set_title(f"Final slag composition (wt-%)  ·  B2 = {static.basicity_B2:.2f}", fontsize=11)
for i, k in enumerate(order):
    ax.text(fin[k], i, f" {fin[k]:.1f}%", va="center", fontsize=9)
ax.grid(axis="x", alpha=0.3)

fig.suptitle("Industry-X EAF \u2014 slag composition in weight percent (modern ~130 t UHP)",
             fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.93])
fig.savefig(f"{OUT}/6_slag_composition_wtpct.png", dpi=115)
print("wrote 6_slag_composition_wtpct.png")

# ----------------------------------------------------------------------- #
# 7. Reaction kinetics: Turkdogan C-FeO coupling (validates the rate laws)
# ----------------------------------------------------------------------- #
import math as _m
_CCRIT = default_parameters().get("decarb_critical_carbon")
fig, axs = plt.subplots(1, 2, figsize=(13, 5.0))
h7 = dyn.history
Cs = np.array(h7["C"]); Fs = np.array(h7["FeO"]); ts = np.array(h7["t"]) / 60.0

ax = axs[0]
Cg = np.linspace(0.02, 0.6, 200)
for Tc, col in [(1500, "#9ecae1"), (1600, "#4292c6"), (1700, "#084594")]:
    K = _m.exp(12325.0 / (Tc + 273.15) - 6.357)
    ax.plot(Cg, np.minimum(K / Cg, 45), color=col, lw=1.6,
            label=f"Turkdogan eqm {Tc}\u00b0C  (%FeO)(%C)={K:.2f}")
sc = ax.scatter(Cs[Cs > 0.015], Fs[Cs > 0.015], c=ts[Cs > 0.015], cmap="autumn_r",
                s=14, zorder=5, label="model trajectory")
plt.colorbar(sc, ax=ax, label="time (min)")
ax.axhspan(17, 23, color="#c8e6c9", alpha=0.45, zorder=0)
ax.text(0.42, 20, "foaming window", fontsize=8, color="#2e6b34")
ax.set_xlabel("bath carbon (wt-%)"); ax.set_ylabel("slag FeO (wt-%)")
ax.set_xlim(0, 0.6); ax.set_ylim(0, 45)
ax.set_title("Carbon\u2013FeO coupling vs Turkdogan equilibrium", fontsize=10)
ax.legend(fontsize=7, loc="upper right"); ax.grid(alpha=0.3)

ax = axs[1]
ax.plot(ts, Cs, color="#1f77b4", label="bath [C] (wt-%)")
ax.axhline(_CCRIT, color="k", ls=":", lw=1.2)
ax.text(ts[-1] * 0.55, _CCRIT * 1.06,
        "critical C (~0.30%): O$_2$-limited \u2192 C-mass-transfer limited", fontsize=7.5)
ax.set_xlabel("time (min)"); ax.set_ylabel("bath carbon (wt-%)", color="#1f77b4")
ax2b = ax.twinx()
ax2b.plot(ts, Fs, color="#d62728", label="slag FeO (wt-%)")
ax2b.plot(ts, np.array(h7["foam"]) * 10, color="#7b3294", ls="--", lw=1.2,
          label="foam index \u00d710")
ax2b.set_ylabel("slag FeO (wt-%) / foam", color="#d62728")
ax.set_title("Two-regime decarburisation drives FeO & foaming", fontsize=10)
ax.grid(alpha=0.3)
lines = ax.get_lines()[:1] + ax2b.get_lines()
ax.legend(lines, [l.get_label() for l in lines], fontsize=7.5, loc="upper left")

fig.suptitle("Industry-X EAF \u2014 reaction kinetics validation (mechanistic rate laws)",
             fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.93])
fig.savefig(f"{OUT}/7_kinetics_validation.png", dpi=115)
print("wrote 7_kinetics_validation.png")
