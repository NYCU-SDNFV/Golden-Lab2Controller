#!/bin/sh
# Check Part C -- 9-switch ring shortest-path controller. Do not modify.
. "$(dirname "$0")/lib.sh"
banner "check C1: 9-switch ring (sequential MACs)"

require_container

# Clean + start controller
dexec sh -c 'pkill -f sp_controller.py; mn -c' >/dev/null 2>&1
sleep 1
dexec sh -c 'cd /workspace && python3 harness/sp_controller.py > /tmp/sp_ctl.log 2>&1 &'
sleep 2

dexec sh -c 'ss -ltn | grep -q :6653' \
  || die "sp_controller.py is not listening on port 6653" \
         "check /tmp/sp_ctl.log inside the container"
pass "sp_controller.py is listening"

# Run grader with 9-switch ring
dexec python3 /workspace/tests/grade_ring.py --num 9 --topo /workspace/topo/ring_topo.py
RC=$?

if [ "$RC" -ne 0 ]; then
  echo "      --- sp_controller.py log (last 30 lines) ---"
  dexec tail -30 /tmp/sp_ctl.log 2>/dev/null | sed 's/^/      /'
fi

dexec sh -c 'pkill -f sp_controller.py; mn -c' >/dev/null 2>&1
exit $RC
