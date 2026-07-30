"""
run_demo.py
===========
A guided, non-interactive tour of the EAF static + dynamic control model.

Run:
    python run_demo.py

It will:
  1. show how parameters are listed and documented (help files),
  2. run the STATIC mass/energy balance and print the energy breakdown,
  3. run the DYNAMIC heat simulation and save a plot,
  4. print operator GUIDANCE for the heat,
  5. demonstrate a "what-if" study (more oxygen + carbon), and
  6. reproduce a PROCESS PROBLEM (cold, low-basicity heat) and show the
     guidance catching it.
"""

from eaf_control_model import (default_parameters, StaticEAFModel,
                               DynamicEAFModel, Diagnostics)


def section(title):
    print("\n\n" + "#" * 70)
    print("#  " + title)
    print("#" * 70)


# --------------------------------------------------------------------------- #
# 1. Parameters and their help files                                          #
# --------------------------------------------------------------------------- #
section("1. PARAMETERS  (everything you can modify, each with a help file)")
reg = default_parameters()
reg.list("operating")
print("\nExample help file for one parameter:")
reg.help("oxygen_total")
reg.help("post_combustion_ratio")


# --------------------------------------------------------------------------- #
# 2. Static model                                                             #
# --------------------------------------------------------------------------- #
section("2. STATIC MODEL  (plan the heat: yield, fluxes, oxygen, energy)")
static = StaticEAFModel(reg).solve()
print(static.summary())
print()
print(static.energy_breakdown())


# --------------------------------------------------------------------------- #
# 3 + 4. Dynamic model + guidance                                             #
# --------------------------------------------------------------------------- #
section("3. DYNAMIC MODEL  (simulate the heat through time)")
dyn = DynamicEAFModel(reg).simulate(mode="endpoint")
print(dyn.summary())
try:
    path = dyn.plot("eaf_heat_baseline.png")
    print(f"\n[plot saved to {path}]")
except Exception as e:
    print(f"[plot skipped: {e}]")

section("4. OPERATOR GUIDANCE for that heat")
dg = Diagnostics(reg)
print(dg.render(dg.from_dynamic(dyn)))


# --------------------------------------------------------------------------- #
# 5. What-if study                                                            #
# --------------------------------------------------------------------------- #
section("5. WHAT-IF  (raise oxygen flow + carbon: effect on energy & time)")
print(f"{'scenario':<24}{'elec kWh/t':>12}{'chem kWh':>12}"
      f"{'O2 Nm3':>10}{'tap-tap min':>14}")
for label, changes in [
    ("baseline", {}),
    ("+O2 flow", {"oxygen_flow_rate": 3500}),
    ("+O2 +carbon", {"oxygen_flow_rate": 3500, "injected_carbon": 1600,
                     "charge_carbon": 1800}),
    ("+burners", {"natural_gas": 700}),
]:
    r = default_parameters()
    for k, v in changes.items():
        r.set(k, v)
    res = DynamicEAFModel(r).simulate(mode="endpoint")
    st = res.final
    print(f"{label:<24}{st.E_elec_MJ/3.6/(st.m_lSc/1000):>12.0f}"
          f"{st.E_chem_MJ/3.6:>12.0f}{st.O2_used_Nm3:>10.0f}"
          f"{res.tap_to_tap_min:>14.1f}")


# --------------------------------------------------------------------------- #
# 6. Reproduce a process problem and diagnose it                              #
# --------------------------------------------------------------------------- #
section("6. PROCESS PROBLEM  (too little lime + short power-on = cold, acid)")
bad = default_parameters()
bad.set("lime_charged", 400)          # far too little lime
bad.set("power_on_time", 35)          # too short
bad.set("target_tap_temperature", 1640)
badstatic = StaticEAFModel(bad).solve()
print(badstatic.summary())
print()
dgb = Diagnostics(bad)
print(dgb.render(dgb.from_static(badstatic)))

print("\n\nDemo complete. See eaf_heat_baseline.png for the heat plot.")
