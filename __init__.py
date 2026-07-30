"""
eaf_control_model
=================
A static + dynamic control model for Electric Arc Furnace (EAF) steelmaking,
with a fully documented, modifiable parameter set and an operator-guidance
(decision-support) layer.

Quick start
-----------
>>> from eaf_control_model import (default_parameters, StaticEAFModel,
...                                DynamicEAFModel, Diagnostics)
>>> reg = default_parameters()          # all operating + technical parameters
>>> reg.list("operating")               # see what you can change (with help)
>>> reg.set("oxygen_total", 3600)       # modify a parameter (range-checked)
>>>
>>> static = StaticEAFModel(reg).solve()
>>> print(static.summary())
>>> print(Diagnostics(reg).render(Diagnostics(reg).from_static(static)))
>>>
>>> dyn = DynamicEAFModel(reg).simulate(mode="endpoint")
>>> print(dyn.summary())
>>> dyn.plot("heat.png")

Modelling basis
---------------
* Dynamic model  : control-oriented zone model after Logar, Dovzan & Skrjanc,
                   ISIJ Int. 52 (2012) 402 & 413.
* Static model   : standard EAF mass/energy balance.
* Guidance layer : model-based decision-support concept.
See the module docstrings and the README for details and calibration notes.
"""

from .parameters import (Parameter, ParameterRegistry, default_parameters)
from .static_model import StaticEAFModel, StaticResult
from .dynamic_model import (DynamicEAFModel, DynamicResult, State, Charge,
                            Schedule)
from .diagnostics import Diagnostics, Check, BENCHMARKS
from . import thermodata

__all__ = [
    "Parameter", "ParameterRegistry", "default_parameters",
    "StaticEAFModel", "StaticResult",
    "DynamicEAFModel", "DynamicResult", "State", "Charge", "Schedule",
    "Diagnostics", "Check", "BENCHMARKS",
    "thermodata", "sensitivity",
]

__version__ = "1.0.0"


# ``sensitivity`` and ``gui`` are imported lazily (PEP 562) so that importing
# the package -- e.g. ``python -m eaf_control_model.gui`` -- can never fail on
# them at import time or on a stale cache. They remain accessible on first use,
# e.g. ``from eaf_control_model import sensitivity``.
def __getattr__(name):
    if name in ("sensitivity", "gui"):
        import importlib
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
