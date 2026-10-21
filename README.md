# Static-shelf ISOMIP through NUOPC on Gadi

This control runs MOM6 with a fixed ice-shelf geometry through the ACCESS-OM3 NUOPC driver and CMEPS (`MED OCN`). MOM6 reads geometry from `INPUT/Ocean0_3D_Claire.nc`; there is no active atmosphere, runoff or ice-sheet component. Shelf melt, heat exchange and drag respond to the ocean while the prescribed geometry stays fixed.

It preserves the June 2026 idealised warm reference and its 900 kg/m³ ice density. It is a starting point for ocean parameter tests, not a claim of complete ISOMIP+ protocol compliance. The retained atmosphere/runoff stream files and small placeholder inputs support Payu staging; they do not force the ocean in this configuration.

## Get and check the control

Clone the sharing branch:

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

Inspect `work/nuopc.runconfig`: components must be `MED OCN`, `ATM_model=satm`, `ROF_model=srof`, `zero_missing_imports=true`, and `apply_startup_lag=false`. The checked-in `datm/drof` labels are required by Payu 1.3.2; the setup hook changes only the staged configuration. See [runtime and restart notes](#nuopc-runtime-and-restart-details).

After inspecting staging, remove the staged work directory with `payu sweep --lab "$isomip_lab"`. To submit the smoke run yourself:

```bash
payu run --lab "$isomip_lab" -n 1
```

This sharing preparation did not submit any new model runs. [validation record](#validation-record) records the setup checks and the existing June numerical evidence.

## Ocean parameter experiments

Edit `MOM_override` for the chosen parameter. Start each member in a separate checkout with a separate laboratory, and retain its config/diff and executable/input identities. Keep geometry, timestep and decomposition fixed when testing a single parameter. Configure duration before starting a fresh experiment:

```bash
python3 tools/set_duration_profile.py day
# Other profiles: smoke, half-day, month, 45-day, three-month.
```

Edit `project`, `shortpath` and storage requests in `config.yaml` if using another allocation. Use a new laboratory name for each independent cold start; subsequent Payu segments in an existing laboratory are continuations. Do not set `input_filename='n'` in `input.nml`, as that overrides the restart filename supplied by the cap. The comparison helpers in `tools/` require NumPy and netCDF4; staging and the checksum helper do not.

## Implementation and provenance

[MOM cap notes](#mom-cap-notes) explains the cap and supporting shelf changes needed for the June control. They are already compiled into the pinned executable. No new MOM6 or CMEPS changes are introduced by this branch.

The original geometry/control was assembled by Claire Yung from the [MOM6-examples ISOMIP/rho case](https://github.com/NOAA-GFDL/MOM6-examples/tree/dev/gfdl/ocean_only/ISOMIP/rho); John Reilly prepared the NUOPC parity configuration. Attribution to those inputs is retained; this branch does not assign a new license to them. Vendored ACCESS-NRI archive helpers retain their headers and Apache-2.0 license in `tools/archive_scripts/`.

[provenance/baseline.json](provenance/baseline.json) records the original control commit, historical model bases, executable/input hashes and archive-helper origins. The current MOM6 working tree contains later changes and is not an exact June source snapshot.


## NUOPC runtime and restart details

The [README](README.md) is the quick start and [MOM cap notes](#mom-cap-notes) explain the implementation.

`component_list: MED OCN` runs a single mediator rank and 48 ocean ranks. All atmosphere/runoff imports are disconnected and initialized to zero by the patched cap. MOM6 retains internally calculated shelf pressure, melting/freezing, drag and configured gustiness. Geometry is read directly by MOM6 and held fixed.

The checked-in `nuopc.runconfig` uses `ATM_model=datm` and `ROF_model=drof` solely for Payu 1.3.2 compatibility. After Payu stages files, the setup hook changes the staged labels to `satm/srof`. It also creates regular `rpointer.atm`, `rpointer.rof` and corresponding `payu_stub.*.r` targets for Payu bookkeeping. They are not scientific restarts and are not read by CMEPS.

For a fresh experiment, use a new laboratory and `start_type=startup`. Payu manages continuation state when another segment is run in an existing laboratory. A complete real continuation needs the mediator and ocean restart/pointers and `Shelf.res.nc`, as well as the bookkeeping files expected by Payu. Do not add `input_filename='n'` to `input.nml`; it overrides the ocean filename provided by `rpointer.ocn` and prevents correct continuation.

The cold-start configuration has no saved restart manifest or pointers. New Payu manifests are generated locally and ignored by Git. The immutable baseline hashes live separately under `provenance/`.

The existing June comparisons used different calendar epochs for solo and NUOPC (year 1 versus year 1900). Compare by elapsed time. The sharing default is a two-step smoke, not the historical 90-day duration; use `tools/set_duration_profile.py three-month` in a new experiment to select that duration.


## MOM cap notes

These are the changes recorded for the validated June 2026 executable. They let MOM6 run through NUOPC without atmosphere/runoff forcing while retaining shelf physics and matching the solo reference. This sharing branch changes configuration packaging and documentation only; it does not edit model source.

| Change | Why it was needed |
| --- | --- |
| Optional `zero_missing_imports` | A NUOPC ocean cap normally expects atmosphere/runoff inputs. Initialize disconnected imports to zero before reading any connected fields so missing fields do not leave undefined values. This control explicitly enables the option; its model default is false. |
| Finite import checks and extrema diagnostics | Detect undefined forcing and make the atmosphere-free setup inspectable. Zero atmospheric pressure import does not remove internally calculated ice-shelf pressure. |
| Separate/masked shelf force and flux initialization | Initialize ice-shelf pressure, basal fluxes and stresses through the coupled driver, including the correct masks. An absent atmosphere must not disable shelf forcing. |
| Temporary flux-buffer initialization (`OS%flux_tmp`) and shelf-stress allocation | Allocate and initialize the working arrays used by the NUOPC forcing path instead of relying on the solo driver's setup. |
| Zero-stress wind-direction guard | Give zero wind direction for zero stress rather than evaluating `atan2(0,0)`. |
| Optional `apply_startup_lag` | Set false here so each 300-second driver call advances exactly 300 seconds. The retained legacy cold-start skip had produced a first advance of 600 seconds with only one shelf-flux evaluation and did not match solo. The model default remains true. |
| Shelf restart I/O using `additional_restart_dir` | Read and write `Shelf.res.nc` alongside the ocean continuation state so a continuation restores the shelf instead of silently reinitializing it. |

The work involved `mom_cap.F90`, `mom_cap_methods.F90`, `mom_ocean_model_nuopc.F90`, `mom_surface_forcing_nuopc.F90` and supporting `MOM_ice_shelf.F90` changes. Shelf initialization/restart work was not confined to the cap itself. There is no GLC geometry import in this control and no custom geometry routing required in CMEPS.

### Settings retained for parity

```text
component_list: MED OCN
zero_missing_imports = true
apply_startup_lag = false
MOM6 DT = DT_FORCING = coupling interval = 300 seconds
ICE_SHELF_USTAR_FROM_VEL_BUGFIX = False
```

The last setting is the historical answer-compatibility choice, not a new fix made for this handoff. Preserve the 900 kg/m³ ice density and matching initial-pressure scale (8820 Pa/m) when reproducing this reference.

### Payu compatibility is separate from the model changes

Payu 1.3.2's ACCESS-OM3 adapter expects `datm/drof` labels and their archival pointers. `tools/patch_ocean_only_runconfig.py` changes the staged labels to `satm/srof` and writes tiny bookkeeping files for those absent components. CMEPS runs only MED and OCN and does not consume the bookkeeping files. The run sequence has no MED→OCN forcing transfer.

The local archive hook standardizes archived filenames and packages any ESMF trace streams. Its copied Python helpers are ordinary Payu postprocessing, not MOM cap code.

### Source and evidence limits

The June MOM6 base was `c664721ebd58c033964b502e7fcdcccd05f02947` (`2026.01.001`), with uncommitted local changes; ACCESS3 used `825a3f4835bb088b12f68babe0149b017b16ba72` (`2026.03.000`). These base commits alone do not rebuild the patched executable. Reusing the hash-verified executable is the supported Gadi handoff; a source rebuild would need an independently recovered and checked June patch set.

The behavioral list and numerical evidence come from the historical `ISOMIP_THREE_PATH_RUNBOOK.md` before this documentation cleanup. [validation record](#validation-record) preserves its comparison details and job IDs. Do not interpret later evolving-geometry/ISSM source changes as requirements for this static case.


## Validation record

### Sharing preparation — 22 October 2026

No new ocean/model experiments were run or submitted. The Gadi handoff reuses the preserved June executable:

```text
access-om3-MOM6
SHA-256: 6d9cb9566606019b6c690a7c12cbbc7a82840ea248ff08d3578d7411fbc32777
```

The input files and reference physics files match the original control at `a9fd74a4a4d1d43230598f4708b631ad36d974bf`. This branch changes packaging/documentation, localizes the archive hook, and selects a two-step smoke duration. It does not alter MOM6 physics or geometry.

Preparation checks passed in an isolated scratch copy with Payu 1.3.2:

- All 18 input-file checksums and the configured executable match the reference.
- `payu setup` succeeds without old manifests, restart files or metadata.
- Staged components are MED/OCN with 48 ocean ranks and one mediator rank.
- Staged atmosphere/runoff labels are `satm/srof`; both bookkeeping pointers resolve to regular files.
- `zero_missing_imports=true`, `apply_startup_lag=false`, `start_type=startup`, and a two-step stop are retained.
- Every input link resolves, no real OCN/CMEPS restart pointer is inherited, and the staged configuration does not refer to the original control directory.
- The archive hook correctly renames a synthetic MOM output file, preserves stream content and metadata, and removes loose streams after creating their tar archive.
- `payu sweep` removes only the isolated staged work directory.

A fresh Git clone of runtime commit `2866f9d` also passes the documented setup command and checksum check, with a clean working tree after staging. Logs and machine-readable checks are retained under `provenance/`. The smoke profile has been staged, not newly integrated.

### Existing numerical evidence — 8–9 June 2026

The original three-path comparison used MOM6-solo, stock CMEPS `MED OCN`, and the toy mediator with matching 300-second ocean/forcing timesteps and a 16×3 ocean layout.

| Test | Historical result |
| --- | --- |
| 600-second smoke, one day, one month, 90 days | All three paths passed |
| Ocean temperature, salinity, velocity, thickness and interface height at 90 days | Bitwise equal to solo |
| Compared surface forcing and shelf pressure/melt/heat/stress diagnostics | Bitwise equal to solo |
| Common prognostic restart fields | Equal to solo, excluding the absolute-time `ave_ssh` accumulator |
| 12+12-hour and 45+45-day continuous/split tests | All 21 MOM restart variables and all three shelf variables equal; all 23 common numeric CMEPS restart variables equal |

Recorded jobs: solo 90-day `170282886`, CMEPS 90-day `170282887`, toy 90-day `170283761`, CMEPS split `170283788` and `170285364`, toy split `170283762` and `170285351`.

The historical record was `ISOMIP_THREE_PATH_RUNBOOK.md` before this cleanup; its comparison details and job IDs are reproduced above. The local reference is `/g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs/ISOMIP_THREE_PATH_RUNBOOK.md`. Historical outputs remain under `/scratch/au88/jr5971/isomip-comparison/`; they are evidence, not runtime dependencies of this sharing branch.

This evidence concerns the June static geometry and executable. It does not establish equivalence to the later Ocean3 GLCSTUB configuration, validate another executable or geometry, or predict the scientific results of new parameter choices.
