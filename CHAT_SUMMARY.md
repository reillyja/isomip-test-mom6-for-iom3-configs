# ISOMIP MOM6 payu Work Summary

## Objective

The work investigated the ISOMIP run directory at:

```text
/g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs
```

The goal was to understand its structure and make it runnable with the Gadi
`payu` run manager and a Spack prerelease `mom6-solo` executable.

## Run directory structure

- `config.yaml` controls Gadi resources, modules, executable staging, storage,
  and the scratch laboratory.
- `input.nml` selects the ocean-solo driver and sets the run duration.
- `MOM_input` contains the base MOM6 parameters.
- `MOM_override` contains ISOMIP-specific parameter changes.
- `diag_table` selects diagnostics and output frequency.
- `INPUT/Ocean0_3D_Claire.nc` supplies ice-shelf thickness and surface
  pressure.
- `manifests/` records the exact executable, input, and restart files staged
  by `payu`.
- `work` and `archive` are generated links into the scratch laboratory.

## payu findings

The supported run manager module is:

```text
payu/1.3.2 from /g/data/vk83/modules
```

The final configuration uses:

```yaml
project: au88
laboratory: mom6-isomip
queue: normalsr
ncpus: 48
model: mom6
exe: mom6-solo
```

The executable targets `x86_64_v4`, so the Sapphire Rapids `normalsr` queue
is required. The configured platform has a node size of 104 CPUs and 512 GB
of memory. `payu` requests 192 GB for the 48-rank job.

The working MOM6 decomposition is:

```text
NIPROC = 16
NJPROC = 3
LAYOUT = 16, 3
```

## Executable findings

The initially proposed module was:

```text
access-om3/pr218-1
```

Its module metadata still existed, but its installation prefix had been
removed. It could not provide a runnable executable.

The replacement is:

```text
access-om3/pr218-3
```

It provides:

```text
access-mom6@2026.01.001 +access3 +mom6_solo ~asymmetric_mem ~openmp
MOM6 commit c664721ebd58c033964b502e7fcdcccd05f02947
```

The exact executable is:

```text
/g/data/vk83/prerelease/apps/spack/1.1/release/linux-x86_64_v4/access-mom6-2026.01.001-w6trlhkn2glyynvlunh4lctsaqb2rtpc/bin/mom6-solo
```

Its MD5 hash is:

```text
db2cfe090478f00d99b256b70c71e3b8
```

The `access-om3-MOM6` executable is the NUOPC coupled driver and is not
appropriate for this ocean-only run.

## Configuration changes

`config.yaml` was updated to:

- Use project `au88` and `/scratch/au88`.
- Load `access-om3/pr218-3` inside the batch job.
- Stage `mom6-solo` by executable name.
- Use the local `INPUT` directory.
- Run on `normalsr` with 48 MPI ranks.
- Use `openmpi/4.1.7`.
- Declare the required `au88` and `vk83` storage.
- Require `payu` version 1.3.2.

The executable and input manifests now point to accessible files and contain
their verified hashes. The restart manifest remains empty for a fresh run.

The final configured duration is three months, or 90 model days.

## MOM6 grounding report

The first successful three-month run produced a 627 MB `mom6.err` file. MOM6
was repeatedly reporting:

```text
applyBoundaryFluxesInOut(): Mass created
```

Source inspection at the exact MOM6 commit showed that MOM6 was clipping
residual boundary mass flux when very thin columns would otherwise ground.
The numerical correction was also recorded in the `created_H` diagnostic.

The following documented parameter was added to `MOM_override`:

```text
#override IGNORE_FLUXES_OVER_LAND = True
```

This suppresses the per-step report while retaining the numerical clipping
and diagnostic accounting. Three duplicate overrides that MOM6 was already
ignoring were also removed.

The one-day run before and after this parameter change was compared.
All NetCDF outputs, all restart files, and `ocean.stats` were bit-for-bit
identical. `mom6.err` decreased from about 6.9 MB to 3.7 KB.

## Validation jobs

Three PBS jobs completed successfully:

| Purpose | Job ID | Walltime | Exit status |
| --- | --- | --- | --- |
| Initial one-day smoke test | `170064739.gadi-pbs` | 41 seconds | 0 |
| Three-month validation | `170065761.gadi-pbs` | 6 minutes 8 seconds | 0 |
| Logging-change smoke test | `170069140.gadi-pbs` | 2 minutes 23 seconds | 0 |

The three-month run:

- Reached model date `0001-04-01T00:00:00`.
- Completed 10,800 time steps.
- Produced finite temperature, salinity, velocity, forcing, and melt fields.
- Wrote valid MOM6 and ice-shelf restart files.
- Used approximately 11 GB of memory.
- Produced 18 five-day averaged records and 90 daily forcing and ice
  records.

The completed three-month output is preserved under:

```text
/scratch/au88/jr5971/mom6-isomip-validation-20260605/archive/isomip-test-mom6-for-iom3-configs
```

## Current state

The production laboratory is:

```text
/scratch/au88/jr5971/mom6-isomip
```

It has been reset to a clean fresh-run state. `payu setup --reproduce
--archive` successfully staged the final configuration, executable, input,
and empty restart manifest. The temporary work directory was then removed
with `payu sweep`.

The repository's `archive` link points to the fresh production archive. A
new run can be submitted with:

```bash
module use /g/data/vk83/modules
module load payu/1.3.2
payu run --reproduce
```

Pre-existing coupled-run logs and environment files were left untouched.
The implementation changes are present in the working tree but have not been
committed.

## NUOPC Completion

Subsequent work completed two atmosphere-free NUOPC paths using the same
patched MOM6 library:

1. Stock `access-om3-MOM6` with CMEPS `MED OCN`, staged `satm/srof`, and
   `zero_missing_imports=true`.
2. `mom6-simple-mediator` with a connected `ZeroForcing` component that
   supplies all 22 accepted MOM6 import fields as finite exact zeros.

The matched runtime now uses:

```text
MOM6 DT = 300 seconds
MOM6 DT_FORCING = 300 seconds
coupling interval = 300 seconds
layout = 16 x 3
ocean ranks = 48
```

The local MOM6 worktree is:

```text
/g/data/au88/jr5971/MOM6-isomip-nuopc
branch: isomip-nuopc-zero-forcing
base: 2026.01.001, c664721ebd58c033964b502e7fcdcccd05f02947
```

It includes ice-shelf initialization and restart fixes, import zeroing and
finite checks, a zero-stress wind-direction guard, and
`apply_startup_lag=false` for exact 300-second parity with solo.

Smoke, one-day, one-month, and 90-day runs completed for all three paths.
The 90-day solo, CMEPS, and toy results are bitwise identical for the checked
prognostic, forcing, and shelf diagnostics. Both NUOPC paths are also bitwise
restart reproducible for one-day 12+12-hour and 90-day 45+45-day splits.

The current commands, executable hashes, result paths, and full validation
matrix are recorded in:

```text
ISOMIP_THREE_PATH_RUNBOOK.md
COMMANDS.md
```
