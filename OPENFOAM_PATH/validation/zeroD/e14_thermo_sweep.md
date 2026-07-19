# E14 thermo sweep (Campaign 4 commit 1)

Option R = refit NASA polys + stock THE. Production foam already on Option R;
this sweep removes stale Luo heterogeneous thermo from validation harnesses and
quarantines unused GRI / compressibleGas leftovers.

## Canonical fingerprints (SHA-256)

| File | SHA-256 |
|------|---------|
| `mechanisms/foam/thermo` (Option R / production) | `6b649eaa847f5c90565d46b6057bf9f86952b18ec072466ad2ef8b8ce634e66e` |
| `mechanisms/foam_original_heterogeneous/thermo` | `5d6ae68aca5c5835487685d73fbdfa432af5b003fce70d320b561c4c13882f75` |

## Already Option R (unchanged)

| Path | Match |
|------|-------|
| `cases/chemFoam_0D/constant/thermo` | = production |
| `cases/opposedJet_2D/constant/thermo` | = production |

## Replaced → production Option R

| Path | Before | After |
|------|--------|-------|
| `validation/zeroD/expert_repro/case/constant/thermo` | archived | `6b649eaa…` |
| `validation/zeroD/e9_constprop/luo_p/constant/thermo` | archived | `6b649eaa…` |
| `validation/zeroD/e9_constprop/luo_v/constant/thermo` | archived | `6b649eaa…` |

Pre-replace copies live under `archive/e14_thermo_sweep/validation_zeroD_*_constant_thermo`.

## Quarantined under `archive/e14_thermo_sweep/`

- `cases/chemFoam_0D/chemkin/therm.dat`
- `cases/opposedJet_2D/constant/thermo.compressibleGas`
- `validation/zeroD/e9_constprop/luo_{p,v}/chemkin/therm.dat`
- `validation/zeroD/e9_constprop/gri_{p,v}/chemkin/therm.dat`

## Left alone (intentional)

| Path | Note |
|------|------|
| `validation/zeroD/e9_constprop/gri_{p,v}/constant/thermo` | GRI case thermo (`c65914a8…`) |
| `*/constant_original_hetero/**` | Pre-Option-R backups |
| `validation/zeroD/e3_skeletal_*` | Skeletal mechanism cases |

## Verify

```
diff -q cases/chemFoam_0D/constant/thermo mechanisms/foam/thermo
diff -q cases/opposedJet_2D/constant/thermo mechanisms/foam/thermo
diff -q validation/zeroD/expert_repro/case/constant/thermo mechanisms/foam/thermo
```
All three match after this sweep.
