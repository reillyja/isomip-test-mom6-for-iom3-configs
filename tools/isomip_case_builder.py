#!/usr/bin/env python3
"""Build and inspect configurable MOM6-solo ISOMIP-style cases.

This module is intentionally notebook-friendly: most functions return plain
dataclasses, dictionaries, numpy arrays, or paths that can be inspected before
anything is submitted to payu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import os
import re
import shutil
from typing import Iterable

import netCDF4
import numpy as np

try:
    from yamanifest import hash as yamanifest_hash
except ImportError:  # pragma: no cover - available when the payu module is loaded.
    yamanifest_hash = None


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = Path("/g/data/au88/jr5971/gfz-pik-2016-002/data")
DEFAULT_EXE = Path("/g/data/au88/jr5971/MOM6-isomip-nuopc/install-solo-gfz-geometry/bin/mom6-solo")
DEFAULT_CONTROL_ROOT = Path(f"/scratch/au88/{os.environ.get('USER', 'unknown')}/mom6-isomip-generated-controls")
DEFAULT_LAB_ROOT = Path(f"/scratch/au88/{os.environ.get('USER', 'unknown')}/mom6-isomip-generated")
SOURCE_DX_M = 1000.0
SOURCE_DY_M = 1000.0
RHO_ICE = 900.0
GRAVITY = 9.8
DETERMINISTIC_MTIME = 946_684_800


PROFILE_DURATIONS = {
    "smoke": (0, 0, 0, 10, 0),
    "half-day": (0, 0, 12, 0, 0),
    "day": (0, 1, 0, 0, 0),
    "month": (1, 0, 0, 0, 0),
    "six-month": (6, 0, 0, 0, 0),
    "year": (12, 0, 0, 0, 0),
}


@dataclass(frozen=True)
class GridConfig:
    """Horizontal grid and domain controls."""

    nx: int = 240
    ny: int = 40
    dx_m: float = 2000.0
    dy_m: float = 2000.0
    west_m: float = 320000.0
    south_m: float = 0.0
    method: str = "auto"  # "auto", "cell_mean", or "nearest"


@dataclass(frozen=True)
class GeometryTransform:
    """Simple geometry transforms applied after regridding."""

    thickness_scale: float = 1.0
    front_shift_m: float = 0.0
    channel_width_m: float | None = None
    min_thickness_m: float = 10.0
    floating_fraction_threshold: float = 0.0
    bed_offset_m: float = 0.0
    bed_slope_m_per_km: float = 0.0
    min_cavity_depth_m: float = 1.0
    clear_thin_cavity: bool = True


@dataclass(frozen=True)
class RuntimeConfig:
    """MOM6-solo runtime controls for a generated control."""

    profile: str = "smoke"
    dt_s: int = 300
    nk: int = 36
    regridding_mode: str = "SIGMA_SHELF_ZSTAR"
    queue: str = "normalsr"
    walltime: str = "01:00:00"
    ncpus: int = 48
    jobfs: str = "10GB"
    jobname: str = "mom6_iso_gen"
    thermal_preset: str = "ocean0-warm"
    salinity_top: float = 33.8
    salinity_bottom: float = 34.7
    temp_surface_c: float = -1.9
    temp_bottom_c: float = 1.0


@dataclass(frozen=True)
class CaseConfig:
    """Complete specification for an isolated generated MOM6-solo control."""

    name: str = "ocean3-generated-smoke"
    ocean_case: str = "Ocean3"
    geometry_mode: str = "geometry-noop"  # "static", "geometry-noop", "geometry"
    grid: GridConfig = field(default_factory=GridConfig)
    transform: GeometryTransform = field(default_factory=GeometryTransform)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    control_root: Path = DEFAULT_CONTROL_ROOT
    lab_root: Path = DEFAULT_LAB_ROOT
    source_root: Path = DEFAULT_SOURCE_ROOT
    base_control: Path = REPO_ROOT
    exe: Path = DEFAULT_EXE
    replace: bool = False


@dataclass(frozen=True)
class GeneratedPaths:
    control: Path
    lab: Path
    initial: Path
    geometry: Path
    geometry_noop: Path | None
    topography: Path
    summary_json: Path


@dataclass(frozen=True)
class GeometryData:
    x: np.ndarray
    y: np.ndarray
    time: np.ndarray
    thick: np.ndarray
    base: np.ndarray
    floating_fraction: np.ndarray
    bed: np.ndarray
    grounded_fraction: np.ndarray
    open_ocean_fraction: np.ndarray
    shelf_mass: np.ndarray
    source: Path
    warnings: tuple[str, ...] = ()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def source_path(source_root: Path, ocean_case: str) -> Path:
    require(ocean_case in {"Ocean1", "Ocean2", "Ocean3", "Ocean4"}, f"Unsupported ocean case: {ocean_case}")
    return source_root / f"{ocean_case}_input_geom_v1.01.nc"


def target_axes(grid: GridConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x_edges = grid.west_m + grid.dx_m * np.arange(grid.nx + 1, dtype=np.float64)
    y_edges = grid.south_m + grid.dy_m * np.arange(grid.ny + 1, dtype=np.float64)
    x = 0.5 * (x_edges[:-1] + x_edges[1:])
    y = 0.5 * (y_edges[:-1] + y_edges[1:])
    return x, y, x_edges, y_edges


def _nearest_regrid(field: np.ndarray, source_x: np.ndarray, source_y: np.ndarray, target_x: np.ndarray, target_y: np.ndarray) -> np.ndarray:
    ix = np.clip(np.searchsorted(source_x, target_x), 1, len(source_x) - 1)
    ix = np.where(np.abs(source_x[ix] - target_x) < np.abs(source_x[ix - 1] - target_x), ix, ix - 1)
    iy = np.clip(np.searchsorted(source_y, target_y), 1, len(source_y) - 1)
    iy = np.where(np.abs(source_y[iy] - target_y) < np.abs(source_y[iy - 1] - target_y), iy, iy - 1)
    if field.ndim == 2:
        return field[np.ix_(iy, ix)]
    return field[:, iy[:, None], ix[None, :]]


def _cell_mean_regrid(
    field: np.ndarray,
    source_x: np.ndarray,
    source_y: np.ndarray,
    target_x_edges: np.ndarray,
    target_y_edges: np.ndarray,
    weight: np.ndarray | None = None,
) -> np.ndarray:
    """Average source-cell centers falling inside each target cell."""

    ny = len(target_y_edges) - 1
    nx = len(target_x_edges) - 1
    shape = (ny, nx) if field.ndim == 2 else (field.shape[0], ny, nx)
    out = np.zeros(shape, dtype=np.float64)
    fallback_x = 0.5 * (target_x_edges[:-1] + target_x_edges[1:])
    fallback_y = 0.5 * (target_y_edges[:-1] + target_y_edges[1:])
    fallback = _nearest_regrid(field, source_x, source_y, fallback_x, fallback_y)

    for j in range(ny):
        y_mask = (source_y >= target_y_edges[j]) & (source_y < target_y_edges[j + 1])
        for i in range(nx):
            x_mask = (source_x >= target_x_edges[i]) & (source_x < target_x_edges[i + 1])
            if not np.any(x_mask) or not np.any(y_mask):
                if field.ndim == 2:
                    out[j, i] = fallback[j, i]
                else:
                    out[:, j, i] = fallback[:, j, i]
                continue
            slab = field[..., y_mask, :][..., x_mask]
            if weight is None:
                out[..., j, i] = slab.mean(axis=(-2, -1))
            else:
                w = weight[..., y_mask, :][..., x_mask]
                numerator = np.sum(slab * w, axis=(-2, -1))
                denominator = np.sum(w, axis=(-2, -1))
                mean = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0.0)
                out[..., j, i] = mean
    return out


def _regrid(
    field: np.ndarray,
    source_x: np.ndarray,
    source_y: np.ndarray,
    grid: GridConfig,
    weight: np.ndarray | None = None,
) -> tuple[np.ndarray, str]:
    x, y, x_edges, y_edges = target_axes(grid)
    if grid.method == "nearest":
        return _nearest_regrid(field, source_x, source_y, x, y), "nearest"
    if grid.method in {"auto", "cell_mean"}:
        return _cell_mean_regrid(field, source_x, source_y, x_edges, y_edges, weight=weight), "cell_mean"
    raise ValueError(f"Unknown grid method: {grid.method}")


def _shift_along_x(data: np.ndarray, x: np.ndarray, shift_m: float, fill: float = 0.0) -> np.ndarray:
    if shift_m == 0.0:
        return data
    shifted = np.empty_like(data)
    sample_x = x - shift_m
    flat = data.reshape((-1, data.shape[-1]))
    out = shifted.reshape((-1, shifted.shape[-1]))
    for row, target in zip(flat, out):
        target[:] = np.interp(sample_x, x, row, left=fill, right=fill)
    return shifted


def build_geometry(config: CaseConfig) -> GeometryData:
    src = source_path(config.source_root, config.ocean_case)
    require(src.exists(), f"Missing source geometry file: {src}")
    warnings: list[str] = []
    with netCDF4.Dataset(src) as ds:
        x_src = np.asarray(ds["x"][:], dtype=np.float64)
        y_src = np.asarray(ds["y"][:], dtype=np.float64)
        time = np.asarray(ds["t"][:], dtype=np.float64)
        upper = np.asarray(ds["upperSurface"][:], dtype=np.float64)
        lower = np.asarray(ds["lowerSurface"][:], dtype=np.float64)
        bedrock = np.asarray(ds["bedrockTopography"][:], dtype=np.float64)
        floating = np.asarray(ds["floatingMask"][:], dtype=np.float64)
        grounded = np.asarray(ds["groundedMask"][:], dtype=np.float64)
        open_ocean = np.asarray(ds["openOceanMask"][:], dtype=np.float64)

    require(np.all(np.diff(time) > 0.0), "Source time axis must be strictly increasing")
    require(np.all(np.isfinite(upper)) and np.all(np.isfinite(lower)), "Source ice geometry contains non-finite values")
    require(np.all((floating >= 0.0) & (floating <= 1.0)), "Source floating mask is outside [0, 1]")

    x, y, _, _ = target_axes(config.grid)
    thick_source = np.where(floating > 0.0, np.maximum(upper - lower, 0.0), 0.0)
    thick, method = _regrid(thick_source, x_src, y_src, config.grid, weight=floating)
    base, _ = _regrid(lower, x_src, y_src, config.grid, weight=floating)
    floating_fraction, _ = _regrid(floating, x_src, y_src, config.grid)
    grounded_fraction, _ = _regrid(grounded, x_src, y_src, config.grid)
    open_ocean_fraction, _ = _regrid(open_ocean, x_src, y_src, config.grid)
    bed, _ = _regrid(bedrock, x_src, y_src, config.grid)
    if method != "cell_mean":
        warnings.append("Geometry used nearest-neighbour interpolation; area conservation is approximate.")

    tr = config.transform
    thick = thick * tr.thickness_scale
    if tr.front_shift_m != 0.0:
        thick = _shift_along_x(thick, x, tr.front_shift_m, fill=0.0)
        base = _shift_along_x(base, x, tr.front_shift_m, fill=0.0)
        floating_fraction = np.clip(_shift_along_x(floating_fraction, x, tr.front_shift_m, fill=0.0), 0.0, 1.0)
        warnings.append("Applied front_shift_m by translating shelf fields along x; bed/topography was not shifted.")

    if tr.channel_width_m is not None:
        y_mid = 0.5 * (y[0] + y[-1])
        channel = np.abs(y - y_mid) <= 0.5 * tr.channel_width_m
        thick = np.where(channel[None, :, None], thick, 0.0)
        base = np.where(channel[None, :, None], base, 0.0)
        floating_fraction = np.where(channel[None, :, None], floating_fraction, 0.0)

    bed = bed + tr.bed_offset_m
    if tr.bed_slope_m_per_km != 0.0:
        x_ref = x[0]
        bed = bed + tr.bed_slope_m_per_km * ((x[None, None, :] - x_ref) / 1000.0)

    active = (floating_fraction > tr.floating_fraction_threshold) & (thick >= tr.min_thickness_m)
    cavity = base - bed
    if tr.clear_thin_cavity:
        active = active & (cavity >= tr.min_cavity_depth_m)
    thick = np.where(active, thick, 0.0)
    base = np.where(active, base, 0.0)
    floating_fraction = np.where(active, np.clip(floating_fraction, 0.0, 1.0), 0.0)
    shelf_mass = RHO_ICE * thick

    for name, arr in {
        "thick": thick,
        "base": base,
        "floating_fraction": floating_fraction,
        "bed": bed,
        "grounded_fraction": grounded_fraction,
        "open_ocean_fraction": open_ocean_fraction,
        "shelf_mass": shelf_mass,
    }.items():
        require(np.all(np.isfinite(arr)), f"{name} contains non-finite values")
    require(np.all((floating_fraction >= 0.0) & (floating_fraction <= 1.0)), "floating_fraction outside [0, 1]")

    return GeometryData(
        x=x,
        y=y,
        time=time,
        thick=thick,
        base=base,
        floating_fraction=floating_fraction,
        bed=bed,
        grounded_fraction=np.clip(grounded_fraction, 0.0, 1.0),
        open_ocean_fraction=np.clip(open_ocean_fraction, 0.0, 1.0),
        shelf_mass=shelf_mass,
        source=src,
        warnings=tuple(warnings),
    )


def geometry_summary(data: GeometryData, time_index: int = 0) -> dict[str, float | int | str]:
    thick = data.thick[time_index]
    frac = data.floating_fraction[time_index]
    bed = data.bed[time_index]
    base = data.base[time_index]
    dx = float(np.diff(data.x).mean()) if len(data.x) > 1 else 0.0
    dy = float(np.diff(data.y).mean()) if len(data.y) > 1 else 0.0
    cell_area = dx * dy
    active = (frac > 0.0) & (thick > 0.0)
    cavity = np.where(active, base - bed, np.nan)
    return {
        "source": str(data.source),
        "time_index": int(time_index),
        "nx": int(len(data.x)),
        "ny": int(len(data.y)),
        "dx_m": dx,
        "dy_m": dy,
        "active_shelf_cells": int(active.sum()),
        "shelf_area_km2": float(frac.sum() * cell_area / 1.0e6),
        "max_thickness_m": float(np.nanmax(thick)),
        "min_cavity_m": float(np.nanmin(cavity)) if np.any(active) else float("nan"),
        "max_cavity_m": float(np.nanmax(cavity)) if np.any(active) else float("nan"),
        "floating_fraction_sum": float(frac.sum()),
    }


def _write_axis(var, units: str, axis: str, long_name: str, values: np.ndarray) -> None:
    var.units = units
    var.axis = axis
    var.cartesian_axis = axis
    var.long_name = long_name
    if axis == "T":
        var.standard_name = "time"
        var.calendar = "noleap"
        var.calendar_type = "NOLEAP"
    var[:] = values


def write_initial_file(path: Path, data: GeometryData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dx = float(np.diff(data.x).mean()) if len(data.x) > 1 else SOURCE_DX_M
    dy = float(np.diff(data.y).mean()) if len(data.y) > 1 else SOURCE_DY_M
    area = data.floating_fraction[0] * dx * dy
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as ds:
        ds.createDimension("ny", len(data.y))
        ds.createDimension("nx", len(data.x))
        fields = {
            "thick": ("m", "floating ice physical thickness", data.thick[0]),
            "area": ("m2", "floating ice shelf area in MOM cell", area),
            "base_elevation": ("m", "floating ice base elevation", data.base[0]),
            "floating_fraction": ("1", "floating ice fraction", data.floating_fraction[0]),
        }
        for name, (units, long_name, values) in fields.items():
            var = ds.createVariable(name, "f8", ("ny", "nx"), fill_value=np.nan)
            var.units = units
            var.long_name = long_name
            var[:, :] = values
        ds.description = "Generated MOM6-solo initial ice-shelf geometry"
        ds.source_file = str(data.source)
        ds.rho_ice_kg_m3 = RHO_ICE
    os.utime(path, (DETERMINISTIC_MTIME, DETERMINISTIC_MTIME))


def write_geometry_file(path: Path, data: GeometryData, noop: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if noop:
        thick = np.broadcast_to(data.thick[0], data.thick.shape).copy()
        base = np.broadcast_to(data.base[0], data.base.shape).copy()
        floating_fraction = np.broadcast_to(data.floating_fraction[0], data.floating_fraction.shape).copy()
        shelf_mass = RHO_ICE * thick
    else:
        thick = data.thick
        base = data.base
        floating_fraction = data.floating_fraction
        shelf_mass = data.shelf_mass
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as ds:
        ds.createDimension("Time", None)
        ds.createDimension("y", len(data.y))
        ds.createDimension("x", len(data.x))
        _write_axis(ds.createVariable("Time", "f8", ("Time",)), "seconds since 0001-01-01 00:00:00", "T", "time", data.time)
        _write_axis(ds.createVariable("y", "f8", ("y",)), "m", "Y", "MOM6 y coordinate", data.y)
        _write_axis(ds.createVariable("x", "f8", ("x",)), "m", "X", "MOM6 x coordinate", data.x)
        for name, units, long_name, values in (
            ("thick", "m", "floating ice physical thickness", thick),
            ("base_elevation", "m", "floating ice base elevation", base),
            ("floating_fraction", "1", "floating ice fraction", floating_fraction),
            ("bed_elevation", "m", "bed elevation", data.bed),
            ("grounded_fraction", "1", "grounded ice fraction", data.grounded_fraction),
            ("open_ocean_fraction", "1", "open ocean fraction", data.open_ocean_fraction),
            ("shelf_mass", "kg m-2", "diagnostic ice mass per shelf area", shelf_mass),
        ):
            var = ds.createVariable(name, "f8", ("Time", "y", "x"), fill_value=np.nan)
            var.units = units
            var.long_name = long_name
            var.coordinates = "Time y x"
            var[:, :, :] = values
        ds.description = "Generated MOM6-solo prescribed ice-shelf geometry"
        ds.source_file = str(data.source)
        ds.rho_ice_kg_m3 = RHO_ICE
        ds.noop_geometry = int(noop)
    os.utime(path, (DETERMINISTIC_MTIME, DETERMINISTIC_MTIME))


def write_topography_file(path: Path, data: GeometryData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as ds:
        ds.createDimension("Time", None)
        ds.createDimension("y", len(data.y))
        ds.createDimension("x", len(data.x))
        _write_axis(ds.createVariable("Time", "f8", ("Time",)), "seconds since 0001-01-01 00:00:00", "T", "time", data.time)
        _write_axis(ds.createVariable("y", "f8", ("y",)), "m", "Y", "MOM6 y coordinate", data.y)
        _write_axis(ds.createVariable("x", "f8", ("x",)), "m", "X", "MOM6 x coordinate", data.x)
        bed = ds.createVariable("bed_elevation", "f8", ("Time", "y", "x"), fill_value=np.nan)
        depth = ds.createVariable("depth", "f8", ("Time", "y", "x"), fill_value=np.nan)
        bed.units = "m"
        depth.units = "m"
        bed.long_name = "bed elevation"
        depth.long_name = "positive-downward ocean depth implied by bed"
        bed[:, :, :] = data.bed
        depth[:, :, :] = np.maximum(-data.bed, 0.0)
        ds.description = "Generated bed/topography preview. MOM v1 controls use ISOMIP analytic topography parameters."
    os.utime(path, (DETERMINISTIC_MTIME, DETERMINISTIC_MTIME))


def _replace_nml_duration(text: str, profile: str) -> str:
    values = dict(zip(("months", "days", "hours", "minutes", "seconds"), PROFILE_DURATIONS[profile]))
    for key, value in values.items():
        text, count = re.subn(rf"^(\s*{key}\s*=\s*)\d+(\s*,?\s*)$", rf"\g<1>{value}\g<2>", text, count=1, flags=re.MULTILINE)
        require(count == 1, f"Could not update {key} in input.nml")
    return text


def _replace_parameter_files(text: str, files: Iterable[str]) -> str:
    replacement = "    parameter_filename = " + ", ".join(f"'{name}'" for name in files) + " /"
    text, count = re.subn(r"^\s*parameter_filename\s*=.*?/\s*$", replacement, text, count=1, flags=re.MULTILINE)
    require(count == 1, "Could not update parameter_filename in input.nml")
    return text


def _replace_yaml_scalar(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{key}:"):
            lines[i] = f"{key}: {value}"
            return "\n".join(lines) + "\n"
    raise RuntimeError(f"Could not find top-level {key}: in config.yaml")


def _set_or_append_param(lines: list[str], key: str, value: str) -> None:
    pattern = re.compile(rf"^(#override\s+)?{re.escape(key)}\s*=")
    for i, line in enumerate(lines):
        if pattern.match(line.strip()):
            prefix = "#override " if line.lstrip().startswith("#override") else ""
            lines[i] = f"{prefix}{key} = {value}"
            return
    lines.append(f"#override {key} = {value}")


def _generated_override(config: CaseConfig, data: GeometryData, initial_rel: str, geometry_rel: str | None) -> str:
    base_lines = (config.base_control / "MOM_override").read_text(encoding="utf-8").splitlines()
    grid = config.grid
    rt = config.runtime
    tr = config.transform
    params = {
        "ICE_THICKNESS_FILE": f'"{initial_rel}"',
        "SURFACE_PRESSURE_FILE": f'"{initial_rel}"',
        "ICE_THICKNESS_VARNAME": '"thick"',
        "ICE_AREA_VARNAME": '"area"',
        "SURFACE_PRESSURE_VAR": '"thick"',
        "SURFACE_PRESSURE_SCALE": f"{RHO_ICE * GRAVITY:.12g}",
        "DENSITY_ICE": f"{RHO_ICE:.12g}",
        "MIN_THICKNESS_SIMPLE_CALVE": f"{tr.min_thickness_m:.12g}",
        "NIGLOBAL": str(grid.nx),
        "NJGLOBAL": str(grid.ny),
        "WESTLON": f"{grid.west_m / 1000.0:.12g}",
        "SOUTHLAT": f"{grid.south_m / 1000.0:.12g}",
        "LENLON": f"{grid.nx * grid.dx_m / 1000.0:.12g}",
        "LENLAT": f"{grid.ny * grid.dy_m / 1000.0:.12g}",
        "NK": str(rt.nk),
        "DT": str(rt.dt_s),
        "DT_THERM": str(rt.dt_s),
        "DT_FORCING": str(rt.dt_s),
        "REGRIDDING_COORDINATE_MODE": f'"{rt.regridding_mode}"',
        "MAXIMUM_DEPTH": f"{max(10.0, float(np.nanmax(-data.bed))):.12g}",
        "MINIMUM_DEPTH": f"{tr.min_cavity_depth_m:.12g}",
        "ISOMIP_DOMAIN_WIDTH": f"{grid.ny * grid.dy_m:.12g}",
        "ISOMIP_TROUGH_WIDTH": f"{0.3 * grid.ny * grid.dy_m:.12g}",
        "ISOMIP_MAX_BEDROCK": f"{max(10.0, float(np.nanmax(-data.bed))):.12g}",
        "ISOMIP_TROUGH_DEPTH": f"{max(10.0, float(np.nanmedian(np.maximum(-data.bed[0], 0.0)))):.12g}",
        "ISOMIP_T_SUR": f"{rt.temp_surface_c:.12g}",
        "ISOMIP_T_BOT": f"{rt.temp_bottom_c:.12g}",
        "ISOMIP_S_TOP": f"{rt.salinity_top:.12g}",
        "ISOMIP_S_BOT": f"{rt.salinity_bottom:.12g}",
        "ISOMIP_T_SUR_SPONGE": f"{rt.temp_surface_c:.12g}",
        "ISOMIP_T_BOT_SPONGE": f"{rt.temp_bottom_c:.12g}",
        "ISOMIP_S_SUR_SPONGE": f"{rt.salinity_top:.12g}",
        "ISOMIP_S_BOT_SPONGE": f"{rt.salinity_bottom:.12g}",
    }
    for key, value in params.items():
        _set_or_append_param(base_lines, key, value)

    block = [
        "",
        f"! Generated by tools/isomip_case_builder.py for {config.name}.",
        "! The horizontal mask is fixed for v1 generated cases.",
    ]
    if geometry_rel is not None:
        block.extend(
            [
                "#override DYNAMIC_SHELF_MASS = True",
                "#override OVERRIDE_SHELF_MOVEMENT = True",
                "#override ICE_SHELF_GEOMETRY_FROM_FILE = True",
                f"#override SHELF_GEOMETRY_FILE = \"{geometry_rel}\"",
                "#override SHELF_GEOMETRY_THICKNESS_VAR = \"thick\"",
                "#override SHELF_GEOMETRY_BASE_VAR = \"base_elevation\"",
                "#override SHELF_GEOMETRY_FLOATING_FRACTION_VAR = \"floating_fraction\"",
                "#override SHELF_GEOMETRY_READ_BED = True",
                "#override SHELF_GEOMETRY_BED_VAR = \"bed_elevation\"",
                "#override SHELF_GEOMETRY_READ_GROUNDED = False",
                "#override SHELF_GEOMETRY_GROUNDED_FRACTION_VAR = \"grounded_fraction\"",
                "#override DYNAMIC_CAVITY_GEOMETRY = False",
                "#override DYNAMIC_CAVITY_ALLOW_DRYING = False",
                f"#override DYNAMIC_CAVITY_MIN_DEPTH_M = {tr.min_cavity_depth_m:.12g}",
                "#override ICE_SHELF_USTAR_FROM_VEL_BUGFIX = True",
            ]
        )
    return "\n".join(base_lines + block) + "\n"


def _write_manifest(path: Path, entries: dict[str, Path]) -> None:
    if yamanifest_hash is None:
        raise RuntimeError("yamanifest is unavailable. Load the payu module before building a runnable control.")
    lines = ["format: yamanifest", "version: 1.0", "---"]
    for work_path, fullpath in sorted(entries.items()):
        lines.extend(
            [
                f"{work_path}:",
                f"  fullpath: {fullpath.resolve()}",
                "  hashes:",
                f"    binhash: {yamanifest_hash(str(fullpath), 'binhash')}",
                f"    md5: {yamanifest_hash(str(fullpath), 'md5')}",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _copy_base_control(config: CaseConfig, control: Path, lab: Path) -> None:
    if config.replace:
        for path, root in ((control, config.control_root), (lab, config.lab_root)):
            if path.exists() or path.is_symlink():
                resolved = path.resolve()
                root_resolved = root.resolve()
                require(resolved == root_resolved or root_resolved in resolved.parents, f"Refusing to remove {path}")
                shutil.rmtree(path)
    else:
        require(not control.exists(), f"Control path already exists: {control}")
        require(not lab.exists(), f"Lab path already exists: {lab}")
    control.mkdir(parents=True)
    for rel in ("config.yaml", "input.nml", "MOM_input", "MOM_override", "diag_table", "INPUT", "manifests", "tools"):
        src = config.base_control / rel
        dst = control / rel
        if src.is_dir():
            ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "archive", "work", "plots", "*.o[0-9]*", "*.e[0-9]*")
            shutil.copytree(src, dst, symlinks=True, ignore=ignore)
        else:
            shutil.copy2(src, dst)


def build_generated_case(config: CaseConfig) -> GeneratedPaths:
    require(config.geometry_mode in {"static", "geometry-noop", "geometry"}, "geometry_mode must be static, geometry-noop, or geometry")
    require(config.runtime.profile in PROFILE_DURATIONS, f"Unknown runtime profile: {config.runtime.profile}")
    data = build_geometry(config)
    control = config.control_root / config.name
    lab = config.lab_root / config.name
    _copy_base_control(config, control, lab)

    generated_dir = control / "INPUT" / "generated_geometry"
    stem = config.name.replace("/", "_")
    initial = generated_dir / f"{stem}_initial.nc"
    geometry = generated_dir / f"{stem}_geometry.nc"
    geometry_noop = generated_dir / f"{stem}_geometry_noop.nc"
    topography = generated_dir / f"{stem}_topography_preview.nc"
    write_initial_file(initial, data)
    write_geometry_file(geometry, data, noop=False)
    write_geometry_file(geometry_noop, data, noop=True)
    write_topography_file(topography, data)

    initial_rel = f"generated_geometry/{initial.name}"
    if config.geometry_mode == "static":
        geometry_rel = None
        selected_geometry = None
    elif config.geometry_mode == "geometry-noop":
        geometry_rel = f"generated_geometry/{geometry_noop.name}"
        selected_geometry = geometry_noop
    else:
        geometry_rel = f"generated_geometry/{geometry.name}"
        selected_geometry = geometry

    (control / "MOM_override.generated").write_text(_generated_override(config, data, initial_rel, geometry_rel), encoding="utf-8")
    input_nml = (control / "input.nml").read_text(encoding="utf-8")
    input_nml = _replace_nml_duration(input_nml, config.runtime.profile)
    input_nml = _replace_parameter_files(input_nml, ("MOM_input", "MOM_override.generated"))
    (control / "input.nml").write_text(input_nml, encoding="utf-8")

    config_yaml = (control / "config.yaml").read_text(encoding="utf-8")
    config_yaml = _replace_yaml_scalar(config_yaml, "laboratory", config.name)
    config_yaml = _replace_yaml_scalar(config_yaml, "queue", config.runtime.queue)
    config_yaml = _replace_yaml_scalar(config_yaml, "walltime", config.runtime.walltime)
    config_yaml = _replace_yaml_scalar(config_yaml, "jobname", config.runtime.jobname)
    config_yaml = _replace_yaml_scalar(config_yaml, "ncpus", str(config.runtime.ncpus))
    config_yaml = _replace_yaml_scalar(config_yaml, "jobfs", config.runtime.jobfs)
    config_yaml = _replace_yaml_scalar(config_yaml, "exe", str(config.exe))
    (control / "config.yaml").write_text(config_yaml, encoding="utf-8")

    input_entries = {}
    for path in sorted((control / "INPUT").rglob("*")):
        if path.is_file():
            input_entries[f"work/INPUT/{path.relative_to(control / 'INPUT')}"] = path
    _write_manifest(control / "manifests" / "input.yaml", input_entries)
    _write_manifest(control / "manifests" / "exe.yaml", {"work/mom6-solo": config.exe})
    (control / "manifests" / "restart.yaml").write_text("format: yamanifest\nversion: 1.0\n---\n{}\n", encoding="utf-8")

    summary = {
        "config": {
            "name": config.name,
            "ocean_case": config.ocean_case,
            "geometry_mode": config.geometry_mode,
            "profile": config.runtime.profile,
            "control": str(control),
            "lab": str(lab),
        },
        "geometry": geometry_summary(data),
        "warnings": list(data.warnings),
        "commands": payu_commands(control, lab),
        "selected_geometry": str(selected_geometry) if selected_geometry else None,
    }
    summary_json = generated_dir / f"{stem}_summary.json"
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return GeneratedPaths(control, lab, initial, geometry, geometry_noop if config.geometry_mode != "static" else None, topography, summary_json)


def payu_commands(control: Path, lab: Path) -> list[str]:
    return [
        f"cd {control}",
        "module purge",
        "module use /g/data/vk83/modules",
        "module load payu",
        f"payu setup --stacktrace --force --metadata-off --lab {lab}",
        f"payu run --stacktrace -f --lab {lab}",
    ]


def latest_archive(lab_or_archive: Path) -> Path:
    path = Path(lab_or_archive)
    if (path / "output000").exists() or any(path.glob("output[0-9][0-9][0-9]")):
        return path
    archive_dirs = sorted(path.glob("archive/*"))
    if archive_dirs:
        return archive_dirs[-1]
    if (path / "archive").exists():
        nested = sorted((path / "archive").glob("*"))
        if nested:
            return nested[-1]
    raise FileNotFoundError(f"Could not find payu archive below {path}")


def latest_numbered_dir(archive: Path, prefix: str) -> Path | None:
    dirs = sorted(Path(archive).glob(f"{prefix}[0-9][0-9][0-9]"))
    return dirs[-1] if dirs else None


def scan_logs(archive: Path) -> list[str]:
    bad = re.compile(r"\b(FATAL|ERROR|NaN|nan|Inf|infinity|reproducing|abort)\b")
    lines: list[str] = []
    for path in sorted(Path(archive).glob("**/*")):
        if not path.is_file():
            continue
        if path.suffix not in {".out", ".err", ".log"} and "log" not in path.name:
            continue
        try:
            for lineno, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if bad.search(line):
                    lines.append(f"{path}:{lineno}: {line[:220]}")
        except UnicodeDecodeError:
            continue
    return lines


def archive_summary(lab_or_archive: Path) -> dict[str, object]:
    archive = latest_archive(Path(lab_or_archive))
    output = latest_numbered_dir(archive, "output")
    restart = latest_numbered_dir(archive, "restart")
    summary: dict[str, object] = {
        "archive": str(archive),
        "output": str(output) if output else None,
        "restart": str(restart) if restart else None,
        "log_hits": scan_logs(archive)[:50],
    }
    if output and (output / "time_stamp.out").exists():
        summary["time_stamp"] = (output / "time_stamp.out").read_text(errors="replace").splitlines()
    if output and (output / "exitcode").exists():
        summary["exitcode"] = (output / "exitcode").read_text(errors="replace").strip()
    return summary


if __name__ == "__main__":
    cfg = CaseConfig(replace=True)
    paths = build_generated_case(cfg)
    print(json.dumps({"control": str(paths.control), "lab": str(paths.lab), "summary": str(paths.summary_json)}, indent=2))
