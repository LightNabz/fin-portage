# ============================================================
#  fin — Selachii Linux Package Manager
#  GPL v3
#  fin/adopt/lfs.py — stamps LFS base packages as PROTECTED
#
#  Inspired by Sven (HANS TECH © 2024, GPL v3)
#  Original: scripts/adopt_lfs.py
# ============================================================

from fin.config import get_config
from fin.db.local_db import LocalDB
from fin.db.models import Package, Origin


def adopt_lfs(dry_run: bool = False) -> int:
    """
    Stamp all LFS base packages into fin's LocalDB as PROTECTED.
    These will be invisible to Portage and untouchable by `fin install`.

    Returns the count of adopted packages.
    """
    config  = get_config()
    db      = LocalDB()

    protected = config.protected_packages
    provides_map = config.provides_map

    print()
    print("   ╭──────────────────────────────────────────────────╮")
    print("   │  fin adopt lfs  —  Selachii LFS Base Adoption    │")
    print("   ╰──────────────────────────────────────────────────╯")
    print()
    print(f"   :: Stamping {len(protected)} core LFS packages as PROTECTED...")
    print()

    adopted = 0
    skipped = 0

    for pkg_name in protected:
        already = db.get(pkg_name)

        if already and already.protected:
            print(f"      ~ {pkg_name:<35} already protected, skipping")
            skipped += 1
            continue

        provides = provides_map.get(pkg_name, [])

        print(f"      + {pkg_name:<35} [LFS-BASE]  provides={provides or '—'}")

        if not dry_run:
            db.register(
                Package(
                    name      = pkg_name,
                    version   = "LFS-BASE",
                    desc      = "Core LFS system package — managed by original LFS build",
                    url       = "https://www.linuxfromscratch.org",
                    provides  = provides,
                    origin    = Origin.LFS_BASE,
                    protected = True,
                ),
                files     = [],
            )
        adopted += 1

    print()
    if dry_run:
        print(f"   [dry-run] Would adopt {adopted} packages ({skipped} already done).")
    else:
        print(f"   ✓ Adoption complete.")
        print(f"   ✓ {adopted} packages stamped as LFS-BASE.")
        if skipped:
            print(f"   ~ {skipped} packages were already protected.")
    print()

    return adopted
