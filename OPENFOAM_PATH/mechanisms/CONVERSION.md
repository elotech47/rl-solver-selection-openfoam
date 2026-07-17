# Mechanism conversion log

## Source
- `mechanisms/n-dodecane.yaml`
- SHA256: `a28c51c59d4fe251a1cba3905349c7bfffedda44b2826d55f086153ac644c7de`
- Species: 106, Reactions: 678

## Host steps (automated by `tools/convert_mechanism.py`)
1. `Solution.write_chemkin` → `chemkin/chem.inp`, `therm.dat`, `tran.dat`
2. Fix `ELEMENTS` block + `REACTIONS CAL/MOLE` for ESI chemkinReader
3. Rewrite NASA7 headers to 80-col CHEMKIN-II → `therm_of.dat`
4. Provide OpenFOAM-format `transportProperties` (GRI-style `".*"` defaults)

## Container import
```bash
./container/of_shell.sh
# or non-interactive:
docker run --rm --platform=linux/amd64 --entrypoint /bin/bash \
  -v "$PWD:/work" -w /work opencfd/openfoam-default:2312 \
  /work/tools/run_chemkinToFoam.sh
```
Produces `mechanisms/foam/reactions` and `mechanisms/foam/thermo`.

## Status
- Host write_chemkin + patches: **OK**
- chemkinToFoam: see `tools/run_chemkinToFoam.sh` (verified ESI 2312)
