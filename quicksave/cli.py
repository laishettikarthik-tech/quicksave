import argparse
from datetime import datetime

from rich.console import Console
from rich.table import Table

from . import __version__, store

console = Console()


def _root_or_die():
    root = store.find_root()
    if root is None:
        console.print("[red]not a quicksave project[/], run 'quicksave init' first")
        raise SystemExit(1)
    return root


def cmd_init(args):
    root, created = store.init(args.path)
    if created:
        console.print(f"[green]initialized quicksave[/] in {root}")
    else:
        console.print(f"[yellow]already a quicksave project[/]: {root}")


def cmd_save(args):
    root = _root_or_die()
    snap_id, n = store.save(root, message=args.message or "")
    msg = f" [dim]{args.message}[/]" if args.message else ""
    console.print(f"saved [cyan]{snap_id}[/] [dim]({n} files)[/]{msg}")


def cmd_list(args):
    root = _root_or_die()
    snaps = store.list_snapshots(root)
    if not snaps:
        console.print("[dim]no snapshots yet, run 'quicksave save'[/]")
        return
    table = Table(box=None, pad_edge=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("id", style="cyan")
    table.add_column("when")
    table.add_column("files", justify="right")
    table.add_column("message")
    for s in snaps:
        when = datetime.fromtimestamp(s["created_at"]).strftime("%Y-%m-%d %H:%M") if s["created_at"] else "-"
        table.add_row(str(s["seq"]), s["id"], when, str(s["count"]), s["message"] or "[dim]-[/]")
    console.print(table)


def cmd_restore(args):
    root = _root_or_die()
    n, removed, manifest = store.restore(root, args.ref, args.paths, clean=args.clean)
    when = manifest.get("message") or args.ref
    scope = f" [dim]({', '.join(args.paths)})[/]" if args.paths else ""
    extra = f" [red](removed {removed})[/]" if removed else ""
    console.print(f"restored [cyan]{n}[/] files from [cyan]{args.ref}[/] [dim]{when}[/]{scope}{extra}")


def cmd_status(args):
    root = _root_or_die()
    s = store.status(root, args.ref)
    label = f"#{s['seq']} {s['id']}"
    if not (s["added"] or s["removed"] or s["modified"]):
        console.print(f"[green]clean[/] [dim]working tree matches snapshot {label}[/]")
        return
    console.print(f"[dim]changes since snapshot {label}:[/]")
    for path in s["added"]:
        console.print(f"[green]+ {path}[/]")
    for path in s["removed"]:
        console.print(f"[red]- {path}[/]")
    for path in s["modified"]:
        console.print(f"[yellow]~ {path}[/]")


def cmd_diff(args):
    root = _root_or_die()
    d = store.diff(root, args.a, args.b)
    if not any(d.values()):
        console.print(f"[dim]no changes between {args.a} and {args.b}[/]")
        return
    for path in d["added"]:
        console.print(f"[green]+ {path}[/]")
    for path in d["removed"]:
        console.print(f"[red]- {path}[/]")
    for path in d["modified"]:
        console.print(f"[yellow]~ {path}[/]")
    console.print(
        f"[dim]{len(d['added'])} added, {len(d['removed'])} removed, "
        f"{len(d['modified'])} modified[/]"
    )


def cmd_show(args):
    root = _root_or_die()
    data = store.show(root, args.ref, args.path)
    with open(1, "wb", closefd=False) as out:
        out.write(data)


def cmd_gc(args):
    root = _root_or_die()
    r = store.gc(root, keep=args.keep, dry_run=args.dry_run)
    tag = " [dim](dry run)[/]" if r["dry_run"] else ""
    if r["pruned"]:
        for name in r["pruned"]:
            console.print(f"[red]- snapshot {name}[/]")
    if not r["pruned"] and not r["blobs"]:
        console.print(f"[green]nothing to collect[/]{tag}")
        return
    console.print(
        f"removed [cyan]{len(r['pruned'])}[/] snapshots, "
        f"[cyan]{r['blobs']}[/] unreferenced blobs{tag}"
    )


def build_parser():
    p = argparse.ArgumentParser(prog="quicksave", description="F5 for your filesystem")
    p.add_argument("--version", action="version", version=f"quicksave {__version__}")
    sub = p.add_subparsers(dest="cmd")

    pi = sub.add_parser("init", help="start tracking the current directory")
    pi.add_argument("path", nargs="?", default=None)
    pi.set_defaults(func=cmd_init)

    ps = sub.add_parser("save", help="snapshot the working tree")
    ps.add_argument("-m", "--message", default="")
    ps.set_defaults(func=cmd_save)

    pl = sub.add_parser("list", help="list snapshots")
    pl.set_defaults(func=cmd_list)

    pr = sub.add_parser("restore", help="restore files from a snapshot")
    pr.add_argument("ref", help="snapshot id or number from 'quicksave list'")
    pr.add_argument("paths", nargs="*", help="only restore these files or directories")
    pr.add_argument("--clean", action="store_true",
                    help="delete files not in the snapshot (exact rewind)")
    pr.set_defaults(func=cmd_restore)

    pt = sub.add_parser("status", help="show changes since a snapshot (default latest)")
    pt.add_argument("ref", nargs="?", default=None, help="snapshot id or number, defaults to latest")
    pt.set_defaults(func=cmd_status)

    pd = sub.add_parser("diff", help="show what changed between two snapshots")
    pd.add_argument("a", help="snapshot id or number")
    pd.add_argument("b", help="snapshot id or number")
    pd.set_defaults(func=cmd_diff)

    ph = sub.add_parser("show", help="print a file's contents from a snapshot to stdout")
    ph.add_argument("ref", help="snapshot id or number")
    ph.add_argument("path", help="file to print")
    ph.set_defaults(func=cmd_show)

    pg = sub.add_parser("gc", help="drop old snapshots and unreferenced blobs")
    pg.add_argument("--keep", type=int, default=None,
                    help="keep only the N most recent snapshots")
    pg.add_argument("--dry-run", action="store_true",
                    help="show what would be removed without deleting")
    pg.set_defaults(func=cmd_gc)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return
    try:
        args.func(args)
    except store.QuicksaveError as e:
        console.print(f"[red]error:[/] {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
