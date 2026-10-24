"""X3 terrain_pf_beams: the particle filter of X1 with a beam likelihood LEARNED from training runs.

Instead of a hand-set Gaussian clipped at 3 sigma, each beam's vertical residual r is scored with the mixture fitted
in train.py: mostly ordinary noise around mu (sigma), plus a one-sided tail for beams that stop early on trees and
roofs the map does not contain. A short beam is then cheap evidence; a long beam stays strong evidence."""
import json
from pathlib import Path

import numpy as np

from gpsfree.evaluate import load_algorithm

MODEL = json.loads((Path(__file__).parent / "beam_model.json").read_text())["global"]


class Navigator(load_algorithm("terrain_pf")):
    CALIBRATION = Path(__file__).parent.parent / "terrain_pf" / "calibration.json"

    def _loglik(self, r):
        m = MODEL
        n = (1 - m["pi"]) * np.exp(-0.5 * ((r - m["mu"]) / m["sigma"]) ** 2) / (np.sqrt(2 * np.pi) * m["sigma"])
        t = np.where(r > 0, m["pi"] * m["lam"] * np.exp(-m["lam"] * np.maximum(r, 0)), 0.0)
        return np.log(n + t + 1e-12).sum(1)
