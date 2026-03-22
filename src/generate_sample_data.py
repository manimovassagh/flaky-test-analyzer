"""
Generate synthetic TRX files that mimic a 761-test Playwright .NET suite
run 100 times over ~4 days (hourly). Produces realistic flakiness patterns:
  - ~20 tests that are genuinely flaky (5-40% fail rate)
  - ~5 tests that always fail (broken)
  - The rest always pass
Run:  uv run python src/generate_sample_data.py
"""

import random
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

TOTAL_TESTS = 761
TOTAL_RUNS = 100
OUT_DIR = Path("data/sample")

# Flakiness profiles: (test_index, fail_probability)
FLAKY = {i: random.uniform(0.05, 0.40) for i in random.sample(range(TOTAL_TESTS), 20)}
BROKEN = {i: 1.0 for i in random.sample([x for x in range(TOTAL_TESTS) if x not in FLAKY], 5)}

NS = "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"
ET.register_namespace("", NS)

def _tag(name: str) -> str:
    return f"{{{NS}}}{name}"


def make_test_names(n: int) -> list[tuple[str, str]]:
    pages = ["HomePage", "LoginPage", "CheckoutPage", "SearchPage", "ProductPage",
             "CartPage", "AccountPage", "OrderPage", "ProfilePage", "ContactPage"]
    actions = ["Load", "Submit", "Navigate", "Click", "Fill", "Validate",
               "Verify", "Assert", "Check", "Confirm"]
    scenarios = ["HappyPath", "WithError", "WithRetry", "OnMobile", "OnDesktop",
                 "WithAuth", "Anonymous", "Slow", "Fast", "WithNetwork"]
    names = []
    for i in range(n):
        page = pages[i % len(pages)]
        action = actions[(i // len(pages)) % len(actions)]
        scenario = scenarios[(i // (len(pages) * len(actions))) % len(scenarios)]
        test_name = f"{page}_{action}_{scenario}_{i:04d}"
        full_name = f"Tests.{page}.{test_name}"
        names.append((test_name, full_name))
    return names


def build_trx(run_index: int, run_time: datetime, test_names: list[tuple[str, str]]) -> ET.Element:
    root = ET.Element(_tag("TestRun"))
    root.set("id", f"run-{run_index:04d}")
    root.set("name", f"Run {run_index}")
    root.set("start", run_time.isoformat())

    results_el = ET.SubElement(root, _tag("Results"))
    counters = {"total": 0, "passed": 0, "failed": 0}

    for i, (test_name, full_name) in enumerate(test_names):
        fail_p = BROKEN.get(i, FLAKY.get(i, 0.0))
        outcome = "Failed" if random.random() < fail_p else "Passed"

        duration_s = random.uniform(0.5, 8.0)
        if outcome == "Failed":
            duration_s *= random.uniform(1.5, 3.0)  # failures tend to be slower
        duration_str = str(timedelta(seconds=duration_s))

        ur = ET.SubElement(results_el, _tag("UnitTestResult"))
        ur.set("testName", test_name)
        ur.set("outcome", outcome)
        ur.set("duration", duration_str)
        ur.set("startTime", run_time.isoformat())

        if outcome == "Failed":
            output_el = ET.SubElement(ur, _tag("Output"))
            err_el = ET.SubElement(output_el, _tag("ErrorInfo"))
            msg_el = ET.SubElement(err_el, _tag("Message"))
            msg_el.text = f"Playwright assertion failed: Expected element to be visible"
            st_el = ET.SubElement(err_el, _tag("StackTrace"))
            st_el.text = (
                f"   at Tests.{test_name}() in /tests/{test_name}.cs:line {random.randint(10, 200)}\n"
                f"   at Microsoft.Playwright.Core.Page.WaitForSelectorAsync()\n"
            )

        counters["total"] += 1
        counters[f"{'passed' if outcome == 'Passed' else 'failed'}"] += 1

    counters_el = ET.SubElement(root, _tag("ResultSummary"))
    counters_el.set("outcome", "Failed" if counters["failed"] > 0 else "Passed")
    c_el = ET.SubElement(counters_el, _tag("Counters"))
    for k, v in counters.items():
        c_el.set(k, str(v))

    return root


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    test_names = make_test_names(TOTAL_TESTS)

    start = datetime(2026, 3, 18, 0, 0, 0)
    for i in range(TOTAL_RUNS):
        run_time = start + timedelta(hours=i)
        root = build_trx(i, run_time, test_names)
        tree = ET.ElementTree(root)
        out_path = OUT_DIR / f"run_{i:04d}.trx"
        tree.write(out_path, encoding="unicode", xml_declaration=True)

    print(f"Generated {TOTAL_RUNS} TRX files in {OUT_DIR}/")
    print(f"  Flaky tests : {len(FLAKY)}")
    print(f"  Broken tests: {len(BROKEN)}")
    print(f"  Healthy     : {TOTAL_TESTS - len(FLAKY) - len(BROKEN)}")


if __name__ == "__main__":
    main()
