#!/usr/bin/env python3
"""Set matching stop and restart intervals in nuopc.runconfig."""

from argparse import ArgumentParser
from pathlib import Path
import re


PROFILES = {
    "smoke": ("nsteps", 2),
    "half-day": ("nsteps", 144),
    "day": ("nsteps", 288),
    "month": ("nmonths", 1),
    "45-day": ("ndays", 45),
    "three-month": ("nmonths", 3),
}


def replace_setting(text: str, key: str, value: str) -> str:
    pattern = rf"^(\s*{re.escape(key)}\s*=\s*).*$"
    updated, count = re.subn(pattern, rf"\g<1>{value}", text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected one {key} setting, found {count}")
    return updated


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("profile", choices=PROFILES)
    parser.add_argument("--runconfig", type=Path, default=Path("nuopc.runconfig"))
    args = parser.parse_args()

    option, count = PROFILES[args.profile]
    text = args.runconfig.read_text(encoding="utf-8")
    text = replace_setting(text, "stop_option", option)
    text = replace_setting(text, "stop_n", str(count))
    text = replace_setting(text, "restart_option", option)
    text = replace_setting(text, "restart_n", str(count))
    args.runconfig.write_text(text, encoding="utf-8")
    print(f"Set {args.runconfig} to profile {args.profile}: {count} {option}")


if __name__ == "__main__":
    main()
