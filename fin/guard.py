# ============================================================
#  fin — Selachii Linux Package Manager
#  GPL v3
#  fin/guard.py — protection layer, checks before any emerge op
# ============================================================

from fin.db.local_db import LocalDB
from fin.db.models import Package


class ProtectionError(Exception):
    """Raised when an operation would touch a protected LFS package."""
    pass


class Guard:
    """
    Intercepts package operations and blocks anything that would
    modify LFS-BASE protected packages.
    """

    def __init__(self):
        self.db = LocalDB()

    def check(self, packages: list[str], operation: str = "modify") -> None:
        """
        Check if any of the given package names are protected.
        Raises ProtectionError if so.
        """
        violations = []
        for name in packages:
            if self.db.is_protected(name):
                pkg = self.db.get(name)
                violations.append(pkg)

        if violations:
            self._raise(violations, operation)

    def check_one(self, name: str, operation: str = "modify") -> None:
        self.check([name], operation)

    def _raise(self, pkgs: list[Package], operation: str):
        names = ", ".join(p.name for p in pkgs)
        lines = [
            "",
            "   🦈 fin — PROTECTION VIOLATION",
            "   ─────────────────────────────────────────────",
            f"   Operation : {operation}",
            f"   Blocked   : {names}",
            "",
        ]
        for p in pkgs:
            lines.append(f"   {p.name} is an LFS-BASE protected package.")
            lines.append(f"   It was built as part of your Selachii LFS system")
            lines.append(f"   and must NOT be managed by Portage.")
            lines.append("")

        lines += [
            "   To override (dangerous, you will probably break your system):",
            "   Run with --force-unprotect <pkgname>",
            "   Or remove it from /etc/fin/protected.conf first.",
            "",
        ]
        raise ProtectionError("\n".join(lines))

    def is_protected(self, name: str) -> bool:
        return self.db.is_protected(name)

    def list_protected(self) -> list[Package]:
        return self.db.list_protected()
