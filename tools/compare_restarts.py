#!/usr/bin/env python3
"""Compare common numeric variables in two MOM6 or CMEPS restart files."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument(
        "--ignore",
        nargs="*",
        default=(),
        help="variables to exclude, for example absolute-time diagnostic accumulators",
    )
    parser.add_argument("--rtol", type=float, default=0.0)
    parser.add_argument("--atol", type=float, default=0.0)
    args = parser.parse_args()

    ignored = set(args.ignore)
    failed = False
    compared = 0
    with (
        xr.open_dataset(args.reference, decode_times=False, decode_timedelta=False)
        as reference,
        xr.open_dataset(args.candidate, decode_times=False, decode_timedelta=False)
        as candidate,
    ):
        common = sorted(
            (set(reference.data_vars) & set(candidate.data_vars)) - ignored
        )
        for name in common:
            reference_values = np.asarray(reference[name].values)
            candidate_values = np.asarray(candidate[name].values)
            if not (
                np.issubdtype(reference_values.dtype, np.number)
                and np.issubdtype(candidate_values.dtype, np.number)
            ):
                continue

            compared += 1
            if reference_values.shape != candidate_values.shape:
                print(
                    f"FAIL {name}: shapes differ "
                    f"{reference_values.shape} != {candidate_values.shape}"
                )
                failed = True
                continue

            reference_finite = np.isfinite(reference_values)
            candidate_finite = np.isfinite(candidate_values)
            if not np.array_equal(reference_finite, candidate_finite):
                print(f"FAIL {name}: finite masks differ")
                failed = True
                continue

            valid = reference_finite
            difference = np.abs(candidate_values[valid] - reference_values[valid])
            matches = np.allclose(
                candidate_values[valid],
                reference_values[valid],
                rtol=args.rtol,
                atol=args.atol,
            )
            max_absolute = float(np.max(difference)) if difference.size else 0.0
            print(
                f"{'PASS' if matches else 'FAIL'} {name}: "
                f"max_abs={max_absolute:.6e}"
            )
            failed = failed or not matches

    print(f"{'PASS' if not failed else 'FAIL'}: compared {compared} numeric variables")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
