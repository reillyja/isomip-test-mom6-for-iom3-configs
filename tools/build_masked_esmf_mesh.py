#!/usr/bin/env python3
"""Build cavity-masked ESMF mesh files for the ISOMIP NUOPC case.

This keeps the base mesh geometry/connectivity unchanged and only updates
the elementMask so data components do not see ocean cells beneath the shelf.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


def read_ice_mask(ice_path: Path) -> np.ndarray:
    with Dataset(ice_path) as ds:
        thick = np.asarray(ds.variables["thick"][:], dtype=np.float64)
        area = np.asarray(ds.variables["area"][:], dtype=np.float64)
    return (thick > 0.0) & (area > 0.0)


def apply_mask(src_mesh: Path, dst_mesh: Path, cavity_mask: np.ndarray) -> dict[str, int]:
    with Dataset(src_mesh) as src, Dataset(dst_mesh, "w") as dst:
        for name, dim in src.dimensions.items():
            dst.createDimension(name, None if dim.isunlimited() else len(dim))

        for name, var in src.variables.items():
            out = dst.createVariable(name, var.datatype, var.dimensions)
            out.setncatts({attr: var.getncattr(attr) for attr in var.ncattrs()})
            data = var[:]
            if name == "elementMask":
                mask = np.asarray(data).reshape(cavity_mask.shape).copy()
                mask[cavity_mask] = 0
                out[:] = mask.reshape(data.shape)
            else:
                out[:] = data

        dst.setncatts({attr: src.getncattr(attr) for attr in src.ncattrs()})

    total = int(cavity_mask.size)
    masked = int(cavity_mask.sum())
    return {"total_cells": total, "masked_cavity_cells": masked, "open_cells": total - masked}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src-mesh", required=True, type=Path)
    parser.add_argument("--ice-file", required=True, type=Path)
    parser.add_argument("--dst-mesh", required=True, type=Path)
    args = parser.parse_args()

    cavity_mask = read_ice_mask(args.ice_file)
    stats = apply_mask(args.src_mesh, args.dst_mesh, cavity_mask)
    print(
        f"Wrote {args.dst_mesh} with {stats['masked_cavity_cells']} masked cavity cells "
        f"and {stats['open_cells']} open cells."
    )


if __name__ == "__main__":
    main()
