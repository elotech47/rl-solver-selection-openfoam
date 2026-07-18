# E10b — Tcommon / breakpoint histogram
## Luo_106
- file: `mechanisms/foam/thermo`
- n_species: **106**
- distinct (Tlow,Tcommon,Thigh): **31**
- distinct Tcommon: **28**
- uniform breakpoints: **False**

### Tuple histogram
| Tlow | Tcommon | Thigh | count |
|-----:|--------:|------:|------:|
| 300 | 1000 | 5000 | 19 |
| 300 | 1391 | 5000 | 12 |
| 300 | 1385 | 5000 | 10 |
| 300 | 1389 | 5000 | 7 |
| 300 | 1390 | 5000 | 6 |
| 300 | 1393 | 5000 | 6 |
| 300 | 1384 | 5000 | 5 |
| 300 | 1387 | 5000 | 5 |
| 300 | 1382 | 5000 | 4 |
| 300 | 1392 | 5000 | 4 |
| 300 | 1386 | 5000 | 3 |
| 300 | 1378 | 5000 | 2 |
| 300 | 1380 | 5000 | 2 |
| 300 | 1381 | 5000 | 2 |
| 300 | 1383 | 5000 | 2 |
| 300 | 1388 | 5000 | 2 |
| 200 | 1000 | 3500 | 1 |
| 300 | 1000 | 3000 | 1 |
| 300 | 1000 | 4000 | 1 |
| 300 | 1377 | 5000 | 1 |
| 300 | 1394 | 5000 | 1 |
| 300 | 1395 | 5000 | 1 |
| 300 | 1396 | 5000 | 1 |
| 300 | 1397 | 5000 | 1 |
| 300 | 1398 | 5000 | 1 |
| 300 | 1400 | 4000 | 1 |
| 300 | 1402 | 5000 | 1 |
| 300 | 1492 | 5000 | 1 |
| 300 | 1710 | 5000 | 1 |
| 300 | 2042 | 5000 | 1 |
| 300 | 5000 | 5000 | 1 |

### Tcommon histogram (examples)
| Tcommon | count | example species |
|--------:|------:|-----------------|
| 1000 | 22 | ch2cho, o, h2, c2h2, h2o |
| 1391 | 12 | c4h8-1, c12ooh2-4, c12ooh5-7, pc4h9, c12h25o2-6 |
| 1385 | 10 | c9h17, pc4h9o2, nc6h13cho, c12h25-5, c12h25-2 |
| 1389 | 7 | c12ket5-3, c2h5o, c12ket5-7, c12ket2-4, c12ket6-8 |
| 1390 | 6 | c12ooh5-7o2, c7h15-1, c12ooh2-4o2, c6h13-1, c12ooh6-4o2 |
| 1393 | 6 | c12o2-4, c4h7o1-4, c2h3cho, c12o5-7, c4h7ooh1-4 |
| 1384 | 5 | nc5h11cho, c8h16-1, c2h6, nc3h7o2, c9h18-1 |
| 1387 | 5 | nc8h17co, nc4h9coch2, nc8h17cho, c3h8, c4h8ooh1-3o2 |
| 1382 | 4 | c8h17-1, nc4h9co, c9h19-1, c7h15coch2 |
| 1392 | 4 | c10h20-1, c4h10, c4h71-3, c6h12-1 |
| 1386 | 3 | nc4ket13, nc3h7, c5h11coch2 |
| 1378 | 2 | c2h5cho, nc3h7cho |
| 1380 | 2 | c3h5o, nc3h7co |
| 1381 | 2 | c8h17o2-1, nc4h9cho |
| 1383 | 2 | c7h14ooh1-3, nc5h11co |
| 1388 | 2 | c7h15o2-1, c3h6 |
| 1377 | 1 | c4h8ooh1-3 |
| 1394 | 1 | c2h5 |
| 1395 | 1 | c4h7o |
| 1396 | 1 | c5h11-1 |
| 1397 | 1 | c3h5-a |
| 1398 | 1 | c4h6 |
| 1400 | 1 | c3h4-a |
| 1402 | 1 | c2h3co |
| 1492 | 1 | c2h3o1-2 |
| 1710 | 1 | oh |
| 2042 | 1 | c8h17coch2 |
| 5000 | 1 | h |

## skeletal_53
- file: `validation/zeroD/e3_skeletal_dodecane/case/constant/thermo`
- n_species: **52**
- distinct (Tlow,Tcommon,Thigh): **8**
- distinct Tcommon: **5**
- uniform breakpoints: **False**

### Tuple histogram
| Tlow | Tcommon | Thigh | count |
|-----:|--------:|------:|------:|
| 200 | 1000 | 3500 | 19 |
| 300 | 1000 | 5000 | 12 |
| 300 | 1390 | 5000 | 7 |
| 300 | 1392 | 5000 | 6 |
| 200 | 1000 | 6000 | 2 |
| 300 | 1000 | 3000 | 2 |
| 300 | 1385 | 5000 | 2 |
| 300 | 1391 | 5000 | 2 |

### Tcommon histogram (examples)
| Tcommon | count | example species |
|--------:|------:|-----------------|
| 1000 | 35 | OH, pC4H9, C2H3, N2, nC3H7 |
| 1390 | 7 | PXC12H25, PXC8H17, PXC10H21, PXC9H19, PXC6H13 |
| 1392 | 6 | C7H14, C8H16, C10H20, C9H18, C6H12 |
| 1385 | 2 | SXC12H25, S3XC12H25 |
| 1391 | 2 | NC12H26, C12H24 |

## GRI_tutorial
- file: `validation/zeroD/e9_constprop/gri_p/constant/thermo`
- n_species: **53**
- distinct (Tlow,Tcommon,Thigh): **8**
- distinct Tcommon: **4**
- uniform breakpoints: **False**

### Tuple histogram
| Tlow | Tcommon | Thigh | count |
|-----:|--------:|------:|------:|
| 200 | 1000 | 3500 | 27 |
| 200 | 1000 | 6000 | 13 |
| 200 | 1000 | 5000 | 7 |
| 200 | 1000 | 4000 | 2 |
| 200 | 1000 | 3000 | 1 |
| 200 | 1368 | 5000 | 1 |
| 200 | 1382 | 5000 | 1 |
| 200 | 1478 | 5000 | 1 |

### Tcommon histogram (examples)
| Tcommon | count | example species |
|--------:|------:|-----------------|
| 1000 | 50 | OH, CN, C2H3, N2, N |
| 1368 | 1 | HOCN |
| 1382 | 1 | HCNO |
| 1478 | 1 | HNCO |

## Thesis-ready root-cause paragraph

OpenFOAM evaluates mixture sensible enthalpy and heat capacity for `hePsiThermo::correct()` / `THE` by blending each species' NASA-7 *coefficient arrays* by mass fraction (`multiComponentMixture::cellMixture`) and then evaluating the resulting pseudo-species polynomials. That blend is algebraically identical to a mass-weighted property average (`Σ Yi·cp_i`, `Σ Yi·hs_i`) *only* when every species shares the same temperature breakpoints (especially a shared `Tcommon`). In the ESI GRI chemFoam tutorial thermo, **50/53** species share Tcommon = 1000 K (near-uniform; outliers: HOCN, HCNO, HNCO with Tcommon ∈ {1368, 1382, 1478}; Thigh also varies → 8 distinct full tuples). The Luo n-dodecane foam thermo has **31** distinct (Tlow,Tcommon,Thigh) tuples and **28** distinct Tcommon values across 106 species; the skeletal foam thermo shows **8** distinct tuples and **5** distinct Tcommon (52 species parsed). Above the lowest Tcommon in a mixed cell, some species are already on their high-range coefficients while others remain on low-range ones, so the blended coefficients no longer represent any physical mixture average: burnt-gas blended cp collapses toward zero and can change sign, while `Σ Yi·cp_i` stays O(1400) J/(kg·K). The h→T Newton then diverges (E8). This is **H6**: a representation defect exposed by OpenFOAM's coefficient blend under mechanism-heterogeneous JANAF breakpoints, not a corruption of per-species thermo tables (E2).

## Claim check

- GRI Tcommon exact-uniform: **False** (4 distinct; dominant 50/53 = 94.3% at 1000 K)
- GRI Tcommon near-uniform (campaign 'or near'): **True**
- Luo heterogeneous: **True** (28 Tcommon, 31 tuples; only 22/106 at 1000 K)
- Expected claim (GRI near-uniform ∧ Luo heterogeneous): **PASS**
- **STOP (human gate):** GRI is near-uniform, not exact (outliers: HOCN, HCNO, HNCO). H6 mechanism story still holds (severity of heterogeneity: Luo ≫ GRI), and E11 refit remains a valid cure for Luo — but campaign stop condition requires human ack before E11.
