# Validation record

## Sharing preparation — 22 October 2026

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

## Existing numerical evidence — 8–9 June 2026

The original three-path comparison used MOM6-solo, stock CMEPS `MED OCN`, and the toy mediator with matching 300-second ocean/forcing timesteps and a 16×3 ocean layout.

| Test | Historical result |
| --- | --- |
| 600-second smoke, one day, one month, 90 days | All three paths passed |
| Ocean temperature, salinity, velocity, thickness and interface height at 90 days | Bitwise equal to solo |
| Compared surface forcing and shelf pressure/melt/heat/stress diagnostics | Bitwise equal to solo |
| Common prognostic restart fields | Equal to solo, excluding the absolute-time `ave_ssh` accumulator |
| 12+12-hour and 45+45-day continuous/split tests | All 21 MOM restart variables and all three shelf variables equal; all 23 common numeric CMEPS restart variables equal |

Recorded jobs: solo 90-day `170282886`, CMEPS 90-day `170282887`, toy 90-day `170283761`, CMEPS split `170283788` and `170285364`, toy split `170283762` and `170285351`.

The historical record is `ISOMIP_THREE_PATH_RUNBOOK.md` in the original configuration repository's master branch. The local reference is `/g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs/ISOMIP_THREE_PATH_RUNBOOK.md`. Historical outputs remain under `/scratch/au88/jr5971/isomip-comparison/`; they are evidence, not runtime dependencies of this sharing branch.

This evidence concerns the June static geometry and executable. It does not establish equivalence to the later Ocean3 GLCSTUB configuration, validate another executable or geometry, or predict the scientific results of new parameter choices.
