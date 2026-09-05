# Lab 2 -- SDN: OVS + your own learning-switch controller
# Do not modify this file.

COMPOSE   ?= docker compose
CONTAINER ?= lab2
MODE      ?= controller

.PHONY: all build up down policy test a1 a2 a3 a4 report hold shell logs clean

all: up test

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build
	@echo "waiting for $(CONTAINER) to be ready ..."
	@sh tests/wait_ready.sh

down:
	-$(COMPOSE) down --remove-orphans

policy:
	@bash .github/policy/00_layout.sh
	@bash .github/policy/01_integrity.sh

# The full set, in the order the autograder runs them.
test: policy
	@sh tests/00_env.sh
	@sh tests/10_a1_flood.sh
	@sh tests/20_a2_normal.sh
	@sh tests/30_a3_controller.sh
	@sh tests/40_a4_proactive.sh
	@sh tests/50_report.sh
	@sh tests/60_git.sh
	@echo ""
	@echo "All Lab 2 checks passed."

# One part at a time while you work.
a1: ; @sh tests/10_a1_flood.sh
a2: ; @sh tests/20_a2_normal.sh
a3: ; @sh tests/30_a3_controller.sh
a4: ; @sh tests/40_a4_proactive.sh
report: ; @sh tests/50_report.sh

# Bring a mode up and stay in the Mininet CLI (used at the checkpoint):
#   make hold MODE=controller
hold:
	docker exec -it $(CONTAINER) python3 harness/run_mode.py $(MODE) --hold

shell:
	docker exec -it $(CONTAINER) bash

logs:
	-$(COMPOSE) ps
	-$(COMPOSE) logs --no-color --tail=200

clean:
	-docker exec $(CONTAINER) sh -c 'pkill -f osken-manager; mn -c' >/dev/null 2>&1 || true
	-$(COMPOSE) down -v --remove-orphans
	-rm -rf results
