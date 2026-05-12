#!/usr/bin/env python3
# ============================================================
#  fin — Selachii Linux Package Manager
#  GPL v3
#  fin/cli.py — main CLI dispatcher
# ============================================================

import sys
import os

from fin.adopt.lfs   import adopt_lfs
from fin.adopt.blfs  import adopt_blfs
from fin.guard       import Guard, ProtectionError
from fin.emerge      import EmergeWrapper
from fin.db.local_db import LocalDB


HELP = """\
🦈 fin — Selachii Linux Package Manager

USAGE:
    fin <command> [options]

COMMANDS:
    adopt lfs               Stamp LFS base packages as protected (run FIRST!)
    adopt blfs              Auto-discover BLFS packages from filesystem
    adopt all               Run both adopt lfs then adopt blfs

    install <pkg...>        Install packages via Portage (guarded)
    remove  <pkg...>        Remove packages via Portage (guarded)
    update  <pkg...>        Update packages via Portage (guarded)
    update  @world          Full system update (guarded)

    list                    List all packages fin knows about
    list protected          List only LFS-BASE protected packages
    list portage            List only Portage-managed packages

    check <pkg...>          Check if package(s) are LFS-BASE protected

    help                    Show this message

OPTIONS:
    --dry-run               Show what would happen without doing it
    --threshold <n>         Score threshold for adopt blfs (default: 5)
    --force-unprotect <p>   Dangerous: bypass protection for package p

EXAMPLES:
    fin adopt all
    fin adopt lfs --dry-run
    fin adopt blfs --threshold 8
    fin install dev-libs/boost
    fin update @world
    fin list protected
    fin check gcc glibc bash
"""


def parse_flag(args: list[str], flag: str, default=None):
    if flag in args:
        i = args.index(flag)
        try:
            return args[i + 1]
        except IndexError:
            die(f"{flag} requires an argument")
    return default


def cmd_adopt(args: list[str]):
    dry_run   = "--dry-run" in args
    threshold = int(parse_flag(args, "--threshold") or 5)

    subcmd = next((a for a in args if not a.startswith("-")), None)
    if not subcmd:
        die("Usage: fin adopt <lfs|blfs|all>")

    if subcmd == "lfs":
        adopt_lfs(dry_run=dry_run)
    elif subcmd == "blfs":
        adopt_blfs(dry_run=dry_run, threshold=threshold)
    elif subcmd == "all":
        adopt_lfs(dry_run=dry_run)
        adopt_blfs(dry_run=dry_run, threshold=threshold)
    else:
        die(f"Unknown adopt subcommand: {subcmd!r}")


def cmd_install(args: list[str]):
    atoms = [a for a in args if not a.startswith("-")]
    extra = [a for a in args if a.startswith("-")]
    if not atoms:
        die("Usage: fin install <pkg> [pkg...]")

    force = parse_flag(args, "--force-unprotect")

    wrapper = EmergeWrapper()
    if force:
        print(f"\n   ⚠  force-unprotect active for: {force}")
        wrapper.guard.db.remove(force)

    result = wrapper.install(atoms, extra_args=extra)
    sys.exit(result.returncode)


def cmd_remove(args: list[str]):
    atoms = [a for a in args if not a.startswith("-")]
    extra = [a for a in args if a.startswith("-")]
    if not atoms:
        die("Usage: fin remove <pkg> [pkg...]")

    wrapper = EmergeWrapper()
    result  = wrapper.uninstall(atoms, extra_args=extra)
    sys.exit(result.returncode)


def cmd_update(args: list[str]):
    atoms = [a for a in args if not a.startswith("-")]
    extra = [a for a in args if a.startswith("-")]
    if not atoms:
        atoms = ["@world"]

    wrapper = EmergeWrapper()
    result  = wrapper.update(atoms, extra_args=extra)
    sys.exit(result.returncode)


def cmd_list(args: list[str]):
    db   = LocalDB()
    sub  = args[0] if args else None

    if sub == "protected":
        pkgs = db.list_protected()
        print(f"\n   🔒 Protected LFS-BASE packages ({len(pkgs)})\n")
        for p in pkgs:
            provs = f"  provides: {', '.join(p.provides)}" if p.provides else ""
            print(f"   {p.name:<35} {p.version}{provs}")

    elif sub == "portage":
        from fin.db.models import Origin
        pkgs = [p for p in db.list_all() if p.origin == Origin.PORTAGE]
        print(f"\n   📦 Portage-managed packages ({len(pkgs)})\n")
        for p in pkgs:
            print(f"   {p.name:<35} {p.version}")

    else:
        pkgs = db.list_all()
        print(f"\n   📦 All packages known to fin ({len(pkgs)})\n")
        for p in pkgs:
            lock   = "🔒" if p.protected else "  "
            origin = f"[{p.origin.value}]"
            print(f"   {lock} {p.name:<35} {p.version:<25} {origin}")

    print()


def cmd_check(args: list[str]):
    pkgs = [a for a in args if not a.startswith("-")]
    if not pkgs:
        die("Usage: fin check <pkg> [pkg...]")

    guard = Guard()
    print()
    for name in pkgs:
        status = "🔒 PROTECTED  [LFS-BASE]" if guard.is_protected(name) else "✓  not protected"
        print(f"   {name:<35} {status}")
    print()


def die(msg: str):
    print(f"\n   ✗ fin: {msg}\n", file=sys.stderr)
    sys.exit(1)


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("help", "--help", "-h"):
        print(HELP)
        return

    cmd  = args[0]
    rest = args[1:]

    try:
        dispatch = {
            "adopt":   cmd_adopt,
            "install": cmd_install,
            "remove":  cmd_remove,
            "update":  cmd_update,
            "list":    cmd_list,
            "check":   cmd_check,
        }

        if cmd not in dispatch:
            die(f"Unknown command: {cmd!r}. Run `fin help` for usage.")

        dispatch[cmd](rest)

    except ProtectionError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n   Interrupted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
