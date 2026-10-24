import math

import numpy as np

A, E2 = 6378137.0, 6.69437999014e-3


def ecef(lat, lon, h=0.0):
    la, lo = math.radians(lat), math.radians(lon)
    n = A / math.sqrt(1 - E2 * math.sin(la) ** 2)
    return np.array([(n + h) * math.cos(la) * math.cos(lo), (n + h) * math.cos(la) * math.sin(lo), (n * (1 - E2) + h) * math.sin(la)])


def ecef_to_enu_matrix(lat, lon):
    """4x4 affine taking ECEF points to local ENU (origin at lat/lon, h=0)."""
    la, lo = math.radians(lat), math.radians(lon)
    r = np.array([
        [-math.sin(lo), math.cos(lo), 0],
        [-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)],
        [math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)],
    ])
    m = np.eye(4)
    m[:3, :3] = r
    m[:3, 3] = -r @ ecef(lat, lon)
    return m
