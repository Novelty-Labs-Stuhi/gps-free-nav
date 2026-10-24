from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WORLDS = DATA / "worlds"
RUNS = DATA / "runs"
BENCHMARK = ROOT / "benchmark"
ROUTES = BENCHMARK / "routes"
HARDWARE = BENCHMARK / "hardware"
EXPERIMENTS = ROOT / "experiments"
