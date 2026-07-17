#!/bin/bash
set -euo pipefail
source /usr/lib/openfoam/openfoam2312/etc/bashrc
cd /work
mkdir -p mechanisms/foam
if [[ ! -f mechanisms/chemkin/transportProperties ]]; then
  cp "$WM_PROJECT_DIR/tutorials/combustion/chemFoam/gri/chemkin/transportProperties" \
     mechanisms/chemkin/transportProperties
fi
echo "Running chemkinToFoam..."
chemkinToFoam \
  mechanisms/chemkin/chem.inp \
  mechanisms/chemkin/therm_of.dat \
  mechanisms/chemkin/transportProperties \
  mechanisms/foam/reactions \
  mechanisms/foam/thermo
echo "Done."
ls -la mechanisms/foam
wc -l mechanisms/foam/reactions mechanisms/foam/thermo
