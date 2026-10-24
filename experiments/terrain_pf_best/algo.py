"""X7 terrain_pf_best: X3 (learned beam model) plus X4's lost detector, retrained on X3's own statistics.

A logistic regression reads the filter's own statistics (particle agreement, spread, outlier share, residual size,
how informative the terrain is, missing returns, fit, time, start uncertainty) and estimates P(lost), the chance
the drone is more than 50 m from where it thinks. Trained on training runs 20-39 only (train.py). Above the
threshold chosen in training the drone reports "I don't know where I am"; below it the radius widens with P(lost)."""
import json
import sys
from pathlib import Path

import numpy as np

from gpsfree.evaluate import load_algorithm

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import features  # noqa: E402

MODEL = HERE / "lost_model.json"


class Navigator(load_algorithm("terrain_pf_beams")):
    CALIBRATION = HERE.parent / "terrain_pf" / "calibration.json"

    def __init__(self, ctx):
        super().__init__(ctx)
        m = json.loads(MODEL.read_text()) if MODEL.exists() else None
        self.model = m
        self.p_lost = 0.0

    def lost_probability(self):
        m = self.model
        if m is None:
            return 0.0
        x = (features.vector(self.diagnostics()) - np.array(m["mean"])) / np.array(m["std"])
        z = float(x @ np.array(m["w"]) + m["b"])
        return 1 / (1 + np.exp(-z))

    def uncertainty(self):
        base = super().uncertainty()
        self.p_lost = self.lost_probability()
        if self.model and self.p_lost > self.model["threshold"]:
            return np.inf
        return base * (1 + 2 * self.p_lost)
