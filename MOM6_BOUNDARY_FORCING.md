# MOM6 boundary forcing in this ISOMIP configuration

This document describes how lateral and upper-boundary forcing reaches MOM6
in:

1. the working `mom6-solo` ISOMIP experiment in this repository;
2. a MOM6 component driven through NUOPC/CMEPS; and
3. the older FMS coupled-driver interface.

The most important distinction is ownership. All three drivers eventually
populate MOM6's internal `forcing` and `mech_forcing` structures. The drivers
differ in who calculates the fluxes before those structures are populated.

| Driver | External data supplied | Who calculates air-sea fluxes? |
| --- | --- | --- |
| `mom6-solo` in this repository | Ice-shelf geometry; MOM parameters | No ordinary atmosphere is used. MOM calculates ice-shelf melt fluxes internally. |
| Generic `mom6-solo` with file forcing | MOM-ready stress, heat, freshwater, salt, and pressure fields | Usually the data producer, before the run |
| NUOPC/CMEPS | Atmospheric state and radiative/precipitation fields, runoff, and ocean surface state | CMEPS bulk-flux code and mediator |
| FMS coupled driver | Flux-ready FMS ice-ocean boundary fields | The FMS atmosphere/coupler upstream of MOM |

## 1. Terminology

### Lateral boundaries

A true lateral boundary condition controls exchange through a vertical side
of the ocean domain. MOM6 can use:

- closed solid walls;
- periodic or re-entrant boundaries; or
- open boundary condition (OBC) segments that prescribe or calculate
  velocity, sea level, and tracer behavior.

This experiment has none of the latter two:

```text
REENTRANT_X = False
REENTRANT_Y = False
OBC_NUMBER_OF_SEGMENTS = 0
```

The domain therefore has closed lateral walls. There is no external file
providing water, momentum, temperature, or salinity through a side boundary.

### The ISOMIP sponge

The eastern ISOMIP sponge is an interior restoring region, not an open
boundary. It relaxes temperature and salinity near the closed eastern wall
while still allowing no volume transport through that wall.

The effective settings are:

```text
SPONGE = True
SPONGE_CONFIG = "ISOMIP"
ISOMIP_TNUDG = 0.1 days
SPONGE_UV = False
```

`ISOMIP_initialize_sponges` constructs the sponge internally. Between model
longitudes 790 and 800 km its inverse restoring time increases linearly from
zero to `1 / ISOMIP_TNUDG`:

```text
Iresttime = (1 / TNUDG) * (longitude - 790 km) / 10 km
```

The routine also constructs the target vertical temperature and salinity
profiles from these ISOMIP parameter values:

```text
ISOMIP_T_SUR_SPONGE = -1.9 degC
ISOMIP_T_BOT_SPONGE = 1.0 degC
ISOMIP_S_SUR_SPONGE = 33.8 ppt
ISOMIP_S_BOT_SPONGE = 34.7 ppt
```

No sponge NetCDF file is read by this configuration. Only temperature and
salinity are registered with the ALE sponge; velocity is not restored
because `SPONGE_UV=False`.

At each sponge update MOM applies an implicit relaxation equivalent to:

```text
new = (old + dt * Iresttime * target) / (1 + dt * Iresttime)
```

Look at:

- effective parameters: `docs/MOM_parameter_doc.all`;
- setup: `src/user/ISOMIP_initialization.F90`,
  routine `ISOMIP_initialize_sponges`;
- application: `src/parameterizations/vertical/MOM_ALE_sponge.F90`,
  routine `apply_ALE_sponge`.

The source paths above are relative to the MOM6 source tree described in
[Section 8](#8-where-to-look).

## 2. MOM6's common internal forcing interface

MOM6 separates thermodynamic and mechanical boundary data.

### Thermodynamic `forcing`

The `forcing` type can hold:

- shortwave radiation, including multiple penetrating bands;
- net or component longwave radiation;
- sensible and latent heat;
- other directly added heat;
- evaporation;
- rain and snow;
- liquid runoff, frozen runoff, calving, and glacier fluxes;
- sea-ice or ice-shelf melt/freeze water;
- salt flux;
- surface restoring terms;
- shelf area, thickness, and related fields; and
- tracer-specific boundary fluxes.

### Mechanical `mech_forcing`

The `mech_forcing` type holds:

- zonal and meridional surface stress;
- stress magnitude or friction velocity;
- net surface mass source; and
- surface pressure.

These definitions are in `src/core/MOM_forcing_type.F90`.

### MOM sign convention

MOM's thermodynamic boundary terms are generally positive **into the ocean**.
Consequently:

| Quantity | Positive MOM value means |
| --- | --- |
| Shortwave, longwave, sensible, latent heat | Ocean gains heat |
| Rain, snow, runoff, melt | Ocean gains water/mass |
| Evaporation | Stored as a negative water flux when water leaves the ocean |
| Salt flux | Ocean gains salt |
| Stress | Downward stress on the ocean in the model-grid direction |

Coupled adapters are important because upstream systems do not all use these
signs or units.

### What MOM does after receiving fluxes

The core ocean step does not care whether a flux originated in a file, an
idealized solo formula, CMEPS, FMS, sea ice, or the shelf thermodynamics.
After conversion to the two structures, MOM:

1. combines the heat, water, salt, pressure, and stress components;
2. applies incoming water mass at the upper interface;
3. distributes outgoing mass and associated heat/salt over sufficient upper
   ocean thickness when a surface cell is too thin;
4. uses `MINIMUM_FORCING_DEPTH=1 m` in this experiment for that distribution;
5. treats penetrating shortwave radiation separately from non-penetrating
   heat;
6. applies stress in the momentum and vertical-mixing calculations;
7. applies surface pressure in the pressure-gradient calculation; and
8. records any clipped residual boundary mass in diagnostics such as
   `created_H`.

The central thermodynamic application routine is
`applyBoundaryFluxesInOut` in
`src/parameterizations/vertical/MOM_diabatic_aux.F90`.

## 3. The working `mom6-solo` ISOMIP case

### External input

The input manifest contains one NetCDF file:

```text
INPUT/Ocean0_3D_Claire.nc
```

It contains only horizontal `thick` and `area` fields. It contains no wind,
atmospheric state, radiation, precipitation, runoff, lateral velocity, or
lateral tracer data.

The file is selected for both:

```text
ICE_PROFILE_CONFIG = "FILE"
ICE_THICKNESS_FILE = "Ocean0_3D_Claire.nc"
ICE_THICKNESS_VARNAME = "thick"
ICE_AREA_VARNAME = "area"
SURFACE_PRESSURE_FILE = "Ocean0_3D_Claire.nc"
SURFACE_PRESSURE_VAR = "thick"
SURFACE_PRESSURE_SCALE = 8820 Pa/m
TRIM_IC_FOR_P_SURF = True
```

During initialization, MOM reads shelf thickness and area, converts
`thick * 8820 Pa/m` to the imposed initial pressure, and trims the initial
water column to be hydrostatically consistent with that pressure. During
integration, `add_shelf_forces` calculates pressure from the evolving shelf
mass times gravity and the shelf area fraction. Topography, initial
temperature/salinity, and the eastern sponge targets are otherwise generated
by the ISOMIP initialization code and parameters.

### Ordinary atmosphere-ocean forcing

The effective solo settings are:

```text
WIND_CONFIG = "zero"
BUOY_CONFIG = "NONE"
GUST_CONST = 0.02 Pa
```

Their consequences are:

- `taux` and `tauy` are zero;
- there is no atmosphere-derived shortwave, longwave, sensible, latent,
  rain, snow, evaporation, or runoff forcing;
- `GUST_CONST` gives a nonzero friction velocity used by upper-ocean mixing,
  even though directional stress is zero; and
- nonzero heat and freshwater fluxes arise from the interactive ice shelf.

The solo forcing dispatcher is
`config_src/drivers/solo_driver/MOM_surface_forcing.F90`, routine
`set_forcing`. It selects implementations using `WIND_CONFIG` and
`BUOY_CONFIG`.

Generic solo configurations can instead use idealized formulas or
`WIND_CONFIG="file"` and `BUOY_CONFIG="file"`. The file options expect
MOM-ready flux variables. They do not natively read near-surface air
temperature, humidity, pressure, and wind and then run an atmospheric bulk
formula.

### Interactive ice-shelf forcing

For each `DT_FORCING=720 s` forcing interval, the solo driver follows this
sequence:

```text
set_forcing
  -> shelf_calc_flux
  -> add_shelf_forces
  -> step_MOM
```

The call sequence is in
`config_src/drivers/solo_driver/MOM_driver.F90`.

`shelf_calc_flux` receives the shelf geometry and the evolving ocean state,
including:

- upper-ocean temperature and salinity;
- upper or mixed-layer velocity;
- mixed-layer or exchange-layer thickness;
- ocean mass; and
- shelf thickness and area fraction.

With this configuration:

```text
SHELF_INSULATOR = True
SHELF_3EQ_GAMMA = False
SHELF_S_ROOT = False
UTIDE = 0.01 m s-1
CDRAG_SHELF = 0.025
CONST_SEA_LEVEL = False
```

MOM then:

1. calculates the pressure-dependent freezing temperature at the ice-ocean
   interface;
2. calculates under-shelf friction velocity from ocean velocity, tidal
   velocity `UTIDE`, and drag coefficient `CDRAG_SHELF`;
3. uses the Holland and Jenkins (1999) stability-dependent exchange
   formulation because `SHELF_3EQ_GAMMA=False`;
4. iterates for interface salinity because `SHELF_S_ROOT=False`;
5. calculates the ocean-to-interface heat flux and melt/freeze rate;
6. assumes no conductive heat loss into the shelf because
   `SHELF_INSULATOR=True`;
7. represents melt as incoming liquid precipitation and freezing as negative
   evaporation;
8. places the shelf heat exchange in the sensible-heat component;
9. adds any shelf salt exchange to the salt-flux component; and
10. applies ice-overburden pressure through `p_surf`.

`add_shelf_forces` also reduces ordinary atmosphere-ocean forcing by the
open-water fraction where shelf ice is present. That matters in a case with
atmospheric forcing; in the current case those ordinary terms are absent.

The implementation is in `src/ice_shelf/MOM_ice_shelf.F90`, especially
`shelf_calc_flux`, `add_shelf_flux`, and `add_shelf_forces`.

### Evidence from the successful solo run

The three-month validation archive contains:

```text
/scratch/au88/jr5971/mom6-isomip-validation-20260605/
  archive/isomip-test-mom6-for-iom3-configs/output000/forcing.nc
```

Across its 90 daily records:

| Diagnostic | Minimum | Maximum | Interpretation |
| --- | ---: | ---: | --- |
| `taux` | 0 Pa | 0 Pa | No zonal wind stress |
| `tauy` | 0 Pa | 0 Pa | No meridional wind stress |
| `ustar` | 0.004412958 m/s | 0.004412958 m/s | Constant gustiness contribution |
| `PRCmE` | -5.69e-7 | 6.0565e-4 kg/m2/s | Shelf freeze/melt water flux |
| `LwLatSens` | -202.29 | 0.190 W/m2 | Shelf heat exchange in this case |
| `sensible` | -202.29 | 0.190 W/m2 | Same shelf heat component |
| `p_surf` | 0 | 1.2961e7 Pa | Atmosphere/open water to ice overburden |

These diagnostics directly demonstrate that the active upper-boundary
forcing is an internally calculated shelf flux, not forcing from an
atmospheric file.

## 4. NUOPC/CMEPS forcing

NUOPC and CMEPS divide the work across four layers:

```text
atmospheric data/component
  -> CDEPS field preparation
  -> CMEPS bulk fluxes and mediator
  -> MOM6 NUOPC cap
  -> MOM6 common forcing structures
```

The atmospheric input is therefore not passed straight into the MOM6 ocean
core.

### Example atmospheric and runoff inputs

The exploratory coupled work directory for this ISOMIP case uses a JRA55-do
data atmosphere. Its `datm.streams.xml` maps:

| Input variable | Coupler field |
| --- | --- |
| `uas`, `vas` | `Sa_u`, `Sa_v` |
| `tas` | `Sa_tbot` |
| `huss` | `Sa_shum` |
| `psl` | `Sa_pslv` |
| `rsds` | `Faxa_swdn` |
| `rlds` | `Faxa_lwdn` |
| `prra` | `Faxa_prrn` |
| `prsn` | `Faxa_prsn` |

The data runoff component maps:

| Input variable | Coupler field |
| --- | --- |
| `friver` | `Forr_rofl` |
| `licalvf` | `Forr_rofi` |

CDEPS prepares additional atmospheric state needed by the bulk formula. For
JRA55-do it sets bottom pressure from sea-level pressure, sets potential
temperature from the supplied bottom-air temperature, assumes a 10 m
measurement height, and derives air density from pressure, temperature, and
specific humidity.

### Bulk flux calculation in CMEPS

With:

```text
coupling_mode = cesm
ocn_surface_flux_scheme = 0
aoflux_grid = ogrid
```

CMEPS selects its Large and Pond air-ocean bulk-flux scheme. It combines:

- atmospheric wind, temperature, humidity, density, pressure, and reference
  height; with
- ocean surface velocity and sea-surface temperature.

The scheme uses atmosphere-relative-to-ocean wind, a minimum relative wind,
surface saturation humidity, and iterated stability-dependent transfer
coefficients to calculate:

- zonal and meridional stress;
- sensible heat;
- latent heat;
- upward longwave radiation; and
- evaporation.

The relevant files are:

- `CMEPS/CMEPS/mediator/med_phases_aofluxes_mod.F90`;
- `CMEPS/CMEPS/cesm/flux_atmocn/flux_atmocn_driver_mod.F90`; and
- `CMEPS/CMEPS/cesm/flux_atmocn/flux_atmocn_Large.F90`.

The bulk routines use positive-downward heat-flux signs. Upward longwave is
therefore negative. Evaporation normally emerges as a negative water flux
because it removes water from the ocean.

### Mediator assembly

The CMEPS mediator then:

- adds downwelling and upward longwave to form net longwave;
- applies ocean albedo to downwelling shortwave;
- splits shortwave into the visible/near-infrared and
  direct/diffuse bands expected by MOM;
- combines rain and snow components;
- maps liquid and frozen runoff;
- combines open-ocean and sea-ice contributions when CICE is present; and
- sends flux-ready fields to the ocean at the coupling interval.

The example `nuopc.runseq` runs the air-ocean flux phase and sends mediator
fields to MOM every 300 s.

Look at:

- `CMEPS/CMEPS/mediator/esmFldsExchange_cesm_mod.F90`;
- `CMEPS/CMEPS/mediator/med_phases_prep_ocn_mod.F90`;
- `nuopc.runconfig`; and
- `nuopc.runseq`.

### Conversion in the MOM6 NUOPC cap

The MOM6 NUOPC cap imports net, flux-ready quantities such as:

- stress;
- net longwave;
- shortwave bands;
- sensible heat;
- evaporation;
- rain and snow;
- liquid and frozen runoff;
- surface pressure; and
- sea-ice heat, water, salt, stress, pressure, and area fields when present.

It rotates east/north stress onto the MOM model grid, applies units and
masks, handles staggered grids and halos, and converts the imported fields
into MOM's `forcing` and `mech_forcing` structures. It also derives terms such
as latent heat associated with evaporation and frozen precipitation where
needed.

MOM does **not** rerun the atmospheric bulk formula in this cap. The cap is a
field adapter; CMEPS owns the atmosphere-to-flux transformation.

Look at:

- `config_src/drivers/nuopc_cap/mom_cap_methods.F90`;
- `config_src/drivers/nuopc_cap/mom_surface_forcing_nuopc.F90`; and
- `config_src/drivers/nuopc_cap/mom_ocean_model_nuopc.F90`.

An interactive MOM ice shelf may still calculate and add its local
under-shelf fluxes after coupled atmospheric fields have been converted. In
that arrangement CMEPS owns open-ocean air-sea exchange while MOM owns
ice-shelf-ocean thermodynamics.

### With and without CICE

`access-om3-MOM6` has no active CICE component. Sea-ice-mediated flux fields
are absent or zero, while CMEPS supplies open-ocean air-sea fluxes.

`access-om3-MOM6-CICE6` adds CICE. CMEPS then merges open-water atmospheric
fluxes with ice-ocean stress, heat, freshwater, salt, pressure, and ice
fraction before exporting the ocean forcing fields.

### Atmosphere-free NUOPC testing

The ocean-only NUOPC worktree is:

```text
/g/data/au88/jr5971/
  isomip-test-mom6-for-iom3-configs-nuopc-ocean-only
```

Its runtime component list contains only `MED OCN`. In CMEPS,
`ATM_model=satm` and `ROF_model=srof` are sentinel values: they set the
mediator's atmosphere and runoff presence flags to false. They do not create
components and do not generate neutral atmospheric fields.

This resembles `mom6-solo` only in the narrow sense that no atmosphere or
runoff component runs. It is not a zero-forcing configuration. With no
`MED -> OCN` transfer, MOM6's flux-ready imports remain disconnected.

Payu 1.3.2 currently insists that an `access-om3` control file declare
`datm/drof`. The worktree keeps those values in the control file for staging,
then its `userscripts.setup` hook changes the staged runtime file to
`satm/srof`. Inspect `work/nuopc.runconfig`, not only the control copy, when
checking what the executable received.

A second, independent test uses:

```text
/g/data/au88/jr5971/issm_simple_mediator
```

The new `mom6-simple-mediator` target reuses the ISSM toy mediator pattern but
does not link ISSM. It connects a `ZeroForcing` NUOPC component directly to
the installed MOM6 cap and explicitly exports zero stress, heat, radiation,
freshwater, runoff, pressure and associated heat-content fields. This is a
cap-level diagnostic:

- success here but failure with CMEPS points to mediator configuration or
  mediator field transformations;
- failure in both paths points toward MOM6-cap negotiation, imported fields,
  or the ISOMIP MOM configuration.

The existing ISSM target remains separate because its GCC/OpenMPI/ESMF ABI is
not compatible with the Intel/OpenMPI/ESMF ABI used by ACCESS3 MOM6.

The distinction is important with the current ACCESS MOM6 cap. Its
`state_getimport_2d` helper returns without writing the destination array when
a field is absent. Some callers initialize their destinations first, but the
locally allocated stress arrays `taux` and `tauy` do not. A stock `satm`
experiment therefore initializes successfully for the cap's skipped
cold-start call, then reaches non-finite data in `reproducing_EFP_sum` on the
first actual ocean advance. The toy component avoids this ambiguity by
connecting every required field and writing finite zeros.

## 5. FMS coupled forcing

FMS coupling is not another name for NUOPC. It is an older, separate MOM6
driver and field interface.

The FMS cap receives an `ice_ocean_boundary_type` object whose fields are
already expressed as ice/ocean boundary fluxes. The cap:

- maps FMS field names into MOM forcing components;
- converts FMS signs to MOM's positive-into-ocean convention;
- converts units;
- applies masks;
- constructs latent heat from water fluxes and frozen inputs where needed;
  and
- passes the resulting common forcing structures into the ocean.

For example, the adapter reverses FMS water and heat signs where required:
FMS `q_flux` becomes MOM evaporation with the opposite sign, and FMS
`t_flux` becomes MOM sensible heat with the opposite sign.

The atmospheric state-to-flux calculation is upstream in the FMS
atmosphere/coupler system, not inside this MOM adapter.

Look at:

- `config_src/drivers/FMS_cap/MOM_surface_forcing_gfdl.F90`; and
- `config_src/drivers/FMS_cap/ocean_model_MOM.F90`.

## 6. Exact difference in responsibility

| Operation | Current solo ISOMIP | NUOPC/CMEPS | FMS coupled |
| --- | --- | --- | --- |
| Read raw atmospheric state | Not done | CDEPS/data atmosphere | FMS atmosphere/coupler |
| Calculate bulk air-sea stress | Not done; zero stress selected | CMEPS | Upstream FMS system |
| Calculate bulk sensible/latent heat | Not done | CMEPS | Upstream FMS system |
| Combine down/up longwave | Not done | CMEPS mediator | Upstream FMS system |
| Apply ocean albedo/split shortwave bands | Not done | CMEPS mediator | Upstream FMS system/cap |
| Map rain, snow, runoff | Not supplied | CDEPS/CMEPS | FMS coupler/cap |
| Convert signs, units, grid orientation | Solo forcing module as needed | MOM NUOPC cap | MOM FMS cap |
| Calculate interactive shelf melt | MOM | MOM, if shelf enabled | MOM, if shelf enabled |
| Apply fluxes to ocean layers | MOM core | MOM core | MOM core |
| Apply eastern ISOMIP sponge | MOM core | MOM core if configured | MOM core if configured |

In short:

```text
mom6-solo:
prescribed MOM fluxes or MOM idealized/shelf formulas -> MOM core

NUOPC:
atmospheric state -> CDEPS -> CMEPS bulk formula/mediator
                  -> MOM NUOPC adapter -> MOM core

FMS:
atmosphere/FMS coupler -> FMS flux boundary object
                       -> MOM FMS adapter -> MOM core
```

## 7. Current coupled-work status

The files under:

```text
/scratch/au88/jr5971/access-om3/work/
  isomip-test-mom6-for-iom3-configs/
```

are useful evidence of the intended NUOPC field path, especially:

- `nuopc.runconfig`;
- `nuopc.runseq`;
- `datm_in`;
- `datm.streams.xml`; and
- `drof.streams.xml`.

They came from an exploratory coupled setup, not the validated production
result documented for `mom6-solo`. Treat them as a concrete example of field
names and sequencing, not proof that the coupled ISOMIP configuration has
completed successfully.

## 8. Where to look

### This control directory

| File | Why inspect it |
| --- | --- |
| `MOM_input` | Base grid, initialization, shelf, wind, and buoyancy choices |
| `MOM_override` | Effective ISOMIP shelf, forcing interval, sponge, and flux-handling overrides |
| `docs/MOM_parameter_doc.all` | Complete effective parameter set written by the validated model |
| `INPUT/Ocean0_3D_Claire.nc` | The only external geometry input |
| `diag_table` | Requested boundary and shelf diagnostics |
| `manifests/input.yaml` | Exact staged input provenance |
| `manifests/exe.yaml` | Exact staged `mom6-solo` executable |
| `config.yaml` | `payu` module and executable selection |

Useful inspection commands:

```bash
ncdump -h INPUT/Ocean0_3D_Claire.nc
rg -n 'WIND_CONFIG|BUOY_CONFIG|SPONGE|SHELF_|DT_FORCING' \
  MOM_input MOM_override docs/MOM_parameter_doc.all
ncdump -h /scratch/au88/jr5971/mom6-isomip-validation-20260605/\
archive/isomip-test-mom6-for-iom3-configs/output000/forcing.nc
```

### Exact MOM6 source used by the solo executable

The validated executable is:

```text
access-mom6@2026.01.001
MOM6 commit c664721ebd58c033964b502e7fcdcccd05f02947
repository https://github.com/ACCESS-NRI/MOM6
```

Important source files:

```text
src/core/MOM_forcing_type.F90
src/parameterizations/vertical/MOM_diabatic_aux.F90
src/parameterizations/vertical/MOM_ALE_sponge.F90
src/user/ISOMIP_initialization.F90
src/ice_shelf/MOM_ice_shelf.F90
config_src/drivers/solo_driver/MOM_driver.F90
config_src/drivers/solo_driver/MOM_surface_forcing.F90
config_src/drivers/nuopc_cap/mom_cap_methods.F90
config_src/drivers/nuopc_cap/mom_surface_forcing_nuopc.F90
config_src/drivers/nuopc_cap/mom_ocean_model_nuopc.F90
config_src/drivers/FMS_cap/MOM_surface_forcing_gfdl.F90
```

### Exact ACCESS3/CMEPS/CDEPS source used for the prerelease investigation

As inspected on 2026-06-08:

```text
access-om3/pr218-3
access3-share commit 825a3f4835bb088b12f68babe0149b017b16ba72
CMEPS submodule commit 1f8d26a23be9809848146b1334ffa55d1b9d7fa1
CDEPS submodule commit 0b2d3bddbe881ba381fb1fba54d0dd27e706c752
```

The exact recursive source archive installed with the prerelease is:

```text
/g/data/vk83/prerelease/apps/spack/1.1/sourcecache/_source-cache/git/\
ACCESS-NRI/access3-share/825a3f4835bb088b12f68babe0149b017b16ba72.tar.gz
```

The corresponding project repositories are:

- <https://github.com/ACCESS-NRI/access3-share>
- <https://github.com/ACCESS-NRI/cmeps>
- <https://github.com/ACCESS-NRI/cdeps>

The local recursive archive is the authoritative reference for the exact
submodule revisions used by this installed prerelease.
