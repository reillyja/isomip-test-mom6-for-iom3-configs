#!/usr/bin/env python3
"""Apply atmosphere-free runtime settings after Payu stages the case.

Payu 1.3.2's access-om3 adapter requires datm/drof in the control file and
expects their restart pointers during archival. CMEPS receives satm/srof in
the staged file; the tiny pointer targets created here are Payu bookkeeping
only and are never read by the executable.
"""

from pathlib import Path
import re


RUNCONFIG = Path("work/nuopc.runconfig")


def replace_setting(text: str, key: str, old: str, new: str) -> str:
    pattern = re.compile(
        rf"^(\s*{re.escape(key)}\s*=\s*){re.escape(old)}(\s*)$",
        re.MULTILINE,
    )
    updated, count = pattern.subn(rf"\g<1>{new}\g<2>", text)
    if count != 1:
        raise RuntimeError(
            f"Expected one '{key} = {old}' entry in {RUNCONFIG}, found {count}"
        )
    return updated


def write_payu_stub(realm: str) -> None:
    work = RUNCONFIG.parent
    restart_name = f"payu_stub.{realm}.r"
    pointer = work / f"rpointer.{realm}"
    restart = work / restart_name
    for path in (pointer, restart):
        if path.is_symlink():
            path.unlink()
    pointer.write_text(f"{restart_name}\n", encoding="ascii")
    restart.write_text(
        "Payu bookkeeping stub for an intentionally absent component.\n",
        encoding="ascii",
    )


def main() -> None:
    text = RUNCONFIG.read_text(encoding="utf-8")
    if not re.search(r"^component_list:\s+MED\s+OCN\s*$", text, re.MULTILINE):
        raise RuntimeError("Ocean-only component_list is missing from staged nuopc.runconfig")

    text = replace_setting(text, "ATM_model", "datm", "satm")
    text = replace_setting(text, "ROF_model", "drof", "srof")
    RUNCONFIG.write_text(text, encoding="utf-8")
    write_payu_stub("atm")
    write_payu_stub("rof")
    print(f"Patched staged ocean-only runtime settings in {RUNCONFIG}")


if __name__ == "__main__":
    main()
