export DEVICE ?= /dev/ttyACM0

.PHONY: install-%
install-%:
	badge/scripts/install-app.sh $*

.PHONY: uninstall-%
uninstall-%:
	badge/scripts/uninstall-app.sh $*
