# E7 — per-reaction rate dump vs Cantera-refit

Primary gate: ≤0.1% on qf/qr/qnet and reversible Kc.

| Pin | PASS_rop | qf | Kc_rev | kf | species_net |
|-----|----------|----|--------|----|-------------|
| T1301 | False | 0.0492% | 1.3319% | 0.5947% | 0.2825% |
| T1500 | False | 0.0349% | 1.3231% | 0.2194% | 0.3466% |
| T1701 | False | 0.0268% | 1.3156% | 0.0985% | 0.2277% |
| T2001 | False | 0.0228% | 1.3210% | 0.0386% | 0.0969% |

Overall PASS=False; worst_char=1.3829%.

Species-net residual remains the E13.2 0.23–0.35% band at T1301–T1701;
ROP gates are the localization target. Irreversible Kc excluded.
