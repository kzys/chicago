export DEVICE ?= /dev/ttyACM0

.PHONY: install-secrets
install-secrets:
	python3 scripts/install_secrets.py $(FILE)

.PHONY: install-%
install-%:
	python3 scripts/install_app.py $*

.PHONY: uninstall-%
uninstall-%:
	python3 scripts/uninstall_app.py $*
