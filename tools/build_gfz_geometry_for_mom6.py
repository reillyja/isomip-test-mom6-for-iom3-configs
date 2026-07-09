#!/usr/bin/env python3
"""Build MOM6-ready ISOMIP geometry files from the GFZ/PIK inputs."""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import sys
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import netCDF4
import numpy as np
import yaml

try:
    from yamanifest import hash as yamanifest_hash
except ImportError:  # pragma: no cover - this should be available on Gadi.
    yamanifest_hash = None


DEFAULT_SOURCE_ROOT = Path("/g/data/au88/jr5971/gfz-pik-2016-002/data")
DEFAULT_CASES = ("Ocean3", "Ocean4")
EXPECTED_X0 = 320_500.0
EXPECTED_Y0 = 500.0
SOURCE_DX = 1_000.0
SOURCE_DY = 1_000.0
SOURCE_NX = 480
SOURCE_NY = 80
MOM_NX = 240
MOM_NY = 40
MOM_CELL_AREA = 4.0e6
MOM_DX = 2_000.0
MOM_DY = 2_000.0
DETERMINISTIC_MTIME = 946_684_800  # 2000-01-01T00:00:00Z


@dataclass(frozen=True)
class CaseOutputs:
    initial: Path
    shelf_mass: Path
    noop_shelf_mass: Path
    geometry: Path
    noop_geometry: Path
    plot: Path


def sha256sum(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def check_axis(values: np.ndarray, start: float, step: float, name: str) -> None:
    expected = start + step * np.arange(values.size, dtype=np.float64)
    require(
        np.allclose(values, expected, rtol=0.0, atol=1.0e-9),
        f"{name} axis does not match expected {step:g} m GFZ grid",
    )


def coarsen_2x2(field: np.ndarray) -> np.ndarray:
    """Conservatively average 1 km fields onto the 2 km MOM6 grid."""
    require(field.shape[-2:] == (SOURCE_NY, SOURCE_NX), f"Unexpected field shape {field.shape}")
    reshaped = field.reshape(field.shape[:-2] + (MOM_NY, 2, MOM_NX, 2))
    return reshaped.mean(axis=(-3, -1))


def coarsen_2x2_weighted(field: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Average a source field over the floating part of each 2 km cell."""
    require(field.shape == weight.shape, f"Weighted coarsening shape mismatch: {field.shape} vs {weight.shape}")
    numerator = coarsen_2x2(field * weight)
    denominator = coarsen_2x2(weight)
    return np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0.0)


@dataclass(frozen=True)
class CaseData:
    time_seconds: np.ndarray
    thick: np.ndarray
    base_elevation: np.ndarray
    floating_fraction: np.ndarray
    bed_elevation: np.ndarray
    grounded_fraction: np.ndarray
    open_ocean_fraction: np.ndarray
    shelf_mass: np.ndarray
    source_sha256: str


def read_case(source: Path, rho_ice: float, threshold: float) -> CaseData:
    with netCDF4.Dataset(source) as dataset:
        require(dataset.dimensions["x"].size == SOURCE_NX, "raw x dimension must be 480")
        require(dataset.dimensions["y"].size == SOURCE_NY, "raw y dimension must be 80")
        require(dataset.dimensions["t"].size == 101, "raw t dimension must be 101")

        for name in (
            "x",
            "y",
            "t",
            "upperSurface",
            "lowerSurface",
            "bedrockTopography",
            "floatingMask",
            "groundedMask",
            "openOceanMask",
        ):
            require(name in dataset.variables, f"raw source is missing {name}")

        x = np.asarray(dataset.variables["x"][:], dtype=np.float64)
        y = np.asarray(dataset.variables["y"][:], dtype=np.float64)
        time_seconds = np.asarray(dataset.variables["t"][:], dtype=np.float64)
        upper_surface = np.asarray(dataset.variables["upperSurface"][:], dtype=np.float64)
        lower_surface = np.asarray(dataset.variables["lowerSurface"][:], dtype=np.float64)
        bedrock = np.asarray(dataset.variables["bedrockTopography"][:], dtype=np.float64)
        floating_mask = np.asarray(dataset.variables["floatingMask"][:], dtype=np.float64)
        grounded_mask = np.asarray(dataset.variables["groundedMask"][:], dtype=np.float64)
        open_ocean_mask = np.asarray(dataset.variables["openOceanMask"][:], dtype=np.float64)

    check_axis(x, EXPECTED_X0, SOURCE_DX, "x")
    check_axis(y, EXPECTED_Y0, SOURCE_DY, "y")
    require(np.all(np.isfinite(time_seconds)), "time coordinate contains non-finite values")
    require(np.all(np.diff(time_seconds) > 0.0), "time coordinate must be strictly increasing")
    require(time_seconds[0] == 0.0, "time coordinate should start at zero")
    require(np.all(np.isfinite(upper_surface)), "upperSurface contains non-finite values")
    require(np.all(np.isfinite(lower_surface)), "lowerSurface contains non-finite values")
    require(np.all(np.isfinite(bedrock)), "bedrockTopography contains non-finite values")
    require(np.all(np.isfinite(floating_mask)), "floatingMask contains non-finite values")
    for name, mask in (
        ("floatingMask", floating_mask),
        ("groundedMask", grounded_mask),
        ("openOceanMask", open_ocean_mask),
    ):
        require(np.all(np.isfinite(mask)), f"{name} contains non-finite values")
        require(np.all((mask >= 0.0) & (mask <= 1.0)), f"{name} must be in [0, 1]")

    thick_1km = np.where(floating_mask > 0.0, np.maximum(upper_surface - lower_surface, 0.0), 0.0)
    thick_2km = coarsen_2x2_weighted(thick_1km, floating_mask)
    base_2km = coarsen_2x2_weighted(lower_surface, floating_mask)
    floating_fraction = coarsen_2x2(floating_mask)
    grounded_fraction = coarsen_2x2(grounded_mask)
    open_ocean_fraction = coarsen_2x2(open_ocean_mask)
    bed_2km = coarsen_2x2(bedrock)

    active = (floating_fraction > 0.0) & (thick_2km >= threshold)
    thick_2km = np.where(active, thick_2km, 0.0)
    base_2km = np.where(active, base_2km, 0.0)
    floating_fraction = np.where(active, floating_fraction, 0.0)
    shelf_mass = rho_ice * thick_2km

    require(thick_2km.shape == (101, MOM_NY, MOM_NX), "coarsened thickness has wrong shape")
    require(np.all(np.isfinite(thick_2km)), "coarsened thickness contains non-finite values")
    require(np.all(np.isfinite(base_2km)), "coarsened base elevation contains non-finite values")
    require(np.all((floating_fraction >= 0.0) & (floating_fraction <= 1.0)), "floating fraction out of range")
    require(np.all((grounded_fraction >= 0.0) & (grounded_fraction <= 1.0)), "grounded fraction out of range")
    require(np.all((open_ocean_fraction >= 0.0) & (open_ocean_fraction <= 1.0)), "open-ocean fraction out of range")
    require(np.all(shelf_mass >= 0.0), "shelf_mass must be non-negative")

    return CaseData(
        time_seconds=time_seconds,
        thick=thick_2km,
        base_elevation=base_2km,
        floating_fraction=floating_fraction,
        bed_elevation=bed_2km,
        grounded_fraction=grounded_fraction,
        open_ocean_fraction=open_ocean_fraction,
        shelf_mass=shelf_mass,
        source_sha256=sha256sum(source),
    )


def write_initial_file(
    path: Path,
    case: str,
    source: Path,
    source_sha256: str,
    thick: np.ndarray,
    base_elevation: np.ndarray,
    floating_fraction: np.ndarray,
    rho_ice: float,
    threshold: float,
) -> None:
    area = floating_fraction * MOM_CELL_AREA
    require(np.all((area >= 0.0) & (area <= MOM_CELL_AREA)), "area must be within one MOM cell")

    path.parent.mkdir(parents=True, exist_ok=True)
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as dataset:
        dataset.createDimension("ny", MOM_NY)
        dataset.createDimension("nx", MOM_NX)

        thick_var = dataset.createVariable("thick", "f8", ("ny", "nx"), fill_value=np.nan)
        area_var = dataset.createVariable("area", "f8", ("ny", "nx"), fill_value=np.nan)
        base_var = dataset.createVariable("base_elevation", "f8", ("ny", "nx"), fill_value=np.nan)
        fraction_var = dataset.createVariable("floating_fraction", "f8", ("ny", "nx"), fill_value=np.nan)
        thick_var.units = "m"
        thick_var.long_name = "floating ice physical thickness coarsened to the MOM6 2 km grid"
        area_var.units = "m2"
        area_var.long_name = "floating ice shelf area on the MOM6 2 km grid"
        base_var.units = "m"
        base_var.long_name = "floating ice base elevation coarsened to the MOM6 2 km grid"
        fraction_var.units = "1"
        fraction_var.long_name = "floating ice fraction on the MOM6 2 km grid"
        thick_var[:, :] = thick
        area_var[:, :] = area
        base_var[:, :] = base_elevation
        fraction_var[:, :] = floating_fraction

        dataset.description = f"{case} GFZ/PIK ISOMIP geometry coarsened from 1 km to 2 km for MOM6"
        dataset.source_file = str(source)
        dataset.source_sha256 = source_sha256
        dataset.case = case
        dataset.rho_ice_kg_m3 = rho_ice
        dataset.thickness_threshold_m = threshold
        dataset.coarsening = "2x2 area-weighted mean over floating source cells with floating area fraction"
        dataset.mom6_grid = "ny=40, nx=240, 2 km Cartesian ISOMIP grid"

    os.utime(path, (DETERMINISTIC_MTIME, DETERMINISTIC_MTIME))


def write_shelf_mass_file(
    path: Path,
    case: str,
    source: Path,
    source_sha256: str,
    time_seconds: np.ndarray,
    shelf_mass: np.ndarray,
    thick: np.ndarray,
    rho_ice: float,
    threshold: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The FMS time-interpolation reader used by MOM6's prescribed shelf-mass
    # path requires recognizable X/Y/T axis metadata, even when the data are
    # already on the MOM6 grid.
    x = EXPECTED_X0 + 0.5 * SOURCE_DX + MOM_DX * np.arange(MOM_NX, dtype=np.float64)
    y = EXPECTED_Y0 + 0.5 * SOURCE_DY + MOM_DY * np.arange(MOM_NY, dtype=np.float64)
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as dataset:
        dataset.createDimension("Time", None)
        dataset.createDimension("y", MOM_NY)
        dataset.createDimension("x", MOM_NX)

        time_var = dataset.createVariable("Time", "f8", ("Time",))
        y_var = dataset.createVariable("y", "f8", ("y",))
        x_var = dataset.createVariable("x", "f8", ("x",))
        mass_var = dataset.createVariable("shelf_mass", "f8", ("Time", "y", "x"), fill_value=np.nan)
        thick_var = dataset.createVariable("thick", "f8", ("Time", "y", "x"), fill_value=np.nan)

        time_var.units = "seconds since 0001-01-01 00:00:00"
        time_var.calendar = "noleap"
        time_var.axis = "T"
        time_var.cartesian_axis = "T"
        time_var.standard_name = "time"
        time_var.long_name = "time from the start of the ISOMIP experiment"
        y_var.units = "m"
        y_var.axis = "Y"
        y_var.cartesian_axis = "Y"
        y_var.long_name = "MOM6 2 km grid y coordinate"
        x_var.units = "m"
        x_var.axis = "X"
        x_var.cartesian_axis = "X"
        x_var.long_name = "MOM6 2 km grid x coordinate"
        mass_var.units = "kg m-2"
        mass_var.long_name = "prescribed ice shelf mass per horizontal area"
        mass_var.coordinates = "Time y x"
        thick_var.units = "m"
        thick_var.long_name = "diagnostic ice shelf thickness used to form shelf_mass"
        thick_var.coordinates = "Time y x"

        time_var[:] = time_seconds
        y_var[:] = y
        x_var[:] = x
        mass_var[:, :, :] = shelf_mass
        thick_var[:, :, :] = thick

        dataset.description = f"{case} GFZ/PIK prescribed shelf mass on the MOM6 2 km grid"
        dataset.source_file = str(source)
        dataset.source_sha256 = source_sha256
        dataset.case = case
        dataset.rho_ice_kg_m3 = rho_ice
        dataset.thickness_threshold_m = threshold
        dataset.coarsening = "2x2 arithmetic mean of floating ice thickness; shelf_mass=rho_ice*thick"
        dataset.mom6_grid = "ny=40, nx=240, 2 km Cartesian ISOMIP grid"

    os.utime(path, (DETERMINISTIC_MTIME, DETERMINISTIC_MTIME))


def write_geometry_file(
    path: Path,
    case: str,
    source: Path,
    source_sha256: str,
    data: CaseData,
    rho_ice: float,
    threshold: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    x = EXPECTED_X0 + 0.5 * SOURCE_DX + MOM_DX * np.arange(MOM_NX, dtype=np.float64)
    y = EXPECTED_Y0 + 0.5 * SOURCE_DY + MOM_DY * np.arange(MOM_NY, dtype=np.float64)
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as dataset:
        dataset.createDimension("Time", None)
        dataset.createDimension("y", MOM_NY)
        dataset.createDimension("x", MOM_NX)

        time_var = dataset.createVariable("Time", "f8", ("Time",))
        y_var = dataset.createVariable("y", "f8", ("y",))
        x_var = dataset.createVariable("x", "f8", ("x",))
        variables = {
            "thick": ("m", "floating ice physical thickness"),
            "base_elevation": ("m", "floating ice base elevation"),
            "floating_fraction": ("1", "floating ice fraction"),
            "bed_elevation": ("m", "bed elevation"),
            "grounded_fraction": ("1", "grounded ice fraction"),
            "open_ocean_fraction": ("1", "open ocean fraction"),
            "shelf_mass": ("kg m-2", "diagnostic ice mass per floating shelf area"),
        }
        ncvars = {
            name: dataset.createVariable(name, "f8", ("Time", "y", "x"), fill_value=np.nan)
            for name in variables
        }

        time_var.units = "seconds since 0001-01-01 00:00:00"
        time_var.calendar = "noleap"
        time_var.axis = "T"
        time_var.cartesian_axis = "T"
        time_var.standard_name = "time"
        time_var.long_name = "time from the start of the ISOMIP experiment"
        y_var.units = "m"
        y_var.axis = "Y"
        y_var.cartesian_axis = "Y"
        y_var.long_name = "MOM6 2 km grid y coordinate"
        x_var.units = "m"
        x_var.axis = "X"
        x_var.cartesian_axis = "X"
        x_var.long_name = "MOM6 2 km grid x coordinate"
        for name, (units, long_name) in variables.items():
            ncvars[name].units = units
            ncvars[name].long_name = long_name
            ncvars[name].coordinates = "Time y x"

        time_var[:] = data.time_seconds
        y_var[:] = y
        x_var[:] = x
        ncvars["thick"][:, :, :] = data.thick
        ncvars["base_elevation"][:, :, :] = data.base_elevation
        ncvars["floating_fraction"][:, :, :] = data.floating_fraction
        ncvars["bed_elevation"][:, :, :] = data.bed_elevation
        ncvars["grounded_fraction"][:, :, :] = data.grounded_fraction
        ncvars["open_ocean_fraction"][:, :, :] = data.open_ocean_fraction
        ncvars["shelf_mass"][:, :, :] = data.shelf_mass

        dataset.description = f"{case} GFZ/PIK prescribed ice-shelf geometry on the MOM6 2 km grid"
        dataset.source_file = str(source)
        dataset.source_sha256 = source_sha256
        dataset.case = case
        dataset.rho_ice_kg_m3 = rho_ice
        dataset.thickness_threshold_m = threshold
        dataset.coarsening = "2x2 floating-area-weighted geometry plus cell fractions"
        dataset.mom6_grid = "ny=40, nx=240, 2 km Cartesian ISOMIP grid"

    os.utime(path, (DETERMINISTIC_MTIME, DETERMINISTIC_MTIME))


def write_case_plot(
    path: Path,
    case: str,
    time_seconds: np.ndarray,
    thick: np.ndarray,
    floating_fraction: np.ndarray,
    shelf_mass: np.ndarray,
    threshold: float,
) -> None:
    years = time_seconds / (365.0 * 24.0 * 3600.0)
    shelf_area_km2 = floating_fraction.sum(axis=(1, 2)) * MOM_CELL_AREA / 1.0e6
    shelf_mass_gt = (shelf_mass * floating_fraction).sum(axis=(1, 2)) * MOM_CELL_AREA / 1.0e12

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    for ax, data, title in (
        (axes[0, 0], thick[0], "initial thickness (m)"),
        (axes[0, 1], thick[-1], "final thickness (m)"),
        (axes[0, 2], thick[-1] - thick[0], "final - initial thickness (m)"),
    ):
        image = ax.imshow(data, origin="lower", aspect="auto")
        ax.set_title(title)
        ax.set_xlabel("nx")
        ax.set_ylabel("ny")
        fig.colorbar(image, ax=ax, shrink=0.78)

    axes[1, 0].plot(years, shelf_area_km2)
    axes[1, 0].set_title("shelf area")
    axes[1, 0].set_xlabel("year")
    axes[1, 0].set_ylabel("km2")

    axes[1, 1].plot(years, shelf_mass_gt)
    axes[1, 1].set_title("total shelf mass")
    axes[1, 1].set_xlabel("year")
    axes[1, 1].set_ylabel("Gt")

    axes[1, 2].plot(years, np.nanmax(thick, axis=(1, 2)), label="max")
    axes[1, 2].plot(years, np.nanmean(thick, axis=(1, 2)), label="mean")
    axes[1, 2].set_title("thickness summary")
    axes[1, 2].set_xlabel("year")
    axes[1, 2].set_ylabel("m")
    axes[1, 2].legend()

    fig.suptitle(f"{case} GFZ geometry on MOM6 2 km grid")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def update_manifest(manifest_path: Path, files: Iterable[Path], repo_root: Path) -> None:
    if yamanifest_hash is None:
        raise RuntimeError("Cannot update manifest: yamanifest Python package is unavailable")

    if manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as handle:
            docs = list(yaml.safe_load_all(handle))
        require(len(docs) == 2, f"{manifest_path} should contain yamanifest header and data docs")
        header, data = docs
    else:
        header = {"format": "yamanifest", "version": 1.0}
        data = {}

    if data is None:
        data = {}

    for path in files:
        fullpath = path.resolve()
        relative = fullpath.relative_to(repo_root.resolve())
        key = f"work/{relative.as_posix()}"
        data[key] = {
            "fullpath": str(fullpath),
            "hashes": {
                "binhash": yamanifest_hash(str(fullpath), "binhash"),
                "md5": yamanifest_hash(str(fullpath), "md5"),
            },
        }

    with manifest_path.open("w", encoding="utf-8") as handle:
        handle.write("format: yamanifest\n")
        handle.write("version: 1.0\n")
        handle.write("---\n")
        yaml.safe_dump(data, handle, sort_keys=True)


def build_case(
    case: str,
    source_root: Path,
    output_dir: Path,
    plots_dir: Path,
    rho_ice: float,
    threshold: float,
) -> CaseOutputs:
    source = source_root / f"{case}_input_geom_v1.01.nc"
    require(source.exists(), f"Source file does not exist: {source}")

    data = read_case(source, rho_ice, threshold)
    initial = output_dir / f"{case}_2km_initial.nc"
    shelf_mass_path = output_dir / f"{case}_2km_shelf_mass.nc"
    noop_path = output_dir / f"{case}_2km_shelf_mass_noop.nc"
    geometry_path = output_dir / f"{case}_2km_geometry.nc"
    noop_geometry_path = output_dir / f"{case}_2km_geometry_noop.nc"
    plot_path = plots_dir / f"{case}_2km_geometry_overview.png"

    write_initial_file(
        initial,
        case,
        source,
        data.source_sha256,
        data.thick[0],
        data.base_elevation[0],
        data.floating_fraction[0],
        rho_ice,
        threshold,
    )
    write_shelf_mass_file(
        shelf_mass_path,
        case,
        source,
        data.source_sha256,
        data.time_seconds,
        data.shelf_mass,
        data.thick,
        rho_ice,
        threshold,
    )
    write_geometry_file(geometry_path, case, source, data.source_sha256, data, rho_ice, threshold)

    noop_thick = np.broadcast_to(data.thick[0], data.thick.shape).copy()
    noop_base = np.broadcast_to(data.base_elevation[0], data.base_elevation.shape).copy()
    noop_floating = np.broadcast_to(data.floating_fraction[0], data.floating_fraction.shape).copy()
    noop_bed = np.broadcast_to(data.bed_elevation[0], data.bed_elevation.shape).copy()
    noop_grounded = np.broadcast_to(data.grounded_fraction[0], data.grounded_fraction.shape).copy()
    noop_open = np.broadcast_to(data.open_ocean_fraction[0], data.open_ocean_fraction.shape).copy()
    noop_mass = rho_ice * noop_thick
    noop_data = CaseData(
        time_seconds=data.time_seconds,
        thick=noop_thick,
        base_elevation=noop_base,
        floating_fraction=noop_floating,
        bed_elevation=noop_bed,
        grounded_fraction=noop_grounded,
        open_ocean_fraction=noop_open,
        shelf_mass=noop_mass,
        source_sha256=data.source_sha256,
    )
    write_shelf_mass_file(
        noop_path,
        case,
        source,
        data.source_sha256,
        data.time_seconds,
        noop_mass,
        noop_thick,
        rho_ice,
        threshold,
    )
    write_geometry_file(noop_geometry_path, case, source, data.source_sha256, noop_data, rho_ice, threshold)
    write_case_plot(plot_path, case, data.time_seconds, data.thick, data.floating_fraction, data.shelf_mass, threshold)

    require(np.allclose(data.thick[0], data.shelf_mass[0] / rho_ice), "initial thick and mass are inconsistent")
    require(np.all(np.isfinite(data.shelf_mass)), "shelf_mass output contains non-finite values")

    return CaseOutputs(
        initial=initial,
        shelf_mass=shelf_mass_path,
        noop_shelf_mass=noop_path,
        geometry=geometry_path,
        noop_geometry=noop_geometry_path,
        plot=plot_path,
    )


def parse_args() -> object:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "cases",
        nargs="*",
        metavar="case",
        help=f"GFZ/PIK cases to process: {', '.join(DEFAULT_CASES)}",
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=Path("INPUT/gfz_geometry"))
    parser.add_argument("--plots-dir", type=Path, default=Path("plots/gfz_geometry"))
    parser.add_argument("--manifest", type=Path, default=Path("manifests/input.yaml"))
    parser.add_argument("--update-manifest", action="store_true")
    parser.add_argument("--rho-ice", type=float, default=900.0)
    parser.add_argument("--threshold", type=float, default=10.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = tuple(args.cases) if args.cases else DEFAULT_CASES
    unknown_cases = sorted(set(cases).difference(DEFAULT_CASES))
    if unknown_cases:
        raise RuntimeError(f"Unknown case(s): {', '.join(unknown_cases)}")
    repo_root = Path.cwd()
    written_files: list[Path] = []

    for case in cases:
        outputs = build_case(
            case=case,
            source_root=args.source_root,
            output_dir=args.output_dir,
            plots_dir=args.plots_dir,
            rho_ice=args.rho_ice,
            threshold=args.threshold,
        )
        written_files.extend([
            outputs.initial,
            outputs.shelf_mass,
            outputs.noop_shelf_mass,
            outputs.geometry,
            outputs.noop_geometry,
        ])
        print(f"{case}:")
        print(f"  initial: {outputs.initial}")
        print(f"  shelf_mass: {outputs.shelf_mass}")
        print(f"  noop_shelf_mass: {outputs.noop_shelf_mass}")
        print(f"  geometry: {outputs.geometry}")
        print(f"  noop_geometry: {outputs.noop_geometry}")
        print(f"  plot: {outputs.plot}")

    if args.update_manifest:
        update_manifest(args.manifest, written_files, repo_root)
        print(f"Updated {args.manifest}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
