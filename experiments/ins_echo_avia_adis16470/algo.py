"""ins_echo on real hardware: ADIS16470 INS + Livox Avia scanning lidar looking down (benchmark/hardware/, benchmark/rangers/)."""
from gpsfree.evaluate import load_algorithm


class Navigator(load_algorithm("ins_echo")):
    hardware = "adis16470"
    ranger = "avia"
