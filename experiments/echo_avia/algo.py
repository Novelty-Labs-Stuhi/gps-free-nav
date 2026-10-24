"""Livox Avia alone: position from terrain matching only. The Avia's built-in BMI088 gives attitude (gyro, with
tilt pulled towards gravity); its accelerometer is never integrated into position. Particles move at constant
velocity between scans and the scans alone have to find where they are."""
from gpsfree.evaluate import load_algorithm


class Navigator(load_algorithm("ins_echo")):
    hardware = "bmi088"  # the Avia's built-in IMU
    ranger = "avia"
    USE_ACCEL = False
    TILT_TAU_S = 10.0
    Q_V = 1.0
    Q_YAW = 0.01
