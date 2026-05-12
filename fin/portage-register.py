# ============================================================
#  fin — Selachii Linux Package Manager
#  GPL v3
#  fin/portage_register.py — create VDB stubs for LFS packages
#                             so Portage's dep resolver sees them
#                             as already installed
#
#  Two mechanisms used together:
#
#  1. VDB stubs — /var/db/pkg/<cat>/<pkg>-<ver>/
#     Portage checks these first when resolving deps.
#     Required files per stub:
#       EAPI, SLOT, PF, PN, PV, PVR, CATEGORY,
#       DESCRIPTION, LICENSE, KEYWORDS, IUSE, USE,
#       RDEPEND, DEPEND, BUILD_TIME, COUNTER, CONTENTS
#
#  2. soname-provided profile file
#     Tells Portage to assume certain .so files exist,
#     even without a VDB entry. Designed exactly for LFS.
#     Lives at /etc/portage/profile/soname-provided
# ============================================================

import os
import time
from pathlib import Path

from fin.config import get_config, LFS_PROVIDES
from fin.db.local_db import LocalDB
from fin.db.models import Origin


VDB_ROOT     = Path("/var/db/pkg")
PROFILE_DIR  = Path("/etc/portage/profile")
SONAME_FILE  = PROFILE_DIR / "soname-provided"

# ── Gentoo category map ───────────────────────────────────────
# Maps LFS package name → best-fit Gentoo category
# Used for VDB stub directory naming

CATEGORY_MAP: dict[str, str] = {
    "man-pages":   "sys-apps",
    "iana-etc":    "net-misc",
    "glibc":       "sys-libs",
    "zlib":        "sys-libs",
    "bzip2":       "app-arch",
    "xz":          "app-arch",
    "lz4":         "app-arch",
    "zstd":        "app-arch",
    "file":        "sys-apps",
    "readline":    "sys-libs",
    "m4":          "sys-devel",
    "bc":          "sys-devel",
    "flex":        "sys-devel",
    "tcl":         "dev-lang",
    "expect":      "dev-tcltk",
    "dejagnu":     "dev-util",
    "pkgconf":     "dev-util",
    "binutils":    "sys-devel",
    "gmp":         "dev-libs",
    "mpfr":        "dev-libs",
    "mpc":         "dev-libs",
    "attr":        "sys-apps",
    "acl":         "sys-apps",
    "libcap":      "sys-libs",
    "libxcrypt":   "sys-libs",
    "shadow":      "sys-apps",
    "gcc":         "sys-devel",
    "ncurses":     "sys-libs",
    "sed":         "sys-apps",
    "psmisc":      "sys-apps",
    "gettext":     "sys-devel",
    "bison":       "sys-devel",
    "grep":        "sys-apps",
    "bash":        "app-shells",
    "libtool":     "sys-devel",
    "gdbm":        "sys-libs",
    "gperf":       "dev-util",
    "expat":       "dev-libs",
    "inetutils":   "net-misc",
    "less":        "sys-apps",
    "perl":        "dev-lang",
    "xml-parser":  "dev-perl",
    "intltool":    "dev-util",
    "autoconf":    "sys-devel",
    "automake":    "sys-devel",
    "openssl":     "dev-libs",
    "kmod":        "sys-apps",
    "libelf":      "dev-libs",
    "libffi":      "dev-libs",
    "python":      "dev-lang",
    "flit-core":   "dev-python",
    "wheel":       "dev-python",
    "setuptools":  "dev-python",
    "ninja":       "dev-util",
    "meson":       "dev-util",
    "coreutils":   "sys-apps",
    "check":       "dev-libs",
    "diffutils":   "sys-apps",
    "gawk":        "sys-apps",
    "findutils":   "sys-apps",
    "groff":       "sys-apps",
    "grub":        "sys-boot",
    "gzip":        "app-arch",
    "iproute2":    "sys-apps",
    "kbd":         "sys-apps",
    "libpipeline": "dev-libs",
    "make":        "sys-devel",
    "patch":       "sys-devel",
    "tar":         "app-arch",
    "texinfo":     "sys-apps",
    "vim":         "app-editors",
    "markupsafe":  "dev-python",
    "jinja2":      "dev-python",
    "udev":        "virtual",
    "man-db":      "sys-apps",
    "procps-ng":   "sys-process",
    "util-linux":  "sys-apps",
    "e2fsprogs":   "sys-fs",
    "sysklogd":    "app-admin",
    "sysvinit":    "sys-apps",
}

# ── soname map ────────────────────────────────────────────────
# Maps arch → list of .so files the LFS system provides
# Portage reads this from /etc/portage/profile/soname-provided
# and treats them as pre-satisfied .so dependencies

def _build_soname_map() -> dict[str, list[str]]:
    """
    Scan /usr/lib and /lib for actual .so files present on the system
    and build a soname map for the profile soname-provided file.
    """
    import platform
    machine = platform.machine()

    # map uname machine → Portage multilib category
    arch_map = {
        "x86_64":  "x86_64",
        "aarch64": "arm64",
        "armv7l":  "arm32",
        "i686":    "x86_32",
        "i386":    "x86_32",
        "riscv64": "riscv64",
    }
    arch = arch_map.get(machine, "x86_64")

    sonames = set()
    for lib_dir in ["/usr/lib", "/usr/lib64", "/lib", "/lib64"]:
        p = Path(lib_dir)
        if not p.exists():
            continue
        for f in p.glob("*.so*"):
            if f.is_file() or f.is_symlink():
                # only grab the base soname (libfoo.so.2 NOT libfoo.so.2.1.3)
                name = f.name
                parts = name.split(".so")
                if len(parts) >= 2:
                    suffix = parts[1]
                    # keep only major version: .so.2 not .so.2.1.3
                    sub = suffix.lstrip(".")
                    major = sub.split(".")[0] if sub else ""
                    soname = parts[0] + ".so" + (f".{major}" if major else "")
                    sonames.add(soname)

    return {arch: sorted(sonames)}


# ── VDB stub writer ───────────────────────────────────────────

def _write_stub(pkg_name: str, version: str, category: str, provides: list[str]):
    """Write a minimal VDB stub directory for one package."""
    pv  = version.lstrip("LFS-").lstrip("BLFS-") or "0"
    # sanitize version — Portage is picky, use 0 for our fake ones
    if not pv[0].isdigit():
        pv = "0"
    pvr = pv
    pf  = f"{pkg_name}-{pvr}"

    pkg_dir = VDB_ROOT / category / pf
    pkg_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "EAPI":        "8",
        "SLOT":        "0",
        "PF":          pf,
        "PN":          pkg_name,
        "PV":          pv,
        "PVR":         pvr,
        "CATEGORY":    category,
        "DESCRIPTION": f"LFS base package — managed by Selachii/fin",
        "LICENSE":     "unknown",
        "KEYWORDS":    "amd64 arm64 x86",
        "IUSE":        "",
        "USE":         "",
        "RDEPEND":     "",
        "DEPEND":      "",
        "BDEPEND":     "",
        "PROVIDES":    " ".join(provides),
        "BUILD_TIME":  str(int(time.time())),
        "COUNTER":     "0",
        "CONTENTS":    "",   # empty — we don't track LFS file manifests here
        "repository":  "fin-lfs",
    }

    for fname, content in files.items():
        (pkg_dir / fname).write_text(content + "\n")

    return pkg_dir


# ── soname-provided writer ────────────────────────────────────

def _write_soname_provided(dry_run: bool = False) -> int:
    """
    Write /etc/portage/profile/soname-provided so Portage treats
    all present .so files as pre-satisfied soname deps.
    """
    soname_map = _build_soname_map()
    total = sum(len(v) for v in soname_map.values())

    if not dry_run:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Generated by fin portage-register — DO NOT EDIT MANUALLY\n",
            "# Tells Portage that these sonames are provided by the LFS base system\n",
            "# Re-run `fin portage-register` after updating LFS packages\n\n",
        ]
        for arch, sonames in soname_map.items():
            for so in sonames:
                lines.append(f"{arch} {so}\n")

        SONAME_FILE.write_text("".join(lines))

    return total


# ── Main function ─────────────────────────────────────────────

def portage_register(dry_run: bool = False) -> int:
    """
    Register all LFS-BASE packages into Portage's VDB as stubs,
    and write the soname-provided profile file.

    Returns count of registered packages.
    """
    config   = get_config()
    local_db = LocalDB()

    print()
    print("   ╭──────────────────────────────────────────────────╮")
    print("   │  fin portage-register  —  VDB Stub Creation      │")
    print("   ╰──────────────────────────────────────────────────╯")
    print()

    if not VDB_ROOT.exists():
        print(f"   ⚠  /var/db/pkg does not exist.")
        print(f"   ⚠  Install Portage first, then re-run this command.")
        print()
        return 0

    protected = local_db.list_protected()

    if not protected:
        print("   ⚠  No LFS-BASE packages in fin LocalDB.")
        print("   ⚠  Run `fin adopt lfs` first.")
        print()
        return 0

    # ── Phase 1: VDB stubs ────────────────────────────────────
    print(f"   [1/2] Writing VDB stubs to {VDB_ROOT}...")
    print()

    registered = 0
    skipped    = 0

    for pkg in protected:
        category = CATEGORY_MAP.get(pkg.name, "sys-apps")
        pv       = "0"
        pf       = f"{pkg.name}-{pv}"
        stub_dir = VDB_ROOT / category / pf

        if stub_dir.exists():
            print(f"      ~ {pkg.name:<35} already registered, skipping")
            skipped += 1
            continue

        provides = LFS_PROVIDES.get(pkg.name, [])
        print(f"      + {category}/{pf:<40} provides={provides or '—'}")

        if not dry_run:
            _write_stub(pkg.name, pv, category, provides)

        registered += 1

    # ── Phase 2: soname-provided ──────────────────────────────
    print(f"\n   [2/2] Writing {SONAME_FILE}...")

    soname_count = _write_soname_provided(dry_run=dry_run)
    print(f"         {soname_count} sonames registered")

    # ── Summary ───────────────────────────────────────────────
    print()
    if dry_run:
        print(f"   [dry-run] Would register {registered} VDB stubs ({skipped} already exist).")
        print(f"   [dry-run] Would write {soname_count} sonames to soname-provided.")
    else:
        print(f"   ✓ Done.")
        print(f"   ✓ {registered} VDB stubs written.")
        if skipped:
            print(f"   ~ {skipped} already existed, left untouched.")
        print(f"   ✓ {soname_count} sonames written to soname-provided.")
        print()
        print(f"   Portage now knows your LFS base system exists.")
        print(f"   Run `emerge --sync` then `fin install <pkg>` freely. 🦈")
    print()

    return registered