export DEVICE ?= /dev/ttyACM0

.PHONY: install-hello-world
install-hello-world:
	badge/scripts/install-app.sh hello_world

.PHONY: uninstall-hello-world
uninstall-hello-world:
	badge/scripts/uninstall-app.sh hello_world
