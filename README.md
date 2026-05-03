# Idealised ISOMIP+ like config for iom3 examples

Modified from the MOM6-examples rho case by using a symmetric ice thickness file and adding to the `MOM_override` https://github.com/NOAA-GFDL/MOM6-examples/tree/dev/gfdl/ocean_only/ISOMIP/rho

- Fixes some bugs identified from pressure gradient and initialisation 
- Adds some parameters for ISOMIP+ config (https://github.com/gustavo-marques/ISOMIP) so that it resembles the Ocean0 warm test case (the MOM6-examples one is more like the cold case)
- Uses HJ99 melt parameterisation and conductive heat flux into ice shelf (non-standard)
- Runs on 48 cpus, 3 months in ~6 minutes

### Executable used

Checked that it ran using a version of MOM6 compiled on gadi using Angus Gibson's [ninja](https://github.com/angus-g/mom6-ninja-nci) method. You can see the FMS/MOM6 versions in the src folder. https://github.com/claireyung/setup-mom6-nci-executable/tree/test-ice-shelf-config-iom3

Before compiling with ninja I loaded the following modules on gadi (I had trouble with just the latest defaults)
```
module load intel-mkl/2021.4.0
module load python3/3.9.2
module load intel-compiler/2021.8.0
module load openmpi/4.1.4
module load netcdf/4.9.2
```

### Debugging plots

To generate quick diagnostics for NUOPC mask issues and grounding-cell failures, run:

```bash
cd /g/data/au88/jr5971/isomip-test-mom6-for-iom3-configs
python tools/isomip_error_diagnostics.py
```

This writes figures and a text summary to `diagnostics/`, including:

- ocean/shelf geometry and cavity thickness
- full versus cavity-masked ESMF mesh masks
- logged grounding/error points from `access-om3.err` or `work/warnfile.000000.out`
- placeholder forcing fields overlaid with the failure points
