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
quicksave diff 2 3             # see what changed between two snapshots
```

Typical flow with an agent:

```
quicksave save -m "pre-agent"
# let the agent run wild
quicksave list                 # see what you can fall back to
quicksave restore 0            # roll back if it broke something
```

`restore` brings back every file that was in the snapshot, so deleting a directory and restoring
gets it back. It is additive: it won't touch new files you created after the snapshot.

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
