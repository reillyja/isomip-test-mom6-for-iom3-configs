#!/usr/bin/env python3
"""Generate high-signal debugging plots for the NUOPC ISOMIP case.

This script focuses on:
1. Ocean/shelf geometry and cavity thickness.
2. Coupler/data-component masks versus under-shelf cells.
3. Logged failure points from MOM6 grounding-cell warnings.
4. Placeholder forcing fields that may contribute to failures.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from netCDF4 import Dataset


def load_2d_var(path: Path, name: str) -> np.ndarray:
    with Dataset(path) as ds:
        return np.asarray(ds.variables[name][:])


def load_time0_2d_var(path: Path, name: str) -> np.ndarray:
    with Dataset(path) as ds:
        return np.asarray(ds.variables[name][0, :, :])


def load_geometry(work_dir: Path) -> dict[str, np.ndarray]:
    path = work_dir / "ocean_geometry.nc"
    with Dataset(path) as ds:
        return {
            "lon": np.asarray(ds.variables["lonh"][:]),
            "lat": np.asarray(ds.variables["lath"][:]),
            "wet": np.asarray(ds.variables["wet"][:]),
            "depth": np.asarray(ds.variables["D"][:]),
            "area": np.asarray(ds.variables["Ah"][:]),
        }


def load_shelf(repo_root: Path) -> dict[str, np.ndarray]:
    path = repo_root / "INPUT" / "Ocean0_3D_Claire.nc"
    with Dataset(path) as ds:
        return {
            "thick": np.asarray(ds.variables["thick"][:]),
            "area": np.asarray(ds.variables["area"][:]),
        }


def load_mesh_mask(path: Path, shape: tuple[int, int]) -> np.ndarray:
    with Dataset(path) as ds:
        return np.asarray(ds.variables["elementMask"][:]).reshape(shape)


def parse_grounding_points(err_path: Path, warn_path: Path) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    if err_path.exists():
        text = err_path.read_text(errors="replace")
        pattern = re.compile(
            r"Called from applyBoundaryFluxesInOut \(grounding\).*?lon,lat =\s*([0-9.E+\-]+)\s+([0-9.E+\-]+)",
            re.S,
        )
        for lon, lat in pattern.findall(text):
            points.append((float(lon), float(lat)))
    if not points and warn_path.exists():
        text = warn_path.read_text(errors="replace")
        pattern = re.compile(r"Mass created\. x,y,dh=\s*([0-9.E+\-]+)\s+([0-9.E+\-]+)\s+[0-9A-Za-z.+\-]+")
        for lon, lat in pattern.findall(text):
            points.append((float(lon), float(lat)))
    unique: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for point in points:
        if point not in seen:
            seen.add(point)
            unique.append(point)
    return unique


def parse_pet_nan_counts(work_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    pattern = re.compile(r"ERROR:\s+([0-9]+) nans found in ([A-Za-z0-9_]+)")
    for pet in sorted(work_dir.glob("PET*.ESMF_LogFile")):
        text = pet.read_text(errors="replace")
        for count, field in pattern.findall(text):
            counts[field] = max(counts.get(field, 0), int(count))
    return counts


def forcing_fields(repo_root: Path) -> dict[str, np.ndarray]:
    inp = repo_root / "INPUT"
    return {
        "tas": load_time0_2d_var(inp / "RYF.tas.1990_1991.nc", "tas"),
        "huss": load_time0_2d_var(inp / "RYF.huss.1990_1991.nc", "huss"),
        "psl": load_time0_2d_var(inp / "RYF.psl.1990_1991.nc", "psl"),
        "uas": load_time0_2d_var(inp / "RYF.uas.1990_1991.nc", "uas"),
        "vas": load_time0_2d_var(inp / "RYF.vas.1990_1991.nc", "vas"),
        "rlds": load_time0_2d_var(inp / "RYF.rlds.1990_1991.nc", "rlds"),
        "rsds": load_time0_2d_var(inp / "RYF.rsds.1990_1991.nc", "rsds"),
    }


def lonlat_mesh(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.meshgrid(lon, lat)


def scatter_points(ax: plt.Axes, points: list[tuple[float, float]], label: str = "error point") -> None:
    if not points:
        return
    xs, ys = zip(*points)
    ax.scatter(xs, ys, s=42, facecolor="none", edgecolor="crimson", linewidth=1.6, label=label, zorder=5)


def save_geometry_plot(
    out_path: Path,
    lon2d: np.ndarray,
    lat2d: np.ndarray,
    depth: np.ndarray,
    shelf: np.ndarray,
    cavity: np.ndarray,
    points: list[tuple[float, float]],
) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), constrained_layout=True)
    panels = [
        (depth, "Bathymetry D [m]", "Blues"),
        (shelf, "Ice Shelf Thickness [m]", "Purples"),
        (cavity, "Cavity Thickness [m]", "viridis"),
    ]
    for ax, (field, title, cmap) in zip(axes, panels):
        im = ax.pcolormesh(lon2d, lat2d, field, shading="nearest", cmap=cmap)
        scatter_points(ax, points)
        ax.set_title(title)
        ax.set_xlabel("x [km]")
        ax.set_ylabel("y [km]")
        fig.colorbar(im, ax=ax, shrink=0.9)
    if points:
        axes[0].legend(loc="upper right")
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def save_mask_plot(
    out_path: Path,
    lon2d: np.ndarray,
    lat2d: np.ndarray,
    under_shelf: np.ndarray,
    mesh_full: np.ndarray,
    mesh_atm: np.ndarray | None,
    mesh_rof: np.ndarray | None,
    points: list[tuple[float, float]],
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 8), constrained_layout=True)
    fields = [
        (under_shelf.astype(float), "Under-Shelf Cells", "Greys"),
        (mesh_full.astype(float), "Full OCN Mesh Mask", "cividis"),
        (mesh_atm.astype(float) if mesh_atm is not None else np.full_like(mesh_full, np.nan), "ATM Mesh Mask", "cividis"),
        (mesh_rof.astype(float) if mesh_rof is not None else np.full_like(mesh_full, np.nan), "ROF Mesh Mask", "cividis"),
    ]
    for ax, (field, title, cmap) in zip(axes.flat, fields):
        im = ax.pcolormesh(lon2d, lat2d, field, shading="nearest", cmap=cmap, vmin=0, vmax=1)
        scatter_points(ax, points)
        ax.set_title(title)
        ax.set_xlabel("x [km]")
        ax.set_ylabel("y [km]")
        fig.colorbar(im, ax=ax, shrink=0.85)
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def save_forcing_plot(
    out_path: Path,
    lon2d: np.ndarray,
    lat2d: np.ndarray,
    forcing: dict[str, np.ndarray],
    points: list[tuple[float, float]],
) -> None:
    wind = np.hypot(forcing["uas"], forcing["vas"])
    fields = [
        (forcing["tas"], "tas [K]", "coolwarm"),
        (forcing["huss"], "huss [1]", "magma"),
        (wind, "wind speed [m/s]", "plasma"),
        (forcing["rlds"], "rlds [W/m2]", "inferno"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 8), constrained_layout=True)
    for ax, (field, title, cmap) in zip(axes.flat, fields):
        im = ax.pcolormesh(lon2d, lat2d, field, shading="nearest", cmap=cmap)
        scatter_points(ax, points)
        ax.set_title(title)
        ax.set_xlabel("x [km]")
        ax.set_ylabel("y [km]")
        fig.colorbar(im, ax=ax, shrink=0.85)
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def save_summary(
    out_path: Path,
    points: list[tuple[float, float]],
    pet_nan_counts: dict[str, int],
    under_shelf_cells: int,
    mesh_full_exposed_under_shelf: int,
    mesh_atm_exposed_under_shelf: int | None,
    mesh_rof_exposed_under_shelf: int | None,
) -> None:
    lines = []
    lines.append("ISOMIP NUOPC Error Diagnostics")
    lines.append("")
    lines.append(f"Grounding/error points parsed: {len(points)}")
    for i, (lon, lat) in enumerate(points, start=1):
        lines.append(f"  {i}. lon={lon:.3f} km, lat={lat:.3f} km")
    lines.append("")
    lines.append(f"Under-shelf wet cells: {under_shelf_cells}")
    lines.append(f"Under-shelf cells exposed by full OCN mesh: {mesh_full_exposed_under_shelf}")
    if mesh_atm_exposed_under_shelf is not None:
        lines.append(f"Under-shelf cells exposed by ATM mesh: {mesh_atm_exposed_under_shelf}")
    if mesh_rof_exposed_under_shelf is not None:
        lines.append(f"Under-shelf cells exposed by ROF mesh: {mesh_rof_exposed_under_shelf}")
    lines.append("")
    if pet_nan_counts:
        lines.append("PET NaN counts:")
        for field, count in sorted(pet_nan_counts.items()):
            lines.append(f"  {field}: {count}")
    else:
        lines.append("No PET NaN counts found.")
    out_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--outdir", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    work_dir = (repo_root / "work").resolve()
    outdir = args.outdir or (repo_root / "diagnostics")
    outdir.mkdir(parents=True, exist_ok=True)

    geom = load_geometry(work_dir)
    shelf = load_shelf(repo_root)
    lon2d, lat2d = lonlat_mesh(geom["lon"], geom["lat"])

    wet = geom["wet"] > 0
    under_shelf = wet & (shelf["thick"] > 0) & (shelf["area"] > 0)
    cavity = np.where(under_shelf, geom["depth"] - shelf["thick"], np.nan)

    mesh_full = load_mesh_mask(repo_root / "INPUT" / "access-om3-25km-ESMFmesh.nc", under_shelf.shape)
    mesh_atm_path = repo_root / "INPUT" / "JRA55do-datm-cavitymasked-ESMFmesh.nc"
    mesh_rof_path = repo_root / "INPUT" / "JRA55do-drof-cavitymasked-ESMFmesh.nc"
    mesh_atm = load_mesh_mask(mesh_atm_path, under_shelf.shape) if mesh_atm_path.exists() else None
    mesh_rof = load_mesh_mask(mesh_rof_path, under_shelf.shape) if mesh_rof_path.exists() else None

    points = parse_grounding_points(repo_root / "access-om3.err", work_dir / "warnfile.000000.out")
    pet_nan_counts = parse_pet_nan_counts(work_dir)
    forcing = forcing_fields(repo_root)

    save_geometry_plot(outdir / "geometry_and_errors.png", lon2d, lat2d, geom["depth"], shelf["thick"], cavity, points)
    save_mask_plot(outdir / "mask_comparison.png", lon2d, lat2d, under_shelf, mesh_full, mesh_atm, mesh_rof, points)
    save_forcing_plot(outdir / "forcing_fields.png", lon2d, lat2d, forcing, points)

    save_summary(
        outdir / "error_summary.txt",
        points,
        pet_nan_counts,
        int(under_shelf.sum()),
        int(((mesh_full == 1) & under_shelf).sum()),
        int(((mesh_atm == 1) & under_shelf).sum()) if mesh_atm is not None else None,
        int(((mesh_rof == 1) & under_shelf).sum()) if mesh_rof is not None else None,
    )

    print(f"Wrote diagnostics to {outdir}")
    for name in ["geometry_and_errors.png", "mask_comparison.png", "forcing_fields.png", "error_summary.txt"]:
        print(f" - {outdir / name}")


if __name__ == "__main__":
    main()
