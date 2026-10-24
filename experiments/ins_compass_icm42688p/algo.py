"""ins_compass on real hardware: TDK InvenSense ICM-42688-P + PNI RM3100 (benchmark/hardware/icm42688p.json)."""
from gpsfree.evaluate import load_algorithm


class Navigator(load_algorithm("ins_compass")):
    hardware = "icm42688p"
