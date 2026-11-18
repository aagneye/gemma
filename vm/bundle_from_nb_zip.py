#!/usr/bin/env python3
"""Extract a submission bundle that a public notebook embeds as a base64 zip, e.g. Repair Lab's exact scored run:
parent_original = base64.b64decode('...', validate=True). The notebook is read as text and never run. Checks the
zip's sha256 against the value the notebook asserts, refuses unsafe member paths, optionally compares every member
with an already extracted copy, then writes the members to a new bundle dir.

Some notebooks keep their scored bundle this way while their root submission.zip is a newer, unscored candidate
(Repair Lab, Nov 18: root = exp025 with 40 calls, embedded = exp021, public 0.22). Extract the scored one.

  python3 -I bundle_from_nb_zip.py <notebook.ipynb> <variable> <expected_sha256> <out_dir> [<compare_dir>]
"""
import base64, hashlib, io, json, re, sys, zipfile
from pathlib import Path


def main():
    nb, var, want, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
    ref = Path(sys.argv[5]) if len(sys.argv) > 5 else None
    src = "\n".join("".join(c.get("source") or []) for c in json.loads(nb.read_text(encoding="utf-8"))["cells"]
                    if c.get("cell_type") == "code")
    m = re.search(re.escape(var) + r"\s*=\s*base64\.b64decode\('([A-Za-z0-9+/=]+)'", src)
    if not m:
        sys.exit(f"{var} = base64.b64decode('...') not found")
    data = base64.b64decode(m.group(1))
    got = hashlib.sha256(data).hexdigest()
    print(f"embedded zip: {len(data)} bytes, sha256 {got[:16]}... {'OK' if got == want else 'MISMATCH'}")
    if got != want:
        sys.exit(1)
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} exists and is not empty")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.testzip() is None
        for info in z.infolist():
            name = info.filename
            p = Path(name)
            if p.is_absolute() or ".." in p.parts or "\\" in name:
                sys.exit(f"unsafe member {name}")
            if name.endswith("/"):
                continue
            body = z.read(name)
            note = ""
            if ref is not None:
                c = ref / name
                note = "  copy: " + ("identical" if c.is_file() and c.read_bytes() == body else "DIFFERENT" if c.is_file() else "missing")
            print(f"  {name:24} {len(body):6} bytes{note}")
            dst = out / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(body)
    if ref is not None:
        extra = sorted(p.relative_to(ref).as_posix() for p in ref.rglob("*")
                       if p.is_file() and not (out / p.relative_to(ref)).is_file())
        print("files in the copy but not in the zip:", extra or "none")
    print("wrote", out)


if __name__ == "__main__":
    main()
