# GFZ/PIK Time-Evolving Geometry in MOM6-Solo

This runbook describes the local test pathway for using the GFZ/PIK Ocean3 and
Ocean4 time-evolving ice-shelf geometries with the existing MOM6-solo ISOMIP
configuration.

## Generate MOM6 Inputs

From this repository:

```bash
cd /g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs
python3 tools/build_gfz_geometry_for_mom6.py --update-manifest
```

This reads:

```text
/g/data/au88/jr5971/gfz-pik-2016-002/data/Ocean3_input_geom_v1.01.nc
/g/data/au88/jr5971/gfz-pik-2016-002/data/Ocean4_input_geom_v1.01.nc
```

and writes:

```text
INPUT/gfz_geometry/Ocean3_2km_initial.nc
INPUT/gfz_geometry/Ocean3_2km_shelf_mass.nc
INPUT/gfz_geometry/Ocean3_2km_shelf_mass_noop.nc
INPUT/gfz_geometry/Ocean3_2km_geometry.nc
INPUT/gfz_geometry/Ocean3_2km_geometry_noop.nc
INPUT/gfz_geometry/Ocean4_2km_initial.nc
INPUT/gfz_geometry/Ocean4_2km_shelf_mass.nc
INPUT/gfz_geometry/Ocean4_2km_shelf_mass_noop.nc
INPUT/gfz_geometry/Ocean4_2km_geometry.nc
INPUT/gfz_geometry/Ocean4_2km_geometry_noop.nc
plots/gfz_geometry/Ocean3_2km_geometry_overview.png
plots/gfz_geometry/Ocean4_2km_geometry_overview.png
```

The preprocessing conservatively coarsens the GFZ 1 km grid to the existing
MOM6 2 km `240 x 40` grid. The new geometry files contain physical shelf
thickness, ice-base elevation, floating fraction, bed elevation, grounded
fraction, open-ocean fraction, and a shelf-mass diagnostic. Thickness and base
are floating-area weighted over the source cells; fractions are exact `2 x 2`
means. Ice thickness below 10 m is removed before forming the prescribed
geometry and legacy shelf-mass products.

## Select A Geometry Case

Use the helper to update `input.nml`:

```bash
python3 tools/set_gfz_geometry_case.py baseline
python3 tools/set_gfz_geometry_case.py ocean3-static
python3 tools/set_gfz_geometry_case.py ocean3-noop
python3 tools/set_gfz_geometry_case.py ocean3
python3 tools/set_gfz_geometry_case.py ocean3-geometry-noop
python3 tools/set_gfz_geometry_case.py ocean3-geometry
python3 tools/set_gfz_geometry_case.py ocean4-static
python3 tools/set_gfz_geometry_case.py ocean4-noop
python3 tools/set_gfz_geometry_case.py ocean4
python3 tools/set_gfz_geometry_case.py ocean4-geometry-noop
python3 tools/set_gfz_geometry_case.py ocean4-geometry
```

The static cases use only the initial GFZ geometry. The no-op cases enable the
dynamic shelf-mass reader, but every time slice repeats the initial geometry.
The `ocean3` and `ocean4` cases use the real time-evolving prescribed shelf
mass. The `*-geometry-noop` and `*-geometry` cases are now the primary path:
they read prescribed thickness, ice-base elevation, and floating fraction from
the new geometry files and call MOM6's dynamic ice-shelf geometry updater. The
horizontal MOM ocean mask is still fixed for first-pass validation, so
`DYNAMIC_CAVITY_GEOMETRY` remains disabled until a pre-wettable cavity envelope
is generated. Drying remains disabled.

For GFZ cases, the helper writes `MOM_override.gfz_active` and points
`input.nml` at:

```fortran
parameter_filename = 'MOM_input', 'MOM_override.gfz_active'
```

This is intentional. MOM6 does not allow the same parameter to be `#override`d
twice with inconsistent values, so GFZ cases must not stack a small geometry
override after the baseline `MOM_override`.

## Select A Run Duration

```bash
python3 tools/set_solo_profile.py smoke
python3 tools/set_solo_profile.py day
python3 tools/set_solo_profile.py month
python3 tools/set_solo_profile.py six-month
python3 tools/set_solo_profile.py year
python3 tools/set_solo_profile.py five-year
python3 tools/set_solo_profile.py ten-year
python3 tools/set_solo_profile.py hundred-year
```

The recommended ladder is:

```text
ocean3-static smoke
ocean3-static day
ocean3-geometry-noop smoke
ocean3-geometry-noop day
ocean3-geometry-noop month
ocean3-geometry smoke
ocean3-geometry day
ocean3-geometry month
ocean3-geometry year
```

Then repeat the same ladder for Ocean4.

## Run With Payu

The `config.yaml` uses the stable payu module and an absolute path to the
locally built geometry-aware `mom6-solo` executable:

```yaml
modules:
  use:
    - /g/data/vk83/modules
  load:
    - payu/1.3.2

exe: /g/data/au88/jr5971/MOM6-isomip-nuopc/install-solo-gfz-geometry/bin/mom6-solo
```

This binary was built from `/g/data/au88/jr5971/MOM6-isomip-nuopc` with the
solo driver enabled. Its install RUNPATH includes OpenMPI, Intel runtime, and
NetCDF libraries, so `ldd` should not report missing libraries in a clean shell.

To stage and submit a selected case:

```bash
module use /g/data/vk83/modules
module load payu/1.3.2
payu setup --force --metadata-off
payu run -f
```

For reproducible staging, use the updated `manifests/input.yaml`, which now
contains the generated GFZ files.

## Isolated Test Helper

For the GFZ test ladder, prefer isolated control/lab pairs:

```bash
LAB_ROOT=/scratch/au88/$USER/mom6-isomip-gfz
CONTROL_ROOT=/scratch/au88/$USER/mom6-isomip-gfz-controls

python3 tools/submit_gfz_case.py ocean3-static day --replace
python3 tools/submit_gfz_case.py ocean3-geometry-noop smoke --replace
python3 tools/submit_gfz_case.py ocean3-geometry day --replace --queue normal
```

The helper:

```text
copies a fresh control directory
resets restart.yaml to an empty cold-start manifest
selects the GFZ case and duration profile
updates queue, walltime, jobname and normal-queue platform shape
optionally rewrites exe and manifests/exe.yaml for a local mom6-solo
prints the exact payu command
```

Manual submission from a prepared control:

```bash
cd /scratch/au88/$USER/mom6-isomip-gfz-controls/ocean3-geometry-noop-smoke
module use /g/data/vk83/modules
module load payu/1.3.2
payu run --stacktrace -f --lab /scratch/au88/$USER/mom6-isomip-gfz/ocean3-geometry-noop-smoke
```

Validation:

```bash
python3 tools/validate_gfz_run.py \
  --archive /scratch/au88/$USER/mom6-isomip-gfz/ocean3-static-day/archive/ocean3-static-day \
  --case ocean3 \
  --mode static \
  --duration day

python3 tools/validate_gfz_run.py \
  --archive /scratch/au88/$USER/mom6-isomip-gfz/ocean3-geometry-noop-smoke/archive/ocean3-geometry-noop-smoke \
  --case ocean3 \
  --mode geometry-noop \
  --duration smoke
```

## Current Test Status

As of 2026-07-08:

```text
PASS  ocean3-static day, fresh isolated lab
PASS  ocean4-static smoke, fresh isolated lab
PASS  ocean4-static day, fresh isolated lab
FAIL  ocean3-noop smoke with stock prerelease mom6-solo:
      FMS initially rejected the shelf-mass file axis metadata.
FIXED regenerated dynamic files with Time/y/x coordinate variables and
      axis/cartesian_axis metadata.
FAIL  ocean3-noop smoke then reached a MOM6 prescribed-shelf-mass source-path
      bug: initialize_ice_shelf_dyn was called without an associated dCS.
FIXED locally in /g/data/au88/jr5971/MOM6 by guarding ice-dynamics init and
      energy writes with active_shelf_dynamics rather than shelf_mass_is_dynamic.
FAIL  ocean3-noop smoke with patched mom6-solo now reaches add_shelf_flux, then
      fails with NaN/overflow in the constant-sea-level balance.
DONE  Added geometry-file generation for Ocean3/Ocean4, including no-op files.
DONE  Added geometry-file case selection and validation modes.
DONE  Added MOM6 solo prescribed-geometry path in MOM_ice_shelf.F90 using the
      coupled update_ice_shelf_geometry machinery.
DONE  Built and installed new solo binary:
      /g/data/au88/jr5971/MOM6-isomip-nuopc/install-solo-gfz-geometry/bin/mom6-solo
PASS  ldd check on the new binary after install RUNPATH patch; no missing libs.
BLOCK ocean3-geometry-noop smoke payu setup prepared the isolated control, then
      failed before staging with:
      "Installation issue: starter-suid doesn't have setuid bit set"
FIXED rerunning setup with a clean module environment and `module load payu`.
FAIL  ocean3-geometry-noop smoke with DYNAMIC_CAVITY_GEOMETRY=True:
      update_ice_shelf_geometry rejected the fixed-mask solo setup because v2
      dynamic-cavity mode needs pre-wettable-envelope cells.
FIXED first-stage geometry cases now set DYNAMIC_CAVITY_GEOMETRY=False while
      keeping ICE_SHELF_GEOMETRY_FROM_FILE=True.
FAIL  ocean3-geometry-noop smoke then reported invalid GLC geometry cells=3207:
      fixed-mask validation needs the updater to treat the already initialized
      shelf footprint as part of the allowable cavity envelope.
FIXED MOM_ice_shelf.F90 now allows prescribed geometry updates on cells that
      were already shelf-covered at initialization; rebuilt mom6-solo and
      refreshed manifests/exe.yaml.
FAIL  ocean3-geometry-noop smoke then cleared 32 thin-cavity edge cells on the
      first update but failed on the second update because the same cells were
      no longer in the active shelf footprint.
FIXED thin-cavity rejection is now applied before fixed-envelope invalid checks,
      so those edge cells are cleared consistently each update.
PASS  ocean3-geometry-noop smoke with fixed-mask geometry mode:
      model reached 0001-01-01T00:10:00 with exit code 0; validator passed.
      The 10-minute point diagnostics are all missing-value, so restart000 was
      used for the physical shelf-state check. It has finite h_shelf,
      shelf_area and shelf_mass, exact shelf_mass = 900*h_shelf, exact common
      cell area match to the prescribed geometry, and 32 intentionally cleared
      thin-cavity edge cells.
```

The old mass-only patched executable is retained only as a legacy reference:

```text
/g/data/au88/jr5971/MOM6/install-solo-gfz-prescribed/bin/mom6-solo
```

It was built from:

```text
/g/data/au88/jr5971/MOM6
```

with install RPATH added for NetCDF, Intel and OpenMPI runtime libraries.

Temporary diagnostics were added in `MOM_ice_shelf.F90:add_shelf_flux` to catch
the first bad `water_flux`, `area_shelf_h`, or `bal_frac` cell before the global
reproducing sum. The last diagnostic rerun was cancelled before execution
because PBS could not reserve allocation from project `au88`. The next primary
runtime target is now:

```bash
python3 tools/submit_gfz_case.py ocean3-geometry-noop smoke --replace --setup-only
```

Once the site `starter-suid` issue is resolved, rerun setup and submit with the
printed `payu run` command, then validate in `geometry-noop` mode.

## Stability Checks

For every test, check:

```text
no NaNs or infinities
no reproducing-sum failures
no MPI aborts
final model time matches the selected profile
```

Useful outputs are already requested in `diag_table`:

```text
forcing.nc: taux, tauy, ustar, PRCmE, LwLatSens, p_surf
ice.nc: area_shelf_h, shelf_mass, h_shelf, dynamic_cavity_category, mass_flux, melt_rate, tflux_shelf, ustar_shelf
ave_prog.nc: u, v, h, e, temp, salt
```

For geometry cases, confirm that `h_shelf`, `area_shelf_h`, `shelf_mass`, and
`p_surf` follow the prescribed GFZ geometry. `dynamic_cavity_category` should
not report unexpected outside-envelope or would-dry cells while drying is
disabled. Melt, shelf heat exchange, and `PRCmE` are still generated internally
by MOM6.

## First Debugging Moves

If a run fails:

```text
1. Re-run the matching static case.
2. Re-run the matching no-op geometry case.
3. Compare the first failing cell with the shelf front and grounding line.
4. Confirm shelf_mass[0] / 900 exactly matches the initial thick field.
5. Try a 150 s timestep only as a sensitivity test; keep 300 s as the target.
```
