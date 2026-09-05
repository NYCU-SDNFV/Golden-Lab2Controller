#!/usr/bin/env python3
"""Lab 2 grader. Lives under .github/ so it is restored from the template on
every submission -- editing it changes nothing on the autograder.

    python3 .github/grade/lab2_grade.py <flood|normal|controller|proactive|report>

Reads results/<mode>.json written by harness/run_mode.py and applies the
checks below. Exit 0 = all checks for that part passed. Every FAIL comes with
a hint; read it before changing code.

Grading is *relational*: we compare numbers with each other (leak in FLOOD
must be larger than in the other modes, the controller's first-packet RTT
must stand out against the proactive table, ...), not against fixed values,
because absolute numbers differ between laptops and the CI runner.
"""
import json
import os
import re
import sys

RESULTS = "results"
MODES = ("flood", "normal", "controller", "proactive")

_pass = 0
_fail = 0


def ok(msg):
    global _pass
    _pass += 1
    print("PASS  " + msg)


def fail(msg, hint=None):
    global _fail
    _fail += 1
    print("FAIL  " + msg)
    if hint:
        print("      hint: " + hint)


def check(cond, msg, hint=None):
    if cond:
        ok(msg)
    else:
        fail(msg, hint)
    return bool(cond)


def load(mode, required=True):
    path = os.path.join(RESULTS, "%s.json" % mode)
    if not os.path.exists(path):
        if required:
            fail("%s is missing" % path,
                 "run `make %s` (or `python3 harness/run_mode.py %s` inside the container); "
                 "if it crashed, the traceback is the real error" % (MODE_TARGET[mode], mode))
        return None
    with open(path) as f:
        return json.load(f)


MODE_TARGET = {"flood": "a1", "normal": "a2", "controller": "a3", "proactive": "a4"}


def has_action(r, token, with_dst=None):
    """Is there a flow whose actions contain `token`? with_dst=True/False
    restricts to flows that do / do not match on dl_dst."""
    for l in r["flows_dump"]:
        acts = l.split("actions=", 1)[1] if "actions=" in l else ""
        if token not in acts:
            continue
        if with_dst is None or (("dl_dst=" in l) == with_dst):
            return True
    return False


# ----------------------------------------------------------------------------
def grade_flood():
    r = load("flood")
    if not r:
        return
    n = r["ping_count"]
    check(r["ping_loss_pct"] == 0, "A1: h1 can ping h2 (loss=%d%%)" % r["ping_loss_pct"],
          "an OpenFlow 1.3 switch with an empty table drops everything -- did flood() install a rule? "
          "check the flow table printed above")
    check(r["leak_to_h3"] >= n, "A1: h3 (the eavesdropper) saw the h1<->h2 traffic (%d ICMP packets)" % r["leak_to_h3"],
          "in hub mode EVERY frame must be copied to every other port; h3 should see both requests and replies")
    check(has_action(r, "FLOOD") or has_action(r, "ALL"),
          "A1: a flow with a flood action is installed (%d flow(s))" % r["openflow_flows"],
          "use actions=FLOOD (or ALL); NORMAL is A2, not A1")
    if r["fdb_entries"] == 0:
        ok("A1: OVS learned nothing (fdb=0) -- flooding is stateless")
    else:
        print("INFO  A1: fdb has %d entries while flooding -- interesting, explain it in the report" % r["fdb_entries"])


def grade_normal():
    r = load("normal")
    if not r:
        return
    check(r["ping_loss_pct"] == 0, "A2: h1 can ping h2 (loss=%d%%)" % r["ping_loss_pct"],
          "did normal() install a rule with actions=NORMAL?")
    check(has_action(r, "NORMAL"), "A2: the NORMAL action is in use",
          "A2 is about OVS's built-in learning switch: one rule, actions=NORMAL")
    check(not r["dst_mapping"], "A2: no explicit dl_dst flows (learning happens inside OVS, not in the OpenFlow table)",
          "you programmed the table by hand -- that is A4 (proactive), not A2")
    check(r["fdb_entries"] >= 2, "A2: OVS learned the talking hosts (fdb=%d)" % r["fdb_entries"],
          "with actions=NORMAL, `ovs-appctl fdb/show s1` must list h1 and h2 after the ping. "
          "If it is empty you are probably still flooding")
    check(r["leak_to_h3"] == 0, "A2: nothing leaked to h3 (%d)" % r["leak_to_h3"],
          "once a MAC is learned, unicast to it must not reach h3")


def grade_controller():
    r = load("controller")
    if not r:
        return
    check(r["controller_connected"], "A3: s1 is connected to your controller",
          "osken-manager did not come up or crashed -- read results/controller.log")
    check(has_action(r, "CONTROLLER", with_dst=False), "A3: a table-miss flow sends unknown packets to the controller",
          "TODO 1: without a table-miss entry the controller never receives a packet-in")
    check(r["ping_loss_pct"] == 0, "A3: h1 can ping h2 (loss=%d%%)" % r["ping_loss_pct"],
          "if the table-miss check above failed, fix that first (nothing reaches you). Otherwise packets reach the controller but are not forwarded: check the out_port decision (TODO 3) and the PacketOut")
    check(r["packet_ins"] >= 1, "A3: the controller received packet-ins (%d)" % r["packet_ins"],
          "n_packets on the CONTROLLER flow is 0 -- nothing was ever sent to you")
    check(len(r["dst_mapping"]) >= 2 and r["dst_mapping_correct"],
          "A3: explicit dl_dst flows were installed with the right ports (%s)" % r["dst_mapping"],
          "TODO 2/4: learn src MAC -> in_port, then install a flow matching eth_dst that outputs to that port")
    check(not has_action(r, "NORMAL"), "A3: the controller does not delegate to NORMAL",
          "installing actions=NORMAL from the controller is A2 with extra steps -- the learning must be yours")
    check(not has_action(r, "FLOOD", with_dst=True), "A3: no flow floods a known destination",
          "never install a flow whose action is FLOOD -- flood the *packet* (PacketOut), not the *flow*")
    check(r["leak_to_h3"] == 0, "A3: nothing leaked to h3 (%d)" % r["leak_to_h3"],
          "after learning, h1<->h2 unicast must go out one port only")
    # relational: reactive first-packet penalty must stand out against the proactive table
    p = load("proactive", required=False)
    ratio, pratio = r["first_rtt_ratio"], (p or {}).get("first_rtt_ratio")
    if ratio is None:
        fail("A3: could not compute the first-packet RTT ratio", "the ping produced fewer than 3 RTT samples")
    elif pratio:
        check(ratio > 2 * pratio,
              "A3: first-packet RTT stands out (%.1fx the steady RTT vs %.1fx in proactive) -- this is the cost of reactive learning" % (ratio, pratio),
              "in a reactive controller the FIRST packet must take the slow path (packet-in). "
              "If the ratio is as small as proactive's, your controller is not on the path")
    else:
        check(ratio > 3, "A3: first-packet RTT stands out (%.1fx the steady RTT)" % ratio,
              "run A4 as well; the grader compares this against the proactive table")


def grade_proactive():
    r = load("proactive")
    if not r:
        return
    check(r["ping_loss_pct"] == 0, "A4: h1 can ping h2 (loss=%d%%)" % r["ping_loss_pct"],
          "100% loss with correct dl_dst flows = the ARP request (broadcast, dst ff:ff:ff:ff:ff:ff) "
          "matches none of them and is dropped. Add a rule for it")
    check(len(r["dst_mapping"]) >= len(r["dst_mapping_truth"]) and r["dst_mapping_correct"],
          "A4: one dl_dst flow per host, all pointing at the right port (%s)" % r["dst_mapping"],
          "install one flow per (mac, port) in `hosts` -- all of them, including h3")
    check(not has_action(r, "CONTROLLER") and r["packet_ins"] == 0, "A4: no controller involved",
          "proactive means the table is complete before the first packet; nothing should go to a controller")
    check(not has_action(r, "NORMAL"), "A4: no NORMAL action (no learning)",
          "proactive = no learning at all; the table is programmed from known topology")
    check(r["leak_to_h3"] == 0 and not r["first_packet_leaked"],
          "A4: nothing leaked to h3, not even the first packet (%d)" % r["leak_to_h3"],
          "with a complete table there is no unknown-unicast flood at all")
    if r["fdb_entries"] == 0:
        ok("A4: fdb is empty -- the switch learned nothing, everything came from the control plane")


# ----------------------------------------------------------------------------
def parse_table_rows(text, labels):
    """Return {label: [cells...]} for markdown table rows whose first cell is a label."""
    rows = {}
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0].lower() in labels:
            rows[cells[0].lower()] = cells[1:]
    return rows


def num(cell):
    m = re.search(r"-?\d+(\.\d+)?", cell or "")
    return float(m.group(0)) if m else None


def grade_report():
    if not check(os.path.exists("REPORT.md"), "report: REPORT.md exists", "keep the file name; the template is REPORT.md"):
        return
    text = open("REPORT.md", encoding="utf-8", errors="replace").read()
    todo = [l for l in text.splitlines() if "TODO" in l and not l.lstrip().startswith(">")]
    check(not todo, "report: no TODO markers left (%d line(s) still have one)" % len(todo),
          "fill in every TODO in REPORT.md")

    # Part A table: rows labelled by mode; columns: flows | fdb | leak | first-RTT ratio | packet-ins
    rows = parse_table_rows(text, set(MODES))
    check(len(rows) == 4, "report: Part A table has all four mode rows (%d found)" % len(rows),
          "keep the four rows labelled flood / normal / controller / proactive")
    for mode in MODES:
        r = load(mode, required=False)
        cells = rows.get(mode)
        if not r or not cells or len(cells) < 3:
            continue
        flows, leak = num(cells[0]), num(cells[2])
        if mode == "flood":
            good = leak is not None and leak >= r["ping_count"] and abs(leak - r["leak_to_h3"]) <= 2
            hint = "the number must come from YOUR run (results/flood.json), not from a classmate or a sample"
        else:
            good = leak is not None and leak == 0 == r["leak_to_h3"]
            hint = "your own measurement shows %d leaked packets" % r["leak_to_h3"]
        check(good, "report: %s row leak matches your measurement (%s vs %d)" % (mode, cells[2], r["leak_to_h3"]), hint)
        check(flows is not None and flows == r["openflow_flows"],
              "report: %s row flow count matches your measurement (%s vs %d)" % (mode, cells[0], r["openflow_flows"]),
              "copy the flow count from results/%s.json" % mode)

    # Part B failure-mode table: 3 scenarios x 3 modes, no empty cells
    frows = parse_table_rows(text, {"mac move", "mac flooding", "controller down"})
    check(len(frows) == 3, "report: Part B failure-mode table has the three scenario rows (%d found)" % len(frows),
          "rows must be labelled 'MAC move', 'MAC flooding', 'controller down'")
    empty = sum(1 for cells in frows.values() for c in cells[:3] if len(c) < 8)
    check(len(frows) == 3 and empty == 0, "report: every failure-mode cell has content",
          "%d cell(s) are empty or too short; each needs a predicted behaviour, not a yes/no" % empty)

    if check(os.path.exists("ai-usage.md"), "report: ai-usage.md exists", "the template ships it; do not delete it"):
        ai = open("ai-usage.md", encoding="utf-8", errors="replace").read()
        check(len(ai.strip()) > 80 and "TODO" not in ai, "report: ai-usage.md is filled in",
              "a few honest sentences: which tools, for what, what you had to fix yourself. 'None' is a valid answer if true")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in MODES + ("report",):
        sys.exit("usage: lab2_grade.py <%s|report>" % "|".join(MODES))
    {"flood": grade_flood, "normal": grade_normal, "controller": grade_controller,
     "proactive": grade_proactive, "report": grade_report}[sys.argv[1]]()
    print("--- %d passed, %d failed ---" % (_pass, _fail))
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
