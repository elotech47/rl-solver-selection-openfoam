# chemFoam 0D case scaffold for Luo n-dodecane (ESI v2312)
#
# Setup inside Docker:
#   ./container/of_shell.sh
#   cd cases/chemFoam_0D
#   ./Allrun   # after mechanisms/foam exists

README
====

This case is bootstrapped from the ESI `chemFoam` tutorial and retargeted at the
Luo 106 mechanism imported via `chemkinToFoam`.

chemistryProperties should select `ode` (stock smoke) or custom `cvode` / `qss`
after libraries are `wmake`'d:

```
chemistryType
{
    chemistrySolver   ode;   // smoke: ode | later: cvode | qss
    chemistryThermo   psi;
}
```

Paper IC MidT_MidP for smoke: T=800 K, P=10 atm, Z=0.062.
