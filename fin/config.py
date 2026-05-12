# ============================================================
#  fin — Selachii Linux Package Manager
#  GPL v3
#  fin/config.py — configuration and protected manifest
# ============================================================

import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────

FIN_ETC         = Path(os.environ.get("FIN_ETC", "/etc/fin"))
FIN_DB          = Path(os.environ.get("FIN_DB",  "/var/lib/fin"))
PROTECTED_CONF  = FIN_ETC / "protected.conf"
LOCAL_DB_PATH   = FIN_DB  / "local.db"

# ── LFS Core Protected Packages ──────────────────────────────
# These are the packages built during LFS chapter 8.
# fin will NEVER let Portage touch these unless explicitly forced.

LFS_BASE_PACKAGES = [
    "man-pages",
    "iana-etc",
    "glibc",
    "zlib",
    "bzip2",
    "xz",
    "lz4",
    "zstd",
    "file",
    "readline",
    "m4",
    "bc",
    "flex",
    "tcl",
    "expect",
    "dejagnu",
    "pkgconf",
    "binutils",
    "gmp",
    "mpfr",
    "mpc",
    "attr",
    "acl",
    "libcap",
    "libxcrypt",
    "shadow",
    "gcc",
    "ncurses",
    "sed",
    "psmisc",
    "gettext",
    "bison",
    "grep",
    "bash",
    "libtool",
    "gdbm",
    "gperf",
    "expat",
    "inetutils",
    "less",
    "perl",
    "xml-parser",
    "intltool",
    "autoconf",
    "automake",
    "openssl",
    "kmod",
    "libelf",
    "libffi",
    "python",
    "flit-core",
    "wheel",
    "setuptools",
    "ninja",
    "meson",
    "coreutils",
    "check",
    "diffutils",
    "gawk",
    "findutils",
    "groff",
    "grub",
    "gzip",
    "iproute2",
    "kbd",
    "libpipeline",
    "make",
    "patch",
    "tar",
    "texinfo",
    "vim",
    "markupsafe",
    "jinja2",
    "udev",
    "man-db",
    "procps-ng",
    "util-linux",
    "e2fsprogs",
    "sysklogd",
    "sysvinit",
]

# ── Provides map ─────────────────────────────────────────────
# Maps LFS package name → virtual provides
# mirrors Sven's approach but keyed for Portage virtual names

LFS_PROVIDES: dict[str, list[str]] = {
    "bash":        ["sh"],
    "pkgconf":     ["pkg-config", "pkgconfig"],
    "gawk":        ["awk"],
    "perl":        ["perl5"],
    "python":      ["python3"],
    "util-linux":  ["libuuid.so", "libblkid.so", "libmount.so", "uuid"],
    "zlib":        ["libz.so"],
    "openssl":     ["libssl.so", "libcrypto.so"],
    "gcc":         ["cc", "c99", "c11", "fortran"],
    "binutils":    ["ld", "as", "ar"],
    "shadow":      ["passwd", "login", "su"],
    "ncurses":     ["libncurses.so", "libtinfo.so", "libcurses.so"],
    "readline":    ["libreadline.so"],
    "gmp":         ["libgmp.so"],
    "mpfr":        ["libmpfr.so"],
    "libffi":      ["libffi.so"],
    "expat":       ["libexpat.so"],
    "libcap":      ["libcap.so"],
    "libxcrypt":   ["libcrypt.so"],
    "e2fsprogs":   ["libext2fs.so", "libcom_err.so"],
    "kmod":        ["libkmod.so", "modprobe", "insmod", "lsmod"],
    "procps-ng":   ["libprocps.so", "ps", "top", "free"],
    "gdbm":        ["libgdbm.so"],
    "libelf":      ["libelf.so"],
    "iproute2":    ["ip", "ss", "tc"],
    "udev":        ["libudev.so"],
}


class Config:
    def __init__(self):
        self._extra_protected: list[str] = []
        self._load_protected_conf()

    def _load_protected_conf(self):
        """Load any extra protected packages from /etc/fin/protected.conf"""
        if PROTECTED_CONF.exists():
            lines = PROTECTED_CONF.read_text().splitlines()
            self._extra_protected = [
                l.strip() for l in lines
                if l.strip() and not l.startswith("#")
            ]

    @property
    def protected_packages(self) -> list[str]:
        return list(dict.fromkeys(LFS_BASE_PACKAGES + self._extra_protected))

    @property
    def provides_map(self) -> dict[str, list[str]]:
        return LFS_PROVIDES


_config: Config | None = None

def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
