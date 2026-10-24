"""ins_echo on real hardware: ADIS16470 INS + LightWare GRF-500 single-beam rangefinder looking down
(benchmark/hardware/, benchmark/rangers/). One beam per frame, so matching works like TERCOM: the filter correlates the height
profile flown so far against the map."""
from gpsfree.evaluate import load_algorithm


class Navigator(load_algorithm("ins_echo")):
    hardware = "adis16470"
    ranger = "grf500"
