"""ins_echo on the cheapest real hardware: TDK ICM-42688-P INS + LightWare GRF-500 single beam (benchmark/hardware/, benchmark/rangers/).
The consumer gyro's tilt drift corrupts the INS acceleration, so tilt is pulled towards gravity and the particles'
velocity is allowed to wander more."""
from gpsfree.evaluate import load_algorithm


class Navigator(load_algorithm("ins_echo")):
    hardware = "icm42688p"
    ranger = "grf500"
    TILT_TAU_S = 10.0
    Q_V = 1.0
    Q_YAW = 0.01
