#!/usr/bin/env python3
"""Prepare and optionally submit an isolated GFZ/PIK ISOMIP payu test."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import os
import shutil
import subprocess
import sys

try:
    from yamanifest import hash as yamanifest_hash
except ImportError:  # pragma: no cover - expected on Gadi with payu available.
    yamanifest_hash = None


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LAB_ROOT = Path(f"/scratch/au88/{os.environ.get('USER', 'unknown')}/mom6-isomip-gfz")
DEFAULT_CONTROL_ROOT = Path(f"/scratch/au88/{os.environ.get('USER', 'unknown')}/mom6-isomip-gfz-controls")

CASE_CHOICES = (
    "ocean3-static",
    "ocean3-noop",
    "ocean3",
    "ocean3-geometry-noop",
    "ocean3-geometry",
    "ocean4-static",
    "ocean4-noop",
    "ocean4",
    "ocean4-geometry-noop",
    "ocean4-geometry",
)
PROFILE_CHOICES = (
    "smoke",
    "half-day",
    "day",
    "month",
    "six-month",
    "45-day",
    "three-month",
    "year",
    "five-year",
    "ten-year",
    "hundred-year",
)

QUEUE_DEFAULTS = {
    "smoke": ("normalsr", "01:00:00"),
    "half-day": ("normalsr", "01:00:00"),
    "day": ("normalsr", "01:00:00"),
    "month": ("normal", "04:00:00"),
    "six-month": ("normal", "18:00:00"),
    "45-day": ("normal", "06:00:00"),
    "three-month": ("normal", "12:00:00"),
    "year": ("normal", "30:00:00"),
    "five-year": ("normal", "48:00:00"),
    "ten-year": ("normal", "48:00:00"),
    "hundred-year": ("normal", "48:00:00"),
}

COPY_PATHS = (
    "config.yaml",
    "input.nml",
    "MOM_input",
    "MOM_override",
    "diag_table",
    "INPUT",
    "manifests",
    "tools",
)


def case_label(case: str) -> str:
    return {
        "ocean3": "ocean3-dynamic",
        "ocean4": "ocean4-dynamic",
        "ocean3-geometry": "ocean3-geometry-dynamic",
        "ocean4-geometry": "ocean4-geometry-dynamic",
    }.get(case, case)


def test_name(case: str, profile: str) -> str:
    return f"{case_label(case)}-{profile}"


def short_job_name(case: str, profile: str) -> str:
    case_part = {
        "ocean3-static": "o3s",
        "ocean3-noop": "o3n",
        "ocean3": "o3d",
        "ocean3-geometry-noop": "o3gn",
        "ocean3-geometry": "o3gd",
        "ocean4-static": "o4s",
        "ocean4-noop": "o4n",
        "ocean4": "o4d",
        "ocean4-geometry-noop": "o4gn",
        "ocean4-geometry": "o4gd",
    }[case]
    profile_part = {
        "smoke": "smk",
        "half-day": "hday",
        "day": "day",
        "month": "mon",
        "six-month": "6mon",
        "45-day": "45d",
        "three-month": "3mon",
        "year": "yr",
        "five-year": "5yr",
        "ten-year": "10yr",
        "hundred-year": "100yr",
    }[profile]
    return f"gfz_{case_part}_{profile_part}"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def ensure_child(path: Path, root: Path) -> None:
    path_resolved = path.resolve()
    root_resolved = root.resolve()
    require(
        path_resolved == root_resolved or root_resolved in path_resolved.parents,
        f"Refusing to remove path outside root: {path}",
    )


def replace_yaml_scalar(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith(f"{key}:"):
            lines[idx] = f"{key}: {value}"
            return "\n".join(lines) + "\n"
    raise RuntimeError(f"Could not find top-level {key}: setting")


def replace_module_loads(text: str, loads: list[str]) -> str:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line == "  load:":
            end = idx + 1
            while end < len(lines) and lines[end].startswith("    - "):
                end += 1
            replacement = ["  load:"] + [f"    - {module}" for module in loads]
            return "\n".join(lines[:idx] + replacement + lines[end:]) + "\n"
    raise RuntimeError("Could not find modules.load setting")


def replace_platform_scalar(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    in_platform = False
    for idx, line in enumerate(lines):
        if line == "platform:":
            in_platform = True
            continue
        if in_platform and line and not line.startswith(" "):
            break
        if in_platform and line.startswith(f"  {key}:"):
            lines[idx] = f"  {key}: {value}"
            return "\n".join(lines) + "\n"
    raise RuntimeError(f"Could not find platform.{key} setting")


def write_exe_manifest(path: Path, exe: Path) -> None:
    if yamanifest_hash is None:
        raise RuntimeError("Cannot update executable manifest: yamanifest is unavailable")
    path.write_text(
        "\n".join(
            [
                "format: yamanifest",
                "version: 1.0",
                "---",
                "work/mom6-solo:",
                f"  fullpath: {exe.resolve()}",
                "  hashes:",
                f"    binhash: {yamanifest_hash(str(exe), 'binhash')}",
                f"    md5: {yamanifest_hash(str(exe), 'md5')}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def prepare_control(
    control: Path,
    lab: Path,
    case: str,
    profile: str,
    queue: str,
    walltime: str,
    exe: Path | None,
    module_loads: list[str],
    replace: bool,
) -> None:
    if replace:
        for path, root in ((control, control.parent), (lab, lab.parent)):
            if path.exists() or path.is_symlink():
                ensure_child(path, root)
                shutil.rmtree(path)
    else:
        require(not control.exists(), f"Control path already exists: {control}; use --replace")
        require(not lab.exists(), f"Lab path already exists: {lab}; use --replace")

    control.mkdir(parents=True)
    for rel in COPY_PATHS:
        src = REPO_ROOT / rel
        dst = control / rel
        if src.is_dir():
            ignore = shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                "archive",
                "work",
                "plots",
                "*.o[0-9]*",
                "*.e[0-9]*",
            )
            shutil.copytree(src, dst, symlinks=True, ignore=ignore)
        else:
            shutil.copy2(src, dst)

    # A fresh cold-start control must not inherit restart manifests written by
    # previous continuation runs in the shared development directory.
    (control / "manifests" / "restart.yaml").write_text(
        "format: yamanifest\nversion: 1.0\n---\n{}\n",
        encoding="utf-8",
    )

    config = (control / "config.yaml").read_text(encoding="utf-8")
    config = replace_yaml_scalar(config, "queue", queue)
    config = replace_yaml_scalar(config, "walltime", walltime)
    config = replace_yaml_scalar(config, "jobname", short_job_name(case, profile))
    if queue == "normal":
        config = replace_platform_scalar(config, "nodesize", "48")
        config = replace_platform_scalar(config, "nodemem", "192")
    if exe is not None:
        require(exe.exists(), f"Executable does not exist: {exe}")
        config = replace_yaml_scalar(config, "exe", str(exe.resolve()))
        write_exe_manifest(control / "manifests" / "exe.yaml", exe)
    if module_loads:
        config = replace_module_loads(config, module_loads)
    (control / "config.yaml").write_text(config, encoding="utf-8")

    run_python_tool(control, "tools/set_gfz_geometry_case.py", case)
    run_python_tool(control, "tools/set_solo_profile.py", profile)


def run_python_tool(control: Path, script: str, *args: str) -> None:
    subprocess.run(
        [sys.executable, script, *args],
        cwd=control,
        check=True,
    )


def run_payu(control: Path, lab: Path, setup_only: bool) -> None:
    if setup_only:
        cmd = (
            "module use /g/data/vk83/modules; "
            "module load payu/1.3.2; "
            f"payu setup --stacktrace --force --metadata-off --lab {lab}"
        )
    else:
        cmd = (
            "module use /g/data/vk83/modules; "
            "module load payu/1.3.2; "
            f"payu run --stacktrace -f --lab {lab}"
        )
    subprocess.run(["bash", "-lc", cmd], cwd=control, check=True)


def parse_args() -> object:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASE_CHOICES)
    parser.add_argument("profile", choices=PROFILE_CHOICES)
    parser.add_argument("--lab-root", type=Path, default=DEFAULT_LAB_ROOT)
    parser.add_argument("--control-root", type=Path, default=DEFAULT_CONTROL_ROOT)
    parser.add_argument("--name", help="Override test name used for lab/control directories")
    parser.add_argument("--queue")
    parser.add_argument("--walltime")
    parser.add_argument("--exe", type=Path, help="Override the MOM6 executable in the copied control config")
    parser.add_argument(
        "--module-load",
        action="append",
        default=[],
        help="Replace copied control modules.load entries; may be repeated",
    )
    parser.add_argument("--replace", action="store_true", help="Replace existing lab/control paths for this test")
    parser.add_argument("--submit", action="store_true", help="Submit the payu job")
    parser.add_argument("--setup-only", action="store_true", help="Run payu setup instead of payu run")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    default_queue, default_walltime = QUEUE_DEFAULTS[args.profile]
    queue = args.queue or default_queue
    walltime = args.walltime or default_walltime
    name = args.name or test_name(args.case, args.profile)
    lab = args.lab_root / name
    control = args.control_root / name

    prepare_control(
        control=control,
        lab=lab,
        case=args.case,
        profile=args.profile,
        queue=queue,
        walltime=walltime,
        exe=args.exe,
        module_loads=args.module_load,
        replace=args.replace,
    )

    action = "setup" if args.setup_only else "run"
    print(f"Prepared GFZ test: {name}")
    print(f"  control: {control}")
    print(f"  lab:     {lab}")
    print(f"  case:    {args.case}")
    print(f"  profile: {args.profile}")
    print(f"  queue:   {queue}")
    print(f"  walltime:{walltime}")
    if args.exe is not None:
        print(f"  exe:     {args.exe.resolve()}")
    if args.module_load:
        print("  modules:")
        for module in args.module_load:
            print(f"    - {module}")
    print("  command:")
    print(f"    cd {control}")
    print("    module use /g/data/vk83/modules")
    print("    module load payu/1.3.2")
    print(f"    payu {action} --stacktrace {'--force --metadata-off ' if args.setup_only else '-f '}--lab {lab}")

    if args.submit or args.setup_only:
        run_payu(control=control, lab=lab, setup_only=args.setup_only)
    else:
        print("Dry run only. Add --submit to submit the job.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
