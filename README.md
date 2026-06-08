# quicksave

F5 for your filesystem. Checkpoint before every risky command, restore even after `rm -rf`.

Coding agents run shell commands you didn't read. Most undo tools only track git or the editor's
own session, so an agent's `rm`, `mv`, or a stray script can wipe files that nothing was watching.
quicksave snapshots the whole working tree into a local content-addressed store, so you can roll
back to any checkpoint - including files that were never committed.

## Install

```
pip install -e .
```

Needs Python 3.10+.

## Usage

```
quicksave init                 # start tracking this directory
quicksave save -m "before refactor"
quicksave list
quicksave restore 3            # restore by number from the list
quicksave restore a1b2c3       # or by id
quicksave restore 3 src/app.py # only pull back one file or directory
quicksave restore 3 --clean    # exact rewind: also delete files added after the snapshot
quicksave status               # what changed in the tree since the last snapshot
quicksave diff 2 3             # see what changed between two snapshots
quicksave gc --keep 10         # drop old snapshots and blobs nothing points at
```

Typical flow with an agent:

```
quicksave save -m "pre-agent"
# let the agent run wild
quicksave list                 # see what you can fall back to
quicksave restore 0            # roll back if it broke something
```

`restore` brings back every file that was in the snapshot, so deleting a directory and restoring
gets it back. Pass one or more paths to only restore those (a directory name matches everything
under it). By default it is additive: it won't touch new files you created after the snapshot. Add
`--clean` for an exact rewind that also deletes files the snapshot didn't have, so the tree matches
the checkpoint byte for byte.

`status` compares the working tree to a snapshot (the latest one unless you name another) and shows
what was added, removed or modified since then, so you can see what a checkpoint would pull you back
to before you run it.

## How it works

- Files are hashed with SHA-256 and stored once under `.quicksave/objects/` (identical content is
  deduplicated).
- Each `save` writes a manifest in `.quicksave/snapshots/` mapping every path to its hash, size and
  mode.
- Restore just copies the blobs back to their paths.

Caches and vendored deps are skipped by default: `.git`, `node_modules`, `__pycache__`, `venv`,
`.venv`, `dist`, `build` and friends.

## Why not just git?

git is great, but for this job it gets in the way:

- It only protects what you `git add` and commit. Untracked files, `.env`, and build output are on
  their own.
- A `git stash` / `git checkout` is itself a destructive operation an agent can run.
- It mixes "I want to publish this" history with "save me from the last 30 seconds" checkpoints.

quicksave is a separate safety net that snapshots everything in one command and never rewrites your
git history.

## Tests

```
pip install -e .
pip install pytest
pytest
```

## License

MIT. Made by [qorexdevs](https://github.com/qorexdevs).
