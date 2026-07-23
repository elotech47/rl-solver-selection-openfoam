#!/usr/bin/env python3
"""Quiet progress filter for E17 smoke: one line / 20 steps + propSanity / writes."""
from __future__ import annotations

import re
import sys
import time

TIME_RE = re.compile(r"^Time = ([0-9.eE+-+-]+)")
EXEC_RE = re.compile(r"ExecutionTime = ([0-9.eE+-]+) s\s+ClockTime = ([0-9.eE+-]+) s")
TMAX_RE = re.compile(r"min/max\(T\) = [0-9.eE+-]+, ([0-9.eE+-]+)")
PROPS_RE = re.compile(
    r"propSanity: T ([0-9.eE+-]+) ([0-9.eE+-]+)"
)
WROTE_RE = re.compile(r"^Writing field (\S+) at time ([0-9.eE+-]+)")


def main() -> None:
    end_time = float(sys.argv[1]) if len(sys.argv) > 1 else 5e-4
    step = 0
    last_t = None
    last_clock = None
    last_tmax = None
    t0 = time.time()

    for raw in sys.stdin:
        line = raw.rstrip("\n")

        m = TIME_RE.match(line)
        if m:
            last_t = float(m.group(1))
            continue

        m = TMAX_RE.search(line)
        if m:
            last_tmax = float(m.group(1))
            continue

        m = EXEC_RE.search(line)
        if m and last_t is not None:
            step += 1
            clock = float(m.group(2))
            dt = None
            if last_clock is not None and clock > last_clock:
                dt = clock - last_clock
            last_clock = clock
            if step % 20 == 0:
                eta = ""
                if dt and last_t > 0:
                    rem = max(end_time - last_t, 0.0)
                    eta_s = rem * dt / max(last_t, 1e-30)
                    eta = f" ETA={eta_s/60:.1f}m"
                print(
                    f"t={last_t:.6g} dt={dt or 0:.4g}s maxT={last_tmax or 0:.1f} "
                    f"s/step={dt or 0:.3g}{eta}",
                    flush=True,
                )
            continue

        m = PROPS_RE.search(line)
        if m and step % 10 == 0:
            print(
                f"propSanity t={last_t or 0:.6g} Tint={m.group(1)} Tmax={m.group(2)}",
                flush=True,
            )
            continue

        if line.startswith("rlUsage"):
            print(line, flush=True)
            continue

        m = WROTE_RE.match(line)
        if m:
            print(f"WROTE t={m.group(2)} field={m.group(1)}", flush=True)


if __name__ == "__main__":
    main()
