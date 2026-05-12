# ============================================================
#  fin — Selachii Linux Package Manager
#  Makefile — install / uninstall helpers
# ============================================================

PREFIX     ?= /usr
BINDIR     ?= $(PREFIX)/bin
LIBDIR     ?= $(PREFIX)/lib/fin
ETCDIR     ?= /etc/fin
VARDIR     ?= /var/lib/fin
PYTHON     ?= python3

.PHONY: all install uninstall dev-install check

all:
	@echo "Run 'make install' to install fin to $(PREFIX)"

install:
	@echo ":: Installing fin..."
	install -dm755 $(DESTDIR)$(LIBDIR)
	install -dm755 $(DESTDIR)$(ETCDIR)
	install -dm755 $(DESTDIR)$(VARDIR)

	# copy Python package
	cp -r fin $(DESTDIR)$(LIBDIR)/
	
	# install CLI wrapper
	install -dm755 $(DESTDIR)$(BINDIR)
	install -m755 scripts/fin $(DESTDIR)$(BINDIR)/fin

	# patch sys.path in installed script
	sed -i "s|sys.path.insert.*|sys.path.insert(0, '$(LIBDIR)')|" \
		$(DESTDIR)$(BINDIR)/fin

	# install default config (don't overwrite existing)
	install -m644 -b etc/fin/protected.conf \
		$(DESTDIR)$(ETCDIR)/protected.conf 2>/dev/null || true

	@echo ":: fin installed to $(BINDIR)/fin"
	@echo ":: Run 'fin adopt all' to initialise your Selachii system"

uninstall:
	rm -f  $(DESTDIR)$(BINDIR)/fin
	rm -rf $(DESTDIR)$(LIBDIR)
	@echo ":: fin uninstalled (config and DB kept at $(ETCDIR) and $(VARDIR))"

# dev install — editable, runs from source
dev-install:
	pip install -e . --break-system-packages
	@echo ":: fin installed in editable mode"

check:
	$(PYTHON) -m pytest tests/ -v
