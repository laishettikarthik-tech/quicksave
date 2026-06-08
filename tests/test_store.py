import os

import pytest

from quicksave import store


def test_init_creates_layout(tmp_path):
    root, created = store.init(tmp_path)
    assert created is True
    assert (tmp_path / ".quicksave" / "objects").is_dir()
    assert (tmp_path / ".quicksave" / "snapshots").is_dir()
    # second init is a no-op
    _, created2 = store.init(tmp_path)
    assert created2 is False


def test_save_requires_init(tmp_path):
    with pytest.raises(store.QuicksaveError):
        store.save(tmp_path)


def test_save_and_list(tmp_path):
    store.init(tmp_path)
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("world")

    snap_id, n = store.save(tmp_path, message="first")
    assert n == 2
    snaps = store.list_snapshots(tmp_path)
    assert len(snaps) == 1
    assert snaps[0]["id"] == snap_id
    assert snaps[0]["message"] == "first"
    assert snaps[0]["count"] == 2


def test_ignore_rules(tmp_path):
    store.init(tmp_path)
    (tmp_path / "keep.txt").write_text("x")
    for junk in ["node_modules", "__pycache__", ".venv"]:
        d = tmp_path / junk
        d.mkdir()
        (d / "trash").write_text("nope")
    _, n = store.save(tmp_path)
    assert n == 1


def test_dedup_same_content(tmp_path):
    store.init(tmp_path)
    (tmp_path / "a.txt").write_text("same")
    (tmp_path / "b.txt").write_text("same")
    store.save(tmp_path)
    objects = list((tmp_path / ".quicksave" / "objects").rglob("*"))
    blobs = [p for p in objects if p.is_file()]
    assert len(blobs) == 1


def test_restore_after_delete(tmp_path):
    store.init(tmp_path)
    (tmp_path / "code.py").write_text("print('keep me')")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.txt").write_text("payload")
    snap_id, _ = store.save(tmp_path, message="before rm")

    # simulate an agent nuking the tree
    os.remove(tmp_path / "code.py")
    os.remove(tmp_path / "data" / "x.txt")
    assert not (tmp_path / "code.py").exists()

    n, _ = store.restore(tmp_path, snap_id)
    assert n == 2
    assert (tmp_path / "code.py").read_text() == "print('keep me')"
    assert (tmp_path / "data" / "x.txt").read_text() == "payload"


def test_restore_by_number(tmp_path):
    store.init(tmp_path)
    (tmp_path / "f.txt").write_text("v1")
    store.save(tmp_path)
    (tmp_path / "f.txt").write_text("v2")
    store.save(tmp_path)

    store.restore(tmp_path, "0")
    assert (tmp_path / "f.txt").read_text() == "v1"


def test_restore_missing_ref(tmp_path):
    store.init(tmp_path)
    with pytest.raises(store.QuicksaveError):
        store.restore(tmp_path, "nope")


def test_diff_between_snapshots(tmp_path):
    store.init(tmp_path)
    (tmp_path / "keep.txt").write_text("same")
    (tmp_path / "gone.txt").write_text("bye")
    (tmp_path / "edit.txt").write_text("v1")
    store.save(tmp_path)

    os.remove(tmp_path / "gone.txt")
    (tmp_path / "edit.txt").write_text("v2")
    (tmp_path / "new.txt").write_text("hi")
    store.save(tmp_path)

    d = store.diff(tmp_path, "0", "1")
    assert d["added"] == ["new.txt"]
    assert d["removed"] == ["gone.txt"]
    assert d["modified"] == ["edit.txt"]


def test_diff_identical_is_empty(tmp_path):
    store.init(tmp_path)
    (tmp_path / "a.txt").write_text("x")
    store.save(tmp_path)
    store.save(tmp_path)
    d = store.diff(tmp_path, "0", "1")
    assert d == {"added": [], "removed": [], "modified": []}


def test_diff_missing_ref(tmp_path):
    store.init(tmp_path)
    store.save(tmp_path)
    with pytest.raises(store.QuicksaveError):
        store.diff(tmp_path, "0", "nope")
