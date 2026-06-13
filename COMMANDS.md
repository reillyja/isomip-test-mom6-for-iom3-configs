# ISOMIP Three-Path Commands

The detailed explanation and validated results are in
`ISOMIP_THREE_PATH_RUNBOOK.md`. This file is the short command reference.

## Common Environment

```bash
module purge
module use /g/data/vk83/modules
module load payu/1.3.2
payu --version
```

Monitor a job:

```bash
qstat -u "$USER"
qstat JOB_ID
qstat -x -f JOB_ID |
  grep -E 'job_state|Exit_status|resources_used.walltime|resources_used.mem'
```

## MOM6 Solo

```bash
cd /g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs

python3 tools/set_solo_profile.py smoke
python3 tools/set_solo_profile.py day
python3 tools/set_solo_profile.py month
python3 tools/set_solo_profile.py three-month

payu run -f -n 1 \
  -l /scratch/au88/jr5971/isomip-comparison/solo-three-month
```

Inspect:

```bash
tail -20 \
  /scratch/au88/jr5971/isomip-comparison/solo-three-month/archive/isomip-test-mom6-for-iom3-configs/output000/ocean.stats
```

## Stock CMEPS `MED OCN`

```bash
cd /g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs-nuopc-ocean-only

python3 tools/set_duration_profile.py smoke
python3 tools/set_duration_profile.py day
python3 tools/set_duration_profile.py month
python3 tools/set_duration_profile.py three-month

payu run -f -n 1 \
  -l /scratch/au88/jr5971/isomip-comparison/cmeps-three-month
```

Inspect the staged `satm/srof` patch:

```bash
payu sweep
payu setup
grep -E 'component_list|ATM_model|ROF_model|zero_missing_imports|apply_startup_lag' \
  work/nuopc.runconfig
payu sweep
```

Expected settings:

```text
component_list: MED OCN
ATM_model = satm
ROF_model = srof
zero_missing_imports = true
apply_startup_lag = false
```

## Toy Mediator

```bash
cd /g/data/au88/jr5971/issm_simple_mediator

./submit_mom6_isomip_profile.sh \
  smoke startup 1900-01-01T00:00:00 \
  /scratch/au88/jr5971/isomip-comparison/toy-smoke

./submit_mom6_isomip_profile.sh \
  day startup 1900-01-01T00:00:00 \
  /scratch/au88/jr5971/isomip-comparison/toy-day

./submit_mom6_isomip_profile.sh \
  month startup 1900-01-01T00:00:00 \
  /scratch/au88/jr5971/isomip-comparison/toy-month

./submit_mom6_isomip_profile.sh \
  three-month startup 1900-01-01T00:00:00 \
  /scratch/au88/jr5971/isomip-comparison/toy-three-month
```

## CMEPS Restart Test

```bash
cd /g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs-nuopc-ocean-only
LAB=/scratch/au88/jr5971/isomip-comparison/cmeps-three-month-split

python3 tools/set_duration_profile.py 45-day
payu run -f -n 1 -l "$LAB"

# Run after the first job and archival have completed.
payu run -f -n 1 -l "$LAB"
```

## Toy Restart Test

```bash
cd /g/data/au88/jr5971/issm_simple_mediator
CASE=/scratch/au88/jr5971/isomip-comparison/toy-three-month-split

./submit_mom6_isomip_profile.sh \
  45-day startup 1900-01-01T00:00:00 "$CASE"

# Run after the first job has completed.
./submit_mom6_isomip_profile.sh \
  45-day continue 1900-02-15T00:00:00 "$CASE"
```

## Compare Diagnostics

```bash
cd /g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs-nuopc-ocean-only

python3 tools/compare_nuopc_outputs.py \
  SOLO/forcing.nc NUOPC/forcing.nc \
  --fields taux tauy ustar PRCmE LwLatSens sensible p_surf \
  --elapsed-seconds 7776000 \
  --reference-start 0001-01-01T00:00:00 \
  --candidate-start 1900-01-01T00:00:00

python3 tools/compare_nuopc_outputs.py \
  SOLO/ave_prog.nc NUOPC/ave_prog.nc \
  --fields temp salt u v h e \
  --elapsed-seconds 7776000 \
  --reference-start 0001-01-01T00:00:00 \
  --candidate-start 1900-01-01T00:00:00 \
  --time-tolerance-seconds 216000
```

## Compare Restarts

Continuous versus split, exact by default:

```bash
python3 tools/compare_restarts.py CONTINUOUS.nc SPLIT.nc
```

Solo versus NUOPC:

```bash
python3 tools/compare_restarts.py SOLO_MOM.res.nc NUOPC_MOM.res.nc \
  --ignore ave_ssh
```

## Check Executables

```bash
sha256sum \
  /g/data/au88/jr5971/MOM6-isomip-nuopc/install-access3-isomip/lib64/libaccess-mom6lib.a \
  /g/data/au88/jr5971/access3-share-isomip/install-mom6-isomip/bin/access-om3-MOM6 \
  /g/data/au88/jr5971/issm_simple_mediator/build-mom6/mom6-simple-mediator
```

Expected SHA-256 values:

```text
Mom6lib:              16f796d8a4276bdd83ed5503ad01b12bd6d744c3f2e710c94c06d199aa74bda1
access-om3-MOM6:      6d9cb9566606019b6c690a7c12cbbc7a82840ea248ff08d3578d7411fbc32777
mom6-simple-mediator: 30dc350e47a8da00b0f6e253430872232b568271b62d14e9818d9d8d3082e762
```
