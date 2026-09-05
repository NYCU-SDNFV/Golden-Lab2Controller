#!/usr/bin/env python3
"""Lab 2 measurement runner. Do not modify.

    python3 harness/run_mode.py <flood|normal|controller|proactive> [--hold]

Builds the 3-host topology (topo/lab2_topo.py), configures s1 in the requested
mode using *your* code (harness/modes.py, harness/controller.py), then runs
one experiment:

    1. h3 starts sniffing ICMP on its interface (it is the eavesdropper).
    2. h1 pings h2 six times.
    3. We record: flow table, FDB, ping loss, per-packet RTT, how many of the
       h1<->h2 ICMP packets h3 saw, the dl_dst->port mapping in the flow table
       and how many packets were sent to the controller.

Everything is written to results/<mode>.json and a one-line summary is
printed. The autograder reads the same JSON with .github/grade/lab2_grade.py,
so what you see locally is what is graded.

--hold keeps the network (and the controller) running and drops you into the
Mininet CLI after the measurement. Use it to poke around, and at the in-person
checkpoint.
"""
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from mininet.log import setLogLevel                           # noqa: E402
from topo.lab2_topo import build_net, HOSTS, SWITCH          # noqa: E402
from harness import modes                                     # noqa: E402

setLogLevel("warning")          # hide Mininet's '*** ...' progress chatter

MODES = ("flood", "normal", "controller", "proactive")
CONTROLLER_PORT = 6653
PING_COUNT = 6
RESULTS_DIR = "results"


def ofctl(s1, cmd, *args):
    return s1.cmd("ovs-ofctl -O OpenFlow13 %s %s %s" % (cmd, SWITCH, " ".join(args)))


def flow_entries(s1):
    """Flow entries as a list of raw lines (header dropped)."""
    out = ofctl(s1, "dump-flows")
    return [l.strip() for l in out.splitlines() if "actions=" in l]


def fdb_entries(s1):
    out = s1.cmd("ovs-appctl fdb/show %s" % SWITCH)
    return [l for l in out.splitlines() if re.search(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", l)]


def parse_flows(lines):
    """Extract dl_dst->port mapping and controller packet count from dump-flows."""
    mapping, packet_ins, catchall = {}, 0, []
    for l in lines:
        m_dst = re.search(r"dl_dst=([0-9a-f:]{17})", l)
        m_out = re.search(r"actions=output:\"?([^\s,\"]+)\"?", l)
        n_pk = re.search(r"n_packets=(\d+)", l)
        if m_dst and m_out:
            port = m_out.group(1)
            m = re.search(r"eth(\d+)$", port)          # userspace dp prints "s1-eth1"
            mapping[m_dst.group(1)] = int(m.group(1)) if m else port
        if "CONTROLLER" in l and n_pk:
            packet_ins += int(n_pk.group(1))
        if ("FLOOD" in l or "ALL" in l or "CONTROLLER" in l or "NORMAL" in l) and not m_dst:
            catchall.append(l)
    return mapping, packet_ins, catchall


def wait_port(port, timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def start_controller(logpath):
    """Start harness/controller.py under osken-manager. Returns the Popen,
    or None if a controller is already listening on the port (we reuse it and
    leave it running -- handy when you run osken-manager by hand to see its log)."""
    if wait_port(CONTROLLER_PORT, timeout=0.5):
        print("reusing the controller already listening on tcp:%d" % CONTROLLER_PORT)
        return None
    subprocess.call("pkill -f osken-manager >/dev/null 2>&1", shell=True)
    here = os.path.dirname(os.path.abspath(__file__))
    app = os.path.join(here, "controller.py")
    log = open(logpath, "w")
    proc = subprocess.Popen(
        ["osken-manager", "--ofp-tcp-listen-port", str(CONTROLLER_PORT), app],
        stdout=log, stderr=subprocess.STDOUT)
    if not wait_port(CONTROLLER_PORT):
        proc.kill()
        sys.exit("controller did not start listening on tcp:%d within 15s -- "
                 "see %s" % (CONTROLLER_PORT, logpath))
    return proc


def wait_connected(s1, timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = s1.cmd("ovs-vsctl --columns=is_connected list controller")
        if re.search(r"is_connected\s*:\s*true", st):
            return True
        time.sleep(0.3)
    return False


def apply_mode(net, mode, ctl_log):
    s1 = net.get(SWITCH)
    hosts = [(net.get(h).MAC(), i) for i, h in enumerate(HOSTS, start=1)]
    ofctl(s1, "del-flows")
    proc = None
    if mode == "flood":
        modes.flood(s1)
    elif mode == "normal":
        modes.normal(s1)
    elif mode == "proactive":
        modes.proactive(s1, hosts)
    elif mode == "controller":
        proc = start_controller(ctl_log)
        s1.cmd("ovs-vsctl set-controller %s tcp:127.0.0.1:%d" % (SWITCH, CONTROLLER_PORT))
        if not wait_connected(s1):
            print("WARN: s1 did not connect to the controller within 15s")
        # give the controller a moment to install its initial flows
        for _ in range(20):
            if flow_entries(s1):
                break
            time.sleep(0.25)
    return proc


def measure(net, mode):
    s1, h1, h2, h3 = net.get(SWITCH, *HOSTS)
    cap = "/tmp/lab2_%s_h3.txt" % mode
    h3.cmd("rm -f %s" % cap)
    h3.cmd("timeout %d tcpdump -i %s-eth0 -nn -l icmp > %s 2>/dev/null &"
           % (PING_COUNT + 6, h3.name, cap))
    time.sleep(1.5)                                 # let tcpdump attach
    out = h1.cmd("ping -c %d -i 0.2 %s" % (PING_COUNT, h2.IP()))
    time.sleep(1.5)                                 # drain
    h3.cmd("pkill -f 'tcpdump -i %s-eth0'" % h3.name)

    m = re.search(r"(\d+)% packet loss", out)
    loss = int(m.group(1)) if m else 100
    rtts = [float(x) for x in re.findall(r"time=([\d.]+)", out)]
    try:
        capture = open(cap).read()
    except OSError:
        capture = ""
    leaked = [l for l in capture.splitlines() if "ICMP echo" in l]
    first_leaked = any(re.search(r"seq 1,", l) and "request" in l for l in leaked)

    flows = flow_entries(s1)
    mapping, packet_ins, catchall = parse_flows(flows)
    truth = {net.get(h).MAC(): i for i, h in enumerate(HOSTS, start=1)}
    checked = {mac: p for mac, p in mapping.items() if mac in truth}
    mapping_correct = bool(checked) and all(truth[mac] == p for mac, p in checked.items())
    connected = bool(re.search(r"is_connected\s*:\s*true",
                               s1.cmd("ovs-vsctl --columns=is_connected list controller")))
    ratio = (rtts[0] / statistics.median(rtts[1:])) if len(rtts) >= 3 and statistics.median(rtts[1:]) > 0 else None

    return {
        "mode": mode,
        "ping_count": PING_COUNT,
        "ping_loss_pct": loss,
        "rtt_ms": rtts,
        "first_rtt_ratio": ratio,
        "leak_to_h3": len(leaked),
        "first_packet_leaked": first_leaked,
        "openflow_flows": len(flows),
        "fdb_entries": len(fdb_entries(s1)),
        "dst_mapping": mapping,
        "dst_mapping_truth": truth,
        "dst_mapping_correct": mapping_correct,
        "packet_ins": packet_ins,
        "catchall_flows": catchall,
        "controller_connected": connected,
        "flows_dump": flows,
        "h3_capture_lines": leaked[:20],
    }


def summary(r):
    return ("RESULT %-10s loss=%d%% leak_to_h3=%d flows=%d fdb=%d packet_ins=%d "
            "mapping_correct=%s first_rtt_ratio=%s"
            % (r["mode"], r["ping_loss_pct"], r["leak_to_h3"], r["openflow_flows"],
               r["fdb_entries"], r["packet_ins"], r["dst_mapping_correct"],
               "%.1f" % r["first_rtt_ratio"] if r["first_rtt_ratio"] else "n/a"))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    hold = "--hold" in sys.argv
    if len(args) != 1 or args[0] not in MODES:
        sys.exit("usage: run_mode.py <%s> [--hold]" % "|".join(MODES))
    mode = args[0]
    os.makedirs(RESULTS_DIR, exist_ok=True)
    subprocess.call("mn -c >/dev/null 2>&1", shell=True)

    net = build_net()
    proc = None
    try:
        try:
            proc = apply_mode(net, mode, os.path.join(RESULTS_DIR, "controller.log"))
        except NotImplementedError as e:
            print("unfinished: %s" % e)
            sys.exit(2)
        r = measure(net, mode)
        with open(os.path.join(RESULTS_DIR, "%s.json" % mode), "w") as f:
            json.dump(r, f, indent=2)
        print(summary(r))
        print("flow table:")
        for l in r["flows_dump"]:
            print("   ", l)
        if hold:
            from mininet.cli import CLI
            print("\n--hold: network is up. 'exit' to tear down.")
            CLI(net)
    finally:
        if proc:
            proc.terminate()
        net.stop()


if __name__ == "__main__":
    main()
