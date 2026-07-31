export DEVICE ?= /dev/ttyACM0

.PHONY: install-secrets
install-secrets:
	python3 scripts/install_secrets.py $(or $(FILE),secrets.py)

.PHONY: set-wifi-password
set-wifi-password:
	python3 scripts/set_wifi_password.py "$(SSID)" $(if $(FILE),-f $(FILE))

.PHONY: install-config-state
install-config-state:
	python3 scripts/install_state_file.py $(or $(FILE),config.json) config.json

.PHONY: provision-wifi
provision-wifi:
	python3 scripts/provision_wifi_json.py -o config.json
	$(MAKE) install-config-state

.PHONY: add-wifi-network
add-wifi-network:
	$(MAKE) set-wifi-password SSID="$(SSID)"
	$(MAKE) install-config-state

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
