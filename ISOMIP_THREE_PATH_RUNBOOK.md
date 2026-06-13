# ISOMIP Three-Path Runbook

This runbook reproduces the matched ISOMIP tests through:

| Path | Directory | Forcing interface | Ranks |
| --- | --- | --- | --- |
| MOM6 solo | `/g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs` | MOM6 solo forcing | 48 |
| Stock CMEPS | `/g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs-nuopc-ocean-only` | Disconnected imports initialized to zero | 48 OCN + 1 MED |
| Toy mediator | `/g/data/au88/jr5971/issm_simple_mediator` | 22 connected exact-zero fields | 48 |

All paths use a 300-second MOM6 timestep, 300-second forcing/coupling
interval, and a `16 x 3` ocean layout.

## Validated Result

The completed tests on June 8-9, 2026 all passed:

| Test | Solo | CMEPS | Toy |
| --- | --- | --- | --- |
| 600-second smoke | PASS | PASS | PASS |
| One day | PASS | PASS | PASS |
| January 1 to February 1 | PASS | PASS | PASS |
| January 1 to April 1, 90 days | PASS | PASS | PASS |
| 12-hour + 12-hour restart | n/a | Bitwise exact | Bitwise exact |
| 45-day + 45-day restart | n/a | Bitwise exact | Bitwise exact |

At 90 days, both NUOPC paths are bitwise identical to solo for:

- `temp`, `salt`, `u`, `v`, `h`, and interface height `e`;
- `taux`, `tauy`, `ustar`, `PRCmE`, `LwLatSens`, and `sensible`;
- `p_surf`, `mass_flux`, `melt_rate`, `tflux_shelf`, and `ustar_shelf`;
- 20 common numeric MOM6 prognostic restart variables, excluding the
  absolute-time diagnostic accumulator `ave_ssh`;
- all three shelf restart variables.

Continuous and split runs are bitwise exact for all 21 MOM6 restart
variables, all three shelf variables, and, for CMEPS, all 23 common numeric
coupler restart variables.

## Source And Executables

The patched MOM6 worktree is:

```text
/g/data/au88/jr5971/MOM6-isomip-nuopc
branch: isomip-nuopc-zero-forcing
base commit: c664721ebd58c033964b502e7fcdcccd05f02947
base tag: 2026.01.001
```

The working tree contains the uncommitted ISOMIP NUOPC changes. The important
files are:

```text
config_src/drivers/nuopc_cap/mom_cap.F90
config_src/drivers/nuopc_cap/mom_cap_methods.F90
config_src/drivers/nuopc_cap/mom_ocean_model_nuopc.F90
config_src/drivers/nuopc_cap/mom_surface_forcing_nuopc.F90
src/ice_shelf/MOM_ice_shelf.F90
```

Built artifacts:

| Artifact | SHA-256 |
| --- | --- |
| `libaccess-mom6lib.a` | `16f796d8a4276bdd83ed5503ad01b12bd6d744c3f2e710c94c06d199aa74bda1` |
| `access-om3-MOM6` | `6d9cb9566606019b6c690a7c12cbbc7a82840ea248ff08d3578d7411fbc32777` |
| `mom6-simple-mediator` | `30dc350e47a8da00b0f6e253430872232b568271b62d14e9818d9d8d3082e762` |

The stock executable MD5 recorded by Payu is:

```text
69d45364a056d436b4fc1fc44109388a
```

## MOM6 Cap Changes

The local MOM6 library includes:

- separate and masked ice-shelf force/flux initialization;
- initialization of `OS%flux_tmp`;
- NUOPC shelf-stress allocation;
- shelf restart read/write through `additional_restart_dir`;
- a zero-stress guard so `atan2(0,0)` gives zero wind direction;
- `zero_missing_imports`, defaulting to `false`;
- finite/minimum/maximum checks for imported forcing;
- `apply_startup_lag`, defaulting to `true`.

Both validated NUOPC configurations set:

```text
apply_startup_lag = false
```

This makes every 300-second driver call advance MOM6 by 300 seconds. Retaining
the legacy cold-start skip caused the first advance to cover 600 seconds with
only one ice-shelf flux evaluation and did not match solo.

`ICE_SHELF_USTAR_FROM_VEL_BUGFIX=False` is retained for parity with the
validated solo executable.

## Build The Shared MOM6 Library

```bash
module purge
module load intel-compiler-llvm/2025.2.0
module load openmpi/4.1.7
module use /g/data/vk83/modules
module load access-om3/2026.03.000

cd /g/data/au88/jr5971/MOM6-isomip-nuopc

cmake -S . -B build-access3-isomip \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PWD/install-access3-isomip" \
  -DMOM6_ACCESS3=ON \
  -DMOM6_SOLO=OFF \
  -DMOM6_OPENMP=OFF \
  -DCMAKE_Fortran_COMPILER="$(command -v ifx)"

cmake --build build-access3-isomip --parallel 16
cmake --install build-access3-isomip
```

## Build Stock `access-om3-MOM6`

The ACCESS3 source is tag `2026.03.000`, commit
`825a3f4835bb088b12f68babe0149b017b16ba72`.

```bash
cd /g/data/au88/jr5971/access3-share-isomip

cmake -S . -B build-mom6-isomip \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PWD/install-mom6-isomip" \
  -DBuildConfigurations=MOM6 \
  -DMom6lib_DIR=/g/data/au88/jr5971/MOM6-isomip-nuopc/install-access3-isomip/lib64/cmake/Mom6lib

cmake --build build-mom6-isomip --parallel 16
cmake --install build-mom6-isomip
```

The local install needs the same runtime search path as the hosted executable:

```bash
PATCHELF=/g/data/xp65/public/apps/med_conda_scripts/analysis3-26.02.d/bin/patchelf
HOSTED="$(command -v access-om3-MOM6)"
LOCAL="$PWD/install-mom6-isomip/bin/access-om3-MOM6"
"$PATCHELF" --set-rpath "$("$PATCHELF" --print-rpath "$HOSTED")" "$LOCAL"
ldd "$LOCAL" | grep 'not found'
```

The final command should produce no output.

## Build The Toy Mediator

```bash
cd /g/data/au88/jr5971/issm_simple_mediator

MOM6LIB_PREFIX=/g/data/au88/jr5971/MOM6-isomip-nuopc/install-access3-isomip \
  ./build_mom6.sh build-mom6
```

Production runs use `ESMF_LOGKIND_MULTI_ON_ERROR`, `DumpFields=false`, low
MOM6 verbosity, and no per-step summary. The `ZeroForcing` component still
checks all 22 fields for finite exact-zero values on every advance.

## Duration Profiles

The common named profiles are:

| Profile | Duration |
| --- | --- |
| `smoke` | 2 x 300 seconds |
| `half-day` | 144 steps |
| `day` | 288 steps |
| `month` | January 1 to February 1 |
| `45-day` | 12,960 steps |
| `three-month` | January 1 to April 1, 25,920 steps |

## Run MOM6 Solo

```bash
cd /g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs
module purge
module use /g/data/vk83/modules
module load payu/1.3.2

python3 tools/set_solo_profile.py three-month
payu run -f -n 1 \
  -l /scratch/au88/jr5971/isomip-comparison/solo-three-month
```

Solo uses year 1, while both NUOPC paths use year 1900. Compare by elapsed
time, not absolute date.

## Run Stock CMEPS

```bash
cd /g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs-nuopc-ocean-only
module purge
module use /g/data/vk83/modules
module load payu/1.3.2

python3 tools/set_duration_profile.py three-month
payu run -f -n 1 \
  -l /scratch/au88/jr5971/isomip-comparison/cmeps-three-month
```

The checked-in control file says `datm/drof` because Payu 1.3.2 requires
those labels. `tools/patch_ocean_only_runconfig.py` changes only the staged
file to:

```text
ATM_model = satm
ROF_model = srof
```

It also creates tiny Payu bookkeeping restart pointers for the absent ATM and
ROF components. They are regular files used only by Payu archival and are not
read by CMEPS. The executable runs `MED OCN`, with no `MED -> OCN` transfer,
and MOM6 sets `zero_missing_imports=true`.

Inspect staging with:

```bash
payu sweep
payu setup
grep -E 'component_list|ATM_model|ROF_model|zero_missing_imports|apply_startup_lag' \
  work/nuopc.runconfig
payu sweep
```

## Run The Toy Mediator

```bash
cd /g/data/au88/jr5971/issm_simple_mediator

./submit_mom6_isomip_profile.sh \
  three-month startup 1900-01-01T00:00:00 \
  /scratch/au88/jr5971/isomip-comparison/toy-three-month
```

The run sequence is:

```text
ZeroForcing -> MOM6
MOM6
MOM6 -> OceanSink
ZeroForcing
```

`zero_missing_imports=false` is intentional: the toy must connect and provide
all 22 accepted fields.

## Restart Tests

### CMEPS 45 + 45 Days

```bash
cd /g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs-nuopc-ocean-only
module use /g/data/vk83/modules
module load payu/1.3.2

LAB=/scratch/au88/jr5971/isomip-comparison/cmeps-three-month-split
python3 tools/set_duration_profile.py 45-day
payu run -f -n 1 -l "$LAB"

# Submit after the first job and archive complete.
payu run -f -n 1 -l "$LAB"
```

Expected final restart files include:

```text
restart001/rpointer.cpl
restart001/rpointer.ocn
restart001/nuopc_isomip.cpl.r.1900-04-01-00000.nc
restart001/nuopc_isomip.mom6.r.1900-04-01-00000.nc
restart001/Shelf.res.nc
```

### Toy 45 + 45 Days

```bash
cd /g/data/au88/jr5971/issm_simple_mediator
CASE=/scratch/au88/jr5971/isomip-comparison/toy-three-month-split

./submit_mom6_isomip_profile.sh \
  45-day startup 1900-01-01T00:00:00 "$CASE"

# Submit after the first job completes.
./submit_mom6_isomip_profile.sh \
  45-day continue 1900-02-15T00:00:00 "$CASE"
```

Continuation preserves `rpointer.ocn`, the MOM6 restart, and `Shelf.res.nc`.

## Compare Outputs

The comparison tools live in the stock NUOPC worktree:

```bash
cd /g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs-nuopc-ocean-only
```

Example 90-day prognostic comparison:

```bash
python3 tools/compare_nuopc_outputs.py \
  /scratch/au88/jr5971/isomip-comparison/solo-three-month/archive/isomip-test-mom6-for-iom3-configs/output000/ave_prog.nc \
  /scratch/au88/jr5971/isomip-comparison/cmeps-three-month/archive/isomip-test-mom6-for-iom3-configs-nuopc-ocean-only/output000/ave_prog.nc \
  --fields temp salt u v h e \
  --elapsed-seconds 7776000 \
  --reference-start 0001-01-01T00:00:00 \
  --candidate-start 1900-01-01T00:00:00 \
  --time-tolerance-seconds 216000
```

The tolerance is 2.5 days because `ave_prog.nc` stores the midpoint of each
five-day average. Instantaneous files use the default exact time tolerance.

Exact restart comparison:

```bash
python3 tools/compare_restarts.py CONTINUOUS.nc SPLIT.nc
```

For cross-path solo/NUOPC core restarts, exclude `ave_ssh` because it contains
an absolute-time-dependent diagnostic accumulator:

```bash
python3 tools/compare_restarts.py SOLO_MOM.res.nc NUOPC_MOM.res.nc \
  --ignore ave_ssh
```

## Validation Archives And Jobs

| Case | Job ID | Result path |
| --- | --- | --- |
| Solo month | `170281666` | `/scratch/au88/jr5971/isomip-comparison/solo-month` |
| CMEPS month | `170281664` | `/scratch/au88/jr5971/isomip-comparison/cmeps-month` |
| Toy month | `170282635` | `/scratch/au88/jr5971/isomip-comparison/toy-month` |
| Solo 90-day | `170282886` | `/scratch/au88/jr5971/isomip-comparison/solo-three-month` |
| CMEPS 90-day | `170282887` | `/scratch/au88/jr5971/isomip-comparison/cmeps-three-month` |
| Toy 90-day | `170283761` | `/scratch/au88/jr5971/isomip-comparison/toy-three-month` |
| CMEPS split | `170283788`, `170285364` | `/scratch/au88/jr5971/isomip-comparison/cmeps-three-month-split` |
| Toy split | `170283762`, `170285351` | `/scratch/au88/jr5971/isomip-comparison/toy-three-month-split` |

All listed production jobs have `Exit_status = 0`. Their checked logs contain
no NaNs, infinities, reproducing-sum failures, MPI aborts, or fatal errors.
