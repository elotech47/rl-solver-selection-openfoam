#!/usr/bin/env bash
# E18 Stage 1 — configure opposedJet_E18 cold-mixing case (chemistry OFF).
# Geometry: Ember example_diffusion gap L=8 mm (xLeft=-4mm…xRight=+4mm).
# Strain a=100 s⁻¹ → V_inlet = a·L/2 = 0.4 m/s.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SRC="$ROOT/cases/opposedJet_2D"
CASE="$ROOT/cases/opposedJet_E18"
OUT="$ROOT/validation/zeroD/e18_prep/stage1_cold"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

L=0.008
A=100
V=$(python3 -c "print(0.5*$A*$L)")
P=1013250
T_AIR=1000
T_FUEL=300

mkdir -p "$OUT"
rm -rf "$CASE"
mkdir -p "$CASE"
# Selective copy — do NOT drag E17 time/processor dumps
cp -a --no-preserve=ownership "$SRC/0" "$CASE/0"
cp -a --no-preserve=ownership "$SRC/constant" "$CASE/constant"
cp -a --no-preserve=ownership "$SRC/system" "$CASE/system"
rm -rf "$CASE/constant/polyMesh" 2>/dev/null || true
rm -f "$CASE/0/e17_kernel_meta.txt" 2>/dev/null || true

cp "$SCRIPT_DIR/stage1_blockMeshDict" "$CASE/system/blockMeshDict"

python3 - <<PY
from pathlib import Path
import re
case = Path(r"$CASE")
V, T_air, T_fuel, P = float("$V"), float("$T_AIR"), float("$T_FUEL"), float("$P")

def patch_uniform(path, patch_name, value_str):
    t = path.read_text()
    pat = re.compile(
        rf"({re.escape(patch_name)}\s*\{{[^}}]*?value\s+uniform\s+)[^;]+",
        re.S,
    )
    t2, n = pat.subn(rf"\g<1>{value_str}", t, count=1)
    if n != 1:
        raise SystemExit(f"failed patch {path.name} {patch_name} (n={n})")
    path.write_text(t2)

def patch_vector(path, patch_name, vx, vy=0.0, vz=0.0):
    t = path.read_text()
    pat = re.compile(
        rf"({re.escape(patch_name)}\s*\{{[^}}]*?value\s+uniform\s+)\([^)]+\)",
        re.S,
    )
    t2, n = pat.subn(rf"\g<1>({vx} {vy} {vz})", t, count=1)
    if n != 1:
        raise SystemExit(f"failed vector patch {path.name} {patch_name} (n={n})")
    path.write_text(t2)

p = case / "0/p"
t = p.read_text()
t = re.sub(r"internalField\s+uniform\s+[^;]+;", f"internalField   uniform {P};", t, count=1)
p.write_text(t)

T = case / "0/T"
t = T.read_text()
t = re.sub(r"internalField\s+uniform\s+[^;]+;", f"internalField   uniform {T_air};", t, count=1)
T.write_text(t)
patch_uniform(T, "fuel", str(T_fuel))
patch_uniform(T, "air", str(T_air))
t = T.read_text()
t = re.sub(
    r"(outlet\s*\{[^}]*?inletValue\s+uniform\s+)[^;]+",
    rf"\g<1>{T_air}",
    t, count=1, flags=re.S,
)
t = re.sub(
    r"(outlet\s*\{[^}]*?value\s+uniform\s+)[^;]+",
    rf"\g<1>{T_air}",
    t, count=1, flags=re.S,
)
T.write_text(t)

U = case / "0/U"
t = U.read_text()
t = re.sub(r"internalField\s+uniform\s+\([^)]+\);", f"internalField   uniform ({V} 0 0);", t, count=1)
U.write_text(t)
patch_vector(U, "fuel", V)
patch_vector(U, "air", -V)

for name, fuel_v, air_v, internal in [
    ("nc12h26", 1.0, 0.0, 0.0),
    ("o2", 0.0, 0.233, 0.233),
    ("n2", 0.0, 0.767, 0.767),
]:
    f = case / f"0/{name}"
    t = f.read_text()
    t = re.sub(r"internalField\s+uniform\s+[^;]+;", f"internalField   uniform {internal};", t, count=1)
    f.write_text(t)
    patch_uniform(f, "fuel", str(fuel_v))
    patch_uniform(f, "air", str(air_v))

print(f"BCs: V=±{V} T_fuel={T_fuel} T_air={T_air} P={P}")
u = (case / "0/U").read_text()
assert f"({V}" in u and f"(-{V}" in u
print("U patches OK")
PY

python3 - <<PY
from pathlib import Path
import re
case = Path(r"$CASE")
chem = case / "constant/chemistryProperties"
t = chem.read_text()
t = re.sub(r"chemistry\s+[^;]+;", "chemistry       off;", t, count=1)
chem.write_text(t)
comb = case / "constant/combustionProperties"
ct = comb.read_text()
ct = re.sub(r"active\s+[^;]+;", "active           false;", ct, count=1)
comb.write_text(ct)
print("chemistry off; combustion active false")
PY

python3 - <<PY
from pathlib import Path
import re
p = Path(r"$CASE/system/controlDict")
t = p.read_text()
subs = {
    r"application\s+[^;]+;": "application     reactingFoamDebug;",
    r"endTime\s+[^;]+;": "endTime         0.05;",
    r"deltaT\s+[^;]+;": "deltaT          1e-5;",
    r"writeInterval\s+[^;]+;": "writeInterval   0.005;",
    r"writeControl\s+[^;]+;": "writeControl    adjustableRunTime;",
    r"purgeWrite\s+[^;]+;": "purgeWrite      20;",
    r"writeFormat\s+[^;]+;": "writeFormat     ascii;",
    r"writeCompression\s+[^;]+;": "writeCompression off;",
    r"maxCo\s+[^;]+;": "maxCo           0.5;",
    r"maxDeltaT\s+[^;]+;": "maxDeltaT       1e-4;",
    r"adjustTimeStep\s+[^;]+;": "adjustTimeStep  yes;",
}
for pat, rep in subs.items():
    t2, n = re.subn(pat, rep, t, count=1)
    t = t2 if n else t
if "propSanity" not in t:
    t += "\npropSanity true;\npropSanityInterval 20;\n"
if "SolverPerformance" not in t:
    t += "\nDebugSwitches\n{\n    SolverPerformance 0;\n}\n"
p.write_text(t)
print("controlDict cold: endTime=0.05 writeInterval=0.005")
PY

python3 - <<PY
from pathlib import Path
import re
p = Path(r"$CASE/system/decomposeParDict")
if p.is_file():
    t = p.read_text()
    t = re.sub(r"numberOfSubdomains\s+[^;]+;", "numberOfSubdomains 8;", t, count=1)
    p.write_text(t)
PY

cat > "$OUT/STAGE1_SETUP.md" <<EOF
# E18 Stage 1 — cold mixing setup

| Quantity | Value | Rationale |
|----------|-------|-----------|
| Gap L | **${L} m (8 mm)** | Ember \`example_diffusion.py\`: \`xLeft=-0.004\`, \`xRight=0.004\` → width 8 mm |
| Strain a | ${A} s⁻¹ | Stage 0 pick |
| V_inlet | **±${V} m/s** | \`a·L/2\` to preserve a=100 with matched gap |
| p | 10 atm | Stage 0 pick |
| T_fuel / T_air | ${T_FUEL} / ${T_AIR} K | Stage 0 pick |
| Mesh | 200×100 = 20k, mid-plane refined | Stage 1 target 15–30k |
| Chemistry | **OFF** | inert transport |
| Geometric midplane | x = L/2 = 0.004 m | stagnation shifts toward air (ρ_fuel ≫ ρ_air) |

**Rejected:** E17 gap L=0.02 m → V=1.0 m/s — not Ember-matched.
EOF

echo "CASE=$CASE OUT=$OUT L=$L V=$V"
du -sh "$CASE"
