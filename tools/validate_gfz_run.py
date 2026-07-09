#!/usr/bin/env python3
"""Validate a GFZ/PIK ISOMIP MOM6-solo payu archive."""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
import re
import sys

import netCDF4
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
SECONDS_PER_DAY = 86400.0
FILL_THRESHOLD = 1.0e30
RHO_ICE = 900.0
GRAVITY = 9.8

PROFILE_DURATIONS = {
    "smoke": (0, 0, 0, 10, 0),
    "half-day": (0, 0, 12, 0, 0),
    "day": (0, 1, 0, 0, 0),
    "month": (1, 0, 0, 0, 0),
    "six-month": (6, 0, 0, 0, 0),
    "45-day": (0, 45, 0, 0, 0),
    "three-month": (3, 0, 0, 0, 0),
    "year": (12, 0, 0, 0, 0),
    "five-year": (60, 0, 0, 0, 0),
    "ten-year": (120, 0, 0, 0, 0),
    "hundred-year": (1200, 0, 0, 0, 0),
}

LOG_BAD_PATTERN = re.compile(r"\b(FATAL|ERROR|NaN|nan|Inf|infinity|reproducing|abort)\b")
LOG_IGNORE_PATTERNS = (
    "OOR_WARNINGS_FATAL",
    "fatal_errors = 0",
)


@dataclass
class CheckResult:
    errors: list[str]
    warnings: list[str]

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def output_number(path: Path) -> int:
    match = re.search(r"(\d+)$", path.name)
    return int(match.group(1)) if match else -1


def select_output(archive: Path, output: str) -> Path:
    if output != "latest":
        path = archive / output
        if not path.is_dir():
            raise RuntimeError(f"Output directory does not exist: {path}")
        return path
    outputs = sorted(archive.glob("output[0-9][0-9][0-9]"), key=output_number)
    if not outputs:
        raise RuntimeError(f"No outputNNN directories found in {archive}")
    return outputs[-1]


def parse_timestamp(path: Path) -> tuple[int, int, int, int, int, int]:
    lines = [line.split() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 2:
        raise RuntimeError(f"Expected at least two timestamp lines in {path}")
    vals = tuple(int(value) for value in lines[-1][:6])
    return vals  # type: ignore[return-value]


def add_profile_duration(profile: str) -> tuple[int, int, int, int, int, int]:
    months, days, hours, minutes, seconds = PROFILE_DURATIONS[profile]
    year, month, day = 1, 1, 1
    total_months = (month - 1) + months
    year += total_months // 12
    month = (total_months % 12) + 1

    # All tested durations start on Jan 1 and either add whole months or a
    # small number of days. This is enough for the profiles used here.
    noleap_days_in_month = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    day += days
    while day > noleap_days_in_month[month - 1]:
        day -= noleap_days_in_month[month - 1]
        month += 1
        if month > 12:
            month = 1
            year += 1

    total_seconds = hours * 3600 + minutes * 60 + seconds
    hour = total_seconds // 3600
    minute = (total_seconds % 3600) // 60
    second = total_seconds % 60
    return year, month, day, hour, minute, second


def read_valid(var: netCDF4.Variable) -> tuple[np.ndarray, np.ndarray]:
    data = var[:]
    arr = np.asarray(data.filled(np.nan) if np.ma.isMaskedArray(data) else data)
    valid = np.isfinite(arr) & (np.abs(arr) < FILL_THRESHOLD)
    return arr, valid


def scan_logs(output_dir: Path, archive: Path, result: CheckResult, scan_archive_logs: bool) -> None:
    files = list(output_dir.glob("*.out")) + list(output_dir.glob("*.err")) + [output_dir / "ocean.stats"]
    if scan_archive_logs:
        for extra_dir in (archive / "error_logs", archive / "pbs_logs"):
            if extra_dir.is_dir():
                files.extend(extra_dir.glob("*.out"))
                files.extend(extra_dir.glob("*.err"))

    for path in sorted(set(files)):
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(pattern in line for pattern in LOG_IGNORE_PATTERNS):
                continue
            if LOG_BAD_PATTERN.search(line):
                result.errors.append(f"Bad log token in {path}:{lineno}: {line[:180]}")


def check_ocean_stats(output_dir: Path, result: CheckResult, max_cfl: float) -> None:
    stats = output_dir / "ocean.stats"
    result.require(stats.exists(), f"Missing {stats}")
    if not stats.exists():
        return

    truncs: list[int] = []
    cfls: list[float] = []
    for line in stats.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\s*\d+,", line):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            truncs.append(int(parts[2]))
        match = re.search(r"CFL\s+([0-9.Ee+-]+)", line)
        if match:
            cfls.append(float(match.group(1)))

    result.require(bool(truncs), "No step rows found in ocean.stats")
    result.require(all(value == 0 for value in truncs), f"Non-zero truncations in ocean.stats: {truncs}")
    if cfls:
        result.require(max(cfls) < max_cfl, f"Max CFL {max(cfls):.6g} exceeds threshold {max_cfl}")


def initial_mass(case: str) -> np.ndarray:
    return RHO_ICE * initial_thick(case)


def initial_thick(case: str) -> np.ndarray:
    with netCDF4.Dataset(REPO_ROOT / "INPUT" / "gfz_geometry" / f"{case.capitalize()}_2km_initial.nc") as ds:
        return np.asarray(ds.variables["thick"][:], dtype=np.float64)


def initial_area(case: str) -> np.ndarray:
    with netCDF4.Dataset(REPO_ROOT / "INPUT" / "gfz_geometry" / f"{case.capitalize()}_2km_initial.nc") as ds:
        return np.asarray(ds.variables["area"][:], dtype=np.float64)


def shelf_file(case: str, mode: str) -> Path:
    case_name = case.capitalize()
    suffix = {
        "noop": "shelf_mass_noop",
        "dynamic": "shelf_mass",
        "geometry-noop": "geometry_noop",
        "geometry": "geometry",
    }[mode]
    return REPO_ROOT / "INPUT" / "gfz_geometry" / f"{case_name}_2km_{suffix}.nc"


def expected_field(case: str, mode: str, field: str, time_days: float) -> np.ndarray:
    if mode == "static":
        if field == "shelf_mass":
            return initial_mass(case)
        if field == "h_shelf":
            return initial_thick(case)
        if field == "area_shelf_h":
            return initial_area(case)
        raise RuntimeError(f"Unsupported static field {field}")

    path = shelf_file(case, mode)
    with netCDF4.Dataset(path) as ds:
        time_name = "Time" if "Time" in ds.variables else "time"
        times = np.asarray(ds.variables[time_name][:], dtype=np.float64)
        if field == "h_shelf":
            source_name = "thick"
            scale = 1.0
        elif field == "area_shelf_h":
            source_name = "floating_fraction"
            scale = 4.0e6
        else:
            source_name = field
            scale = 1.0
        values = np.asarray(ds.variables[source_name][:], dtype=np.float64) * scale

    target = time_days * SECONDS_PER_DAY
    if target <= times[0]:
        return values[0]
    if target >= times[-1]:
        return values[-1]
    upper = int(np.searchsorted(times, target, side="right"))
    lower = upper - 1
    weight = (target - times[lower]) / (times[upper] - times[lower])
    return (1.0 - weight) * values[lower] + weight * values[upper]


def expected_mass(case: str, mode: str, time_days: float) -> np.ndarray:
    return expected_field(case, mode, "shelf_mass", time_days)


def compare_array(
    name: str,
    actual: np.ndarray,
    valid: np.ndarray,
    expected: np.ndarray,
    result: CheckResult,
    rtol: float,
    atol: float,
) -> None:
    result.require(actual.shape[-2:] == expected.shape, f"{name} shape {actual.shape} incompatible with {expected.shape}")
    if actual.shape[-2:] != expected.shape:
        return
    if not valid.any():
        result.warn(f"{name} has no non-fill values")
        return
    actual_values = actual[valid]
    expected_values = expected[valid[-expected.shape[0] :, -expected.shape[1] :] if valid.ndim == 2 else valid]
    close = np.allclose(actual_values, expected_values, rtol=rtol, atol=atol)
    if not close:
        diff = np.abs(actual_values - expected_values)
        result.errors.append(f"{name} differs from expected: max abs diff {diff.max():.6g}")


def check_diagnostics(
    output_dir: Path,
    case: str,
    mode: str,
    duration: str,
    result: CheckResult,
    rtol: float,
    atol: float,
) -> None:
    require_values = duration != "smoke"

    forcing_path = output_dir / "forcing.nc"
    ice_path = output_dir / "ice.nc"
    shelf_ic_path = output_dir / "MOM_Shelf_IC.nc"
    for path in (forcing_path, ice_path):
        result.require(path.exists(), f"Missing diagnostic file {path}")

    if forcing_path.exists():
        with netCDF4.Dataset(forcing_path) as ds:
            for name in ("taux", "tauy"):
                if name not in ds.variables:
                    result.errors.append(f"Missing forcing variable {name}")
                    continue
                arr, valid = read_valid(ds.variables[name])
                if valid.any():
                    result.require(np.allclose(arr[valid], 0.0, rtol=0.0, atol=0.0), f"{name} is not exactly zero")
                elif require_values:
                    result.errors.append(f"{name} has no non-fill values")
                else:
                    result.warn(f"{name} all-fill in short run")

    shelf_mass_checked = False
    if ice_path.exists():
        with netCDF4.Dataset(ice_path) as ds:
            times = np.asarray(ds.variables.get("Time")[:], dtype=np.float64) if "Time" in ds.variables else np.array([])
            for name in ("shelf_mass", "h_shelf", "area_shelf_h", "melt_rate", "ustar_shelf"):
                if name not in ds.variables:
                    result.errors.append(f"Missing ice variable {name}")
                    continue
                arr, valid = read_valid(ds.variables[name])
                if valid.any():
                    result.require(np.isfinite(arr[valid]).all(), f"{name} contains non-finite valid values")
                elif require_values:
                    result.errors.append(f"{name} has no non-fill values")
                else:
                    result.warn(f"{name} all-fill in short run")

            if times.size:
                for name in ("shelf_mass", "h_shelf", "area_shelf_h"):
                    if name not in ds.variables:
                        continue
                    if name == "area_shelf_h" and mode not in {"static", "geometry-noop", "geometry"}:
                        continue
                    arr, arr_valid = read_valid(ds.variables[name])
                    if not arr_valid.any():
                        continue
                    for idx, time_days in enumerate(times):
                        expected = expected_field(case, mode, name, float(time_days))
                        compare_array(
                            f"ice.nc:{name}[{idx}]",
                            arr[idx],
                            arr_valid[idx],
                            expected,
                            result,
                            rtol=rtol,
                            atol=atol,
                        )
                    if name == "shelf_mass":
                        shelf_mass_checked = True

                if mode in {"geometry-noop", "geometry"} and "dynamic_cavity_category" in ds.variables:
                    category, category_valid = read_valid(ds.variables["dynamic_cavity_category"])
                    bad = category_valid & ((category == 5.0) | (category == 6.0))
                    result.require(not bad.any(), "dynamic_cavity_category contains outside-envelope or would-dry cells")

    if not shelf_mass_checked and shelf_ic_path.exists():
        with netCDF4.Dataset(shelf_ic_path) as ds:
            mass, valid = read_valid(ds.variables["shelf_mass"])
            expected = expected_mass(case, mode, 0.0)
            compare_array("MOM_Shelf_IC.nc:shelf_mass", mass[0], valid[0], expected, result, rtol=rtol, atol=atol)
            shelf_mass_checked = True

    result.require(shelf_mass_checked, "Could not validate shelf_mass against prescribed geometry")

    if forcing_path.exists() and ice_path.exists():
        with netCDF4.Dataset(forcing_path) as forcing, netCDF4.Dataset(ice_path) as ice:
            if "p_surf" in forcing.variables and "shelf_mass" in ice.variables:
                p_surf, p_valid = read_valid(forcing.variables["p_surf"])
                mass, m_valid = read_valid(ice.variables["shelf_mass"])
                ntime = min(p_surf.shape[0], mass.shape[0])
                for idx in range(ntime):
                    valid = p_valid[idx] & m_valid[idx]
                    if valid.any():
                        diff = np.abs(p_surf[idx][valid] - GRAVITY * mass[idx][valid])
                        result.require(diff.max() <= 1.0, f"p_surf != shelf_mass*g at record {idx}: max diff {diff.max():.6g} Pa")
                    elif require_values:
                        result.errors.append("No common valid p_surf/shelf_mass values")


def compare_reference(
    archive: Path,
    reference_archive: Path,
    output_dir: Path,
    result: CheckResult,
    rtol: float,
    atol: float,
) -> None:
    ref_output = select_output(reference_archive, "latest")
    variables = {
        "forcing.nc": ("taux", "tauy", "ustar", "PRCmE", "LwLatSens", "p_surf"),
        "ice.nc": ("area_shelf_h", "shelf_mass", "h_shelf", "melt_rate", "ustar_shelf"),
        "ocean.stats.nc": ("Mass", "Salt", "Heat", "max_CFL_trans"),
    }
    for fname, names in variables.items():
        path = output_dir / fname
        ref_path = ref_output / fname
        if not path.exists() or not ref_path.exists():
            result.warn(f"Skipping reference comparison for missing {fname}")
            continue
        with netCDF4.Dataset(path) as ds, netCDF4.Dataset(ref_path) as ref:
            for name in names:
                if name not in ds.variables or name not in ref.variables:
                    continue
                arr, valid = read_valid(ds.variables[name])
                ref_arr, ref_valid = read_valid(ref.variables[name])
                if arr.shape != ref_arr.shape:
                    result.warn(f"Skipping {fname}:{name}; shape {arr.shape} != reference {ref_arr.shape}")
                    continue
                common = valid & ref_valid
                if common.any():
                    if not np.allclose(arr[common], ref_arr[common], rtol=rtol, atol=atol):
                        diff = np.abs(arr[common] - ref_arr[common])
                        result.errors.append(f"{fname}:{name} differs from reference: max abs diff {diff.max():.6g}")


def parse_args() -> object:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--case", choices=("ocean3", "ocean4"), required=True)
    parser.add_argument("--mode", choices=("static", "noop", "dynamic", "geometry-noop", "geometry"), required=True)
    parser.add_argument("--duration", choices=PROFILE_DURATIONS, required=True)
    parser.add_argument("--output", default="latest")
    parser.add_argument("--reference-archive", type=Path)
    parser.add_argument("--scan-archive-logs", action="store_true")
    parser.add_argument("--rtol", type=float, default=1.0e-5)
    parser.add_argument("--atol", type=float, default=1.0e-8)
    parser.add_argument("--max-cfl", type=float, default=0.5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    archive = args.archive
    output_dir = select_output(archive, args.output)
    result = CheckResult(errors=[], warnings=[])

    exitcode = output_dir / "exitcode"
    result.require(exitcode.exists(), f"Missing {exitcode}")
    if exitcode.exists():
        result.require(exitcode.read_text(encoding="utf-8").strip() == "0", f"{exitcode} is not zero")

    timestamp = output_dir / "time_stamp.out"
    result.require(timestamp.exists(), f"Missing {timestamp}")
    if timestamp.exists():
        actual = parse_timestamp(timestamp)
        expected = add_profile_duration(args.duration)
        result.require(actual == expected, f"Final timestamp {actual} != expected {expected}")

    scan_logs(output_dir, archive, result, args.scan_archive_logs)
    check_ocean_stats(output_dir, result, args.max_cfl)
    check_diagnostics(output_dir, args.case, args.mode, args.duration, result, args.rtol, args.atol)

    if args.reference_archive:
        compare_reference(archive, args.reference_archive, output_dir, result, args.rtol, args.atol)

    print(f"Archive: {archive}")
    print(f"Output:  {output_dir.name}")
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    if result.errors:
        print("FAILED:")
        for error in result.errors:
            print(f"  - {error}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
