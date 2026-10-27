"""Cold start (fresh interpreter: import + first parse) and warm p50/p95 per call.

Run: uv run python benchmarks/latency.py
"""

import json
import platform
import statistics
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

CASES = [json.loads(l)["input"] for l in (Path(__file__).parents[1] / "tests/fixtures/required_examples.jsonl").read_text().splitlines()]
COLD = "import time; t = time.perf_counter(); from quantity_parser import parse_quantity; parse_quantity('two and a half times'); print(time.perf_counter() - t)"


def ms(seconds):
    return f"{seconds * 1000:.2f} ms"


def main(rounds: int = 200, cold_runs: int = 5):
    from quantity_parser import parse_quantity
    from quantity_parser.cardinal import cardinal_value

    cold = [float(subprocess.check_output([sys.executable, "-c", COLD])) for _ in range(cold_runs)]

    def warm(clear_cache: bool):
        samples = []
        for _ in range(rounds):
            for text in CASES:
                if clear_cache:
                    cardinal_value.cache_clear()
                t = time.perf_counter()
                parse_quantity(text)
                samples.append(time.perf_counter() - t)
        q = statistics.quantiles(samples, n=100)
        return q[49], q[94]

    hot, cold_cache = warm(False), warm(True)
    print(f"python {platform.python_version()} | {platform.platform()} | {platform.processor() or platform.machine()}")
    print(f"lark {version('lark')} | text2num {version('text2num')} | {len(CASES)} cases x {rounds} rounds")
    print(f"cold start (import + first parse), median of {cold_runs}: {ms(statistics.median(cold))}")
    print(f"warm, adapter cache hot:   p50 {ms(hot[0])}  p95 {ms(hot[1])}")
    print(f"warm, adapter cache clear: p50 {ms(cold_cache[0])}  p95 {ms(cold_cache[1])}")


if __name__ == "__main__":
    main()
