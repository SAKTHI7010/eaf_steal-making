# SmartEAF&trade; — Electric Arc Furnace Digital Twin &amp; Process Optimizer

**Extractmet Private Limited** · first-principles static + dynamic EAF model, operator console and decision-support platform.
Reference plant anonymised throughout as **Industry-X**.

> The model is a validated **reduced-order engineering tool**. Its coefficients are realistic but generic —
> calibrate the flagged parameters and the diagnostic bands to a specific furnace (a few real heats) before
> trusting absolute numbers operationally.

---

## 1. What is in this deck

| File | What it is |
|---|---|
| `smarteaf_web.html` | **Web operator console** — a single self-contained HTML file. Opens in any modern browser, fully offline. Interactive reactor schematic, all inputs with help, separate **Static** and **Dynamic** sections, **event log**, and 8+ live plots. |
| `eaf_control_model/` | **Python package** — the model library + a native **desktop operator console** (Tkinter) + CLI + sensitivity engine. |
| `generate_deck_plots.py` | Regenerates the validated figure set into `deck_plots/`. |
| `deck_plots/` | Process trajectory, validation-vs-literature, mass/energy balance, and refractory thermal figures. |
| `SmartEAF_Pitch_Deck.pptx` | 14-slide commercial pitch (problem → solution → capabilities → validation → ROI → packages → contact). |
| `SmartEAF_Product_Datasheet.pdf` | One-page product datasheet. |
| `screenshots/` | Console screenshots (web + desktop schematic, dynamic, event log). |

---

## 2. The model

SmartEAF couples two models that share one parameter set:

**Static model** — a per-heat mass &amp; energy balance. Given the charge (scrap composition, DRI, hot metal), fluxes,
oxygen, carbon, power and targets it computes tap weight and metallic yield, oxygen and flux demand, slag amount and
basicity, tapped-steel composition, an itemised energy balance (sinks vs sources) and the specific electrical energy.

**Dynamic model** — a control-oriented, lumped-zone time simulation (solid scrap, liquid steel, slag, gas) integrated
across the whole heat. At **every time step** it resolves:

- **Elemental mass balances** (C, Si, Mn, P, Fe, Cu…) and a full **heat balance** per zone;
- **Reaction thermodynamics &amp; kinetics** — decarburisation with an O₂-limited → mass-transfer-limited regime change,
  Si/Mn/P oxidation toward equilibrium, FeO formation and reduction by carbon, CO post-combustion;
- **Heat &amp; mass transfer** — arc-to-bath transfer (foaming/shielding dependent), oxy-fuel burners, immersion melting
  of scrap by the superheated bath, mass-transfer-limited refining;
- **Scrap melting &amp; dissolution kinetics** — a continuous heating/melting split (after Logar et al., ISIJ 2012), and
  **lime dissolution** into the slag so basicity builds over time;
- **Coupled conduction–convection–radiation heat loss** through the refractory wall — a multi-layer 1-D conduction
  network (working lining / safety lining / insulation / steel shell) coupled to external convection and radiation,
  solved for the shell and interface temperatures (configurable to your refractory thickness &amp; properties);
- **Slag &amp; foaming** — slag chemistry, basicity and a CO-driven foaming index that feeds back on arc efficiency.

It emits full **time trajectories**, an **event log** (charges, additions, phase changes, endpoint — with timings),
and the **final composition &amp; weights** of steel, slag and off-gas.

**Recalibrated to a modern ~130 t UHP furnace with India-relevant DRI practice**, with reaction kinetics
rebuilt from the literature (Turkdogan; Bekker 1999; Logar/Meier 2012-17; Kirschen 2021).

**Kinetics — mechanistic, not fitted.** Decarburisation uses the classical two-regime law (oxygen-supply
limited above the critical carbon; carbon-mass-transfer limited below, first order in [C]). Slag FeO and
bath carbon are coupled by the **Turkdogan carbon-oxygen product (%FeO)(%C) = K_CO(T)** (K_CO = 1.8 / 1.25 /
0.89 at 1500 / 1600 / 1700 degC), which sets *both* the equilibrium carbon for decarburisation *and* the
equilibrium FeO for slag reduction from a single thermodynamic constant. FeO reduction by injected carbon
is slag-side mass-transfer controlled. Lime dissolution, scrap/DRI melting and foaming follow the same
rate-law approach.

**Validation - scrap baseline (default heat):** ~446 kWh/t electrical static / ~430 kWh/t dynamic,
~567 kWh/t total, tap ~1664 degC, tap-to-tap ~58 min (power-on ~45 min), ~97% metallic yield (pure-metal
basis), tap slag **FeO ~21-27%**, CaO ~39%, SiO2 ~19%, MgO ~9% (saturation), B2 ~2.1, slag ~74 kg/t.
Bands: electrical 350-450, total 560-650, tap-to-tap 40-60, FeO 20-32%, MgO 6-12%, B2 1.8-2.4,
slag 70-110 kg/t.

**All plots reviewed and unit-correct.** The mass plot now shows solid/liquid steel in tonnes with slag on its own axis (previously slag was in kg on a tonnes axis), and liquid-steel mass is recomputed from its components each step so iron lost to slag as FeO correctly reduces the tapped weight. Both GUIs gained new panels (phase conversion, specific energy, off-gas/O₂, B2/B3, C–FeO coupling), and the validation figure now includes tap-slag composition and FeO-evolution-shape checks against literature bands.

**Reaction kinetics are mechanistic and literature-grounded.** Decarburisation uses the two-regime law (oxygen-supply limited above the critical carbon ~0.30 wt%, carbon-mass-transfer limited and first-order in [C] below it, Turkdogan). Slag FeO is *not* a fitted curve: it is coupled to bath carbon through the Turkdogan carbon-oxygen product **(%FeO)(%C) = K_CO(T)** (K = 1.8 / 1.25 / 0.89 at 1500 / 1600 / 1700 °C), which sets both the equilibrium carbon for decarburisation and the FeO floor for carbon reduction from one thermodynamic constant. FeO reduction by injected carbon is slag-side mass-transfer controlled; lime dissolution is product-layer (2CaO·SiO₂) limited; scrap/DRI melting is shell-freeze then remelt.
**Resulting FeO trajectory matches plant practice:** ~33 wt% at meltdown (scrap rust + early O₂) → dip to ~10–13% during the carbon boil under injection/foaming → rise to ~22% at tap as bath carbon falls — the shape documented by Kirschen and Morales, reproduced from the rate laws rather than imposed.
**India high-DRI:** coal-based DRI raises energy ~ +1.8 kWh/t per %DRI (gangue + endothermic FeO
reduction), slag mass toward ~140-200 kg/t and tap FeO higher. Use the **High-DRI** preset.

---

## 3. The web console (`smarteaf_web.html`)

Just **double-click the file** (or open it in Chrome / Edge / Firefox). No install, no server, no internet. Tabs:

- **Reactor Schematic** — interactive cross-section (electrodes, arc, bath, foaming slag, refractory, water panels,
  O₂ lance, carbon injection, EBT tap) with a live readout panel and the refractory build-up.
- **Inputs / Parameters** — every operating &amp; technical parameter, grouped and editable, each with a help tooltip.
  Presets: low-carbon heat, high-DRI, hot-metal charge.
- **Static Model** — KPIs + energy sinks/sources, slag pie, input/output mass bars, tapped-steel table.
- **Dynamic Model** — a **12-panel operator dashboard**: masses (steel in t, slag on its own axis), solid→liquid phase conversion, temperatures, bath chemistry, slag composition (wt-% stacked) and oxide masses, the carbon–FeO coupling vs Turkdogan equilibrium, foaming & FeO, cumulative + specific energy, power/heat-loss, off-gas (CO/CO₂) & oxygen, and basicity B2/B3 with lime dissolution
  foaming, power/heat-loss breakdown, decarburisation vs oxygen, lime dissolution vs dephosphorisation) + final
  steel / slag / off-gas tables.
- **Event Log** — timed table of the heat.
- **Help &amp; Model** — modelling basis, validation table, and a searchable parameter reference.

The model is re-implemented in JavaScript and validated to match the Python reference within rounding.

---

## 4. The Python package &amp; desktop console

```bash
pip install matplotlib numpy          # add python3-tk on Linux for the desktop GUI
python -m eaf_control_model.gui        # desktop operator console
python -m eaf_control_model.cli        # interactive console
python generate_deck_plots.py          # (re)generate the figures
```

```python
from eaf_control_model import default_parameters, StaticEAFModel, DynamicEAFModel, Diagnostics
reg = default_parameters()
reg.set("oxygen_flow_rate", 3000)
static = StaticEAFModel(reg).solve();      print(static.summary())
dyn    = DynamicEAFModel(reg).simulate(mode="endpoint")
print(dyn.summary())
for e in dyn.events:  print(f"{e['t']/60:5.1f} min  [{e['phase']}]  {e['event']}")
dyn.plot("heat.png")                       # 6-panel trajectory
```

The desktop console mirrors the web app: editable parameters with help, Static / Dynamic results, a **reactor
schematic**, colour-coded **guidance**, on-demand **sensitivity** studies, and an **event log** tab.

Package modules: `parameters` (documented registry), `static_model`, `dynamic_model` (zones, chemistry, foaming,
dissolution, refractory loss, plotting), `refractory` (coupled conduction/convection/radiation), `diagnostics`
(operator guidance), `sensitivity` (sweeps / grids / tornado), `thermodata`, `gui`, `cli`.

---

## 5. Notes

- All customer/plant references are anonymised as **Industry-X**.
- Figures are for guidance; calibrate before operational use. Parameters flagged `[CALIBRATE]` in their help text
  (refractory conductivities, kinetic rates, foaming, efficiencies) are the first to tune to plant data.
- Commercial enquiries: **Extractmet Private Limited**, IIT Madras Research Park, Chennai · contact@extractmet.com
