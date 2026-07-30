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

st.set_page_config(page_title="EAF Operator Desk", layout="wide")

SENS_STUDIES = {
    "Static: energy vs hot metal":     ("static", "elec_kwh_t"),
    "Static: energy vs charge carbon": ("static", "elec_kwh_t"),
    "Static: basicity vs lime":        ("static", "basicity"),
    "Static: tornado (energy)":        ("static", "tornado"),
    "Dynamic: tap-to-tap vs power":    ("dynamic", "taptap_min"),
    "Dynamic: energy vs oxygen flow":  ("dynamic", "elec_kwh_t"),
    "Dynamic: tornado (energy)":       ("dynamic", "tornado"),
}

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

def draw_schematic(res):
    st_final = res.final
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
    
    # bath + slag (slag thickness ~ foam index)
    ax.add_patch(Polygon([(2.15, 3.0), (2.3, 1.75), (7.7, 1.75), (7.85, 3.0)],
                         closed=True, fc="#c94f2a", ec="none"))
    th = 0.15 + st_final.foam_index * 0.5
    ax.add_patch(Rectangle((2.2, 3.0), 5.6, th, fc="#6aa84f", ec="none", alpha=0.9))
    
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

# UI Sidebar
st.sidebar.title("⚙️ Operating Parameters")
if st.sidebar.button("Reset defaults"):
    st.session_state.reg.reset_all()

st.sidebar.markdown("---")
param_inputs = {}
for name in st.session_state.reg.names("operating"):
    p = st.session_state.reg[name]
    
    if isinstance(p.value, bool):
        val = st.sidebar.checkbox(f"{name} ({p.unit})", value=p.value, help=p.help)
    elif isinstance(p.value, int) and not isinstance(p.value, bool):
        val = st.sidebar.number_input(f"{name} ({p.unit})", value=int(p.value), help=p.help)
    elif isinstance(p.value, float):
        val = st.sidebar.number_input(f"{name} ({p.unit})", value=float(p.value), help=p.help)
    elif isinstance(p.value, dict):
        val = st.sidebar.text_input(f"{name} ({p.unit})", value=" ".join(f"{k}={v:g}" for k, v in p.value.items()), help=p.help)
    else:
        val = st.sidebar.text_input(f"{name} ({p.unit})", value=str(p.value), help=p.help)
    
    # Convert dicts
    if isinstance(p.value, dict) and isinstance(val, str):
        try:
            out = dict(p.value)
            for pair in val.replace(",", " ").split():
                if "=" in pair or ":" in pair:
                    sep = "=" if "=" in pair else ":"
                    k, v = pair.split(sep)
                    out[k.strip()] = float(v)
            param_inputs[name] = out
        except:
            param_inputs[name] = p.value
    else:
        param_inputs[name] = val


# Top Toolbar Area
col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
with col1:
    st.markdown("### EAF Control Model")
with col2:
    if st.button("Apply Changes", type="primary", use_container_width=True):
        apply_changes(param_inputs)
with col3:
    if st.button("Run STATIC", use_container_width=True):
        apply_changes(param_inputs)
        try:
            res = StaticEAFModel(st.session_state.reg).solve()
            st.session_state.last_static = res
            st.success(f"Static done: {res.steel_mass/1000:.1f} t tapped, {res.electrical_energy_specific:.0f} kWh/t, B2 {res.basicity_B2:.2f}.")
        except Exception as e:
            st.error(f"Static model error: {e}")

with col4:
    if st.button("Run DYNAMIC", use_container_width=True):
        apply_changes(param_inputs)
        try:
            res = DynamicEAFModel(st.session_state.reg).simulate(mode="endpoint")
            st.session_state.last_dynamic = res
            st_final = res.final
            st.success(f"Dynamic done: tap {st_final.T_lSc-273.15:.0f} degC / C {st_final.pct['C']:.3f}%, {res.tap_to_tap_min:.1f} min, {st_final.E_elec_MJ/3.6/(st_final.m_lSc/1000):.0f} kWh/t.")
        except Exception as e:
            st.error(f"Dynamic model error: {e}")


# Main Content Area
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Static result", "Dynamic result", "Guidance", "Sensitivity", "Reactor schematic", "Event log"
])

with tab1:
    if st.session_state.last_static:
        res = st.session_state.last_static
        st.text(res.summary())
        st.text(res.energy_breakdown())
    else:
        st.info("Run Static model to see results.")

with tab2:
    if st.session_state.last_dynamic:
        res = st.session_state.last_dynamic
        st.text(res.summary())
        fig = res.figure(figsize=(12, 7))
        st.pyplot(fig)
    else:
        st.info("Run Dynamic model to see results.")

with tab3:
    if st.session_state.last_dynamic or st.session_state.last_static:
        dg = Diagnostics(st.session_state.reg)
        if st.session_state.last_dynamic:
            checks = dg.from_dynamic(st.session_state.last_dynamic)
            source = "DYNAMIC"
        else:
            checks = dg.from_static(st.session_state.last_static)
            source = "STATIC"
            
        n_act = sum(c.status == "ACT" for c in checks)
        n_watch = sum(c.status == "WATCH" for c in checks)
        st.subheader(f"{source} guidance — {n_act} action(s), {n_watch} watch")
        
        for c in checks:
            if c.status == "OK":
                st.success(f"**{c.name}**: {c.value} - {c.message}")
            elif c.status == "WATCH":
                st.warning(f"**{c.name}**: {c.value} - {c.message}\n\n*Recommendation*: {c.recommendation}")
            else:
                st.error(f"**{c.name}**: {c.value} - {c.message}\n\n*Recommendation*: {c.recommendation}")
    else:
        st.info("Run a model to get guidance.")

with tab4:
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

with tab5:
    if st.session_state.last_dynamic:
        fig = draw_schematic(st.session_state.last_dynamic)
        st.pyplot(fig)
    else:
        st.info("Run Dynamic model to see reactor schematic.")

with tab6:
    if st.session_state.last_dynamic:
        events = st.session_state.last_dynamic.events
        if events:
            df = pd.DataFrame(events)
            df['t'] = df['t'].apply(lambda x: f"{x/60:.1f} min")
            st.dataframe(df, use_container_width=True)
        else:
            st.write("No events recorded.")
    else:
        st.info("Run Dynamic model to see event log.")
