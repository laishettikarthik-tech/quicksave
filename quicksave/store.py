import hashlib
import json
import os
import time
from pathlib import Path

STORE_DIR = ".quicksave"

# dirs we never want in a snapshot: vcs metadata, caches, vendored deps, envs
DEFAULT_IGNORE = {
    ".git", ".hg", ".svn",
    STORE_DIR,
    "node_modules", "bower_components",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "venv", ".venv", "env", "virtualenv",
    "dist", "build", ".next", ".cache",
    ".idea", ".vscode", ".DS_Store",
}


class QuicksaveError(Exception):
    pass


def store_path(root):
    return Path(root) / STORE_DIR


def find_root(start=None):
    cur = Path(start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / STORE_DIR).is_dir():
            return p
    return None


def init(path=None):
    root = Path(path or Path.cwd()).resolve()
    store = store_path(root)
    if store.is_dir():
        return root, False
    (store / "objects").mkdir(parents=True)
    (store / "snapshots").mkdir(parents=True)
    return root, True


def iter_files(root, ignore=DEFAULT_IGNORE):
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        # prune ignored dirs so os.walk does not descend into them
        dirnames[:] = [d for d in dirnames if d not in ignore]
        rel_dir = Path(dirpath).relative_to(root)
        for name in filenames:
            if name in ignore:
                continue
            yield rel_dir / name if str(rel_dir) != "." else Path(name)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _write_blob(store, data):
    digest = _sha256(data)
    obj = store / "objects" / digest[:2] / digest[2:]
    if not obj.exists():
        obj.parent.mkdir(parents=True, exist_ok=True)
        tmp = obj.with_name(obj.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(obj)
    return digest


def _snapshot_files(store):
    d = Path(store) / "snapshots"
    if not d.is_dir():
        return []
    return sorted(d.glob("*.json"))


def save(root, message="", ignore=DEFAULT_IGNORE):
    root = Path(root)
    store = store_path(root)
    if not store.is_dir():
        raise QuicksaveError("not a quicksave project, run 'quicksave init' first")

    files = {}
    for rel in iter_files(root, ignore):
        full = root / rel
        try:
            data = full.read_bytes()
        except OSError:
            continue
        digest = _write_blob(store, data)
        files[rel.as_posix()] = {
            "sha256": digest,
            "size": len(data),
            "mode": full.stat().st_mode & 0o777,
        }

    manifest = {"message": message, "created_at": time.time(), "files": files}
    body = json.dumps(manifest, sort_keys=True).encode()
    snap_id = _sha256(body)[:12]
    seq = len(_snapshot_files(store))
    name = f"{seq:04d}-{snap_id}.json"
    (store / "snapshots" / name).write_text(json.dumps(manifest, indent=2))
    return snap_id, len(files)


def list_snapshots(root):
    store = store_path(root)
    out = []
    for f in _snapshot_files(store):
        seq, _, snap_id = f.stem.partition("-")
        m = json.loads(f.read_text())
        out.append({
            "seq": int(seq),
            "id": snap_id,
            "message": m.get("message", ""),
            "created_at": m.get("created_at", 0),
            "count": len(m.get("files", {})),
        })
    return out


def _find_snapshot(store, ref):
    ref = str(ref)
    files = _snapshot_files(store)
    # a bare number is a sequence from 'list'; resolve it before any id-prefix
    # match so an id that happens to start with that digit can't shadow it
    for f in files:
        seq, _, _ = f.stem.partition("-")
        if f.stem == ref or (ref.isdigit() and int(seq) == int(ref)):
            return f
    for f in files:
        _, _, snap_id = f.stem.partition("-")
        if snap_id.startswith(ref):
            return f
    return None


def diff(root, ref_a, ref_b):
    store = store_path(root)
    fa = _find_snapshot(store, ref_a)
    if fa is None:
        raise QuicksaveError(f"snapshot '{ref_a}' not found")
    fb = _find_snapshot(store, ref_b)
    if fb is None:
        raise QuicksaveError(f"snapshot '{ref_b}' not found")

    a = json.loads(fa.read_text())["files"]
    b = json.loads(fb.read_text())["files"]
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    modified = sorted(p for p in set(a) & set(b) if a[p]["sha256"] != b[p]["sha256"])
    return {"added": added, "removed": removed, "modified": modified}


def status(root, ref=None, ignore=DEFAULT_IGNORE):
    store = store_path(root)
    snaps = _snapshot_files(store)
    if not snaps:
        raise QuicksaveError("no snapshots yet, run 'quicksave save' first")
    f = snaps[-1] if ref is None else _find_snapshot(store, ref)
    if f is None:
        raise QuicksaveError(f"snapshot '{ref}' not found")

    snap = {p: m["sha256"] for p, m in json.loads(f.read_text())["files"].items()}
    cur = {}
    for rel in iter_files(root, ignore):
        try:
            cur[rel.as_posix()] = _sha256((Path(root) / rel).read_bytes())
        except OSError:
            continue

    seq, _, snap_id = f.stem.partition("-")
    return {
        "seq": int(seq),
        "id": snap_id,
        "added": sorted(set(cur) - set(snap)),
        "removed": sorted(set(snap) - set(cur)),
        "modified": sorted(p for p in set(cur) & set(snap) if cur[p] != snap[p]),
    }


def _path_selected(relpath, paths):
    for p in paths:
        if relpath == p or relpath.startswith(p.rstrip("/") + "/"):
            return True
    return False


def restore(root, ref, paths=None, clean=False, ignore=DEFAULT_IGNORE):
    root = Path(root)
    store = store_path(root)
    f = _find_snapshot(store, ref)
    if f is None:
        raise QuicksaveError(f"snapshot '{ref}' not found")

    manifest = json.loads(f.read_text())
    files = manifest["files"]
    wanted = [Path(p).as_posix() for p in paths] if paths else None
    if wanted:
        files = {rel: meta for rel, meta in files.items() if _path_selected(rel, wanted)}
        if not files:
            raise QuicksaveError(f"no files matching {', '.join(paths)} in snapshot '{ref}'")

    restored = 0
    for relpath, meta in files.items():
        digest = meta["sha256"]
        obj = store / "objects" / digest[:2] / digest[2:]
        if not obj.exists():
            raise QuicksaveError(f"missing blob {digest} for {relpath}")
        target = root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(obj.read_bytes())
        try:
            os.chmod(target, meta["mode"])
        except OSError:
            pass
        restored += 1

    removed = 0
    if clean:
        keep = set(files)
        for rel in iter_files(root, ignore):
            relp = rel.as_posix()
            if relp in keep:
                continue
            if wanted and not _path_selected(relp, wanted):
                continue
            try:
                (root / relp).unlink()
                removed += 1
            except OSError:
                pass
    return restored, removed, manifest
