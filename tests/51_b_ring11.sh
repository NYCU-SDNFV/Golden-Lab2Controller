#!/bin/sh
# Check Part B -- 11-switch ring with random MACs. Do not modify.
# Tests that the controller does not hardcode switch count or MAC patterns.
. "$(dirname "$0")/lib.sh"
banner "check B2: 11-switch ring (random MACs)"

require_container

# Clean + start controller with --num 11
dexec sh -c 'pkill -f sp_controller.py; mn -c' >/dev/null 2>&1
sleep 1
dexec sh -c 'cd /workspace && python3 harness/sp_controller.py -n 11 > /tmp/sp_ctl11.log 2>&1 &'
sleep 2

dexec sh -c 'ss -ltn | grep -q :6653' \
  || die "sp_controller.py is not listening on port 6653" \
         "check /tmp/sp_ctl11.log inside the container"
pass "sp_controller.py is listening (11-switch mode)"

# Run grader with 11-switch ring and random MACs
dexec python3 /workspace/tests/grade_ring.py --num 11 --topo /workspace/topo/ring11_topo.py
RC=$?

if [ "$RC" -ne 0 ]; then
  echo "      --- sp_controller.py log (last 30 lines) ---"
  dexec tail -30 /tmp/sp_ctl11.log 2>/dev/null | sed 's/^/      /'
fi

dexec sh -c 'pkill -f sp_controller.py; mn -c' >/dev/null 2>&1
exit $RC
