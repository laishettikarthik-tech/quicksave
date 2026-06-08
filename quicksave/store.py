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
    for f in _snapshot_files(store):
        seq, _, snap_id = f.stem.partition("-")
        if f.stem == ref or snap_id.startswith(ref):
            return f
        if ref.isdigit() and int(seq) == int(ref):
            return f
    return None


def restore(root, ref):
    root = Path(root)
    store = store_path(root)
    f = _find_snapshot(store, ref)
    if f is None:
        raise QuicksaveError(f"snapshot '{ref}' not found")

    manifest = json.loads(f.read_text())
    restored = 0
    for relpath, meta in manifest["files"].items():
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
    return restored, manifest
