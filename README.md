# Static-shelf ISOMIP through NUOPC on Gadi

This control runs MOM6 with a fixed ice-shelf geometry through the ACCESS-OM3 NUOPC driver and CMEPS (`MED OCN`). MOM6 reads geometry from `INPUT/Ocean0_3D_Claire.nc`; there is no active atmosphere, runoff or ice-sheet component. Shelf melt, heat exchange and drag respond to the ocean while the prescribed geometry stays fixed.

It preserves the June 2026 idealised warm reference and its 900 kg/m³ ice density. It is a starting point for ocean parameter tests, not a claim of complete ISOMIP+ protocol compliance. The retained atmosphere/runoff stream files and small placeholder inputs support Payu staging; they do not force the ocean in this configuration.

## Get and check the control

Once the sharing branch is published:

```bash
git clone --branch share-med-ocn-static \
  https://github.com/reillyja/isomip-test-mom6-for-iom3-configs.git isomip-med-ocn
cd isomip-med-ocn

module use /g/data/vk83/modules
module load payu/1.3.2
/usr/bin/python3 tools/verify_handoff.py
```

All inputs are tracked in Git (about 3.6 MB); there is no separate download. The executable stays on Gadi at:

```text
/g/data/au88/jr5971/access3-share-isomip/install-mom6-isomip/bin/access-om3-MOM6
```

The verification script checks this configured executable and every input against the recorded SHA-256 values. A colleague needs read/execute access to that installation and access to the `au88` and `vk83` storage used in `config.yaml`. If the executable is relocated, update `exe` and verify the copied binary. A hosted stock executable is not a validated substitute.

## Stage and run

The default duration is two 300-second steps. The ocean uses 48 ranks (`16 × 3` layout), plus one mediator rank: 49 CPUs in total.

```bash
isomip_lab=/scratch/au88/$USER/isomip-med-ocn-smoke
payu setup --lab "$isomip_lab"
```

Inspect `work/nuopc.runconfig`: components must be `MED OCN`, `ATM_model=satm`, `ROF_model=srof`, `zero_missing_imports=true`, and `apply_startup_lag=false`. The checked-in `datm/drof` labels are required by Payu 1.3.2; the setup hook changes only the staged configuration. See [NUOPC_ISOMIP.md](NUOPC_ISOMIP.md).

After inspecting staging, remove the staged work directory with `payu sweep --lab "$isomip_lab"`. To submit the smoke run yourself:

```bash
payu run --lab "$isomip_lab" -n 1
```

This sharing preparation did not submit any new model runs. [VALIDATION.md](VALIDATION.md) records the setup checks and the existing June numerical evidence.

## Ocean parameter experiments

Edit `MOM_override` for the chosen parameter. Start each member in a separate checkout with a separate laboratory, and retain its config/diff and executable/input identities. Keep geometry, timestep and decomposition fixed when testing a single parameter. Configure duration before starting a fresh experiment:

```bash
python3 tools/set_duration_profile.py day
# Other profiles: smoke, half-day, month, 45-day, three-month.
```

Edit `project`, `shortpath` and storage requests in `config.yaml` if using another allocation. Use a new laboratory name for each independent cold start; subsequent Payu segments in an existing laboratory are continuations. Do not set `input_filename='n'` in `input.nml`, as that overrides the restart filename supplied by the cap. The comparison helpers in `tools/` require NumPy and netCDF4; staging and the checksum helper do not.

## Implementation and provenance

[MOM_CAP_NOTES.md](MOM_CAP_NOTES.md) explains the cap and supporting shelf changes needed for the June control. They are already compiled into the pinned executable. No new MOM6 or CMEPS changes are introduced by this branch.

The original geometry/control was assembled by Claire Yung from the [MOM6-examples ISOMIP/rho case](https://github.com/NOAA-GFDL/MOM6-examples/tree/dev/gfdl/ocean_only/ISOMIP/rho); John Reilly prepared the NUOPC parity configuration. Attribution to those inputs is retained; this branch does not assign a new license to them. Vendored ACCESS-NRI archive helpers retain their headers and Apache-2.0 license in `tools/archive_scripts/`.

[provenance/baseline.json](provenance/baseline.json) records the original control commit, historical model bases, executable/input hashes and archive-helper origins. The current MOM6 working tree contains later changes and is not an exact June source snapshot.
