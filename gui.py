"""
gui.py
======
Operator-desk GUI for the EAF static + dynamic control model.

A single-window desktop dashboard (Tkinter + embedded matplotlib) intended to
sit on the operator's screen:

  * LEFT  — every OPERATING parameter as an editable field, with a help button,
            an "Apply" action (range-checked), and Save/Load of a parameter set.
  * RIGHT — tabs:
        Static result   : mass/energy balance summary + energy breakdown
        Dynamic result  : heat summary + embedded 4-panel heat plot
        Guidance        : colour-coded OK / WATCH / ACT advice with actions
        Sensitivity     : pick a study and view the plot (computed on demand)
  * TOP   — Run Static / Run Dynamic / Reset buttons and a status line.

Run it with:
    python -m eaf_control_model.gui

Requires: Python's tkinter (usually the system package 'python3-tk') and
matplotlib.
"""

from __future__ import annotations

import json
import queue
import threading

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .parameters import default_parameters
from .static_model import StaticEAFModel
from .dynamic_model import DynamicEAFModel
from .diagnostics import Diagnostics
from . import sensitivity as S


# colours ------------------------------------------------------------------- #
BG      = "#1f2733"
PANEL   = "#2a3542"
ACCENT  = "#00b4d8"
TEXT    = "#e6edf3"
STATUS_COLOR = {"OK": "#2e7d32", "WATCH": "#ef8f00", "ACT": "#c62828"}

SENS_STUDIES = {
    "Static: energy vs hot metal":     ("static", "elec_kwh_t"),
    "Static: energy vs charge carbon": ("static", "elec_kwh_t"),
    "Static: basicity vs lime":        ("static", "basicity"),
    "Static: tornado (energy)":        ("static", "tornado"),
    "Dynamic: tap-to-tap vs power":    ("dynamic", "taptap_min"),
    "Dynamic: energy vs oxygen flow":  ("dynamic", "elec_kwh_t"),
    "Dynamic: tornado (energy)":       ("dynamic", "tornado"),
}


class EAFDeskApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.reg = default_parameters()
        self.entries = {}                 # param name -> tk.StringVar
        self.last_static = None
        self.last_dynamic = None
        self._canvas_dyn = None
        self._canvas_sens = None
        self._canvas_schem = None
        self.task_q = queue.Queue()

        root.title("EAF Operator Desk  —  Static & Dynamic Control Model")
        root.geometry("1360x840")
        root.configure(bg=BG)

        self._style()
        self._build_toolbar()
        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._build_param_editor(body)
        self._build_notebook(body)
        self._build_statusbar()

        self._poll_queue()
        self.set_status("Ready.  Edit operating parameters on the left, then "
                        "Run Static or Run Dynamic.", "OK")

    # --------------------------------------------------------------------- #
    def _style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background=PANEL, foreground=TEXT,
                     padding=(14, 6))
        st.map("TNotebook.Tab", background=[("selected", ACCENT)],
               foreground=[("selected", "#0b0f14")])
        st.configure("TCombobox", fieldbackground="white")

    # --------------------------------------------------------------------- #
    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=8, pady=8)
        tk.Label(bar, text="  EAF  ", bg=ACCENT, fg="#0b0f14",
                 font=("Segoe UI", 15, "bold")).pack(side="left", padx=(0, 10))
        tk.Label(bar, text="Static & Dynamic Control Model  ·  Operator Desk",
                 bg=BG, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(side="left")

        def btn(text, cmd, color=PANEL):
            b = tk.Button(bar, text=text, command=cmd, bg=color, fg=TEXT,
                          activebackground=ACCENT, relief="flat",
                          font=("Segoe UI", 10, "bold"), padx=12, pady=6,
                          cursor="hand2")
            b.pack(side="right", padx=4)
            return b

        btn("Run DYNAMIC", self.run_dynamic, "#0077b6")
        btn("Run STATIC", self.run_static, "#0077b6")
        btn("Reset", self.reset_params)

    # --------------------------------------------------------------------- #
    def _build_param_editor(self, parent):
        outer = tk.LabelFrame(parent, text=" Operating parameters ",
                              bg=PANEL, fg=ACCENT, font=("Segoe UI", 10, "bold"),
                              labelanchor="n", bd=2, relief="groove")
        outer.pack(side="left", fill="y", padx=(0, 8))

        # scrollable area
        canvas = tk.Canvas(outer, bg=PANEL, width=390, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas, bg=PANEL)
        frame.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        # mouse wheel
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-e.delta/120), "units"))

        hdr = tk.Frame(frame, bg=PANEL); hdr.pack(fill="x", pady=(4, 2))
        for txt, w in (("parameter", 20), ("value", 12), ("unit", 8), ("", 3)):
            tk.Label(hdr, text=txt, bg=PANEL, fg="#9fb3c8", width=w,
                     anchor="w", font=("Segoe UI", 8, "bold")).pack(side="left")

        for name in self.reg.names("operating"):
            p = self.reg[name]
            row = tk.Frame(frame, bg=PANEL); row.pack(fill="x", pady=1)
            tk.Label(row, text=name, bg=PANEL, fg=TEXT, width=20, anchor="w",
                     font=("Consolas", 8)).pack(side="left")
            var = tk.StringVar(value=self._fmt(p.value))
            self.entries[name] = var
            tk.Entry(row, textvariable=var, width=12, font=("Consolas", 8),
                     bg="white").pack(side="left")
            tk.Label(row, text=p.unit, bg=PANEL, fg="#9fb3c8", width=8,
                     anchor="w", font=("Segoe UI", 8)).pack(side="left")
            tk.Button(row, text="?", width=2, relief="flat", bg="#3b4a5a",
                      fg=TEXT, cursor="hand2",
                      command=lambda n=name: self._show_help(n)).pack(side="left")

        # action buttons
        act = tk.Frame(outer, bg=PANEL); act.pack(fill="x", side="bottom", pady=6)
        for text, cmd in (("Apply changes", self.apply_changes),
                          ("Save…", self.save_params),
                          ("Load…", self.load_params)):
            tk.Button(act, text=text, command=cmd, bg="#3b4a5a", fg=TEXT,
                      relief="flat", font=("Segoe UI", 9, "bold"),
                      padx=8, pady=4, cursor="hand2").pack(side="left", padx=4)

    # --------------------------------------------------------------------- #
    def _build_notebook(self, parent):
        self.nb = ttk.Notebook(parent)
        self.nb.pack(side="left", fill="both", expand=True)

        # Static tab
        self.tab_static = tk.Frame(self.nb, bg=PANEL)
        self.txt_static = scrolledtext.ScrolledText(
            self.tab_static, bg="#0b1016", fg="#c8facc",
            font=("Consolas", 10), wrap="none", insertbackground=TEXT)
        self.txt_static.pack(fill="both", expand=True, padx=6, pady=6)
        self.nb.add(self.tab_static, text="Static result")

        # Dynamic tab (summary + plot)
        self.tab_dyn = tk.Frame(self.nb, bg=PANEL)
        self.txt_dyn = scrolledtext.ScrolledText(
            self.tab_dyn, bg="#0b1016", fg="#c8d7fa", height=9,
            font=("Consolas", 9), wrap="none")
        self.txt_dyn.pack(fill="x", padx=6, pady=(6, 3))
        self.dyn_plot_frame = tk.Frame(self.tab_dyn, bg=PANEL)
        self.dyn_plot_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.nb.add(self.tab_dyn, text="Dynamic result")

        # Guidance tab
        self.tab_guide = tk.Frame(self.nb, bg=PANEL)
        gc = tk.Canvas(self.tab_guide, bg=PANEL, highlightthickness=0)
        gsb = ttk.Scrollbar(self.tab_guide, orient="vertical", command=gc.yview)
        self.guide_frame = tk.Frame(gc, bg=PANEL)
        self.guide_frame.bind("<Configure>",
                              lambda e: gc.configure(scrollregion=gc.bbox("all")))
        gc.create_window((0, 0), window=self.guide_frame, anchor="nw", width=880)
        gc.configure(yscrollcommand=gsb.set)
        gc.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        gsb.pack(side="right", fill="y")
        self.nb.add(self.tab_guide, text="Guidance")

        # Sensitivity tab
        self.tab_sens = tk.Frame(self.nb, bg=PANEL)
        top = tk.Frame(self.tab_sens, bg=PANEL); top.pack(fill="x", padx=6, pady=6)
        tk.Label(top, text="Study:", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 10)).pack(side="left")
        self.sens_choice = ttk.Combobox(top, values=list(SENS_STUDIES),
                                         state="readonly", width=32)
        self.sens_choice.current(0)
        self.sens_choice.pack(side="left", padx=6)
        tk.Button(top, text="Generate", command=self.run_sensitivity,
                  bg="#0077b6", fg=TEXT, relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=10, pady=3,
                  cursor="hand2").pack(side="left", padx=6)
        self.sens_plot_frame = tk.Frame(self.tab_sens, bg=PANEL)
        self.sens_plot_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.nb.add(self.tab_sens, text="Sensitivity")

        # Reactor schematic tab
        self.tab_schem = tk.Frame(self.nb, bg=PANEL)
        self.schem_frame = tk.Frame(self.tab_schem, bg=PANEL)
        self.schem_frame.pack(fill="both", expand=True, padx=6, pady=6)
        self.nb.add(self.tab_schem, text="Reactor schematic")

        # Event log tab
        self.tab_events = tk.Frame(self.nb, bg=PANEL)
        cols = ("time", "phase", "event", "detail")
        self.event_tree = ttk.Treeview(self.tab_events, columns=cols,
                                       show="headings", height=22)
        for c, w in (("time", 70), ("phase", 150), ("event", 260), ("detail", 430)):
            self.event_tree.heading(c, text=c.title())
            self.event_tree.column(c, width=w, anchor="w")
        evsb = ttk.Scrollbar(self.tab_events, orient="vertical",
                             command=self.event_tree.yview)
        self.event_tree.configure(yscrollcommand=evsb.set)
        self.event_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        evsb.pack(side="right", fill="y")
        self.nb.add(self.tab_events, text="Event log")

    # --------------------------------------------------------------------- #
    def _build_statusbar(self):
        self.status = tk.Label(self.root, text="", bg="#11161d", fg=TEXT,
                               anchor="w", font=("Segoe UI", 9), padx=10, pady=4)
        self.status.pack(fill="x", side="bottom")

    # ===================================================================== #
    #  Helpers                                                               #
    # ===================================================================== #
    @staticmethod
    def _fmt(v):
        if isinstance(v, float):
            return f"{v:g}"
        if isinstance(v, dict):
            return " ".join(f"{k}={val:g}" for k, val in v.items())
        return str(v)

    def set_status(self, msg, level="OK"):
        self.status.configure(text="  " + msg,
                              fg=STATUS_COLOR.get(level, TEXT))

    def _show_help(self, name):
        p = self.reg[name]
        win = tk.Toplevel(self.root); win.title(f"Help — {name}")
        win.configure(bg=PANEL); win.geometry("460x300")
        tk.Label(win, text=name, bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(12, 2))
        rng = ""
        if p.minimum is not None or p.maximum is not None:
            rng = f"   range: {p.minimum} .. {p.maximum} {p.unit}"
        tk.Label(win, text=f"default: {p.default} {p.unit}{rng}", bg=PANEL,
                 fg="#9fb3c8", font=("Segoe UI", 9)).pack(anchor="w", padx=12)
        t = tk.Message(win, text=p.help, bg=PANEL, fg=TEXT, width=430,
                       font=("Segoe UI", 10))
        t.pack(anchor="w", padx=12, pady=10)

    def _coerce(self, raw, template):
        try:
            if isinstance(template, bool):
                return raw.strip().lower() in ("1", "true", "yes", "y")
            if isinstance(template, int) and not isinstance(template, bool):
                return int(float(raw))
            if isinstance(template, float):
                return float(raw)
            if isinstance(template, dict):
                out = dict(template)
                for pair in raw.replace(",", " ").split():
                    if "=" in pair or ":" in pair:
                        sep = "=" if "=" in pair else ":"
                        k, v = pair.split(sep)
                        out[k.strip()] = float(v)
                return out
            return raw
        except Exception:
            return None

    # ===================================================================== #
    #  Actions                                                               #
    # ===================================================================== #
    def apply_changes(self):
        warnings = []
        for name, var in self.entries.items():
            val = self._coerce(var.get(), self.reg[name].value)
            if val is None:
                warnings.append(f"could not parse '{name}'")
                continue
            warnings += self.reg.set(name, val)
        if warnings:
            self.set_status("Applied with warnings: " + " | ".join(warnings), "WATCH")
        else:
            self.set_status("Parameters applied.", "OK")

    def reset_params(self):
        self.reg.reset_all()
        for name, var in self.entries.items():
            var.set(self._fmt(self.reg[name].value))
        self.set_status("Parameters reset to defaults.", "OK")

    def run_static(self):
        self.apply_changes()
        try:
            res = StaticEAFModel(self.reg).solve()
        except Exception as e:
            messagebox.showerror("Static model error", str(e)); return
        self.last_static = res
        self.txt_static.delete("1.0", "end")
        self.txt_static.insert("end", res.summary() + "\n\n" + res.energy_breakdown())
        dg = Diagnostics(self.reg)
        self._render_guidance(dg.from_static(res), "STATIC")
        self.nb.select(self.tab_static)
        self.set_status(f"Static done: {res.steel_mass/1000:.1f} t tapped, "
                        f"{res.electrical_energy_specific:.0f} kWh/t, "
                        f"B2 {res.basicity_B2:.2f}.", "OK")

    def _draw_schematic(self, res):
        """Draw the EAF reactor cross-section with live values."""
        from matplotlib.figure import Figure
        from matplotlib.patches import Polygon, Rectangle, Ellipse
        st = res.final
        fig = Figure(figsize=(9.2, 6.3)); ax = fig.add_subplot(111)
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
        th = 0.15 + st.foam_index * 0.5
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
            f"Tap T : {st.T_lSc-273.15:6.0f} degC",
            f"Carbon: {st.pct['C']:6.3f} %",
            f"B2    : {st.basicity:6.2f}",
            f"FeO   : {st.feo_pct:6.0f} %",
            f"Foam  : {st.foam_index:6.2f}",
            f"Shell : {st.shell_temp_C:6.0f} degC",
            f"Steel : {st.m_lSc/1000:6.1f} t",
            f"Slag  : {st.slag_mass/1000:6.2f} t"])
        ax.text(0.12, 7.8, info, color="#48cae4", fontsize=9, family="monospace",
                va="top", ha="left",
                bbox=dict(boxstyle="round", fc="#16212e", ec="#2c3d4d"))
        ax.text(5, 7.5, "Industry-X EAF  —  "
                + ("endpoint reached" if res.reached_endpoint else "end of run"),
                color="#ffb703", fontsize=12, ha="center", fontweight="bold")
        ax.text(6.8, 6.7, "3x graphite\nelectrodes", color="#9fb3c8", fontsize=8)
        fig.tight_layout()
        self._embed(fig, self.schem_frame, "schem")

    def _populate_events(self, events):
        self.event_tree.delete(*self.event_tree.get_children())
        for e in events:
            self.event_tree.insert("", "end", values=(
                f"{e['t']/60:.1f} min", e["phase"], e["event"], e["detail"]))

    def run_dynamic(self):
        self.apply_changes()
        self.set_status("Running dynamic simulation …", "WATCH")
        self.root.update_idletasks()
        try:
            res = DynamicEAFModel(self.reg).simulate(mode="endpoint")
        except Exception as e:
            messagebox.showerror("Dynamic model error", str(e)); return
        self.last_dynamic = res
        self.txt_dyn.delete("1.0", "end")
        self.txt_dyn.insert("end", res.summary())
        fig = res.figure(figsize=(16, 9))
        self._embed(fig, self.dyn_plot_frame, "dyn")
        self._draw_schematic(res)
        self._populate_events(res.events)
        dg = Diagnostics(self.reg)
        self._render_guidance(dg.from_dynamic(res), "DYNAMIC")
        self.nb.select(self.tab_dyn)
        st = res.final
        self.set_status(
            f"Dynamic done: tap {st.T_lSc-273.15:.0f} degC / C {st.pct['C']:.3f}%, "
            f"{res.tap_to_tap_min:.1f} min, "
            f"{st.E_elec_MJ/3.6/(st.m_lSc/1000):.0f} kWh/t.",
            "OK" if res.reached_endpoint else "ACT")

    def _render_guidance(self, checks, source):
        for w in self.guide_frame.winfo_children():
            w.destroy()
        n_act = sum(c.status == "ACT" for c in checks)
        n_watch = sum(c.status == "WATCH" for c in checks)
        tk.Label(self.guide_frame,
                 text=f"{source} guidance — {n_act} action(s), {n_watch} watch",
                 bg=PANEL, fg=ACCENT, font=("Segoe UI", 11, "bold")
                 ).pack(anchor="w", pady=(4, 8), padx=4)
        for c in checks:
            card = tk.Frame(self.guide_frame, bg=STATUS_COLOR.get(c.status, PANEL))
            card.pack(fill="x", padx=4, pady=3)
            inner = tk.Frame(card, bg="#0e141b")
            inner.pack(fill="x", padx=3, pady=3)
            head = f"[{c.status}]  {c.name}:  {c.value}"
            tk.Label(inner, text=head, bg="#0e141b",
                     fg=STATUS_COLOR.get(c.status, TEXT),
                     font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", padx=8, pady=(4, 0))
            tk.Message(inner, text=c.message, bg="#0e141b", fg=TEXT,
                       width=820, font=("Segoe UI", 9)).pack(fill="x", padx=8)
            if c.recommendation:
                tk.Message(inner, text="→ " + c.recommendation, bg="#0e141b",
                           fg="#9fd0ff", width=820,
                           font=("Segoe UI", 9, "italic")).pack(fill="x", padx=8, pady=(0, 4))
        self.nb.select(self.tab_guide)

    # -- embedding a matplotlib figure ------------------------------------ #
    def _embed(self, fig, frame, which):
        attr = f"_canvas_{which}"
        old = getattr(self, attr, None)
        if old is not None:
            old.get_tk_widget().destroy()
        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        setattr(self, attr, canvas)

    # -- sensitivity (compute in a thread, plot on the main thread) -------- #
    def run_sensitivity(self):
        self.apply_changes()
        label = self.sens_choice.get()
        self.set_status(f"Computing sensitivity study '{label}' …", "WATCH")
        self.root.update_idletasks()
        t = threading.Thread(target=self._sens_worker, args=(label,), daemon=True)
        t.start()

    def _sens_worker(self, label):
        try:
            kind, metric = SENS_STUDIES[label]
            import numpy as np
            data = {"label": label, "kind": kind, "metric": metric}
            if label == "Static: energy vs hot metal":
                x = list(np.linspace(0, 40, 10))
                data["x"] = x; data["xlabel"] = "hot metal charge (t)"
                data["y"] = S.sweep_static("hot_metal_mass", x, ["elec_kwh_t"])["elec_kwh_t"]
                data["ylabel"] = "electrical energy (kWh/t)"
            elif label == "Static: energy vs charge carbon":
                x = list(np.linspace(0, 3000, 10))
                data["x"] = x; data["xlabel"] = "charge carbon (kg)"
                data["y"] = S.sweep_static("charge_carbon", x, ["elec_kwh_t"])["elec_kwh_t"]
                data["ylabel"] = "electrical energy (kWh/t)"
            elif label == "Static: basicity vs lime":
                x = list(np.linspace(500, 4000, 10))
                data["x"] = x; data["xlabel"] = "lime charged (kg)"
                data["y"] = S.sweep_static("lime_charged", x, ["basicity"])["basicity"]
                data["ylabel"] = "slag basicity B2"
            elif label == "Static: tornado (energy)":
                params = ["hot_metal_mass", "charge_carbon", "natural_gas",
                          "lime_charged", "iron_oxidation_fraction",
                          "power_off_time", "target_tap_temperature",
                          "electrical_efficiency", "arc_transfer_efficiency",
                          "post_combustion_ratio"]
                data["rows"], data["base"] = S.tornado("static", params,
                                                       "elec_kwh_t", pct=0.20)
                data["unit"] = "electrical energy (kWh/t)"
            elif label == "Dynamic: tap-to-tap vs power":
                x = list(np.linspace(55, 115, 8))
                data["x"] = x; data["xlabel"] = "transformer power (MW)"
                data["y"] = S.sweep_dynamic("transformer_power", x, ["taptap_min"])["taptap_min"]
                data["ylabel"] = "tap-to-tap (min)"
            elif label == "Dynamic: energy vs oxygen flow":
                x = list(np.linspace(1500, 5000, 8))
                data["x"] = x; data["xlabel"] = "oxygen flow (Nm3/h)"
                data["y"] = S.sweep_dynamic("oxygen_flow_rate", x, ["elec_kwh_t"])["elec_kwh_t"]
                data["ylabel"] = "electrical energy (kWh/t)"
            elif label == "Dynamic: tornado (energy)":
                params = ["transformer_power", "oxygen_flow_rate",
                          "injected_carbon", "arc_transfer_efficiency",
                          "electrical_efficiency", "panel_heat_loss",
                          "power_off_time", "scrap_melt_htc",
                          "post_combustion_ratio"]
                data["rows"], data["base"] = S.tornado("dynamic", params,
                                                       "elec_kwh_t", pct=0.20)
                data["unit"] = "electrical energy (kWh/t)"
            self.task_q.put(("sens", data))
        except Exception as e:
            self.task_q.put(("error", str(e)))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.task_q.get_nowait()
                if kind == "sens":
                    self._plot_sensitivity(payload)
                elif kind == "error":
                    messagebox.showerror("Sensitivity error", payload)
                    self.set_status("Sensitivity failed.", "ACT")
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _plot_sensitivity(self, d):
        fig = Figure(figsize=(9.6, 5.6))
        ax = fig.add_subplot(111)
        if d["metric"] == "tornado":
            rows, base = d["rows"], d["base"]
            names = [r[0] for r in rows][::-1]
            for i, r in enumerate(rows[::-1]):
                left, right = sorted([r[1], r[2]])
                ax.barh(i, right - left, left=left, color="#4C78A8",
                        edgecolor="k", alpha=0.85)
            ax.axvline(base, color="crimson", lw=2, label=f"baseline={base:.1f}")
            ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=8)
            ax.set_xlabel(d["unit"]); ax.legend(fontsize=8)
            ax.set_title(d["label"])
        else:
            ax.plot(d["x"], d["y"], "o-", color=ACCENT)
            ax.set_xlabel(d["xlabel"]); ax.set_ylabel(d["ylabel"])
            ax.set_title(d["label"])
        ax.grid(alpha=0.3)
        fig.tight_layout()
        self._embed(fig, self.sens_plot_frame, "sens")
        self.nb.select(self.tab_sens)
        self.set_status(f"Sensitivity study '{d['label']}' ready.", "OK")

    # ------------------------------------------------------------------ #
    def save_params(self):
        fn = filedialog.asksaveasfilename(defaultextension=".json",
                                          initialfile="eaf_parameters.json")
        if not fn:
            return
        self.apply_changes()
        with open(fn, "w") as f:
            json.dump(self.reg.to_dict(), f, indent=2)
        self.set_status(f"Saved parameters to {fn}", "OK")

    def load_params(self):
        fn = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not fn:
            return
        with open(fn) as f:
            data = json.load(f)
        self.reg.update(**{k: v for k, v in data.items() if k in self.reg})
        for name, var in self.entries.items():
            var.set(self._fmt(self.reg[name].value))
        self.set_status(f"Loaded parameters from {fn}", "OK")


def main():
    root = tk.Tk()
    EAFDeskApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
