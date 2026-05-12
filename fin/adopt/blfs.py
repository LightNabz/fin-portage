# ============================================================
#  fin — Selachii Linux Package Manager
#  GPL v3
#  fin/adopt/blfs.py — auto-discover BLFS packages via scored
#                       filesystem scan + Portage VDB matching
#
#  Inspired by Sven (HANS TECH © 2024, GPL v3)
#  Original: scripts/adopt_blfs.py
#  Adapted for Portage/Gentoo repo instead of Arch SyncDB
#
#  Two modes:
#    • VDB mode   — Portage is installed, match against /var/db/pkg
#    • Offline mode — no Portage yet, score against BLFS_KNOWN list
# ============================================================

from pathlib import Path
from dataclasses import dataclass

from fin.db.local_db import LocalDB
from fin.db.portage_db import PortageDB, PortagePkg
from fin.db.models import Package, Origin


# ── Known BLFS packages for offline/no-VDB mode ──────────────
# Common packages people build from BLFS before Portage is around.
# Keyed as (name, expected_binary, expected_lib, expected_pc)
# Any match gets scored — same engine, different source list.

BLFS_KNOWN: list[dict] = [
    # libs
    {"name": "libxml2",    "lib": "libxml2",    "pc": "libxml-2.0"},
    {"name": "libxslt",    "lib": "libxslt",    "pc": "libxslt"},
    {"name": "sqlite",     "lib": "libsqlite3", "pc": "sqlite3"},
    {"name": "curl",       "lib": "libcurl",    "pc": "libcurl",   "bin": "curl"},
    {"name": "libpng",     "lib": "libpng",     "pc": "libpng"},
    {"name": "libjpeg",    "lib": "libjpeg",    "pc": "libjpeg"},
    {"name": "freetype",   "lib": "libfreetype","pc": "freetype2"},
    {"name": "fontconfig", "lib": "libfontconfig","pc":"fontconfig","bin":"fc-list"},
    {"name": "harfbuzz",   "lib": "libharfbuzz","pc": "harfbuzz"},
    {"name": "glib",       "lib": "libglib-2.0","pc": "glib-2.0"},
    {"name": "dbus",       "lib": "libdbus-1",  "pc": "dbus-1",    "bin": "dbus-daemon"},
    {"name": "pcre2",      "lib": "libpcre2-8", "pc": "libpcre2-8"},
    {"name": "libevent",   "lib": "libevent",   "pc": "libevent"},
    {"name": "libuv",      "lib": "libuv",      "pc": "libuv"},
    {"name": "zlib",       "lib": "libz"},
    {"name": "lz4",        "lib": "liblz4",     "pc": "liblz4"},
    {"name": "zstd",       "lib": "libzstd",    "pc": "libzstd"},
    {"name": "xz",         "lib": "liblzma",    "pc": "liblzma"},
    {"name": "bzip2",      "lib": "libbz2"},
    {"name": "libffi",     "lib": "libffi",     "pc": "libffi"},
    {"name": "openssl",    "lib": "libssl",     "pc": "openssl",   "bin": "openssl"},
    {"name": "nss",        "lib": "libnss3",    "pc": "nss"},
    {"name": "gnutls",     "lib": "libgnutls",  "pc": "gnutls"},
    {"name": "cyrus-sasl", "lib": "libsasl2"},
    {"name": "krb5",       "lib": "libkrb5",    "bin": "kinit"},
    # networking
    {"name": "wget",       "bin": "wget"},
    {"name": "openssh",    "bin": "ssh"},
    {"name": "rsync",      "bin": "rsync"},
    {"name": "git",        "bin": "git"},
    {"name": "lynx",       "bin": "lynx"},
    # system tools
    {"name": "sudo",       "bin": "sudo"},
    {"name": "which",      "bin": "which"},
    {"name": "pciutils",   "bin": "lspci"},
    {"name": "usbutils",   "bin": "lsusb"},
    {"name": "lvm2",       "bin": "lvm",        "lib": "libdevmapper"},
    {"name": "mdadm",      "bin": "mdadm"},
    {"name": "dosfstools", "bin": "mkfs.fat"},
    {"name": "ntfs-3g",    "bin": "ntfs-3g"},
    # dev tools
    {"name": "cmake",      "bin": "cmake"},
    {"name": "ninja",      "bin": "ninja"},
    {"name": "meson",      "bin": "meson"},
    {"name": "llvm",       "bin": "llvm-config","lib": "libLLVM"},
    {"name": "rust",       "bin": "rustc"},
    {"name": "go",         "bin": "go"},
    {"name": "nodejs",     "bin": "node"},
    {"name": "python-pip", "bin": "pip3"},
    # X / Wayland
    {"name": "xorg-server","bin": "Xorg"},
    {"name": "wayland",    "lib": "libwayland-client","pc":"wayland-client"},
    {"name": "mesa",       "lib": "libGL",      "pc": "gl"},
    {"name": "libdrm",     "lib": "libdrm",     "pc": "libdrm"},
    {"name": "libinput",   "lib": "libinput",   "pc": "libinput"},
    # audio
    {"name": "alsa-lib",   "lib": "libasound",  "pc": "alsa"},
    {"name": "pulseaudio", "bin": "pulseaudio", "lib": "libpulse"},
    {"name": "pipewire",   "bin": "pipewire",   "lib": "libpipewire-0.3"},
]


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


# ── Offline scorer (no VDB) ───────────────────────────────────

def score_known(
    entry: dict,
    system_libs: set[str],
    system_bins: set[str],
    system_pcs:  set[str],
) -> tuple[int, list[str]]:
    """Score a BLFS_KNOWN entry against the scanned filesystem."""
    score   = 0
    reasons = []

    if bin_ := entry.get("bin"):
        if bin_ in system_bins:
            score += 10
            reasons.append(f"binary:{bin_}")

    if lib := entry.get("lib"):
        for candidate in (lib, f"{lib}.so", f"lib{lib}.so"):
            if candidate in system_libs:
                score += 7
                reasons.append(f"lib:{candidate}")
                break

    if pc := entry.get("pc"):
        if pc in system_pcs:
            score += 6
            reasons.append(f"pkgconfig:{pc}")

    return score, reasons


# ── Main adopt function ───────────────────────────────────────

def adopt_blfs(dry_run: bool = False, threshold: int = SCORE_THRESHOLD) -> int:
    """
    Scan the filesystem, match against Portage VDB (if available) or
    the built-in BLFS_KNOWN list (offline fallback), and register
    detected packages into fin's LocalDB as BLFS-AUTO.

    Returns the count of adopted packages.
    """
    local_db   = LocalDB()
    portage_db = PortageDB()
    vdb_mode   = portage_db.is_available()

    print()
    print("   ╭──────────────────────────────────────────────────╮")
    print("   │  fin adopt blfs  —  Auto-Discovery & Adoption    │")
    print("   ╰──────────────────────────────────────────────────╯")
    print()

    mode_label = "Portage VDB" if vdb_mode else "offline BLFS known-list"
    print(f"   mode: {mode_label}")
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
    already_installed = set(local_db.list_installed())

    # result shape: list of (name, version, score, reasons)
    candidates: list[tuple[str, str, int, list[str]]] = []

    if vdb_mode:
        print("\n   [2/3] Matching against Portage VDB (/var/db/pkg)...")
        portage_pkgs = portage_db.list_installed()

        for pkg in portage_pkgs:
            if pkg.name in already_installed:
                continue
            score, reasons = score_package(
                pkg, system_libs, system_bins, system_pcs, system_includes
            )
            if score >= threshold:
                candidates.append((pkg.name, pkg.version, score, reasons))

    else:
        print("\n   [2/3] Portage VDB not found — using built-in BLFS known-list...")
        print("         (install Portage later and re-run for fuller coverage)\n")

        for entry in BLFS_KNOWN:
            name = entry["name"]
            if name in already_installed:
                continue
            score, reasons = score_known(entry, system_libs, system_bins, system_pcs)
            if score >= threshold:
                candidates.append((name, "BLFS", score, reasons))

    candidates.sort(key=lambda x: x[2], reverse=True)

    if not candidates:
        print("   ✓ No new packages detected. LocalDB looks comprehensive.")
        return 0

    print(f"         {len(candidates)} packages detected\n")

    for name, ver, score, reasons in candidates[:25]:
        reason_str = ", ".join(reasons[:2])
        label = f"{name}-{ver}" if ver != "BLFS" else name
        print(f"      + {label:<45} score={score:>2}  ({reason_str})")

    if len(candidates) > 25:
        print(f"      ... and {len(candidates) - 25} more")

    print()

    # ── Phase 3: Register ─────────────────────────────────────
    print(f"   [3/3] Registering {len(candidates)} packages into LocalDB...")

    adopted = 0
    failed  = 0

    for name, ver, score, reasons in candidates:
        try:
            local_pkg = Package(
                name      = name,
                version   = f"BLFS-{ver}" if ver != "BLFS" else "BLFS",
                desc      = f"Auto-discovered BLFS package",
                url       = "",
                provides  = [],
                origin    = Origin.BLFS_AUTO,
                protected = False,
            )

            if not dry_run:
                local_db.register(local_pkg, files=[])

            adopted += 1

        except Exception as e:
            print(f"      ⚠  Failed to adopt {name}: {e}")
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