"""imu_deadreckoning on real hardware: Analog Devices ADIS16470 + PNI RM3100 (benchmark/hardware/adis16470.json)."""
from gpsfree.evaluate import load_algorithm


class Navigator(load_algorithm("imu_deadreckoning")):
    hardware = "adis16470"
