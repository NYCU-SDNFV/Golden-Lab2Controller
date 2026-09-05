#!/bin/sh
# Check B - the report is filled in and its numbers are your own. Do not modify.
. "$(dirname "$0")/lib.sh"
banner "check B: report cross-checked against your results"
for m in flood normal controller proactive; do
  [ -f "results/$m.json" ] || die "results/$m.json is missing" \
      "the report check needs all four runs; run 'make test' (or make a1..a4) first"
done
python3 .github/grade/lab2_grade.py report
