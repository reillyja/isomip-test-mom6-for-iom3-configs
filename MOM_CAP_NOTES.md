# What changed to make `MED OCN` work?

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

## Settings retained for parity

```text
component_list: MED OCN
zero_missing_imports = true
apply_startup_lag = false
MOM6 DT = DT_FORCING = coupling interval = 300 seconds
ICE_SHELF_USTAR_FROM_VEL_BUGFIX = False
```

The last setting is the historical answer-compatibility choice, not a new fix made for this handoff. Preserve the 900 kg/m³ ice density and matching initial-pressure scale (8820 Pa/m) when reproducing this reference.

## Payu compatibility is separate from the model changes

Payu 1.3.2's ACCESS-OM3 adapter expects `datm/drof` labels and their archival pointers. `tools/patch_ocean_only_runconfig.py` changes the staged labels to `satm/srof` and writes tiny bookkeeping files for those absent components. CMEPS runs only MED and OCN and does not consume the bookkeeping files. The run sequence has no MED→OCN forcing transfer.

The local archive hook standardizes archived filenames and packages any ESMF trace streams. Its copied Python helpers are ordinary Payu postprocessing, not MOM cap code.

## Source and evidence limits

The June MOM6 base was `c664721ebd58c033964b502e7fcdcccd05f02947` (`2026.01.001`), with uncommitted local changes; ACCESS3 used `825a3f4835bb088b12f68babe0149b017b16ba72` (`2026.03.000`). These base commits alone do not rebuild the patched executable. Reusing the hash-verified executable is the supported Gadi handoff; a source rebuild would need an independently recovered and checked June patch set.

The behavioral list and numerical evidence come from the historical `ISOMIP_THREE_PATH_RUNBOOK.md` in the parent project's master branch. [VALIDATION.md](VALIDATION.md) preserves its comparison details and job IDs. Do not interpret later evolving-geometry/ISSM source changes as requirements for this static case.
