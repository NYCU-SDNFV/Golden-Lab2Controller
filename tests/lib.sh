# Shared helpers for the Lab 2 checks. Do not modify.
# shellcheck shell=sh

CONTAINER="${CONTAINER:-lab2}"

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1" >&2; }

die() {
  fail "$1"
  [ -n "$2" ] && printf '      hint: %s\n' "$2" >&2
  exit 1
}

banner() {
  printf '\n=== %s ===\n' "$1"
}

# Is the container up?
container_running() {
  [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ]
}

# Run a command inside the container.
dexec() {
  docker exec "$CONTAINER" "$@"
}

require_container() {
  container_running || die \
    "container '$CONTAINER' is not running" \
    "check TODO 1 and TODO 4 in docker-compose.yml, then: make up; make logs"
}
