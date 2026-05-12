# ============================================================
#  fin — Selachii Linux Package Manager
#  GPL v3
#  fin/db/models.py — data models
# ============================================================

from dataclasses import dataclass, field
from enum import Enum


class Origin(str, Enum):
    LFS_BASE  = "lfs-base"   # stamped by `fin adopt lfs` — PROTECTED
    BLFS_AUTO = "blfs-auto"  # discovered by `fin adopt blfs` — tracked
    PORTAGE   = "portage"    # installed by fin via Portage/emerge
    EXPLICIT  = "explicit"   # user manually registered


@dataclass
class Package:
    name:     str
    version:  str
    desc:     str      = ""
    url:      str      = ""
    provides: list[str] = field(default_factory=list)
    origin:   Origin   = Origin.EXPLICIT
    protected: bool    = False

    def __repr__(self):
        lock = " 🔒" if self.protected else ""
        return f"<Package {self.name}-{self.version} [{self.origin.value}]{lock}>"
