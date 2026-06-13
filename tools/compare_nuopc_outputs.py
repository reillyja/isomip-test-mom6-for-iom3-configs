#!/usr/bin/env python3
"""Compare selected MOM6 diagnostics between solo and NUOPC runs."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import xarray as xr


DEFAULT_FIELDS = (
    "taux",
    "tauy",
    "ustar",
    "PRCmE",
    "sensible",
    "LwLatSens",
    "p_surf",
    "temp",
    "salt",
    "u",
    "v",
    "e",
)
ZERO_FIELDS = {"taux", "tauy"}


def selected_record(
    field: xr.DataArray,
    elapsed_seconds: float | None,
    start_time: str | None,
    time_tolerance_seconds: float,
) -> xr.DataArray:
    for dimension in ("time", "Time"):
        if dimension in field.dims:
            if elapsed_seconds is None:
                return field.isel({dimension: -1}, drop=True)

            if start_time is None:
                raise ValueError("--elapsed-seconds requires both run start times")

            coordinate = field[dimension]
            sample = coordinate.values.flat[0]
            start = datetime.fromisoformat(start_time)
            if hasattr(sample, "calendar"):
                start = type(sample)(
                    start.year,
                    start.month,
                    start.day,
                    start.hour,
                    start.minute,
                    start.second,
                )
            target = start + timedelta(seconds=elapsed_seconds)
            offsets = np.asarray(
                [abs((value - target).total_seconds()) for value in coordinate.values]
            )
            index = int(np.argmin(offsets))
            if offsets[index] > time_tolerance_seconds:
                raise ValueError(
                    f"{field.name}: no record at elapsed {elapsed_seconds:g} seconds "
                    f"(nearest is {offsets[index]:g} seconds away)"
                )
            return field.isel({dimension: index}, drop=True)
    return field


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--fields", nargs="+", default=DEFAULT_FIELDS)
    parser.add_argument("--rtol", type=float, default=1.0e-5)
    parser.add_argument("--atol", type=float, default=1.0e-8)
    parser.add_argument(
        "--elapsed-seconds",
        type=float,
        help="compare records at this elapsed time instead of the final records",
    )
    parser.add_argument("--reference-start", help="ISO start time of the reference run")
    parser.add_argument("--candidate-start", help="ISO start time of the candidate run")
    parser.add_argument(
        "--time-tolerance-seconds",
        type=float,
        default=0.5,
        help="maximum offset allowed when selecting an elapsed-time record",
    )
    args = parser.parse_args()

    if args.elapsed_seconds is not None and (
        args.reference_start is None or args.candidate_start is None
    ):
        parser.error(
            "--elapsed-seconds requires --reference-start and --candidate-start"
        )

    failed = False
    time_coder = xr.coders.CFDatetimeCoder(use_cftime=True)
    with (
        xr.open_dataset(
            args.reference,
            decode_times=time_coder,
            decode_timedelta=False,
        ) as reference,
        xr.open_dataset(
            args.candidate,
            decode_times=time_coder,
            decode_timedelta=False,
        ) as candidate,
    ):
        for name in args.fields:
            if name not in reference or name not in candidate:
                print(f"SKIP {name}: missing from one or both files")
                continue

            reference_field, candidate_field = xr.align(
                selected_record(
                    reference[name],
                    args.elapsed_seconds,
                    args.reference_start,
                    args.time_tolerance_seconds,
                ),
                selected_record(
                    candidate[name],
                    args.elapsed_seconds,
                    args.candidate_start,
                    args.time_tolerance_seconds,
                ),
                join="exact",
            )
            reference_values = np.asarray(reference_field.values)
            candidate_values = np.asarray(candidate_field.values)
            reference_finite = np.isfinite(reference_values)
            candidate_finite = np.isfinite(candidate_values)
            if not np.array_equal(reference_finite, candidate_finite):
                mismatch_count = int(
                    np.count_nonzero(reference_finite != candidate_finite)
                )
                print(
                    f"FAIL {name}: finite mask differs at {mismatch_count} points"
                )
                failed = True
                continue

            valid = reference_finite
            reference_valid = reference_values[valid]
            candidate_valid = candidate_values[valid]
            difference = np.abs(candidate_valid - reference_valid)
            field_atol = 1.0 if name == "p_surf" else args.atol
            matches = np.allclose(
                candidate_valid,
                reference_valid,
                rtol=args.rtol,
                atol=field_atol,
            )
            if name in ZERO_FIELDS and np.any(candidate_valid != 0.0):
                matches = False

            scale = np.maximum(np.abs(reference_valid), field_atol)
            max_relative = float(np.max(difference / scale)) if difference.size else 0.0
            max_absolute = float(np.max(difference)) if difference.size else 0.0
            print(
                f"{'PASS' if matches else 'FAIL'} {name}: "
                f"valid={int(np.count_nonzero(valid))} "
                f"max_abs={max_absolute:.6e} max_rel={max_relative:.6e}"
            )
            failed = failed or not matches

    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
