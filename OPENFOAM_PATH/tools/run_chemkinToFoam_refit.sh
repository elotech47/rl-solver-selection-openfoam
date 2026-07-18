#!/bin/bash
# chemkinToFoam for E11 refit thermo (does NOT overwrite production mechanisms/foam).
set -eo pipefail
source /usr/lib/openfoam/openfoam2312/etc/bashrc
cd /work
mkdir -p mechanisms/refit/foam
echo "Running chemkinToFoam (refit)..."
chemkinToFoam \
  mechanisms/refit/chemkin/chem.inp \
  mechanisms/refit/chemkin/therm_of.dat \
  mechanisms/refit/chemkin/transportProperties \
  mechanisms/refit/foam/reactions \
  mechanisms/refit/foam/thermo
echo "Done."
python3 - <<'PY'
from pathlib import Path
import re
from collections import Counter
text=Path('mechanisms/refit/foam/thermo').read_text()
tc=re.findall(r'Tcommon\s+([0-9.eE+\-]+)', text)
print('n Tcommon entries', len(tc), 'distinct', dict(Counter(tc)))
th=re.findall(r'Thigh\s+([0-9.eE+\-]+)', text)
print('distinct Thigh', dict(Counter(th)))
tl=re.findall(r'Tlow\s+([0-9.eE+\-]+)', text)
print('distinct Tlow', dict(Counter(tl)))
PY
ls -la mechanisms/refit/foam
