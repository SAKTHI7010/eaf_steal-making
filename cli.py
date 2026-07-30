"""
cli.py
======
A lightweight, menu-driven console interface so an operator can drive the model
without writing Python:

    * list operating / technical parameters,
    * read the built-in help ("help file") for any parameter,
    * change a parameter (with range checking),
    * run the STATIC balance and see the energy/mass summary + guidance,
    * run the DYNAMIC simulation and see the heat summary + guidance (and
      optionally save a plot),
    * save / load a parameter set to a JSON file (recipe / practice).

Run it with:
    python -m eaf_control_model.cli
"""

from __future__ import annotations

import json
import sys

from parameters import default_parameters
from static_model import StaticEAFModel
from dynamic_model import DynamicEAFModel
from diagnostics import Diagnostics


BANNER = r"""
   ______      ___    ______   ______            __             __
  / ____/     /   |  / ____/  / ____/___  ____  / /__________  / /
 / __/       / /| | / /_     / /   / __ \/ __ \/ __/ ___/ __ \/ /
/ /___      / ___ |/ __/    / /___/ /_/ / / / / /_/ /  / /_/ / /
\____/     /_/  |_/_/       \____/\____/_/ /_/\__/_/   \____/_/

   Electric Arc Furnace  --  Static & Dynamic Control Model
        static + dynamic + operator guidance (decision support)
"""

MENU = """
 ------------------------------------------------------------------
  1) List OPERATING parameters
  2) List TECHNICAL parameters
  3) Show HELP for a parameter
  4) CHANGE a parameter value
  5) Run STATIC model  (mass & energy balance + guidance)
  6) Run DYNAMIC model (time-resolved heat + guidance)
  7) Show energy BREAKDOWN (last static run)
  8) SAVE parameters to file        9) LOAD parameters from file
  R) RESET all parameters to defaults
  Q) Quit
 ------------------------------------------------------------------
"""


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "Q"


def run():
    reg = default_parameters()
    last_static = None
    print(BANNER)
    print("Type the number/letter of an action and press Enter.")

    while True:
        print(MENU)
        choice = _ask(" > ").lower()

        if choice in ("q", "quit", "exit"):
            print("Goodbye.")
            return

        elif choice == "1":
            reg.list("operating")

        elif choice == "2":
            reg.list("technical")

        elif choice == "3":
            name = _ask(" parameter name: ")
            if name in reg:
                reg.help(name)
            else:
                print(f"  Unknown parameter '{name}'. Use option 1/2 to list names.")

        elif choice == "4":
            name = _ask(" parameter name: ")
            if name not in reg:
                print(f"  Unknown parameter '{name}'.")
                continue
            cur = reg[name]
            print(f"  current: {cur.value} {cur.unit}  ({cur.summary})")
            raw = _ask(f"  new value for '{name}': ")
            val = _coerce(raw, cur.value)
            if val is None:
                print("  Could not parse the value; unchanged.")
                continue
            warn = reg.set(name, val)
            print(f"  set {name} = {val} {cur.unit}")
            for w in warn:
                print("  ! " + w)

        elif choice == "5":
            size = _ask(" size lime to target basicity? (y/N): ").lower() == "y"
            last_static = StaticEAFModel(reg).solve(size_lime_to_target=size)
            print(last_static.summary())
            dg = Diagnostics(reg)
            print(dg.render(dg.from_static(last_static)))

        elif choice == "6":
            mode = _ask(" mode - (e)ndpoint or (f)ixed power-on [e]: ").lower()
            mode = "fixed" if mode.startswith("f") else "endpoint"
            print(" running simulation ...")
            res = DynamicEAFModel(reg).simulate(mode=mode)
            print(res.summary())
            dg = Diagnostics(reg)
            print(dg.render(dg.from_dynamic(res)))
            if _ask(" save plot to eaf_heat.png? (y/N): ").lower() == "y":
                try:
                    p = res.plot("eaf_heat.png")
                    print(f"  plot saved to {p}")
                except Exception as e:
                    print(f"  could not plot ({e}). Is matplotlib installed?")

        elif choice == "7":
            if last_static is None:
                print("  Run the static model first (option 5).")
            else:
                print(last_static.energy_breakdown())

        elif choice == "8":
            fn = _ask(" filename [eaf_parameters.json]: ") or "eaf_parameters.json"
            with open(fn, "w") as f:
                json.dump(reg.to_dict(), f, indent=2)
            print(f"  saved to {fn}")

        elif choice == "9":
            fn = _ask(" filename [eaf_parameters.json]: ") or "eaf_parameters.json"
            try:
                with open(fn) as f:
                    data = json.load(f)
                w = reg.update(**{k: v for k, v in data.items() if k in reg})
                print(f"  loaded {len(data)} values from {fn}")
                for name, warns in w.items():
                    for msg in warns:
                        print("  ! " + msg)
            except FileNotFoundError:
                print(f"  file not found: {fn}")

        elif choice == "r":
            reg.reset_all()
            print("  all parameters reset to defaults.")

        else:
            print("  Unrecognised choice.")


def _coerce(raw: str, template):
    """Parse user text into the same type as the current value."""
    try:
        if isinstance(template, bool):
            return raw.lower() in ("1", "true", "yes", "y")
        if isinstance(template, int) and not isinstance(template, bool):
            return int(float(raw))
        if isinstance(template, float):
            return float(raw)
        if isinstance(template, dict):
            # accept a=1.0,b=2.0 style or JSON
            raw = raw.strip()
            if raw.startswith("{"):
                return json.loads(raw)
            out = dict(template)
            for pair in raw.split(","):
                if ":" in pair or "=" in pair:
                    sep = ":" if ":" in pair else "="
                    k, v = pair.split(sep)
                    out[k.strip()] = float(v)
            return out
        return raw
    except Exception:
        return None


if __name__ == "__main__":
    run()
