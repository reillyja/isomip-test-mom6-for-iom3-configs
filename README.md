# Idealised ISOMIP+ like config for iom3 examples

Modified from the MOM6-examples rho case by using a symmetric ice thickness file and adding to the `MOM_override` https://github.com/NOAA-GFDL/MOM6-examples/tree/dev/gfdl/ocean_only/ISOMIP/rho

- Fixes some bugs identified from pressure gradient and initialisation 
- Adds some parameters for ISOMIP+ config (https://github.com/gustavo-marques/ISOMIP) so that it resembles the Ocean0 warm test case (the MOM6-examples one is more like the cold case)
- Uses the HJ99 stability-dependent melt parameterisation with a perfectly
  insulating ice shelf (no conductive heat loss into the shelf)
- Runs on 48 cpus, 3 months in ~6 minutes

## Run directory

This repository is a `payu` control directory for an ocean-only MOM6
experiment:

- `config.yaml` defines the Gadi resources, model executable, modules, input
  directories, and scratch laboratory.
- `input.nml` selects the ocean-solo driver and run duration.
- `MOM_input` contains the base MOM6 parameters and `MOM_override` contains
  the ISOMIP-specific overrides.
- `diag_table` selects model diagnostics.
- `ISOMIP_THREE_PATH_RUNBOOK.md` gives copyable commands for the validated
  MOM6-solo run, stock CMEPS initialization control, and toy zero-forcing
  mediator.
- `MOM6_BOUNDARY_FORCING.md` traces lateral, surface, and ice-shelf forcing
  through the solo, NUOPC/CMEPS, and FMS driver paths.
- `INPUT/Ocean0_3D_Claire.nc` supplies ice-shelf thickness and surface
  pressure.
- `manifests/` records the exact executable, input, and restart files staged
  by `payu`.
- `work` and `archive` are links into the scratch laboratory after setup and
  execution.

`payu setup` creates the work directory and manifests. `payu run` submits a
PBS job, runs MOM6 under MPI, and archives output and restart files.

## Supported executable

The configuration uses the Spack prerelease module
`access-om3/pr218-3`, which provides:

```text
access-mom6@2026.01.001 +access3 +mom6_solo ~asymmetric_mem ~openmp
MOM6 commit c664721ebd58c033964b502e7fcdcccd05f02947
executable: mom6-solo
```

The earlier `access-om3/pr218-1` module describes the same MOM6 commit and
build variants, but its installation prefix is no longer present as of
2026-06-05. The `access-om3-MOM6` executable is the NUOPC coupled driver and
is not used by this ocean-only experiment.

The model module is loaded from `config.yaml`, rather than only in the
interactive shell. This allows `payu` to find `mom6-solo`, retain its module
dependencies in the batch job, and record the resolved executable in the
manifest.

## Running with payu

Load the supported `payu` module and run commands from this directory:

```bash
module use /g/data/vk83/modules
module load payu/1.3.2

payu run --reproduce
```

`payu run` performs setup before launching the model. To inspect the staged
work directory without submitting a job, run `payu setup --reproduce
--archive`, then run `payu sweep` before the later `payu run --reproduce`.

The executable is built for the `x86_64_v4` target, so the configuration uses
Gadi's `normalsr` Sapphire Rapids queue. MOM6 runs on 48 MPI ranks; the
historical successful decomposition for the 240 by 40 grid is 16 by 3.

`IGNORE_FLUXES_OVER_LAND=True` in `MOM_override` suppresses a very large
per-timestep grounding report from this MOM6 version. The model still clips
residual boundary mass fluxes and accounts for them in the `created_H`
diagnostic.

## Original executable

Checked that it ran using a version of MOM6 compiled on gadi using Angus Gibson's [ninja](https://github.com/angus-g/mom6-ninja-nci) method. You can see the FMS/MOM6 versions in the src folder. https://github.com/claireyung/setup-mom6-nci-executable/tree/test-ice-shelf-config-iom3

Before compiling with ninja I loaded the following modules on gadi (I had trouble with just the latest defaults)
```
module load intel-mkl/2021.4.0
module load python3/3.9.2
module load intel-compiler/2021.8.0
module load openmpi/4.1.4
module load netcdf/4.9.2
```
