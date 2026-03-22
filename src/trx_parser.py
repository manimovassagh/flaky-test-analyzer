"""
Parser for Playwright .NET test results.
Supports TRX (Visual Studio), JUnit XML, and JSON formats.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class TestResult:
    run_id: str
    run_time: datetime
    test_name: str
    full_name: str
    outcome: str          # "Passed", "Failed", "Skipped"
    duration_ms: float
    error_message: str | None = None
    stack_trace: str | None = None


def _parse_duration(duration_str: str | None) -> float:
    """Parse ISO 8601 duration or HH:MM:SS.fff to milliseconds."""
    if not duration_str:
        return 0.0
    try:
        # HH:MM:SS.fffffff (TRX format)
        parts = duration_str.split(":")
        if len(parts) == 3:
            h, m, s = parts
            return (int(h) * 3600 + int(m) * 60 + float(s)) * 1000
    except Exception:
        pass
    return 0.0


def parse_trx(path: Path, run_id: str | None = None) -> list[TestResult]:
    """Parse a .trx file produced by dotnet test."""
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}

    # Determine run time from file name or TestRun attributes
    run_time_str = root.attrib.get("start", None)
    if run_time_str:
        try:
            run_time = datetime.fromisoformat(run_time_str.replace("Z", "+00:00"))
        except Exception:
            run_time = datetime.fromtimestamp(path.stat().st_mtime)
    else:
        run_time = datetime.fromtimestamp(path.stat().st_mtime)

    if run_id is None:
        run_id = path.stem

    results = []
    for unit_result in root.findall(".//t:UnitTestResult", ns):
        outcome = unit_result.attrib.get("outcome", "Unknown")
        test_name = unit_result.attrib.get("testName", "")
        full_name = unit_result.attrib.get("testName", test_name)
        duration_str = unit_result.attrib.get("duration", None)

        error_message = None
        stack_trace = None
        output_el = unit_result.find("t:Output", ns)
        if output_el is not None:
            err_info = output_el.find("t:ErrorInfo", ns)
            if err_info is not None:
                msg_el = err_info.find("t:Message", ns)
                st_el = err_info.find("t:StackTrace", ns)
                error_message = msg_el.text if msg_el is not None else None
                stack_trace = st_el.text if st_el is not None else None

        results.append(TestResult(
            run_id=run_id,
            run_time=run_time,
            test_name=test_name,
            full_name=full_name,
            outcome=outcome,
            duration_ms=_parse_duration(duration_str),
            error_message=error_message,
            stack_trace=stack_trace,
        ))
    return results


def parse_junit_xml(path: Path, run_id: str | None = None) -> list[TestResult]:
    """Parse JUnit XML output (--logger junit)."""
    tree = ET.parse(path)
    root = tree.getroot()

    run_time_str = root.attrib.get("timestamp", None)
    if run_time_str:
        try:
            run_time = datetime.fromisoformat(run_time_str)
        except Exception:
            run_time = datetime.fromtimestamp(path.stat().st_mtime)
    else:
        run_time = datetime.fromtimestamp(path.stat().st_mtime)

    if run_id is None:
        run_id = path.stem

    results = []
    suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
    for suite in suites:
        for tc in suite.findall("testcase"):
            name = tc.attrib.get("name", "")
            classname = tc.attrib.get("classname", "")
            full_name = f"{classname}.{name}" if classname else name
            duration_ms = float(tc.attrib.get("time", 0)) * 1000

            failure = tc.find("failure")
            error = tc.find("error")
            skipped = tc.find("skipped")

            if failure is not None:
                outcome = "Failed"
                error_message = failure.attrib.get("message", failure.text or "")
                stack_trace = failure.text
            elif error is not None:
                outcome = "Failed"
                error_message = error.attrib.get("message", error.text or "")
                stack_trace = error.text
            elif skipped is not None:
                outcome = "Skipped"
                error_message = None
                stack_trace = None
            else:
                outcome = "Passed"
                error_message = None
                stack_trace = None

            results.append(TestResult(
                run_id=run_id,
                run_time=run_time,
                test_name=name,
                full_name=full_name,
                outcome=outcome,
                duration_ms=duration_ms,
                error_message=error_message,
                stack_trace=stack_trace,
            ))
    return results


def load_all(data_dir: Path) -> list[TestResult]:
    """Load all TRX and JUnit XML files from a directory."""
    all_results: list[TestResult] = []
    data_dir = Path(data_dir)

    for path in sorted(data_dir.glob("**/*.trx")):
        all_results.extend(parse_trx(path))

    for path in sorted(data_dir.glob("**/*.xml")):
        try:
            all_results.extend(parse_junit_xml(path))
        except Exception:
            pass  # skip non-JUnit XMLs

    return all_results
