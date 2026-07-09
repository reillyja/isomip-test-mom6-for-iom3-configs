#!/usr/bin/env python3
"""Set a named duration in the MOM6-solo input.nml."""

from argparse import ArgumentParser
from pathlib import Path
import re


PROFILES = {
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


def replace_setting(text: str, key: str, value: int) -> str:
    pattern = rf"^(\s*{re.escape(key)}\s*=\s*)\d+(\s*,?\s*)$"
    updated, count = re.subn(
        pattern,
        rf"\g<1>{value}\g<2>",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise RuntimeError(f"Expected one {key} setting, found {count}")
    return updated


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("profile", choices=PROFILES)
    parser.add_argument("--input-nml", type=Path, default=Path("input.nml"))
    args = parser.parse_args()

    values = dict(zip(("months", "days", "hours", "minutes", "seconds"), PROFILES[args.profile]))
    text = args.input_nml.read_text(encoding="utf-8")
    for key, value in values.items():
        text = replace_setting(text, key, value)
    args.input_nml.write_text(text, encoding="utf-8")
    print(f"Set {args.input_nml} to profile {args.profile}")


if __name__ == "__main__":
    main()
