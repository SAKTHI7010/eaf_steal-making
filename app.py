import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.patches import Polygon, Rectangle, Ellipse

from parameters import default_parameters
from static_model import StaticEAFModel
from dynamic_model import DynamicEAFModel
from diagnostics import Diagnostics
import refractory as rf

plt.style.use('dark_background')

# ============================================================
# 1. Page config & CSS — matches smarteaf_web.html exactly
# ============================================================
st.set_page_config(page_title="SmartEAF™ — EAF Digital Twin & Process Optimizer", layout="wide")

st.markdown("""
<style>
/* ---- colour tokens (from smarteaf_web.html) ---- */
:root {
  --bg:#0e1620; --bg2:#16212e; --panel:#1b2836; --panel2:#22323f;
  --ink:#e7eef5; --dim:#9fb3c8; --line:#2c3d4d;
  --accent:#00b4d8; --accent2:#48cae4; --gold:#ffb703;
  --ok:#2e9e5b; --warn:#e8930c; --act:#d64545;
  --steel:#e46a3f; --slag:#6aa84f; --scrap:#8a94a6; --arc:#7fd0ff;
}
.stApp {
    background-color: #0e1620;
    color: #e7eef5;
    font-family: 'Segoe UI', Roboto, Arial, sans-serif;
}
header[data-testid="stHeader"] {
    display: none !important;
}
.block-container {
    padding-top: 0rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    max-width: 1500px;
}
/* ---- custom header banner ---- */
.eaf-header {
    background: linear-gradient(90deg,#0b1017,#16212e);
    border-bottom: 2px solid var(--accent);
    padding: 12px 18px;
    display: flex; align-items: center; gap: 14px;
    margin: 0rem -1rem 1rem -1rem;
}
.eaf-logo {
    background: #00b4d8; color: #062733; font-weight: 800;
    padding: 6px 12px; border-radius: 6px; font-size: 18px; letter-spacing: 1px;
}
.eaf-title h1 { font-size: 17px; margin: 0; font-weight: 700; color: #e7eef5; line-height: 1.2; }
.eaf-title .sub { color: #9fb3c8; font-size: 12px; }
.eaf-spacer { flex: 1; }
.eaf-co { color: #ffb703; font-weight: 700; font-size: 13px; }

/* ---- hero panel ---- */
.hero {
    background: linear-gradient(135deg,#15222f,#0d1620);
    border: 1px solid #2c3d4d; border-radius: 12px; padding: 18px; margin-bottom: 14px;
}
.hero h2 { margin: 0 0 6px; font-size: 20px; color: #e7eef5; }
.hero p { margin: 0; color: #9fb3c8; font-size: 13px; line-height: 1.6; }
.tag {
    display: inline-block; background: #00b4d8; color: #062733;
    font-size: 10px; font-weight: 800; padding: 2px 8px; border-radius: 4px;
    vertical-align: middle; margin-left: 8px;
}

/* ---- card ---- */
.card {
    background: #1b2836; border: 1px solid #2c3d4d; border-radius: 10px; padding: 14px;
    margin-bottom: 14px;
}
.card h3 {
    margin: 0 0 10px; font-size: 14px; color: #48cae4;
    border-bottom: 1px solid #2c3d4d; padding-bottom: 7px;
}

/* ---- KPI cards (from smarteaf_web.html) ---- */
.kpi-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 10px; margin-bottom: 14px;
}
.kpi {
    background: #22323f; border-radius: 8px; padding: 12px; text-align: center;
    border: 1px solid #2c3d4d;
}
.kpi .v { font-size: 22px; font-weight: 800; color: #48cae4; }
.kpi .l { font-size: 11px; color: #9fb3c8; margin-top: 3px; }
.kpi.ok .v { color: #5fd68a; }
.kpi.warn .v { color: #ffc04d; }
.kpi.act .v { color: #ff7a7a; }

/* ---- readout grid (schematic tab) ---- */
.readout {
    display: grid; grid-template-columns: 1fr 1fr; gap: 6px;
}
.readout div {
    background: #22323f; border-radius: 6px; padding: 8px 10px; border: 1px solid #2c3d4d;
}
.readout .rl { font-size: 10.5px; color: #9fb3c8; }
.readout .rv { font-size: 16px; font-weight: 700; color: #48cae4; }

/* ---- tables (from smarteaf_web.html) ---- */
.eaf-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.eaf-table th, .eaf-table td {
    text-align: left; padding: 6px 8px; border-bottom: 1px solid #2c3d4d;
}
.eaf-table th { color: #9fb3c8; font-weight: 600; background: #16212e; }
.eaf-table tr:hover td { background: #22323f; }
.eaf-table .accent { color: #48cae4; font-weight: 600; }

/* ---- refractory bar ---- */
.ref-bar {
    display: flex; height: 34px; border-radius: 6px; overflow: hidden;
    border: 1px solid #2c3d4d; margin-bottom: 8px;
}
.ref-bar div {
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; color: #111; font-weight: 600;
}
.note { font-size: 12px; color: #9fb3c8; line-height: 1.6; }

/* ---- status badge ---- */
.badge {
    padding: 2px 9px; border-radius: 20px; font-size: 11px; font-weight: 700;
}
.b-ok { background: rgba(46,158,91,.2); color: #5fd68a; }
.b-warn { background: rgba(232,147,12,.2); color: #ffc04d; }
.b-act { background: rgba(214,69,69,.2); color: #ff7a7a; }
.b-charge { background: rgba(0,180,216,.18); color: #48cae4; }
.b-phase { background: rgba(255,183,3,.18); color: #ffb703; }

/* ---- toolbar ---- */
.toolbar {
    background: #1b2836; border: 1px solid #2c3d4d; border-radius: 10px;
    padding: 12px 14px; margin-bottom: 12px;
    display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
}

/* ---- footer (from smarteaf_web.html) ---- */
.eaf-footer {
    color: #9fb3c8; font-size: 11px; text-align: center; padding: 20px;
    border-top: 1px solid #2c3d4d; margin-top: 20px;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# 2. Header banner
# ============================================================
st.markdown("""
<div class="eaf-header">
  <div class="eaf-logo">SmartEAF™</div>
  <div class="eaf-title"><h1>Electric Arc Furnace — Digital Twin &amp; Process Optimizer</h1>
    <div class="sub">Static &amp; dynamic first-principles model · operator decision support · Reference: Industry-X</div></div>
  <div class="eaf-spacer"></div>
  <div class="eaf-co">Extractmet Private Limited</div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 3. Session state setup
# ============================================================
if 'reg' not in st.session_state:
    st.session_state.reg = default_parameters()
if 'last_static' not in st.session_state:
    st.session_state.last_static = None
if 'last_dynamic' not in st.session_state:
    st.session_state.last_dynamic = None

# ============================================================
# 4. Helper functions
# ============================================================
def apply_changes(updated_vals):
    warnings = []
    for k, v in updated_vals.items():
        warnings += st.session_state.reg.set(k, v)
    if warnings:
        st.warning("Warnings: " + " | ".join(warnings))
    else:
        st.success("Parameters applied successfully.")

def run_static(param_inputs):
    apply_changes(param_inputs)
    try:
        res = StaticEAFModel(st.session_state.reg).solve()
        st.session_state.last_static = res
        st.success(f"Static done: {res.steel_mass/1000:.1f} t tapped, {res.electrical_energy_specific:.0f} kWh/t, B2 {res.basicity_B2:.2f}.")
    except Exception as e:
        st.error(f"Static model error: {e}")

def run_dynamic(param_inputs, mode="endpoint"):
    apply_changes(param_inputs)
    try:
        res = DynamicEAFModel(st.session_state.reg).simulate(mode=mode)
        st.session_state.last_dynamic = res
        st_final = res.final
        st.success(f"Dynamic done: tap {st_final.T_lSc-273.15:.0f} °C / C {st_final.pct['C']:.3f}%, {res.tap_to_tap_min:.1f} min, {st_final.E_elec_MJ/3.6/(st_final.m_lSc/1000):.0f} kWh/t.")
    except Exception as e:
        st.error(f"Dynamic model error: {e}")

def kpi_html(value, label, status=""):
    """Generate HTML for a single KPI card matching smarteaf_web.html."""
    cls = f"kpi {status}" if status else "kpi"
    return f'<div class="{cls}"><div class="v">{value}</div><div class="l">{label}</div></div>'

def band(val, lo, hi):
    """Return KPI status class based on value range."""
    if val < lo:
        return "warn"
    elif val > hi:
        return "act"
    return "ok"

def build_refractory_bar():
    """Build refractory bar HTML matching smarteaf_web.html."""
    reg = st.session_state.reg
    layers = [
        rf.Layer("Working lining", reg.get("working_lining_thickness"), reg.get("working_lining_k")),
        rf.Layer("Safety lining", reg.get("safety_lining_thickness"), reg.get("safety_lining_k")),
        rf.Layer("Insulation", reg.get("insulation_thickness"), reg.get("insulation_k")),
        rf.Layer("Steel shell", reg.get("shell_thickness"), reg.get("shell_k")),
    ]
    wall = rf.wall_heat_loss(
        reg.get("target_tap_temperature"), reg.get("ambient_temperature"),
        layers, reg.get("refractory_area"),
        reg.get("convection_coefficient"), reg.get("shell_emissivity")
    )
    tot = sum(L.thickness_mm for L in layers)
    cols = ['#e8a15a', '#d0894a', '#7fc7e8', '#9fb3c8']
    bar_html = '<div class="ref-bar">'
    for i, L in enumerate(layers):
        pct = L.thickness_mm / tot * 100
        bar_html += f'<div title="{L.name}: {L.thickness_mm:.0f}mm, k={L.k}" style="width:{pct:.1f}%;background:{cols[i]}">{L.thickness_mm:.0f}</div>'
    bar_html += '</div>'
    note_html = (
        f'<div class="note">Hot face <b>{wall.interface_temps_C[0]:.0f}°C</b> → shell <b>{wall.shell_temp_C:.0f}°C</b> · '
        f'wall loss <b>{wall.q_watts/1000:.0f} kW</b> '
        f'(conv {wall.conv_fraction*100:.0f}% / rad {wall.rad_fraction*100:.0f}%). '
        f'Total lining {tot:.0f} mm over {reg.get("refractory_area")} m².</div>'
    )
    return bar_html + note_html

def draw_schematic(res):
    st_final = res.final if res else None
    fig = Figure(figsize=(9.2, 6.3))
    ax = fig.add_subplot(111)
    ax.set_xlim(0, 10); ax.set_ylim(0, 8); ax.axis("off"); ax.set_aspect("equal")
    fig.patch.set_facecolor("#0e1620"); ax.set_facecolor("#0e1620")

    # shell, refractory, roof
    ax.add_patch(Polygon([(1.4, 6.4), (1.4, 3.0), (2.0, 1.2), (8.0, 1.2),
                          (8.6, 3.0), (8.6, 6.4)], closed=False, fill=False,
                         ec="#3a4a5a", lw=6))
    ax.add_patch(Polygon([(1.75, 6.2), (1.75, 3.1), (2.25, 1.5), (7.75, 1.5),
                          (8.25, 3.1), (8.25, 6.2)], closed=False, fill=False,
                         ec="#7a5a3a", lw=9, alpha=0.85))
    ax.plot([1.4, 5, 8.6], [6.4, 7.05, 6.4], color="#4a5a6a", lw=6)

    if st_final:
        # bath + slag (slag thickness ~ foam index)
        ax.add_patch(Polygon([(2.15, 3.0), (2.3, 1.75), (7.7, 1.75), (7.85, 3.0)],
                             closed=True, fc="#c94f2a", ec="none"))
        th = 0.15 + st_final.foam_index * 0.5
        ax.add_patch(Rectangle((2.2, 3.0), 5.6, th, fc="#6aa84f", ec="none", alpha=0.9))
    else:
        # default bath
        ax.add_patch(Polygon([(2.15, 3.0), (2.3, 1.75), (7.7, 1.75), (7.85, 3.0)],
                             closed=True, fc="#c94f2a", ec="none"))
        ax.add_patch(Rectangle((2.2, 3.0), 5.6, 0.15, fc="#6aa84f", ec="none", alpha=0.9))

    # electrodes + arcs
    for x in (4.1, 5.0, 5.9):
        ax.add_patch(Rectangle((x - 0.14, 3.35), 0.28, 3.9, fc="#2b2b2b", ec="#111"))
        ax.add_patch(Ellipse((x, 3.25), 0.5, 0.28, fc="#7fd0ff", alpha=0.6))

    # water panels, lance, carbon, tap
    ax.plot([1.55, 1.55], [4.0, 6.2], color="#3aa0d8", lw=4)
    ax.plot([8.45, 8.45], [4.0, 6.2], color="#3aa0d8", lw=4)
    ax.annotate("", xy=(2.45, 3.1), xytext=(0.9, 4.6),
                arrowprops=dict(arrowstyle="-", color="#7fd0ff", lw=3))
    ax.annotate("", xy=(7.55, 3.1), xytext=(9.1, 4.6),
                arrowprops=dict(arrowstyle="-", color="#c98a3a", lw=3))
    ax.text(0.75, 4.75, "O\u2082", color="#7fd0ff", fontsize=9)
    ax.text(9.0, 4.75, "C", color="#c98a3a", fontsize=9)
    ax.add_patch(Polygon([(5, 1.2), (4.7, 0.65), (5.3, 0.65)], closed=True, fc="#c94f2a"))
    ax.text(5, 0.35, "EBT tap", color="#8ba0b4", fontsize=8, ha="center")

    if st_final:
        # live readout panel
        info = "\n".join([
            f"Tap T : {st_final.T_lSc-273.15:6.0f} °C",
            f"Carbon: {st_final.pct['C']:6.3f} %",
            f"B2    : {st_final.basicity:6.2f}",
            f"FeO   : {st_final.feo_pct:6.0f} %",
            f"Foam  : {st_final.foam_index:6.2f}",
            f"Shell : {st_final.shell_temp_C:6.0f} °C",
            f"Steel : {st_final.m_lSc/1000:6.1f} t",
            f"Slag  : {st_final.slag_mass/1000:6.2f} t"])
        ax.text(0.12, 7.8, info, color="#48cae4", fontsize=9, family="monospace",
                va="top", ha="left",
                bbox=dict(boxstyle="round", fc="#16212e", ec="#2c3d4d"))
        ax.text(5, 7.5, "Industry-X EAF  —  "
                + ("endpoint reached" if res.reached_endpoint else "end of run"),
                color="#ffb703", fontsize=12, ha="center", fontweight="bold")
    ax.text(6.8, 6.7, "3x graphite\nelectrodes", color="#9fb3c8", fontsize=8)
    fig.tight_layout()
    return fig


# For inputs, we define parameter groupings
categories = {
    "Charge": ["scrap_charge_mass", "scrap_C", "scrap_Si", "scrap_Mn", "scrap_P", "scrap_S", "scrap_Cu", "dirt_silica", "dri_mass", "dri_metallization", "dri_carbon", "dri_gangue", "hot_metal_mass", "hot_metal_carbon", "hot_metal_temperature", "scrap_rust_feo"],
    "Fluxes & additions": ["lime_charged", "dolomite_charged", "charge_carbon", "injected_carbon"],
    "Oxygen & burners": ["oxygen_total", "oxygen_flow_rate", "natural_gas"],
    "Electrical & timing": ["transformer_power", "power_on_time", "power_off_time"],
    "Targets": ["target_tap_temperature", "target_carbon", "target_basicity"],
    "Furnace & refractory": ["furnace_capacity", "refractory_area", "working_lining_thickness", "working_lining_k", "safety_lining_thickness", "safety_lining_k", "insulation_thickness", "insulation_k", "shell_thickness", "shell_k", "shell_emissivity", "convection_coefficient", "panel_heat_loss", "offgas_temperature", "ambient_temperature"],
    "Efficiencies & kinetics": ["electrical_efficiency", "arc_transfer_efficiency", "arc_transfer_bare", "post_combustion_ratio", "post_combustion_efficiency", "electrode_consumption_rate", "iron_oxidation_fraction", "dust_rate", "mn_slag_partition", "decarb_critical_carbon", "decarb_mass_transfer_coeff", "scrap_melt_htc", "lime_dissolution_rate", "si_removal_rate", "mn_removal_rate", "p_removal_rate", "feo_reduction_rate", "feo_equilibrium_factor", "slag_feo_max", "decarb_o2_efficiency_max", "foaming_co_reference", "sim_timestep"]
}

# Collect param_inputs globally
param_inputs = {}

# ============================================================
# 5. Tabs (matching smarteaf_web.html — no EDA/Sensitivity)
# ============================================================
tabs = st.tabs([
    "⚙ Reactor Schematic",
    "✎ Inputs / Parameters",
    "▤ Static Model",
    "▶ Dynamic Model",
    "☰ Event Log",
    "? Help & Model"
])

# ============================================================
# TAB 1: Reactor Schematic
# ============================================================
with tabs[0]:
    st.markdown("""
    <div class="hero">
        <h2>Industry-X Electric Arc Furnace <span class="tag">LIVE DIGITAL TWIN</span></h2>
        <p>Interactive cross-section of the EAF reactor. Values update from the latest simulation.
           Run the <b>Dynamic Model</b> to animate the heat and populate live readouts, or the <b>Static Model</b> for a per-heat balance.</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1.35, 1])
    with col1:
        st.markdown('<div class="card"><h3>Furnace cross-section &amp; instrumentation</h3></div>', unsafe_allow_html=True)
        fig = draw_schematic(st.session_state.last_dynamic)
        st.pyplot(fig)
    with col2:
        # Live process readout (styled readout grid from HTML)
        st.markdown('<div class="card"><h3>Live process readout</h3>', unsafe_allow_html=True)
        if st.session_state.last_dynamic:
            sf = st.session_state.last_dynamic.final
            readout_html = '<div class="readout">'
            readout_items = [
                ("Tap temperature", f"{sf.T_lSc-273.15:.0f} °C"),
                ("Bath carbon", f"{sf.pct['C']:.3f} %"),
                ("Basicity B2", f"{sf.basicity:.2f}"),
                ("Slag FeO", f"{sf.feo_pct:.1f} %"),
                ("Foam index", f"{sf.foam_index:.2f}"),
                ("Shell temp", f"{sf.shell_temp_C:.0f} °C"),
                ("Liquid steel", f"{sf.m_lSc/1000:.1f} t"),
                ("Slag mass", f"{sf.slag_mass/1000:.2f} t"),
            ]
            for label, value in readout_items:
                readout_html += f'<div><div class="rl">{label}</div><div class="rv">{value}</div></div>'
            readout_html += '</div>'
            st.markdown(readout_html, unsafe_allow_html=True)
        else:
            st.info("Run Dynamic model to see readout.")
        st.markdown('</div>', unsafe_allow_html=True)

        # Refractory bar
        st.markdown('<div class="card"><h3>Furnace &amp; refractory build-up</h3>', unsafe_allow_html=True)
        st.markdown(build_refractory_bar(), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# TAB 2: Inputs / Parameters
# ============================================================
with tabs[1]:
    # Action Toolbar
    st.markdown("### Actions & Presets")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    if col1.button("▤ Run Static"): run_static(param_inputs)
    if col2.button("▶ Run Dynamic"): run_dynamic(param_inputs)
    if col3.button("↺ Reset defaults"): st.session_state.reg.reset_all(); st.rerun()
    if col4.button("Preset: Low-C"):
        st.session_state.reg.set("target_carbon", 0.04)
        st.session_state.reg.set("oxygen_total", 5000)
        st.rerun()
    if col5.button("Preset: High-DRI"):
        st.session_state.reg.set("dri_mass", 60.0)
        st.session_state.reg.set("scrap_charge_mass", 60.0)
        st.rerun()
    if col6.button("Preset: Hot-metal"):
        st.session_state.reg.set("hot_metal_mass", 40.0)
        st.session_state.reg.set("scrap_charge_mass", 100.0)
        st.rerun()

    st.markdown("---")

    # Input parameters
    for cat, keys in categories.items():
        with st.expander(f"▸ {cat}", expanded=True):
            cols = st.columns(3)
            for i, name in enumerate(keys):
                if name in st.session_state.reg._params:
                    p = st.session_state.reg[name]
                    c = cols[i % 3]
                    help_txt = p.help
                    if isinstance(p.value, bool):
                        val = c.checkbox(f"{name} ({p.unit})", value=p.value, help=help_txt, key=name)
                    elif isinstance(p.value, int) and not isinstance(p.value, bool):
                        val = c.number_input(f"{name} ({p.unit})", value=int(p.value), help=help_txt, key=name)
                    elif isinstance(p.value, float):
                        val = c.number_input(f"{name} ({p.unit})", value=float(p.value), help=help_txt, key=name)
                    elif isinstance(p.value, dict):
                        val_str = c.text_input(f"{name} ({p.unit})", value=" ".join(f"{k}={v:g}" for k, v in p.value.items()), help=help_txt, key=name)
                        try:
                            val = dict(p.value)
                            for pair in val_str.replace(",", " ").split():
                                if "=" in pair or ":" in pair:
                                    sep = "=" if "=" in pair else ":"
                                    k, v = pair.split(sep)
                                    val[k.strip()] = float(v)
                        except:
                            val = p.value
                    else:
                        val = c.text_input(f"{name} ({p.unit})", value=str(p.value), help=help_txt, key=name)
                    param_inputs[name] = val

# ============================================================
# TAB 3: Static Model
# ============================================================
with tabs[2]:
    if st.button("▤ Run Static Mass & Energy Balance"):
        run_static(param_inputs)

    if st.session_state.last_static:
        res = st.session_state.last_static

        # ---- KPI Cards (matching HTML staticKPIs) ----
        o2_per_t = res.oxygen_required / (res.steel_mass / 1000) if res.steel_mass > 0 else 0
        kpi_cards = [
            kpi_html(f"{res.steel_mass/1000:.1f} t", "Liquid steel tapped", "ok"),
            kpi_html(f"{res.metallic_yield*100:.1f}%", "Metallic yield", band(res.metallic_yield*100, 88, 96)),
            kpi_html(f"{res.electrical_energy_specific:.0f}", "Electrical kWh/t", band(res.electrical_energy_specific, 300, 470)),
            kpi_html(f"{res.total_energy_specific:.0f}", "Total kWh/t", band(res.total_energy_specific, 550, 680)),
            kpi_html(f"{res.basicity_B2:.2f}", "Slag basicity B2", band(res.basicity_B2, 1.8, 2.6)),
            kpi_html(f"{res.slag_mass/1000:.1f} t", "Slag mass", "ok"),
            kpi_html(f"{o2_per_t:.0f}", "O₂ Nm³/t", band(o2_per_t, 25, 45)),
            kpi_html(f"{res.chemical_energy_kWh:.0f}", "Chemical kWh", "ok"),
        ]
        st.markdown(f'<div class="kpi-grid">{"".join(kpi_cards)}</div>', unsafe_allow_html=True)

        # ---- 3-column chart grid (energy sinks, sources, slag) ----
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown('<div class="card"><h3>Energy demand (sinks)</h3></div>', unsafe_allow_html=True)
            if res.energy_sinks:
                fig, ax = plt.subplots(figsize=(4, 3)); fig.patch.set_facecolor("#1b2836"); ax.set_facecolor("#1b2836")
                sizes = list(res.energy_sinks.values())
                labels = [k.replace("_"," ") if v > 0.05*sum(sizes) else "" for k, v in res.energy_sinks.items()]
                ax.pie(sizes, labels=labels, autopct=lambda p: f'{p:.1f}%' if p > 5 else '', textprops={'color':"w", 'fontsize':8})
                st.pyplot(fig)
        with col2:
            st.markdown('<div class="card"><h3>Non-electrical energy (sources)</h3></div>', unsafe_allow_html=True)
            if res.energy_sources:
                fig, ax = plt.subplots(figsize=(4, 3)); fig.patch.set_facecolor("#1b2836"); ax.set_facecolor("#1b2836")
                filtered = {k: v for k, v in res.energy_sources.items() if v > 1}
                sizes = list(filtered.values())
                labels = [k.replace("_"," ") if v > 0.05*sum(sizes) else "" for k, v in filtered.items()]
                ax.pie(sizes, labels=labels, autopct=lambda p: f'{p:.1f}%' if p > 5 else '', textprops={'color':"w", 'fontsize':8})
                st.pyplot(fig)
        with col3:
            st.markdown('<div class="card"><h3>Final slag composition</h3></div>', unsafe_allow_html=True)
            if res.slag:
                fig, ax = plt.subplots(figsize=(4, 3)); fig.patch.set_facecolor("#1b2836"); ax.set_facecolor("#1b2836")
                sizes = list(res.slag.values())
                labels = [k if v > 0.05*sum(sizes) else "" for k, v in res.slag.items()]
                ax.pie(sizes, labels=labels, autopct=lambda p: f'{p:.1f}%' if p > 5 else '', textprops={'color':"w", 'fontsize':8})
                st.pyplot(fig)

        # ---- 2-column grid (mass balance + tables) ----
        col4, col5 = st.columns(2)
        with col4:
            st.markdown('<div class="card"><h3>Inputs vs. outputs (mass)</h3></div>', unsafe_allow_html=True)
            mass_in = st.session_state.reg.get("scrap_charge_mass")*1000 + st.session_state.reg.get("dri_mass")*1000 + st.session_state.reg.get("hot_metal_mass")*1000 + st.session_state.reg.get("lime_charged") + st.session_state.reg.get("dolomite_charged")
            mass_out = res.steel_mass + res.slag_mass + res.offgas_mass + res.dust_mass
            fig, ax = plt.subplots(figsize=(5, 3.5)); fig.patch.set_facecolor("#1b2836"); ax.set_facecolor("#1b2836")
            ax.bar(["Inputs", "Outputs (Calculated)"], [mass_in, mass_out], color=["#00b4d8", "#ffb703"])
            ax.set_ylabel("Mass (kg)")
            ax.tick_params(colors='w')
            st.pyplot(fig)
        with col5:
            st.markdown('<div class="card"><h3>Tapped-steel composition &amp; balance</h3></div>', unsafe_allow_html=True)
            # Styled HTML table matching smarteaf_web.html
            table_html = '<table class="eaf-table"><thead><tr><th>Element</th><th>wt-%</th></tr></thead><tbody>'
            for el, val in res.tap_composition.items():
                table_html += f'<tr><td>{el}</td><td class="accent">{val:.3f}</td></tr>'
            table_html += '</tbody></table>'
            table_html += (
                f'<p class="note" style="margin-top:8px">Lime to hit aim B2: <b>{res.lime_required_for_target:.0f} kg</b> · '
                f'off-gas {res.offgas_mass/1000:.2f} t · est. tap-to-tap {res.tap_to_tap_min:.0f} min · '
                f'electrode {res.electrode_consumption_kg:.0f} kg</p>'
            )
            st.markdown(table_html, unsafe_allow_html=True)
    else:
        st.info("Run Static model to see results.")

# ============================================================
# TAB 4: Dynamic Model
# ============================================================
with tabs[3]:
    # ---- Toolbar with mode selector (matching HTML dynamic tab) ----
    tcol1, tcol2, tcol3 = st.columns([1, 1.5, 2])
    with tcol1:
        run_btn = st.button("▶ Run Time-Resolved Simulation")
    with tcol2:
        dyn_mode = st.selectbox(
            "Mode:",
            ["Run to endpoint (aim T & C)", "Fixed power-on time"],
            key="dyn_mode_select",
            label_visibility="collapsed"
        )
    with tcol3:
        if st.session_state.last_dynamic:
            r = st.session_state.last_dynamic
            status_txt = f"done · {len(r.events)} events · {'endpoint reached' if r.reached_endpoint else 'endpoint NOT reached'}"
            st.markdown(f'<span class="note">{status_txt}</span>', unsafe_allow_html=True)

    mode = "endpoint" if "endpoint" in dyn_mode else "fixed"
    if run_btn:
        run_dynamic(param_inputs, mode=mode)

    if st.session_state.last_dynamic:
        res = st.session_state.last_dynamic
        st_final = res.final
        h = res.history
        t_min = [x / 60 for x in h["t"]]  # convert to minutes

        spec_elec = st_final.E_elec_MJ / 3.6 / (st_final.m_lSc / 1000) if st_final.m_lSc > 0 else 0

        # ---- KPI Cards (matching HTML dynKPIs) ----
        target_T = st.session_state.reg.get("target_tap_temperature")
        target_C = st.session_state.reg.get("target_carbon")
        kpi_cards = [
            kpi_html(f"{st_final.T_lSc-273.15:.0f}", "Tap temp °C", band(st_final.T_lSc-273.15, target_T-15, target_T+25)),
            kpi_html(f"{st_final.pct['C']:.3f}", "Tap carbon %", band(st_final.pct['C'], 0.01, target_C+0.03)),
            kpi_html(f"{res.tap_to_tap_min:.1f}", "Tap-to-tap min", band(res.tap_to_tap_min, 40, 60)),
            kpi_html(f"{spec_elec:.0f}", "Electrical kWh/t", band(spec_elec, 300, 470)),
            kpi_html(f"{st_final.basicity:.2f}", "Slag B2", band(st_final.basicity, 1.8, 2.6)),
            kpi_html(f"{st_final.feo_pct:.0f}%", "Slag FeO", band(st_final.feo_pct, 15, 32)),
            kpi_html(f"{st_final.foam_index:.2f}", "Foam index", band(st_final.foam_index, 0.5, 1.2)),
            kpi_html("✔" if res.reached_endpoint else "✘", "Endpoint", "ok" if res.reached_endpoint else "act"),
        ]
        st.markdown(f'<div class="kpi-grid">{"".join(kpi_cards)}</div>', unsafe_allow_html=True)

        # ---- helper to make dual-axis line charts ----
        def make_chart(title, left_series, right_series=None, hline=None, figsize=(6, 3)):
            """Create a styled chart matching smarteaf_web.html panels."""
            fig, ax = plt.subplots(figsize=figsize)
            fig.patch.set_facecolor("#16212e"); ax.set_facecolor("#16212e")
            for s in left_series:
                ax.plot(t_min, s["data"], label=s["label"], color=s["color"],
                        ls=s.get("ls", "-"), lw=s.get("lw", 1.5))
            ax.set_xlabel("time (min)", fontsize=9, color="#9fb3c8")
            ax.set_ylabel(left_series[0].get("ylabel", ""), fontsize=9, color="#9fb3c8")
            ax.tick_params(colors="#9fb3c8", labelsize=8)
            ax.grid(alpha=0.2, color="#2c3d4d")
            if hline is not None:
                ax.axhline(hline, color="#5a6b7a", ls="--", lw=1)
            if right_series:
                ar = ax.twinx()
                for s in right_series:
                    ar.plot(t_min, s["data"], label=s["label"], color=s["color"],
                            ls=s.get("ls", "-."), lw=s.get("lw", 1.5))
                ar.set_ylabel(right_series[0].get("ylabel", ""), fontsize=9, color=right_series[0]["color"])
                ar.tick_params(colors=right_series[0]["color"], labelsize=8)
                # Combined legend
                lines1, labels1 = ax.get_legend_handles_labels()
                lines2, labels2 = ar.get_legend_handles_labels()
                ax.legend(lines1 + lines2, labels1 + labels2, fontsize=7, loc="best")
            else:
                ax.legend(fontsize=7, loc="best")
            ax.set_title(title, fontsize=10, color="#e7eef5", pad=8)
            fig.tight_layout()
            return fig

        # wt-% helper for slag
        def wpct(key):
            return [100.0 * a / b if b > 1e-6 else 0.0 for a, b in zip(h[key], h["m_slag"])]

        # ---- 14 individual charts in 2-col grid (matching HTML) ----
        c1, c2 = st.columns(2)

        # 1. Melting & slag build-up
        with c1:
            st.markdown('<div class="card"><h3>Melting &amp; slag build-up</h3></div>', unsafe_allow_html=True)
            fig = make_chart("",
                [{"data": h["m_sSc"], "label": "solid scrap (t)", "color": "#8c564b"},
                 {"data": h["m_lSc"], "label": "liquid steel (t)", "color": "#1f77b4"}],
                [{"data": [m/1000 for m in h["m_slag"]], "label": "slag (t)", "color": "#2ca02c", "ylabel": "slag (t)"}])
            st.pyplot(fig)

        # 2. Temperatures
        with c2:
            st.markdown('<div class="card"><h3>Temperatures (bath, solid, shell)</h3></div>', unsafe_allow_html=True)
            fig = make_chart("",
                [{"data": h["T_lSc"], "label": "bath °C", "color": "#d64545"},
                 {"data": h["T_sSc"], "label": "solid °C", "color": "#e8930c", "ls": "--"}],
                [{"data": h["T_shell"], "label": "shell °C", "color": "#8ba0b4", "ylabel": "shell (°C)"}],
                hline=target_T)
            st.pyplot(fig)

        c1, c2 = st.columns(2)

        # 3. Bath chemistry
        with c1:
            st.markdown('<div class="card"><h3>Bath chemistry (C, Si, Mn, P)</h3></div>', unsafe_allow_html=True)
            fig = make_chart("",
                [{"data": h["C"], "label": "C", "color": "#1f77b4"},
                 {"data": h["Si"], "label": "Si", "color": "#ff7f0e"},
                 {"data": h["Mn"], "label": "Mn", "color": "#2ca02c"},
                 {"data": h["P"], "label": "P ×10", "color": "#d62728"}])
            st.pyplot(fig)

        # 4. Slag evolution & basicity
        with c2:
            st.markdown('<div class="card"><h3>Slag evolution &amp; basicity</h3></div>', unsafe_allow_html=True)
            fig = make_chart("",
                [{"data": h["slag_CaO"], "label": "CaO", "color": "#1f77b4"},
                 {"data": h["slag_SiO2"], "label": "SiO₂", "color": "#ff7f0e"},
                 {"data": h["slag_FeO"], "label": "FeO", "color": "#d62728"},
                 {"data": h["slag_MgO"], "label": "MgO", "color": "#2ca02c"}],
                [{"data": h["basicity"], "label": "B2", "color": "#e7eef5", "ls": ":", "ylabel": "basicity B2"}])
            st.pyplot(fig)

        c1, c2 = st.columns(2)

        # 5. Slag composition (wt-%)
        with c1:
            st.markdown('<div class="card"><h3>Slag composition (wt-%)</h3></div>', unsafe_allow_html=True)
            fig, ax = plt.subplots(figsize=(6, 3))
            fig.patch.set_facecolor("#16212e"); ax.set_facecolor("#16212e")
            for key, lab, col in [("slag_CaO","CaO","#1f77b4"), ("slag_SiO2","SiO₂","#ff7f0e"),
                                  ("slag_FeO","FeO","#d62728"), ("slag_MgO","MgO","#2ca02c"),
                                  ("slag_MnO","MnO","#9467bd")]:
                ax.plot(t_min, wpct(key), label=lab, color=col, lw=1.5)
            ax.set_xlabel("time (min)", fontsize=9, color="#9fb3c8")
            ax.set_ylabel("wt-%", fontsize=9, color="#9fb3c8")
            ax.tick_params(colors="#9fb3c8", labelsize=8)
            ax.legend(fontsize=7); ax.grid(alpha=0.2, color="#2c3d4d")
            fig.tight_layout()
            st.pyplot(fig)

        # 6. Cumulative energy & foaming
        with c2:
            st.markdown('<div class="card"><h3>Cumulative energy &amp; foaming</h3></div>', unsafe_allow_html=True)
            fig = make_chart("",
                [{"data": h["E_elec"], "label": "electrical kWh", "color": "#1f77b4"},
                 {"data": h["E_chem"], "label": "chemical kWh", "color": "#2ca02c"}],
                [{"data": h["foam"], "label": "foam idx", "color": "#9467bd", "ls": ":", "ylabel": "foam index"}])
            st.pyplot(fig)

        c1, c2 = st.columns(2)

        # 7. Power input & heat-loss breakdown
        with c1:
            st.markdown('<div class="card"><h3>Power input &amp; heat-loss breakdown</h3></div>', unsafe_allow_html=True)
            fig = make_chart("",
                [{"data": h["P_arc_bath"], "label": "arc→bath MW", "color": "#1f77b4"},
                 {"data": h["P_chem"], "label": "chemical", "color": "#2ca02c"},
                 {"data": h["P_panel"], "label": "panel loss", "color": "#ff7f0e"},
                 {"data": h["P_offgas"], "label": "off-gas loss", "color": "#d62728"},
                 {"data": h["P_wall"], "label": "wall loss", "color": "#8c564b"}])
            st.pyplot(fig)

        # 8. Decarburisation vs oxygen use
        with c2:
            st.markdown('<div class="card"><h3>Decarburisation vs. oxygen use</h3></div>', unsafe_allow_html=True)
            fig = make_chart("",
                [{"data": h["C"], "label": "bath C %", "color": "#1f77b4"}],
                [{"data": h["O2_cum"], "label": "cum. O₂ Nm³", "color": "#d62728", "ylabel": "O₂ (Nm³)"}])
            st.pyplot(fig)

        c1, c2 = st.columns(2)

        # 9. Lime dissolution & dephosphorisation
        with c1:
            st.markdown('<div class="card"><h3>Lime dissolution &amp; dephosphorisation</h3></div>', unsafe_allow_html=True)
            fig = make_chart("",
                [{"data": h["lime_undissolved"], "label": "undissolved lime kg", "color": "#e8930c"},
                 {"data": h["P"], "label": "bath P ×10", "color": "#2ca02c"}],
                [{"data": h["basicity"], "label": "B2", "color": "#1f77b4", "ylabel": "basicity B2"}])
            st.pyplot(fig)

        # 10. Solid → liquid conversion (phase %)
        with c2:
            st.markdown('<div class="card"><h3>Solid → liquid conversion (phase %)</h3></div>', unsafe_allow_html=True)
            tot = [max(s + l, 1e-9) for s, l in zip(h["m_sSc"], h["m_lSc"])]
            fsol = [100 * s / tt for s, tt in zip(h["m_sSc"], tot)]
            fliq = [100 - f for f in fsol]
            fig, ax = plt.subplots(figsize=(6, 3))
            fig.patch.set_facecolor("#16212e"); ax.set_facecolor("#16212e")
            ax.stackplot(t_min, fsol, fliq, labels=["solid scrap %", "liquid steel %"],
                         colors=["#8c564b", "#1f77b4"], alpha=0.85)
            ax.set_ylim(0, 100); ax.set_xlabel("time (min)", fontsize=9, color="#9fb3c8")
            ax.set_ylabel("phase %", fontsize=9, color="#9fb3c8")
            ax.tick_params(colors="#9fb3c8", labelsize=8)
            ax.legend(fontsize=7, loc="center right"); ax.grid(alpha=0.2, color="#2c3d4d")
            fig.tight_layout()
            st.pyplot(fig)

        c1, c2 = st.columns(2)

        # 11. Specific energy & cumulative total
        with c1:
            st.markdown('<div class="card"><h3>Specific energy &amp; cumulative total</h3></div>', unsafe_allow_html=True)
            e_total = [e + c for e, c in zip(h["E_elec"], h["E_chem"])]
            fig = make_chart("",
                [{"data": e_total, "label": "total kWh", "color": "#e7eef5", "lw": 1}],
                [{"data": h["spec_energy"], "label": "specific kWh/t", "color": "#e8930c", "ylabel": "kWh/t"}])
            st.pyplot(fig)

        # 12. Off-gas (CO/CO₂) & oxygen use
        with c2:
            st.markdown('<div class="card"><h3>Off-gas (CO / CO₂) &amp; oxygen use</h3></div>', unsafe_allow_html=True)
            fig = make_chart("",
                [{"data": h["CO_out"], "label": "CO out kg", "color": "#636363"},
                 {"data": h["CO2_out"], "label": "CO₂ kg", "color": "#3182bd"}],
                [{"data": [o/max(m,0.001) if m > 20 else 0 for o, m in zip(h["O2_cum"], h["m_lSc"])] if "O2_cum" in h else h.get("O2_cum", [0]*len(t_min)),
                  "label": "O₂ Nm³/t", "color": "#31a354", "ls": ":", "ylabel": "O₂ Nm³/t"}])
            st.pyplot(fig)

        c1, c2 = st.columns(2)

        # 13. Basicity B2/B3 & lime
        with c1:
            st.markdown('<div class="card"><h3>Basicity B2 / B3 &amp; lime</h3></div>', unsafe_allow_html=True)
            fig = make_chart("",
                [{"data": h["basicity"], "label": "B2 = CaO/SiO₂", "color": "#1f77b4"},
                 {"data": h["B3"], "label": "B3 = CaO/(SiO₂+Al₂O₃)", "color": "#9467bd", "ls": "--"}],
                [{"data": h["lime_undissolved"], "label": "undissolved lime kg", "color": "#e8930c", "ylabel": "lime (kg)"}])
            st.pyplot(fig)

        # 14. Foaming index & slag FeO
        with c2:
            st.markdown('<div class="card"><h3>Foaming index &amp; slag FeO</h3></div>', unsafe_allow_html=True)
            fig = make_chart("",
                [{"data": h["FeO"], "label": "slag FeO %", "color": "#d62728"}],
                [{"data": h["foam"], "label": "foam index", "color": "#7b3294", "ls": "--", "ylabel": "foam index"}])
            st.pyplot(fig)

        # ---- Results tables (matching HTML: final steel, final slag, off-gas & balance) ----
        st.markdown("---")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown('<div class="card"><h3>Final tapped steel</h3>', unsafe_allow_html=True)
            steel_rows = [
                ("Mass", f"{st_final.m_lSc/1000:.1f} t"),
                ("Temperature", f"{st_final.T_lSc-273.15:.0f} °C"),
                ("C", f"{st_final.pct['C']:.3f} %"),
                ("Si", f"{st_final.pct['Si']:.3f} %"),
                ("Mn", f"{st_final.pct['Mn']:.3f} %"),
                ("P", f"{st_final.pct['P']:.4f} %"),
            ]
            table_html = '<table class="eaf-table"><tbody>'
            for k, v in steel_rows:
                table_html += f'<tr><td>{k}</td><td class="accent">{v}</td></tr>'
            table_html += '</tbody></table>'
            st.markdown(table_html + '</div>', unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="card"><h3>Final slag</h3>', unsafe_allow_html=True)
            slag_rows = [
                ("Mass", f"{st_final.slag_mass/1000:.2f} t"),
                ("B2", f"{st_final.basicity:.2f}"),
                ("FeO", f"{st_final.feo_pct:.1f} %"),
            ]
            # Add individual oxide masses
            for oxide, mass in st_final.slag.items():
                if mass > 1:
                    slag_rows.append((oxide, f"{mass:.0f} kg"))
            table_html = '<table class="eaf-table"><tbody>'
            for k, v in slag_rows:
                table_html += f'<tr><td>{k}</td><td class="accent">{v}</td></tr>'
            table_html += '</tbody></table>'
            st.markdown(table_html + '</div>', unsafe_allow_html=True)

        with col3:
            st.markdown('<div class="card"><h3>Off-gas &amp; balance</h3>', unsafe_allow_html=True)
            gas_rows = [
                ("Electrical energy", f"{st_final.E_elec_MJ/3.6:.0f} kWh ({spec_elec:.0f} kWh/t)"),
                ("Chemical energy", f"{st_final.E_chem_MJ/3.6:.0f} kWh"),
                ("Oxygen used", f"{st_final.O2_used_Nm3:.0f} Nm³"),
                ("Electrode", f"{st_final.electrode_kg:.0f} kg"),
                ("Power-on time", f"{st_final.power_on_s/60:.1f} min"),
                ("Shell temp", f"{st_final.shell_temp_C:.0f} °C"),
                ("Wall / panel / off-gas loss", f"{st_final.wall_loss_kW:.0f} / {st_final.panel_loss_kW:.0f} / {st_final.offgas_loss_kW:.0f} kW"),
            ]
            table_html = '<table class="eaf-table"><tbody>'
            for k, v in gas_rows:
                table_html += f'<tr><td>{k}</td><td class="accent">{v}</td></tr>'
            table_html += '</tbody></table>'
            st.markdown(table_html + '</div>', unsafe_allow_html=True)

    else:
        st.info("Run Dynamic model to see results.")

# ============================================================
# TAB 5: Event Log
# ============================================================
with tabs[4]:
    st.markdown('<div class="card"><h3>Heat event log — additions, phase changes &amp; milestones (with timings)</h3>', unsafe_allow_html=True)
    st.markdown('<p class="note">Chronological record generated by the dynamic simulation. Run the Dynamic Model to populate.</p>', unsafe_allow_html=True)
    if st.session_state.last_dynamic:
        events = st.session_state.last_dynamic.events
        if events:
            # Styled event table matching HTML
            def phase_badge(phase):
                if phase == "Charge":
                    return "b-charge"
                elif "Flat" in phase or phase == "TAP":
                    return "b-ok"
                else:
                    return "b-phase"

            table_html = '<table class="eaf-table"><thead><tr><th style="width:90px">Time</th><th style="width:150px">Phase</th><th>Event</th><th>Detail</th></tr></thead><tbody>'
            for ev in events:
                t_str = f"{ev['t']/60:.1f} min"
                badge_cls = phase_badge(ev['phase'])
                table_html += f'<tr><td><b>{t_str}</b></td><td><span class="badge {badge_cls}">{ev["phase"]}</span></td><td>{ev["event"]}</td><td class="note">{ev.get("detail","")}</td></tr>'
            table_html += '</tbody></table>'
            st.markdown(table_html, unsafe_allow_html=True)
        else:
            st.write("No events recorded.")
    else:
        st.info("Run Dynamic model to see event log.")
    st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# TAB 6: Help & Model
# ============================================================
with tabs[5]:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="card">
        <h3>About SmartEAF™</h3>
        <p class="note">SmartEAF™ is a first-principles digital twin of the electric arc furnace developed by
        <b>Extractmet Private Limited</b>. It couples a per-heat <b>static mass &amp; energy balance</b> with a
        time-resolved <b>dynamic model</b> that resolves, at every time step, the coupled elemental mass balances,
        heat balances, reaction thermodynamics and kinetics, heat and mass transfer, scrap-melting and dissolution
        kinetics, slag foaming, and coupled conduction–convection–radiation heat loss through the refractory wall.
        The model is calibrated and validated against literature-typical plant data (reference plant anonymised as
        <b>Industry-X</b>).</p>
        <h4 style="margin:12px 0 6px;font-size:12px;color:#ffb703;text-transform:uppercase;letter-spacing:.5px">Modelling basis</h4>
        <ul class="note">
            <li><b>Dynamic zones:</b> solid scrap, liquid steel, slag and gas, each with its own energy balance and a
            continuous heating/melting split (after Logar et al., ISIJ 2012).</li>
            <li><b>Thermochemistry &amp; kinetics:</b> decarburisation (O₂-limited &amp; mass-transfer-limited regimes),
            Si/Mn/P oxidation, FeO formation and carbon reduction, CO post-combustion, all as rate laws toward equilibrium.</li>
            <li><b>Dissolution kinetics:</b> lime dissolves into the slag over time (basicity builds), scrap melts by an
            immersion + arc-exposure closure.</li>
            <li><b>Refractory heat loss:</b> multi-layer 1-D conduction (working lining / safety lining / insulation / shell)
            coupled to external convection and radiation, solved for shell and interface temperatures.</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card"><h3>Parameter reference (help files)</h3>', unsafe_allow_html=True)
        search_term = st.text_input("Filter parameters…", key="help_search",
                                     placeholder="filter parameters…")
        # Show all parameters with their help text
        for cat, keys in categories.items():
            for name in keys:
                if name in st.session_state.reg._params:
                    p = st.session_state.reg[name]
                    if search_term and search_term.lower() not in name.lower() and search_term.lower() not in (p.help or "").lower():
                        continue
                    st.markdown(f"""
                    <div style="padding:8px;border-bottom:1px solid #2c3d4d">
                        <div style="color:#48cae4;font-weight:600;font-size:12.5px">{name} <span style="font-size:10px;color:#00b4d8;font-weight:600">{p.unit}</span></div>
                        <div class="note" style="margin-top:2px;font-size:11px;color:#9fb3c8">default {p.value}</div>
                        <div class="note" style="margin-top:3px">{p.help or ''}</div>
                    </div>
                    """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# Footer (matching smarteaf_web.html)
# ============================================================
st.markdown("""
<div class="eaf-footer">
  SmartEAF™ — Electric Arc Furnace Digital Twin &amp; Process Optimizer &nbsp;|&nbsp; © Extractmet Private Limited &nbsp;|&nbsp;
  Runs fully offline · reference plant anonymised as Industry-X · figures for guidance, calibrate to your furnace before use.
</div>
""", unsafe_allow_html=True)
