#!/bin/bash
# Rebuild chemFoamDebug (header-only hEqn change is enough for wmake).
set -eo pipefail
source /usr/lib/openfoam/openfoam2312/etc/bashrc
export WM_PROJECT_USER_DIR=/work
export FOAM_USER_APPBIN=/work/platforms/${WM_OPTIONS}/bin
export FOAM_USER_LIBBIN=/work/platforms/${WM_OPTIONS}/lib
mkdir -p "$FOAM_USER_APPBIN" "$FOAM_USER_LIBBIN"
cd /work/applications/solvers/chemFoam
wmake -j 2
ls -la "$FOAM_USER_APPBIN/chemFoamDebug"
