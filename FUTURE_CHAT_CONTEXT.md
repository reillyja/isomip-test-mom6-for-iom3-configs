# ISOMIP MOM6 Project Context

Last updated: 2026-06-14

Use this file as the starting context for future chats about the ISOMIP MOM6
work on Gadi.

## Goal

Run the same atmosphere-free ISOMIP experiment through three paths:

1. MOM6's `mom6-solo` executable.
2. Stock `access-om3-MOM6` with CMEPS as an ocean-only `MED OCN` system.
3. A toy NUOPC mediator that explicitly supplies zero forcing to MOM6.

The three paths should use equivalent inputs and timing, support restarts, and
produce comparable ocean and ice-shelf results.

## Current Result

All three paths are working.

The following tests passed:

| Test | Solo | CMEPS | Toy mediator |
| --- | --- | --- | --- |
| Two 300-second cycles | PASS | PASS | PASS |
| One day | PASS | PASS | PASS |
| One month | PASS | PASS | PASS |
| 90 days | PASS | PASS | PASS |
| 12-hour + 12-hour restart | n/a | Bitwise exact | Bitwise exact |
| 45-day + 45-day restart | n/a | Bitwise exact | Bitwise exact |

At 90 days, both NUOPC paths were bitwise identical to solo for the checked
prognostic, surface-forcing, and ice-shelf diagnostics. Continuous and split
NUOPC runs were also bitwise restart reproducible.

The common runtime is:

```text
MOM6 DT = 300 seconds
MOM6 DT_FORCING = 300 seconds
coupling interval = 300 seconds
ocean layout = 16 x 3
ocean ranks = 48
```

Solo uses model year 1 and NUOPC uses model year 1900, so comparisons are
aligned by elapsed time rather than absolute date.

## Important Directories

```text
# Validated solo Payu configuration
/g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs

# Ocean-only CMEPS Payu configuration
/g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs-nuopc-ocean-only

# Toy mediator source and launch scripts
/g/data/au88/jr5971/issm_simple_mediator

# Locally patched MOM6 source and installed Mom6lib
/g/data/au88/jr5971/MOM6-isomip-nuopc

# Locally built access-om3-MOM6 driver
/g/data/au88/jr5971/access3-share-isomip

# Obsidian research vault
/g/data/au88/jr5971/ISSM-MOM6-notes

# Preserved comparison runs
/scratch/au88/jr5971/isomip-comparison
```

## Three Execution Paths

### MOM6 Solo

The solo configuration uses MOM6's internal idealized surface-forcing path.
For this ISOMIP case, external atmospheric stress and flux forcing are zero,
while MOM6 still calculates its configured gustiness and ice-shelf physics.

The validated prerelease executable came from:

```bash
module use /g/data/vk83/prerelease/modules
module load access-om3/pr218-3
```

The originally proposed `pr218-1` module referred to an installation that had
been removed and was not runnable.

### CMEPS Ocean-Only

The executable contains CMEPS and MOM6, but the active component list is:

```text
MED OCN
```

There is no atmosphere or runoff component advancing in the run sequence.
Payu 1.3.2 requires the checked-in control file to retain:

```text
ATM_model = datm
ROF_model = drof
```

The Payu setup hook:

```text
tools/patch_ocean_only_runconfig.py
```

changes only the staged `work/nuopc.runconfig` to:

```text
ATM_model = satm
ROF_model = srof
```

It also creates small ATM/ROF bookkeeping files needed by Payu archival.
These labels do not make CMEPS generate MOM6-ready zero fluxes.

The patched MOM6 cap instead uses:

```text
zero_missing_imports = true
apply_startup_lag = false
```

`zero_missing_imports=true` initializes disconnected atmosphere, radiation,
stress, precipitation, runoff, pressure, and enthalpy imports to zero and
checks that they are finite.

### Toy Mediator

The separate `mom6-simple-mediator` executable connects:

```text
ZeroForcing -> MOM6
MOM6
MOM6 -> OceanSink
ZeroForcing
```

`ZeroForcing` advertises all 22 MOM6 import fields, realizes them as R8,
writes exact zero values during initialization and every advance, marks them
updated, and rejects non-finite values.

This path intentionally uses:

```text
zero_missing_imports = false
```

It therefore tests the connected MOM6 NUOPC import interface rather than the
cap's missing-field fallback. `OceanSink` accepts the MOM6 exports needed for
NUOPC geometry negotiation but does not affect the ocean.

The existing ISSM toy target remains separate because the hosted ISSM and
ACCESS3 MOM6 stacks use incompatible compiler, MPI, and ESMF ABIs.

## MOM6 Cap Issue And Fix

The original `state_getimport_2d` helper copies a field when it exists but
leaves the destination unchanged when it is absent. That is safe only when
the caller initialized the destination first.

The original NUOPC cap allocated temporary `taux` and `tauy` arrays without
initializing them. With no connected atmosphere, absent stress fields could
therefore leave undefined memory that later appeared as NaNs. The first
coupling call could look successful because the legacy cold-start logic
skipped the first MOM6 advance; the failure then appeared during the first
real advance, often in `reproducing_EFP_sum`.

`reproducing_EFP_sum` detected the invalid value but was not its source.

The local patch:

- adds `zero_missing_imports`, defaulting to `false`;
- initializes all relevant import destinations when it is enabled;
- allocates temporary stress arrays with zero sources;
- checks and logs import minima and maxima;
- rejects non-finite imports;
- guards zero stress so `atan2(0,0)` produces zero wind direction;
- fixes ice-shelf initialization, stress allocation, and restart handling;
- initializes `OS%flux_tmp`;
- adds `apply_startup_lag`, defaulting to `true`.

Both validated NUOPC paths set `apply_startup_lag=false`. Otherwise the first
actual ocean advance can cover 600 seconds with only one ice-shelf flux
evaluation, which does not match the 300-second solo sequence.

Important MOM6 files:

```text
config_src/drivers/nuopc_cap/mom_cap.F90
config_src/drivers/nuopc_cap/mom_cap_methods.F90
config_src/drivers/nuopc_cap/mom_ocean_model_nuopc.F90
config_src/drivers/nuopc_cap/mom_surface_forcing_nuopc.F90
src/ice_shelf/MOM_ice_shelf.F90
```

## Source And Git State

### Ocean-Only Configuration

```text
Repository: isomip-test-mom6-for-iom3-configs
Branch: nuopc-isomip-zero-forcing
Commit: a9fd74a
Remote: origin/nuopc-isomip-zero-forcing
Status on 2026-06-14: clean and pushed
```

This branch was created from `nuopc-isomip`, not as a separate repository.

### Patched MOM6

```text
Directory: /g/data/au88/jr5971/MOM6-isomip-nuopc
Branch: isomip-nuopc-zero-forcing
Base tag: 2026.01.001
Base commit: c664721ebd58c033964b502e7fcdcccd05f02947
```

The five source files listed above are modified but uncommitted. Build and
install directories are also untracked. Publishing these MOM6 changes is the
main remaining source-control task.

### Toy Mediator

`/g/data/au88/jr5971/issm_simple_mediator` is not currently a Git repository.
Its MOM6 target, zero-forcing component, runtime YAML, launch scripts, restart
support, and validation checker exist only in that directory unless they are
published separately.

### Solo Configuration

The solo repository is on `master` at `e890ddf`. It has local generated logs,
archive links, tools, and modified manifests. Review those deliberately
before committing; do not add generated run products by accident.

## Built Artifact Hashes

```text
libaccess-mom6lib.a
16f796d8a4276bdd83ed5503ad01b12bd6d744c3f2e710c94c06d199aa74bda1

access-om3-MOM6
6d9cb9566606019b6c690a7c12cbbc7a82840ea248ff08d3578d7411fbc32777

mom6-simple-mediator
30dc350e47a8da00b0f6e253430872232b568271b62d14e9818d9d8d3082e762
```

## Validation And Run Documentation

Start with:

```text
ISOMIP_THREE_PATH_RUNBOOK.md
COMMANDS.md
MOM6_BOUNDARY_FORCING.md
CHAT_SUMMARY.md
```

`ISOMIP_THREE_PATH_RUNBOOK.md` contains build commands, duration profiles,
run commands, restart procedures, output locations, hashes, and comparison
commands.

Validate toy transfer dumps with:

```bash
cd /g/data/au88/jr5971/issm_simple_mediator
python3 tools/check_mom6_zero_forcing.py \
  /scratch/au88/jr5971/mom6_simple_mediator/isomip-zero-forcing
```

The latest checked transfer files contained 22 finite exact-zero imports and
finite MOM6 exports. Some older timestamped logs in the same scratch tree are
failed development runs, so always match logs to the relevant run timestamp.

## Obsidian Vault

The standalone vault at `/g/data/au88/jr5971/ISSM-MOM6-notes` contains curated
ISSM/MOM6 notes plus generated source cards. Its generator is:

```bash
python3 scripts/build_notes.py --write
python3 scripts/build_notes.py --check
```

The completed baseline represented 70 Markdown source paths as 50 deduplicated
source cards. The vault may be copied or synchronized to a local machine and
opened directly in Obsidian; no plugins are required.

## Sensible Next Work

1. Commit the patched MOM6 source on a publishable feature branch, excluding
   build and install products.
2. Put `issm_simple_mediator` under version control and publish the MOM6 toy
   target separately from any incompatible ISSM build artifacts.
3. Decide whether to open pull requests for the ocean-only configuration and
   MOM6 cap changes.
4. Update documentation if executable builds or hashes change.
5. Preserve the validated scratch results until the published revisions can
   reproduce them.

