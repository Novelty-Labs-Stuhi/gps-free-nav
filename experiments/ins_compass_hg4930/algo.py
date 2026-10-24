"""ins_compass on real hardware: Honeywell HG4930 CA + PNI RM3100 (benchmark/hardware/hg4930.json)."""
from gpsfree.evaluate import load_algorithm


class Navigator(load_algorithm("ins_compass")):
    hardware = "hg4930"
