# Все операции со стеком выполняет канонический Makefile в infra/.
.DEFAULT_GOAL := help
.PHONY: help up down reboot reboot-apps ps check smoke-caddy
help up down reboot reboot-apps ps check smoke-caddy:
	$(MAKE) -C infra $@
