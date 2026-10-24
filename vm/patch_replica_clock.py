#!/usr/bin/env python3
"""Replica-only patch of the harness clock in scorer-host-venv (NEVER part of a submission).

The T4s run the 31B 6-16x slower than the scorer's L4s, so a wall-clock cap of 8 min would cut runs short. With
REPLICA_TIME_SCALE=k the harness measures agent time as wall_time / k: the prompt still says "8.0 minutes",
get_status reports L4-equivalent remaining time, and the hard cap becomes k * 8 real minutes.
Idempotent; run once after (re)building scorer-host-venv.  python patch_replica_clock.py <site-packages>/swegemma
"""
import sys
from pathlib import Path

root = Path(sys.argv[1])
ctx = root / "context.py"; s = ctx.read_text()
if "REPLICA_TIME_SCALE" not in s:
    s = s.replace("    def agent_elapsed_seconds(self) -> float:\n",
                  "    def agent_elapsed_seconds(self) -> float:\n        return self._agent_elapsed_wall() / _replica_scale()\n\n"
                  "    def _agent_elapsed_wall(self) -> float:\n", 1)
    s = s.replace("        return time.perf_counter() - self.task_start_time\n",
                  "        return (time.perf_counter() - self.task_start_time) / _replica_scale()\n", 1)
    s = "import os as _os\n\ndef _replica_scale() -> float:\n    return float(_os.environ.get('REPLICA_TIME_SCALE', '1') or 1)\n\n" + s
    # keep __future__ imports first
    if "from __future__" in s:
        lines = s.splitlines(True); fut = [l for l in lines if l.startswith("from __future__")]
        s = "".join(fut) + "".join(l for l in lines if not l.startswith("from __future__"))
    ctx.write_text(s)
ar = root / "harness" / "agent_runner.py"; t = ar.read_text()
if "REPLICA_TIME_SCALE" not in t:
    t = t.replace("            asyncio.timeout(timeout_sec)\n",
                  "            asyncio.timeout(timeout_sec * float(__import__('os').environ.get('REPLICA_TIME_SCALE', '1') or 1))  # REPLICA_TIME_SCALE\n", 1)
    ar.write_text(t)
print("patched" if "REPLICA_TIME_SCALE" in ctx.read_text() and "REPLICA_TIME_SCALE" in ar.read_text() else "PATCH FAILED")
