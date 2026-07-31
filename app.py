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
import sensitivity as S

plt.style.use('dark_background')

# 1. Custom CSS and Layout
st.set_page_config(page_title="SmartEAF™ — EAF Digital Twin & Process Optimizer", layout="wide")

SENS_STUDIES = {
    "Static: energy vs hot metal":     ("static", "elec_kwh_t"),
    "Static: energy vs charge carbon": ("static", "elec_kwh_t"),
    "Static: basicity vs lime":        ("static", "basicity"),
    "Static: tornado (energy)":        ("static", "tornado"),
    "Dynamic: tap-to-tap vs power":    ("dynamic", "taptap_min"),
    "Dynamic: energy vs oxygen flow":  ("dynamic", "elec_kwh_t"),
    "Dynamic: tornado (energy)":       ("dynamic", "tornado"),
}

st.markdown("""
<style>
/* Custom CSS to mimic smarteaf_web.html */
:root {
  --bg:#0e1620; --bg2:#16212e; --panel:#1b2836; --panel2:#22323f;
  --ink:#e7eef5; --dim:#9fb3c8; --line:#2c3d4d;
  --accent:#00b4d8; --accent2:#48cae4; --gold:#ffb703;
}
.stApp {
    background-color: #0e1620;
    color: #e7eef5;
}
header {
    background: linear-gradient(90deg,#0b1017,#16212e);
    border-bottom: 2px solid #00b4d8;
    padding: 10px 18px;
    display: flex; align-items: center; gap: 14px;
}
.logo {
    background: #00b4d8; color: #062733; font-weight: 800; padding: 6px 12px; border-radius: 6px; font-size: 18px; letter-spacing: 1px;
}
.title-box h1 { font-size: 17px; margin: 0; font-weight: 700; color: #e7eef5; line-height: 1.2; }
.title-box .sub { color: #9fb3c8; font-size: 12px; }
.spacer { flex: 1; }
.co { color: #ffb703; font-weight: 700; font-size: 13px; }
/* Override default Streamlit padding */
.block-container {
    padding-top: 1rem;
    padding-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

# 2. Header
st.markdown("""
<header>
  <div class="logo">SmartEAF™</div>
  <div class="title-box"><h1>Electric Arc Furnace — Digital Twin & Process Optimizer</h1>
    <div class="sub">Static & dynamic first-principles model · operator decision support · Reference: Industry-X</div></div>
  <div class="spacer"></div>
  <div class="co">Extractmet Private Limited</div>
</header>
""", unsafe_allow_html=True)

# Setup Session State
if 'reg' not in st.session_state:
    st.session_state.reg = default_parameters()
if 'last_static' not in st.session_state:
    st.session_state.last_static = None
if 'last_dynamic' not in st.session_state:
    st.session_state.last_dynamic = None

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

def run_dynamic(param_inputs):
    apply_changes(param_inputs)
    try:
        res = DynamicEAFModel(st.session_state.reg).simulate(mode="endpoint")
        st.session_state.last_dynamic = res
        st_final = res.final
        st.success(f"Dynamic done: tap {st_final.T_lSc-273.15:.0f} degC / C {st_final.pct['C']:.3f}%, {res.tap_to_tap_min:.1f} min, {st_final.E_elec_MJ/3.6/(st_final.m_lSc/1000):.0f} kWh/t.")
    except Exception as e:
        st.error(f"Dynamic model error: {e}")

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
            f"Tap T : {st_final.T_lSc-273.15:6.0f} degC",
            f"Carbon: {st_final.pct['C']:6.3f} %",
            f"B2    : {st_final.basicity:6.2f}",
            f"FeO   : {st_final.feo_pct:6.0f} %",
            f"Foam  : {st_final.foam_index:6.2f}",
            f"Shell : {st_final.shell_temp_C:6.0f} degC",
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

# 3. Tabs Setup
tabs = st.tabs([
    "⚙ Reactor Schematic", 
    "✎ Inputs / Parameters", 
    "▤ Static Model", 
    "▶ Dynamic Model", 
    "☰ Event Log",
    "📈 EDA & Sensitivity",
    "? Help & Model"
])

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

# Collect param_inputs globally from session state since streamlit re-runs entirely
param_inputs = {}

# -----------------
# TAB 1: Schematic
# -----------------
with tabs[0]:
    st.markdown("""
    <div style='background:linear-gradient(135deg,#15222f,#0d1620);border:1px solid #2c3d4d;border-radius:12px;padding:18px;margin-bottom:14px;'>
        <h2 style='margin:0 0 6px;font-size:20px;color:#e7eef5;'>Industry-X Electric Arc Furnace <span style='display:inline-block;background:#00b4d8;color:#062733;font-size:10px;font-weight:800;padding:2px 8px;border-radius:4px;vertical-align:middle;margin-left:8px;'>LIVE DIGITAL TWIN</span></h2>
        <p style='margin:0;color:#9fb3c8;font-size:13px;line-height:1.6;'>Interactive cross-section of the EAF reactor. Values update from the latest simulation. Run the <b>Dynamic Model</b> to animate the heat and populate live readouts, or the <b>Static Model</b> for a per-heat balance.</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([1.35, 1])
    with col1:
        st.markdown("### Furnace cross-section")
        fig = draw_schematic(st.session_state.last_dynamic)
        st.pyplot(fig)
    with col2:
        st.markdown("### Live process readout")
        if st.session_state.last_dynamic:
            st.text(st.session_state.last_dynamic.summary())
        else:
            st.info("Run Dynamic model to see readout.")

# -----------------
# TAB 2: Inputs
# -----------------
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

# -----------------
# TAB 3: Static
# -----------------
with tabs[2]:
    if st.button("▤ Run Static Mass & Energy Balance"):
        run_static(param_inputs)
        
    if st.session_state.last_static:
        res = st.session_state.last_static
        st.markdown(f"**Steel tapped**: {res.steel_mass/1000:.1f} t | **Electrical energy**: {res.electrical_energy_specific:.0f} kWh/t | **Basicity**: {res.basicity_B2:.2f}")
        
        # Grid g3 (Data/EDA charts matching HTML)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("### Energy demand (sinks)")
            if res.energy_sinks:
                fig, ax = plt.subplots(figsize=(4, 3)); fig.patch.set_facecolor("#1b2836"); ax.set_facecolor("#1b2836")
                sizes = list(res.energy_sinks.values())
                labels = [k if v > 0.05*sum(sizes) else "" for k, v in res.energy_sinks.items()]
                ax.pie(sizes, labels=labels, autopct=lambda p: f'{p:.1f}%' if p > 5 else '', textprops={'color':"w", 'fontsize':8})
                st.pyplot(fig)
        with col2:
            st.markdown("### Non-electrical (sources)")
            if res.energy_sources:
                fig, ax = plt.subplots(figsize=(4, 3)); fig.patch.set_facecolor("#1b2836"); ax.set_facecolor("#1b2836")
                sizes = list(res.energy_sources.values())
                labels = [k if v > 0.05*sum(sizes) else "" for k, v in res.energy_sources.items()]
                ax.pie(sizes, labels=labels, autopct=lambda p: f'{p:.1f}%' if p > 5 else '', textprops={'color':"w", 'fontsize':8})
                st.pyplot(fig)
        with col3:
            st.markdown("### Final slag composition")
            if res.slag:
                fig, ax = plt.subplots(figsize=(4, 3)); fig.patch.set_facecolor("#1b2836"); ax.set_facecolor("#1b2836")
                sizes = list(res.slag.values())
                labels = [k if v > 0.05*sum(sizes) else "" for k, v in res.slag.items()]
                ax.pie(sizes, labels=labels, autopct=lambda p: f'{p:.1f}%' if p > 5 else '', textprops={'color':"w", 'fontsize':8})
                st.pyplot(fig)
                
        # Grid g2 (Mass and Tables)
        col4, col5 = st.columns(2)
        with col4:
            st.markdown("### Mass Balance")
            mass_in = st.session_state.reg.get("scrap_charge_mass").value*1000 + st.session_state.reg.get("dri_mass").value*1000 + st.session_state.reg.get("hot_metal_mass").value*1000 + st.session_state.reg.get("lime_charged").value + st.session_state.reg.get("dolomite_charged").value
            mass_out = res.steel_mass + res.slag_mass + res.offgas_mass + res.dust_mass
            fig, ax = plt.subplots(figsize=(5, 3.5)); fig.patch.set_facecolor("#1b2836"); ax.set_facecolor("#1b2836")
            ax.bar(["Inputs", "Outputs (Calculated)"], [mass_in, mass_out], color=["#00b4d8", "#ffb703"])
            ax.set_ylabel("Mass (kg)")
            ax.tick_params(colors='w')
            st.pyplot(fig)
            st.text(res.energy_breakdown())
        with col5:
            st.markdown("### Tapped-steel composition & balance")
            st.text(res.summary())
            st.dataframe(pd.DataFrame(list(res.tap_composition.items()), columns=["Element", "wt-%"]))

    else:
        st.info("Run Static model to see results.")

# -----------------
# TAB 4: Dynamic
# -----------------
with tabs[3]:
    if st.button("▶ Run Time-Resolved Simulation"):
        run_dynamic(param_inputs)
        
    if st.session_state.last_dynamic:
        res = st.session_state.last_dynamic
        st_final = res.final
        st.markdown(f"**Endpoint**: {st_final.T_lSc-273.15:.0f} degC / {st_final.pct['C']:.3f}% C | **Tap-to-tap**: {res.tap_to_tap_min:.1f} min | **Energy**: {st_final.E_elec_MJ/3.6/(st_final.m_lSc/1000):.0f} kWh/t")
        st.text(res.summary())
        
        # Original 12-panel (serves as the 14-panel grid from HTML)
        fig = res.figure(figsize=(15, 10))
        st.pyplot(fig)
        
        # HTML tables (Final tapped steel, Final slag, Off-gas & balance)
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("### Final tapped steel")
            st.write(f"**Mass**: {st_final.m_lSc/1000:.1f} t")
            st.write(f"**Temperature**: {st_final.T_lSc-273.15:.0f} °C")
            df_s = pd.DataFrame([(k, v) for k,v in st_final.pct.items()], columns=["Element", "wt-%"])
            st.dataframe(df_s, width=300)
        with col2:
            st.markdown("### Final slag")
            st.write(f"**Mass**: {st_final.slag_mass/1000:.1f} t")
            st.write(f"**Basicity B2**: {st_final.basicity:.2f}")
            st.write(f"**Foam Index**: {st_final.foam_index:.2f}")
            df_sl = pd.DataFrame([(k, v) for k,v in st_final.slag_wt_pct.items()], columns=["Oxide", "wt-%"])
            st.dataframe(df_sl, width=300)
        with col3:
            st.markdown("### Off-gas & balance")
            tot_e = st_final.E_elec_MJ/3.6/(st_final.m_lSc/1000)
            st.write(f"**Total Specific Energy**: {tot_e:.0f} kWh/t")
            st.write(f"**Total CO**: {st_final.mass_offgas['CO']:.1f} kg")
            st.write(f"**Total CO2**: {st_final.mass_offgas['CO2']:.1f} kg")
    else:
        st.info("Run Dynamic model to see results.")

# -----------------
# TAB 5: Event Log
# -----------------
with tabs[4]:
    st.markdown("### Heat event log — additions, phase changes & milestones")
    if st.session_state.last_dynamic:
        events = st.session_state.last_dynamic.events
        if events:
            df = pd.DataFrame(events)
            df['t'] = df['t'].apply(lambda x: f"{x/60:.1f} min")
            st.dataframe(df, width=900)
        else:
            st.write("No events recorded.")
    else:
        st.info("Run Dynamic model to see event log.")

# -----------------
# TAB 6: EDA & Sensitivity
# -----------------
with tabs[5]:
    st.markdown("### Exploratory Data Analysis & Sensitivity Studies")
    study_choice = st.selectbox("Study:", list(SENS_STUDIES.keys()))
    if st.button("Generate Sensitivity Study"):
        with st.spinner(f"Computing sensitivity study '{study_choice}'..."):
            try:
                apply_changes(param_inputs)
                kind, metric = SENS_STUDIES[study_choice]
                
                fig = Figure(figsize=(9.6, 5.6))
                ax = fig.add_subplot(111)
                
                if metric == "tornado":
                    if kind == "static":
                        params = ["hot_metal_mass", "charge_carbon", "natural_gas",
                                  "lime_charged", "iron_oxidation_fraction",
                                  "power_off_time", "target_tap_temperature",
                                  "electrical_efficiency", "arc_transfer_efficiency",
                                  "post_combustion_ratio"]
                    else:
                        params = ["transformer_power", "oxygen_flow_rate",
                                  "injected_carbon", "arc_transfer_efficiency",
                                  "electrical_efficiency", "panel_heat_loss",
                                  "power_off_time", "scrap_melt_htc",
                                  "post_combustion_ratio"]
                    rows, base = S.tornado(kind, params, "elec_kwh_t", pct=0.20)
                    names = [r[0] for r in rows][::-1]
                    for i, r in enumerate(rows[::-1]):
                        left, right = sorted([r[1], r[2]])
                        ax.barh(i, right - left, left=left, color="#4C78A8",
                                edgecolor="k", alpha=0.85)
                    ax.axvline(base, color="crimson", lw=2, label=f"baseline={base:.1f}")
                    ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=8)
                    ax.set_xlabel("electrical energy (kWh/t)"); ax.legend(fontsize=8)
                    ax.set_title(study_choice)
                else:
                    if study_choice == "Static: energy vs hot metal":
                        x = list(np.linspace(0, 40, 10))
                        y = S.sweep_static("hot_metal_mass", x, ["elec_kwh_t"])["elec_kwh_t"]
                        xlabel, ylabel = "hot metal charge (t)", "electrical energy (kWh/t)"
                    elif study_choice == "Static: energy vs charge carbon":
                        x = list(np.linspace(0, 3000, 10))
                        y = S.sweep_static("charge_carbon", x, ["elec_kwh_t"])["elec_kwh_t"]
                        xlabel, ylabel = "charge carbon (kg)", "electrical energy (kWh/t)"
                    elif study_choice == "Static: basicity vs lime":
                        x = list(np.linspace(500, 4000, 10))
                        y = S.sweep_static("lime_charged", x, ["basicity"])["basicity"]
                        xlabel, ylabel = "lime charged (kg)", "slag basicity B2"
                    elif study_choice == "Dynamic: tap-to-tap vs power":
                        x = list(np.linspace(55, 115, 8))
                        y = S.sweep_dynamic("transformer_power", x, ["taptap_min"])["taptap_min"]
                        xlabel, ylabel = "transformer power (MW)", "tap-to-tap (min)"
                    elif study_choice == "Dynamic: energy vs oxygen flow":
                        x = list(np.linspace(1500, 5000, 8))
                        y = S.sweep_dynamic("oxygen_flow_rate", x, ["elec_kwh_t"])["elec_kwh_t"]
                        xlabel, ylabel = "oxygen flow (Nm3/h)", "electrical energy (kWh/t)"
                    
                    ax.plot(x, y, "o-", color="#00b4d8")
                    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
                    ax.set_title(study_choice)
                    ax.grid(alpha=0.3)
                
                fig.tight_layout()
                st.pyplot(fig)
            except Exception as e:
                st.error(f"Error computing sensitivity: {e}")

# -----------------
# TAB 7: Help
# -----------------
with tabs[6]:
    st.markdown("""
    ### About SmartEAF™
    SmartEAF™ is a first-principles digital twin of the electric arc furnace developed by **Extractmet Private Limited**. It couples a per-heat **static mass & energy balance** with a time-resolved **dynamic model**.
    
    #### Modelling basis
    - **Dynamic zones:** solid scrap, liquid steel, slag and gas, each with its own energy balance.
    - **Thermochemistry & kinetics:** decarburisation, Si/Mn/P oxidation, FeO formation and carbon reduction.
    - **Dissolution kinetics:** lime dissolves into the slag over time, scrap melts by immersion.
    - **Refractory heat loss:** multi-layer 1-D conduction coupled to external convection and radiation.
    """)
