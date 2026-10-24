"""ins_compass on real hardware: Bosch BMI088 + PNI RM3100 (benchmark/hardware/bmi088.json)."""
from gpsfree.evaluate import load_algorithm


class Navigator(load_algorithm("ins_compass")):
    hardware = "bmi088"
