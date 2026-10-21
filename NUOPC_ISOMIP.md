# Runtime and restart details

The [README](README.md) is the quick start and [MOM cap notes](MOM_CAP_NOTES.md) explain the implementation.

`component_list: MED OCN` runs a single mediator rank and 48 ocean ranks. All atmosphere/runoff imports are disconnected and initialized to zero by the patched cap. MOM6 retains internally calculated shelf pressure, melting/freezing, drag and configured gustiness. Geometry is read directly by MOM6 and held fixed.

The checked-in `nuopc.runconfig` uses `ATM_model=datm` and `ROF_model=drof` solely for Payu 1.3.2 compatibility. After Payu stages files, the setup hook changes the staged labels to `satm/srof`. It also creates regular `rpointer.atm`, `rpointer.rof` and corresponding `payu_stub.*.r` targets for Payu bookkeeping. They are not scientific restarts and are not read by CMEPS.

For a fresh experiment, use a new laboratory and `start_type=startup`. Payu manages continuation state when another segment is run in an existing laboratory. A complete real continuation needs the mediator and ocean restart/pointers and `Shelf.res.nc`, as well as the bookkeeping files expected by Payu. Do not add `input_filename='n'` to `input.nml`; it overrides the ocean filename provided by `rpointer.ocn` and prevents correct continuation.

The cold-start configuration has no saved restart manifest or pointers. New Payu manifests are generated locally and ignored by Git. The immutable baseline hashes live separately under `provenance/`.

The existing June comparisons used different calendar epochs for solo and NUOPC (year 1 versus year 1900). Compare by elapsed time. The sharing default is a two-step smoke, not the historical 90-day duration; use `tools/set_duration_profile.py three-month` in a new experiment to select that duration.
