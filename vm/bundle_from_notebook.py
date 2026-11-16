#!/usr/bin/env python3
"""Extract a submission bundle from a public notebook that holds it as a FILES = {path: text} dict literal, without
running the notebook: the dict is read with ast.literal_eval. Checks the notebook's own EXPECTED_DIGEST
(sha256 of json.dumps(FILES, sort_keys=True), first 12 hex digits) when present, then writes the files.

  python3 -I bundle_from_notebook.py <notebook.ipynb> <out_dir>
"""
import ast, hashlib, json, sys
from pathlib import Path


def find_literal(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def main():
    nb, out = Path(sys.argv[1]), Path(sys.argv[2])
    cells = json.loads(nb.read_text(encoding="utf-8"))["cells"]
    files = digest = None
    for c in cells:
        if c.get("cell_type") != "code":
            continue
        src = "".join(c.get("source") or [])
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        files = files or find_literal(tree, "FILES")
        digest = digest or find_literal(tree, "EXPECTED_DIGEST")
    if not isinstance(files, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
        sys.exit("no FILES dict of str -> str found")
    got = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:12]
    print(f"{len(files)} files; digest {got}" + (f" (notebook says {digest}: {'OK' if got == digest else 'MISMATCH'})" if digest else ""))
    if digest and got != digest:
        sys.exit(1)
    for name, text in sorted(files.items()):
        p = (out / name).resolve()
        if out.resolve() not in p.parents:
            sys.exit(f"path outside the bundle: {name}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print("  wrote", name, len(text), "chars")


if __name__ == "__main__":
    main()
