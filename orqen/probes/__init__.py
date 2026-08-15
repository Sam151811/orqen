from .base import Probe, ProbeResult
from .calibration import CalibrationProbe
from .fairness import FairnessProbe
from .leakage import LeakageProbe
from .robustness import RobustnessProbe

SUITE: list[Probe] = [
    FairnessProbe(), RobustnessProbe(), CalibrationProbe(), LeakageProbe(),
]

__all__ = ["SUITE", "Probe", "ProbeResult"]
