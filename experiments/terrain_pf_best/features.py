"""Features the lost detector reads, all computed inside the filter (no ground truth)."""
import numpy as np

NAMES = ["ess", "log_spread", "outliers", "med_res", "info", "noreturn", "log_fit", "t_min", "start_sigma"]


def vector(d):
    return np.array([d["ess"], np.log1p(d["spread"]), d["outliers"], d["med_res"], d["info"], d["noreturn"],
                     np.log1p(d["fit"]), d["t"] / 60.0, d["start_sigma"] / 100.0])
