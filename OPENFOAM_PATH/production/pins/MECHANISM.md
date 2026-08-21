# Mechanism pin — Luo n-dodecane / Option R

| Item | Value |
|------|-------|
| Species / reactions | 106 / 678 |
| Source YAML | `mechanisms/n-dodecane.yaml` |
| Production thermo | Option R shared JANAF (`Thigh=3500`), in case `constant/thermo` |
| Conversion (rare) | `tools/convert_mechanism.py` + `tools/run_chemkinToFoam_refit.sh` |

**Do not** reconvert for routine cluster twins. Re-run only if Option R or
mechanism version changes; then update this pin and re-freeze Stage 1.
