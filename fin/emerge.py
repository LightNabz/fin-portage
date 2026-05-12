# ============================================================
#  fin — Selachii Linux Package Manager
#  GPL v3
#  fin/emerge.py — Portage/emerge interception wrapper
#
#  This is the CORE of fin. Every emerge call goes through
#  here so we can guard LFS-BASE packages and track what
#  Portage installs into the LocalDB.
# ============================================================

import subprocess
import sys
from dataclasses import dataclass

from fin.guard import Guard, ProtectionError
from fin.db.local_db import LocalDB
from fin.db.portage_db import PortageDB
from fin.db.models import Package, Origin


@dataclass
class EmergeResult:
    returncode: int
    blocked:    bool = False
    reason:     str  = ""


class EmergeWrapper:
    """
    Wraps emerge with fin's LFS protection + LocalDB tracking.

    Flow:
        1. Parse target atoms
        2. Guard check — block if any atom is LFS-BASE protected
        3. Dep resolve preview (emerge -p) to catch indirect hits
        4. Run emerge if all clear
        5. Sync newly installed packages into LocalDB as PORTAGE origin
    """

    def __init__(self):
        self.guard    = Guard()
        self.local_db = LocalDB()
        self.portage_db = PortageDB()

    # ── Public API ────────────────────────────────────────────

    def install(self, atoms: list[str], extra_args: list[str] = []) -> EmergeResult:
        return self._run("install", atoms, extra_args)

    def uninstall(self, atoms: list[str], extra_args: list[str] = []) -> EmergeResult:
        return self._run("uninstall", atoms, extra_args)

    def update(self, atoms: list[str], extra_args: list[str] = []) -> EmergeResult:
        return self._run("update", atoms, extra_args)

    # ── Internal ──────────────────────────────────────────────

    def _run(self, operation: str, atoms: list[str], extra_args: list[str]) -> EmergeResult:
        # strip category prefix for guard check (e.g. sys-libs/glibc → glibc)
        names = [_atom_to_name(a) for a in atoms]

        # ── Step 1: direct guard check ───────────────────────
        try:
            self.guard.check(names, operation)
        except ProtectionError as e:
            print(e, file=sys.stderr)
            return EmergeResult(returncode=1, blocked=True, reason=str(e))

        # ── Step 2: dep-resolve preview check ────────────────
        print(f"\n   🦈 fin: checking dep graph for protected packages...")
        blocked_deps = self._check_dep_graph(atoms)
        if blocked_deps:
            msg = (
                f"\n   🦈 fin — DEP GRAPH PROTECTION VIOLATION\n"
                f"   ─────────────────────────────────────────────\n"
                f"   The following requested packages would pull in\n"
                f"   LFS-BASE protected packages as dependencies:\n\n"
                + "\n".join(f"   ✗  {d}" for d in blocked_deps)
                + "\n\n"
                f"   Emerging these would let Portage overwrite your\n"
                f"   core LFS system. Operation aborted.\n"
            )
            print(msg, file=sys.stderr)
            return EmergeResult(returncode=1, blocked=True, reason=msg)

        # ── Step 3: run emerge ────────────────────────────────
        emerge_cmd = self._build_cmd(operation, atoms, extra_args)
        print(f"   🦈 fin: running {' '.join(emerge_cmd)}\n")

        result = subprocess.run(emerge_cmd)

        # ── Step 4: sync newly installed packages ─────────────
        if result.returncode == 0 and operation in ("install", "update"):
            self._sync_portage_to_localdb(atoms)

        return EmergeResult(returncode=result.returncode)

    def _check_dep_graph(self, atoms: list[str]) -> list[str]:
        """
        Run `emerge -p` (pretend) and parse output to detect if any
        protected package would be pulled in as a dep.
        """
        try:
            proc = subprocess.run(
                ["emerge", "--pretend", "--quiet"] + atoms,
                capture_output=True, text=True, timeout=60
            )
            output = proc.stdout + proc.stderr
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Portage not installed yet — skip dep check
            return []

        blocked = []
        for line in output.splitlines():
            # emerge pretend output format: [ebuild ...] cat/pkg-ver
            if not line.strip().startswith("["):
                continue
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            atom = parts[-1]
            name = _atom_to_name(atom)
            if self.guard.is_protected(name):
                blocked.append(f"{name}  (from dep resolution of {atom})")

        return blocked

    def _build_cmd(self, operation: str, atoms: list[str], extra_args: list[str]) -> list[str]:
        base = ["emerge"]

        if operation == "uninstall":
            base += ["--depclean"] + extra_args + atoms
        elif operation == "update":
            base += ["--update", "--deep", "--newuse"] + extra_args + atoms
        else:
            base += extra_args + atoms

        return base

    def _sync_portage_to_localdb(self, atoms: list[str]):
        """After a successful emerge, register newly installed packages in LocalDB."""
        names = [_atom_to_name(a) for a in atoms]
        for name in names:
            pkg = self.portage_db.get(name)
            if not pkg:
                continue

            self.local_db.register(
                Package(
                    name      = pkg.name,
                    version   = pkg.version,
                    desc      = f"Installed via fin/Portage ({pkg.atom})",
                    provides  = pkg.provides or [],
                    origin    = Origin.PORTAGE,
                    protected = False,
                )
            )
            print(f"   ✓ registered {pkg.atom} in fin LocalDB")


def _atom_to_name(atom: str) -> str:
    """
    Strips category and version from a Portage atom.
    sys-libs/glibc-2.38 → glibc
    =dev-libs/openssl-3.1 → openssl
    """
    import re
    # strip leading = < > ~
    atom = atom.lstrip("=<>~!")
    # strip category
    if "/" in atom:
        atom = atom.split("/", 1)[1]
    # strip version suffix (anything after last hyphen+digit)
    m = re.match(r"^(.*?)-\d", atom)
    return m.group(1) if m else atom
