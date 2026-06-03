# fin — Selachii Linux Package Manager

> Portage wrapper with LFS awareness. Named after the shark fin — for Selachii.


## ATTENTION: THIS PROJECT WAS A FAILED PROJECT T_T
---

## What is fin?

`fin` is a thin but smart layer on top of Gentoo's Portage that makes it safe to use on an LFS (Linux From Scratch) system. It:

- **Protects** your LFS base system packages from being overwritten by Portage
- **Tracks** what's installed — LFS base, BLFS, and Portage — in a unified SQLite database
- **Intercepts** emerge operations and blocks anything that would touch protected packages, including indirect dep-graph hits
- **Auto-discovers** already-installed BLFS packages via a scored filesystem scan

---

## Quick Start

```bash
# 1. Install fin
make install

# 2. Stamp your LFS base as protected (do this first!)
fin adopt lfs

# 3. Auto-discover what else you've built from BLFS
fin adopt blfs

# 4. Now use fin as your package manager
fin install dev-libs/boost
fin update @world
fin remove app-misc/foo
```

---

## The adopt system

Inspired by the adopt scripts from the Sven project (HANS TECH, GPL v3).
Adapted for Portage/Gentoo repos instead of Arch's SyncDB.

### `fin adopt lfs`

Stamps all LFS Chapter 8 packages as `LFS-BASE` with `protected = true`.
These packages are **completely invisible to Portage** — fin will refuse any
operation that would let emerge touch them.

### `fin adopt blfs`

Scans the filesystem and scores each package in the Portage VDB:

| Signal                        | Score |
|-------------------------------|-------|
| Binary match in PATH          | +10   |
| Portage PROVIDES `.so` match  | +8    |
| Expected `libname.so` found   | +7    |
| pkgconfig `.pc` match         | +6    |
| `lib`-prefix `.so` found      | +5    |
| Include directory match       | +4    |
| Header file match             | +3    |

Packages scoring ≥ 5 are registered as `BLFS-AUTO` (tracked, not protected).

---

## Protection model

```
LFS-BASE    → protected = true  → fin BLOCKS all operations
BLFS-AUTO   → protected = false → tracked, Portage can manage
PORTAGE     → protected = false → fully Portage-managed
```

To add your own protected packages, edit `/etc/fin/protected.conf`.

---

## Project structure

```
fin/
├── fin/
│   ├── config.py        # LFS package list + provides map
│   ├── cli.py           # CLI dispatcher
│   ├── emerge.py        # Portage interception wrapper
│   ├── guard.py         # Protection enforcement
│   ├── db/
│   │   ├── models.py    # Package dataclass + Origin enum
│   │   ├── local_db.py  # SQLite local registry
│   │   └── portage_db.py# Read-only Portage VDB wrapper
│   └── adopt/
│       ├── lfs.py       # LFS base adoption
│       └── blfs.py      # BLFS auto-discovery
├── scripts/fin          # CLI entrypoint
├── etc/fin/
│   └── protected.conf   # Extra protected packages
└── Makefile
```

---

## License

GPL v3 — same as Portage itself.

adopt scripts inspired by Sven (HANS TECH © 2024, GPL v3).
