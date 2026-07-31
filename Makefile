export DEVICE ?= /dev/ttyACM0

.PHONY: install-secrets
install-secrets:
	python3 scripts/install_secrets.py $(or $(FILE),secrets.py)

.PHONY: install-config-state
install-config-state:
	python3 scripts/install_state_file.py $(FILE) config.json

.PHONY: install-baseten-state
install-baseten-state:
	python3 scripts/install_state_file.py $(FILE) baseten.json

.PHONY: install-%
install-%:
	python3 scripts/install_app.py $*

.PHONY: uninstall-%
uninstall-%:
	python3 scripts/uninstall_app.py $*

.PHONY: install-all
install-all:
	@for app in $$(grep -vE '^#|^$$' badge/apps/order.txt); do \
		$(MAKE) install-$$app; \
	done
