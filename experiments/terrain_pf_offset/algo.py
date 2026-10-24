"""X2 terrain_pf_offset: the particle filter of X1 plus one shared local map-height offset.

Free elevation maps are wrong by metres, but smoothly: over a few hundred metres the whole map tends to be off by
about the same amount. Each frame the offset moves towards the particle-weighted median vertical residual, so the
beams match the SHAPE of the terrain instead of its absolute height."""
from gpsfree.evaluate import load_algorithm


class Navigator(load_algorithm("terrain_pf")):
    MAP_OFFSET = True
