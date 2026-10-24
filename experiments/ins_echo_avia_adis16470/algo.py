"""ins_echo on real hardware: ADIS16470 INS + Livox Avia scanning lidar looking down (benchmark/hardware/)."""
from gpsfree.evaluate import load_algorithm


class Navigator(load_algorithm("ins_echo")):
    hardware = ("livox_avia", "adis16470")  # the ADIS16470 replaces the Avia's built-in BMI088
