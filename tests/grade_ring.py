#!/usr/bin/env python3
"""Part C grader: ring shortest-path verification.

Runs inside the container. Parameterised by --num and --macs so the same
grader works for the 9-switch and 11-switch (random MAC) rings.

    python3 tests/grade_ring.py --num 9
    python3 tests/grade_ring.py --num 11 --topo topo/ring11_topo.py

Checks:
  1. All host pairs can ping (0% loss)
  2. Flows use shortest paths (output port per destination verified)
  3. No unicast leak to uninvolved hosts (no broadcast storm)
"""
import argparse
import importlib.util
import os
import re
import subprocess
import sys
import time
from functools import partial

from mininet.net import Mininet
from mininet.node import OVSSwitch
from mininet.topo import Topo
from mininet.link import TCLink
from mininet.log import setLogLevel

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


def optimal_hops(src, dst, n):
    if src == dst:
        return 0
    return min((dst - src) % n, (src - dst) % n)


def optimal_port(src, dst, n):
    """Return expected output port: 1=host, 2=clockwise, 3=counter-clockwise."""
    if src == dst:
        return 1
    cw = (dst - src) % n
    ccw = (src - dst) % n
    return 2 if cw <= ccw else 3


def load_topo_module(path):
    """Dynamically load a topology module and return its build_net()."""
    spec = importlib.util.spec_from_file_location("topo_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_flows(switch):
    out = switch.cmd("ovs-ofctl -O OpenFlow13 dump-flows %s" % switch.name)
    return [l.strip() for l in out.splitlines() if "actions=" in l]


def parse_dst_flows(flows):
    """Extract {dst_mac: output_port_number} from flow entries."""
    result = {}
    for f in flows:
        m_dst = re.search(r'dl_dst=([0-9a-f:]+)', f)
        m_out = re.search(r'output:"?([^",\s]+)"?', f)
        if not (m_dst and m_out):
            continue
        port_str = m_out.group(1)
        if port_str.isdigit():
            result[m_dst.group(1)] = int(port_str)
        else:
            pm = re.search(r'eth(\d+)$', port_str)
            if pm:
                result[m_dst.group(1)] = int(pm.group(1))
    return result


def run(num_switches, topo_mod):
    setLogLevel("warning")
    subprocess.run(["mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    net = topo_mod.build_net()

    try:
        net.start()
        hosts = {int(h.name[1:]): h for h in net.hosts}
        switches = {int(s.name[1:]): s for s in net.switches}
        N = num_switches

        # Read actual MACs from the running hosts — no dependency on topology module's dict
        host_macs = {}
        for i, h in hosts.items():
            host_macs[i] = h.MAC(h.defaultIntf())
        print("      host MACs (from running network):")
        for i in sorted(host_macs):
            print("        h%d = %s" % (i, host_macs[i]))

        # Wait for controller to discover and install
        wait = max(8, N)
        print("      waiting for controller to converge (%ds)..." % wait)
        time.sleep(wait)

        # Phase 1: initial ping to trigger ARP + host learning
        print("      phase 1: initial ping (all %d pairs)..." % (N * (N - 1) // 2))
        for i in range(1, N + 1):
            for j in range(i + 1, N + 1):
                hosts[i].cmd("ping -c 1 -W 2 10.0.0.%d" % j)
        time.sleep(3)

        # Phase 2: verification ping
        print("      phase 2: verification ping...")
        failures = []
        for i in range(1, N + 1):
            for j in range(i + 1, N + 1):
                out = hosts[i].cmd("ping -c 2 -W 2 -i 0.3 10.0.0.%d" % j)
                if ", 0 received" in out or "100% packet loss" in out:
                    failures.append("h%d->h%d" % (i, j))

        total_pairs = N * (N - 1) // 2
        check(not failures,
              "C: all host pairs can ping (%d/%d)" % (total_pairs - len(failures), total_pairs),
              "failed: %s" % ", ".join(failures[:10]))

        # Phase 3: verify shortest-path flows
        print("      phase 3: verifying shortest-path flows...")
        path_errors = []
        flows_checked = 0

        for sw_id in range(1, N + 1):
            flows = get_flows(switches[sw_id])
            dst_flows = parse_dst_flows(flows)

            for dst_id in range(1, N + 1):
                if dst_id == sw_id:
                    continue
                dst_mac = host_macs[dst_id]
                if dst_mac not in dst_flows:
                    continue

                out_port = dst_flows[dst_mac]
                expected = optimal_port(sw_id, dst_id, N)
                flows_checked += 1

                if out_port != expected:
                    direction = "CW(port2)" if expected == 2 else "CCW(port3)"
                    path_errors.append(
                        "s%d: dst=h%d(%s) → port %d (expected %d=%s, optimal %d hops)"
                        % (sw_id, dst_id, dst_mac, out_port, expected, direction,
                           optimal_hops(sw_id, dst_id, N)))

        check(not path_errors,
              "C: all %d verified flows use shortest paths" % flows_checked,
              "suboptimal:\n      " + "\n      ".join(path_errors[:15]))

        check(flows_checked >= N * (N - 1) // 2,
              "C: enough flows installed (%d checked, expected >= %d)"
              % (flows_checked, N * (N - 1) // 2),
              "not all switches have per-destination flows installed")

        # Phase 4: no broadcast storm / unicast leak
        print("      phase 4: checking for unicast leak...")
        # Pick a host in the middle of the ring to sniff
        sniffer_id = (N // 2) + 1
        src_id = 1
        dst_id = 2
        sniffer = hosts[sniffer_id]
        src = hosts[src_id]

        sniffer.cmd("timeout 4 tcpdump -i h%d-eth0 -c 30 icmp > /tmp/sniff.txt 2>&1 &" % sniffer_id)
        time.sleep(0.5)
        src.cmd("ping -c 3 -i 0.3 10.0.0.%d" % dst_id)
        time.sleep(4)
        sniff = sniffer.cmd("cat /tmp/sniff.txt")
        leaked = sniff.count("10.0.0.%d" % src_id) + sniff.count("10.0.0.%d" % dst_id)
        check(leaked == 0,
              "C: no unicast leak (h%d saw %d h%d<->h%d packets)" % (sniffer_id, leaked, src_id, dst_id),
              "unicast h%d<->h%d should not reach h%d — flooding or broadcast storm?"
              % (src_id, dst_id, sniffer_id))

        # Summary: print a couple of flow tables
        print("      --- flow table samples ---")
        for sw_id in [1, N // 2 + 1]:
            flows = get_flows(switches[sw_id])
            print("      s%d: %d flows" % (sw_id, len(flows)))
            for f in flows[:12]:
                print("        %s" % f)
            if len(flows) > 12:
                print("        ... (%d more)" % (len(flows) - 12))

    finally:
        net.stop()

    print("\n--- %d passed, %d failed ---" % (_pass, _fail))
    return 1 if _fail else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--num", type=int, default=9, help="number of switches in the ring")
    ap.add_argument("--topo", default=None, help="path to topology module (default: auto)")
    args = ap.parse_args()

    # Resolve topology path
    if args.topo:
        topo_path = args.topo
    elif args.num == 11:
        topo_path = os.path.join(os.path.dirname(__file__), "..", "topo", "ring11_topo.py")
    else:
        topo_path = os.path.join(os.path.dirname(__file__), "..", "topo", "ring_topo.py")

    topo_mod = load_topo_module(topo_path)
    sys.exit(run(args.num, topo_mod))


if __name__ == "__main__":
    main()
