#!/usr/bin/env python3
"""Status / log / output reader for our Kaggle notebooks (run on the VM inside .venv).

  python kev_status.py <slug> [--grep REGEX] [--tail N] [--after REGEX] [--output DIR]
Prints the kernel status, then log lines (stdout+stderr text, nbconvert noise removed) matching --grep,
or the last N lines, or everything after the first line matching --after. --output downloads the kernel output.
"""
import argparse, json, re, subprocess, sys


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("slug"); ap.add_argument("--grep"); ap.add_argument("--tail", type=int, default=0)
    ap.add_argument("--after"); ap.add_argument("--output"); ap.add_argument("--max", type=int, default=60)
    a = ap.parse_args()
    k = a.slug if "/" in a.slug else "aagneye/" + a.slug
    st = subprocess.run(["kaggle", "kernels", "status", k], capture_output=True, text=True).stdout.strip().splitlines()
    print("STATUS", st[-1] if st else "?")
    raw = subprocess.run(["kaggle", "kernels", "logs", k], capture_output=True, text=True).stdout
    try:
        entries = json.loads(raw)
        text = "".join(e.get("data", "") for e in entries)
    except Exception:
        text = raw
    lines = [l for l in text.splitlines() if l.strip() and "NbConvertApp" not in l and "nbconvert" not in l and "MissingIDField" not in l]
    if a.after:
        idx = next((i for i, l in enumerate(lines) if re.search(a.after, l)), None)
        sel = lines[idx:] if idx is not None else []
    elif a.grep:
        sel = [l for l in lines if re.search(a.grep, l, re.I)]
    else:
        sel = lines[-a.tail:] if a.tail else []
    for l in sel[-a.max:] if not a.after else sel[:a.max]:
        print(l[:300])
    if a.output:
        subprocess.run(["kaggle", "kernels", "output", k, "-p", a.output], capture_output=True)
        print("downloaded to", a.output)


if __name__ == "__main__":
    main()
