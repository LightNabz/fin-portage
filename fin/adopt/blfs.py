# ============================================================
#  fin — Selachii Linux Package Manager
#  GPL v3
#  fin/adopt/blfs.py — auto-discover BLFS packages via scored
#                       filesystem scan + Portage VDB matching
#
#  Inspired by Sven (HANS TECH © 2024, GPL v3)
#  Original: scripts/adopt_blfs.py
#  Adapted for Portage/Gentoo repo instead of Arch SyncDB
# ============================================================

from pathlib import Path

from fin.db.local_db import LocalDB
from fin.db.portage_db import PortageDB, PortagePkg
from fin.db.models import Package, Origin


# ── Scan targets ─────────────────────────────────────────────

SCAN_LIBS     = ["/usr/lib", "/usr/lib64"]
SCAN_BINS     = ["/usr/bin", "/usr/sbin", "/bin", "/sbin"]
SCAN_PKGCONF  = ["/usr/lib/pkgconfig", "/usr/lib64/pkgconfig", "/usr/share/pkgconfig"]
SCAN_INCLUDE  = ["/usr/include"]

# Minimum score to be considered an adoptable package
SCORE_THRESHOLD = 5


# ── Filesystem scanners ───────────────────────────────────────

def scan_shared_libraries() -> set[str]:
    libs = set()
    for d in SCAN_LIBS:
        p = Path(d)
        if not p.exists():
            continue
        for f in p.rglob("*.so*"):
            if f.is_file() or f.is_symlink():
                libs.add(f.name)
                # also add base name without version suffix
                # e.g. libfoo.so.2.1 → libfoo.so
                stem = f.name.split(".so")[0] + ".so"
                libs.add(stem)
    return libs


def scan_binaries() -> set[str]:
    bins = set()
    for d in SCAN_BINS:
        p = Path(d)
        if not p.exists():
            continue
        for f in p.iterdir():
            if f.is_file() or f.is_symlink():
                bins.add(f.name)
    return bins


def scan_pkgconfig() -> set[str]:
    pcs = set()
    for d in SCAN_PKGCONF:
        p = Path(d)
        if not p.exists():
            continue
        for f in p.glob("*.pc"):
            pcs.add(f.stem)
    return pcs


def scan_include_dirs() -> set[str]:
    dirs = set()
    p = Path("/usr/include")
    if p.exists():
        for d in p.iterdir():
            if d.is_dir():
                dirs.add(d.name.lower())
    return dirs


# ── Scoring engine ────────────────────────────────────────────
# Ported from Sven's match_packages() — same scoring philosophy
# but matched against Portage VDB instead of Arch SyncDB

def score_package(
    pkg: PortagePkg,
    system_libs:     set[str],
    system_bins:     set[str],
    system_pcs:      set[str],
    system_includes: set[str],
) -> tuple[int, list[str]]:
    """
    Score how likely a Portage package is already on the system.
    Returns (score, reasons).
    """
    score   = 0
    reasons = []
    name    = pkg.name
    namel   = name.lower()

    # ── Check 1: exact binary match (+10) ────────────────────
    if name in system_bins:
        score += 10
        reasons.append(f"binary:{name}")

    # ── Check 2: Portage PROVIDES match .so (+8) ─────────────
    for prov in (pkg.provides or []):
        prov_name = prov.split("=")[0].split(">")[0].split("<")[0].strip()
        if prov_name in system_libs:
            score += 8
            reasons.append(f"provides:{prov_name}")

    # ── Check 3: pkgconfig .pc match (+6) ────────────────────
    for pc in system_pcs:
        if pc.lower() == namel or pc.lower().startswith(namel):
            score += 6
            reasons.append(f"pkgconfig:{pc}")
            break

    # ── Check 4: include dir match (+4) ──────────────────────
    if namel in system_includes:
        score += 4
        reasons.append(f"include:{namel}")

    # ── Check 5: direct libname.so convention (+7) ────────────
    expected_so = f"{name}.so"
    if expected_so in system_libs:
        score += 7
        reasons.append(f"lib:{expected_so}")

    # ── Check 6: lib-prefix convention (+5) ──────────────────
    if not name.startswith("lib"):
        alt_so = f"lib{name}.so"
        if alt_so in system_libs:
            score += 5
            reasons.append(f"lib:{alt_so}")

    # ── Check 7: header file match (+3) ──────────────────────
    # e.g. "zlib" → /usr/include/zlib.h
    header = Path(f"/usr/include/{name}.h")
    if header.exists():
        score += 3
        reasons.append(f"header:{name}.h")

    return score, reasons


# ── Main adopt function ───────────────────────────────────────

def adopt_blfs(dry_run: bool = False, threshold: int = SCORE_THRESHOLD) -> int:
    """
    Scan the filesystem, match against Portage VDB, and register
    detected BLFS packages into fin's LocalDB as BLFS-AUTO.

    Returns the count of adopted packages.
    """
    local_db   = LocalDB()
    portage_db = PortageDB()

    print()
    print("   ╭──────────────────────────────────────────────────╮")
    print("   │  fin adopt blfs  —  Auto-Discovery & Adoption    │")
    print("   ╰──────────────────────────────────────────────────╯")
    print()

    # ── Phase 1: Scan ─────────────────────────────────────────
    print("   [1/3] Scanning filesystem...")
    system_libs     = scan_shared_libraries()
    system_bins     = scan_binaries()
    system_pcs      = scan_pkgconfig()
    system_includes = scan_include_dirs()

    print(f"         {len(system_libs):>5} shared libraries")
    print(f"         {len(system_bins):>5} binaries")
    print(f"         {len(system_pcs):>5} pkgconfig files")
    print(f"         {len(system_includes):>5} include directories")

    # ── Phase 2: Match ────────────────────────────────────────
    print("\n   [2/3] Matching against Portage VDB...")

    if not portage_db.is_available():
        print("   ⚠  Portage VDB not found at /var/db/pkg")
        print("   ⚠  Run `fin sync` first to populate the Portage tree,")
        print("      or install Portage before running `fin adopt blfs`.")
        return 0

    already_installed = set(local_db.list_installed())
    portage_pkgs      = portage_db.list_installed()

    candidates: list[tuple[PortagePkg, int, list[str]]] = []

    for pkg in portage_pkgs:
        if pkg.name in already_installed:
            continue

        score, reasons = score_package(
            pkg, system_libs, system_bins, system_pcs, system_includes
        )

        if score >= threshold:
            candidates.append((pkg, score, reasons))

    candidates.sort(key=lambda x: x[1], reverse=True)

    if not candidates:
        print("   ✓ No new packages detected. LocalDB looks comprehensive.")
        return 0

    print(f"         {len(candidates)} packages detected on system\n")

    preview = candidates[:25]
    for pkg, score, reasons in preview:
        reason_str = ", ".join(reasons[:2])
        print(f"      + {pkg.atom:<45} score={score:>2}  ({reason_str})")

    if len(candidates) > 25:
        print(f"      ... and {len(candidates) - 25} more")

    print()

    # ── Phase 3: Register ─────────────────────────────────────
    print(f"   [3/3] Registering {len(candidates)} packages into LocalDB...")

    adopted = 0
    failed  = 0

    for pkg, score, reasons in candidates:
        try:
            local_pkg = Package(
                name      = pkg.name,
                version   = f"BLFS-{pkg.version}",
                desc      = f"Auto-discovered BLFS package (Portage: {pkg.atom})",
                url       = "",
                provides  = pkg.provides or [],
                origin    = Origin.BLFS_AUTO,
                protected = False,  # BLFS packages are tracked but NOT protected
            )

            if not dry_run:
                local_db.register(local_pkg, files=[])

            adopted += 1

        except Exception as e:
            print(f"      ⚠  Failed to adopt {pkg.name}: {e}")
            failed += 1

    print()
    if dry_run:
        print(f"   [dry-run] Would adopt {adopted} BLFS packages.")
    else:
        print(f"   ✓ Adoption complete.")
        print(f"   ✓ {adopted} BLFS packages registered as BLFS-AUTO.")
        if failed:
            print(f"   ✗ {failed} packages failed to register.")
    print()

    return adopted
