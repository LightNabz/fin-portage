# ============================================================
#  fin — Selachii Linux Package Manager
#  GPL v3
#  fin/db/portage_db.py — thin wrapper around Portage's VDB
# ============================================================
#
#  Portage stores installed packages under /var/db/pkg/<cat>/<pkg>-<ver>/
#  We read from there directly so we don't need portage imported at
#  module level — fin works even on systems without Portage yet.
# ============================================================

from pathlib import Path
from dataclasses import dataclass


VDB_ROOT = Path("/var/db/pkg")


@dataclass
class PortagePkg:
    category: str
    name:     str
    version:  str
    slot:     str = "0"
    provides: list[str] = None

    @property
    def atom(self) -> str:
        return f"{self.category}/{self.name}-{self.version}"


class PortageDB:
    """Read-only view into Portage's VDB."""

    def __init__(self, vdb_root: Path = VDB_ROOT):
        self.root = vdb_root

    def is_available(self) -> bool:
        return self.root.exists()

    def list_installed(self) -> list[PortagePkg]:
        if not self.root.exists():
            return []

        pkgs = []
        for cat_dir in self.root.iterdir():
            if not cat_dir.is_dir():
                continue
            for pkg_dir in cat_dir.iterdir():
                if not pkg_dir.is_dir():
                    continue
                pkg = self._read_pkg(cat_dir.name, pkg_dir)
                if pkg:
                    pkgs.append(pkg)
        return pkgs

    def get(self, name: str) -> PortagePkg | None:
        """Find a package by name (without category)."""
        for pkg in self.list_installed():
            if pkg.name == name:
                return pkg
        return None

    def _read_pkg(self, category: str, pkg_dir: Path) -> PortagePkg | None:
        try:
            # dir name format: <pkgname>-<version>
            pf = pkg_dir.name
            # read PF and PVR files if present
            pf_file = pkg_dir / "PF"
            pvr_file = pkg_dir / "PVR"

            name_ver = pf_file.read_text().strip() if pf_file.exists() else pf
            ver      = pvr_file.read_text().strip() if pvr_file.exists() else ""

            # fallback: split on last hyphen+digit
            if not ver:
                parts = pf.rsplit("-", 1)
                name_ver = parts[0]
                ver = parts[1] if len(parts) == 2 else "unknown"
            else:
                name_ver = name_ver  # from PF which is full pf

            # strip version from name
            pkg_name = _strip_version(name_ver) if pf_file.exists() else name_ver

            slot_file = pkg_dir / "SLOT"
            slot = slot_file.read_text().strip() if slot_file.exists() else "0"

            provides_file = pkg_dir / "PROVIDES"
            provides = []
            if provides_file.exists():
                provides = [
                    p.strip() for p in provides_file.read_text().splitlines()
                    if p.strip()
                ]

            return PortagePkg(
                category = category,
                name     = pkg_name,
                version  = ver,
                slot     = slot,
                provides = provides,
            )
        except Exception:
            return None


def _strip_version(pf: str) -> str:
    """Turn 'gcc-13.2.0' → 'gcc'. Handles r revisions too."""
    import re
    # Portage PF format: name-version, version starts with digit
    m = re.match(r"^(.*?)-(\d[\w.]*)(?:-r\d+)?$", pf)
    return m.group(1) if m else pf
