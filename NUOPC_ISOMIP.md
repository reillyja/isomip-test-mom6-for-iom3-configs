# ISOMIP Through Stock CMEPS

This worktree runs ISOMIP through a locally built `access-om3-MOM6` with:

```text
component_list: MED OCN
ATM_model = satm
ROF_model = srof
```

There is no atmosphere or runoff component and no `MED -> OCN` transfer.
Instead, the patched MOM6 cap uses:

```text
zero_missing_imports = true
```

All missing atmosphere, radiation, stress, precipitation, runoff, pressure,
and enthalpy imports are initialized to zero before connected fields are read.
The cap checks that the resulting imports are finite and logs their extrema.

MOM6 still calculates ice-shelf pressure, melt/freeze, shelf heat exchange,
drag, and configured gustiness internally.

## Matched Runtime

```text
coupling interval: 300 seconds
MOM6 DT:           300 seconds
MOM6 DT_FORCING:   300 seconds
layout:            16 x 3
OCN ranks:         48
MED ranks:         1
total ranks:       49
```

`apply_startup_lag=false` makes every driver cycle advance MOM6 by 300
seconds. This is required for exact parity with `mom6-solo`.

## Payu Compatibility

Payu 1.3.2 requires `datm/drof` in the checked-in `access-om3` control file.
The setup hook `tools/patch_ocean_only_runconfig.py` changes only the staged
`work/nuopc.runconfig` to `satm/srof`.

The hook also creates tiny regular `rpointer.atm`, `rpointer.rof`, and
corresponding Payu stub restart files. These satisfy Payu staging and archival
checks for absent components; CMEPS does not read them.

Inspect the actual staged configuration:

```bash
module use /g/data/vk83/modules
module load payu/1.3.2

payu sweep
payu setup
grep -E 'component_list|ATM_model|ROF_model|zero_missing_imports|apply_startup_lag' \
  work/nuopc.runconfig
payu sweep
```

## Run

```bash
python3 tools/set_duration_profile.py smoke
python3 tools/set_duration_profile.py day
python3 tools/set_duration_profile.py month
python3 tools/set_duration_profile.py 45-day
python3 tools/set_duration_profile.py three-month
```

Example 90-day run:

```bash
python3 tools/set_duration_profile.py three-month
payu run -f -n 1 \
  -l /scratch/au88/jr5971/isomip-comparison/cmeps-three-month
```

## Restart

```bash
LAB=/scratch/au88/jr5971/isomip-comparison/cmeps-three-month-split
python3 tools/set_duration_profile.py 45-day

payu run -f -n 1 -l "$LAB"

# Run after output000/restart000 have been archived.
payu run -f -n 1 -l "$LAB"
```

The final archive must contain:

```text
restart001/rpointer.cpl
restart001/rpointer.ocn
restart001/nuopc_isomip.cpl.r.1900-04-01-00000.nc
restart001/nuopc_isomip.mom6.r.1900-04-01-00000.nc
restart001/Shelf.res.nc
```

Do not set `input_filename='n'` in `input.nml`; it overrides the rpointer
filename supplied by the cap and prevents continuation from reading the
correct restart.

## Validation

The June 9, 2026 tests passed for smoke, one day, one month, and 90 days.
The 45+45-day continuation is bitwise identical to the 90-day continuous run
for:

- 21 common numeric MOM6 restart variables;
- three shelf restart variables;
- 23 common numeric CMEPS coupler restart variables.

At 90 days, temperature, salinity, velocity, layer/interface height, surface
forcing, and ice-shelf diagnostics are bitwise identical to both
`mom6-solo` and the toy mediator.

Comparison tools:

```bash
python3 tools/compare_nuopc_outputs.py REFERENCE.nc CANDIDATE.nc
python3 tools/compare_restarts.py CONTINUOUS.nc SPLIT.nc
```

The complete commands, hashes, result paths, and test matrix are in:

```text
/g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs/ISOMIP_THREE_PATH_RUNBOOK.md
```
