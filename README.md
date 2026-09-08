# Lab 2 — SDN: Open vSwitch + Your Own OpenFlow Controller

**SDNFV (CSIC30127), 115-1 — NYCU Institute of Network Engineering**

> **Grading.** 100 autograded points (the take-home part, 40 % of the lab grade
> — AI tools allowed) plus an **in-person checkpoint and viva** (60 % — proctored,
> no personal AI). Every autograded point is visible: `make test` runs exactly
> what the autograder runs.
>
> **You may use AI tools for the take-home part.** Record how in `ai-usage.md`.
> You are still responsible for being able to explain every line you submit —
> the viva runs on *your* controller, byte by byte.

---

## 1. What this lab is about

OpenFlow is the protocol between an SDN controller and a switch. Frameworks
(Ryu, os-ken, ONOS, …) hide it behind objects; in this lab **you speak it
yourself**: a Python program with nothing but `socket` and `struct` that
accepts the switch's TCP connection, completes the handshake, keeps the
connection alive, decodes the packets the switch sends up, and encodes the
flow entries and packets it sends down. The application on top is the
simplest one there is — a learning switch — so that all of the difficulty is
in the bytes, where it belongs.

To see what your controller changes, the same traffic is forwarded five ways:

| Mode | Who decides | Where the state lives | You write |
|---|---|---|---|
| **A0 reference** | a *given* controller built on a framework | controller memory + flows | nothing — you record what it says on the wire |
| **A1 flood** (hub) | nobody | nowhere | one OpenFlow rule |
| **A2 normal** (learning inside the switch) | OVS's built-in L2 pipeline | the switch FDB | one OpenFlow rule |
| **A3 controller** — *the lab* | **your program, on every packet-in** | controller memory + the flows you install | an OpenFlow 1.3 speaker, from the header up |
| **A4 proactive** | you, before the first packet | the OpenFlow table | one rule per host |

Topology (`topo/lab2_topo.py`, given):

```
        ┌────────────────── container "lab2" ─────────────────────┐
        │                                                         │
        │   h1 ─── port 1 ┐                                       │
        │   h2 ─── port 2 ┼─ s1  (OVS, userspace datapath,        │
        │   h3 ─── port 3 ┘       OpenFlow 1.3, fail_mode secure, │
        │                         EMPTY table)                    │
        │                          │ tcp 127.0.0.1:6653           │
        │                          ▼                              │
        │            harness/controller.py   (A3: yours)          │
        │            reference/refctl.py     (A0: given)          │
        └─────────────────────────────────────────────────────────┘
```

**h3 is the eavesdropper.** It never sends anything. Every h1↔h2 ICMP packet
that shows up on h3 is *leaked* unicast — the number that separates a hub
from a switch. The switch starts with **no controller and an empty table**; an
OpenFlow 1.3 switch drops what matches nothing, so nothing works until your
code says how.

## 2. What you have to change

| File | What to do |
|---|---|
| `harness/modes.py` | Four small functions: `capture_filter()` (A0), `flood()`, `normal()`, `proactive()`. |
| `harness/controller.py` | **The lab.** Ten `TODO`s, `T1`–`T9`: HELLO reply, ECHO reply, FEATURES request/reply, PACKET_IN decoding (fixed fields, OXM match TLVs, Ethernet header), FLOW_MOD and PACKET_OUT encoding, and the learning logic that ties them together. The TCP server loop, message framing, constants and an ERROR decoder are given. |
| `REPORT.md` | Tables from your own `results/*.json`, the wire analysis (A.0), and Part B. Keep the table row labels — the grader parses them. |
| `ai-usage.md` | How you used AI tools (or that you did not). |

Everything else — `Dockerfile`, `docker-compose.yml`, `Makefile`, `topo/`,
`reference/`, `harness/run_mode.py`, `tests/`, `.github/` — is given and
**must not be modified**. `.github/` is restored on every submission and the
rest is integrity-checked; editing a test to make it pass is an academic
integrity violation and gains nothing.

`harness/controller.py` **must use the standard library only.** The grader
checks its imports. os-ken is in the container for the reference controller;
importing it (or Ryu, or Scapy) in your controller fails A3a.

## 3. How to work

```bash
make up                       # build + start the container (as in Lab 0)
make a0                       # run the reference controller, record captures/reference.pcap
make a1  make a2  make a4     # the one-rule modes
make a3                       # run YOUR controller: A3a handshake -> A3b decode -> A3c encode -> A3d behaviour
make report                   # cross-check REPORT.md against your results
make test                     # everything, in autograder order
make hold MODE=controller     # bring a mode up and stay in the Mininet CLI
make shell                    # a shell inside the container
make clean                    # tear down, delete results/ and captures/
```

Each `make aN` runs `harness/run_mode.py <mode>` **inside the container**: it
builds the topology, applies the mode, has h3 sniff, pings h1→h2 six times
and writes `results/<mode>.json`. For the reference and controller modes it
also records the switch↔controller TCP conversation to
`captures/<mode>.pcap`. Then `.github/grade/lab2_grade.py` grades the JSON
**and the capture** and prints `PASS`/`FAIL` lines **with hints**. Read the
hints; they were written for the exact mistake you are about to make.

> **On Windows, work inside WSL 2** — not Git Bash and not PowerShell (see the
> Lab 0 README for why). Docker Desktop with the WSL 2 backend is fine.

### The recommended order

1. `make a0`. Open `captures/reference.pcap` in Wireshark (`Analyze →
   Decode As…` is not needed; port 6653 is recognised as OpenFlow). You now
   have a byte-exact recording of a conversation that works.
2. `make a1`, `a2`, `a4` — quick, and they teach you `ovs-ofctl` flow syntax.
3. `harness/controller.py`, in TODO order. After every one or two TODOs run
   `make a3`; the four sub-checks tell you how far the conversation got. When
   the switch answers with `OFPT_ERROR`, the given `decode_error()` prints
   what it objected to, and `captures/controller.pcap` sits right next to the
   reference capture for a byte-by-byte comparison.
4. `REPORT.md`, then `make test`.

### Running the controller by hand

```bash
make shell
python3 harness/controller.py -v                    # terminal 1: every message in/out is logged
python3 harness/run_mode.py controller --hold       # terminal 2: reuses the running controller
```

Inside the Mininet CLI: `h1 ping -c 3 h2`, `sh ovs-ofctl -O OpenFlow13
dump-flows s1`, `sh ovs-appctl fdb/show s1`, `h3 tcpdump -nn -c 5 icmp`,
`sh tcpdump -i lo -nn port 6653`.

### Reading

- **OpenFlow Switch Specification 1.3.5** (ONF TS-023) — the only document
  you really need. §7.1 header, §7.2.3 OXM match, §7.2.4/§7.2.5 instructions
  and actions, §7.3.1 features, §7.3.4.1 flow-mod, §7.3.7 packet-out,
  §7.4.1 packet-in, §7.4.4 error, §7.5 handshake / echo. The docstrings in
  `controller.py` quote the relevant structs.
- Python `struct` — <https://docs.python.org/3/library/struct.html>
  (`!` = network byte order; `x` = pad byte).
- Wireshark's OpenFlow dissector shows every field name and offset when you
  click a byte in the hex pane. Use it on both captures.
- `ovs-ofctl` flow syntax — `man ovs-ofctl`, *Flow Syntax*, for A1/A2/A4.

## 4. The checks (100 points)

| # | Check | Points | What it really tests |
|---|---|---|---|
| — | policy: repo layout / protected files unchanged | 5 + 5 | Base rules, as in Lab 0 |
| — | environment builds and starts | 10 | `make up` |
| 0 | `tests/00_env.sh` | 0 | container up, tools present, repo mounted |
| A0 | `tests/05_a0_reference.sh` | 5 | `capture_filter()` points tcpdump at the control channel: the capture holds HELLO both ways, PACKET_IN and FLOW_MOD |
| A1 | `tests/10_a1_flood.sh` | 5 | ping works **and** h3 sees the traffic; a flood action is installed |
| A2 | `tests/20_a2_normal.sh` | 5 | `NORMAL` in use, FDB learned h1/h2, 0 leak, no hand-written `dl_dst` flows |
| A3a | `tests/30_a3a_handshake.sh` | 5 | stdlib-only imports; HELLO answered; FEATURES_REQUEST/REPLY with matching `xid`; every ECHO_REQUEST answered with the same `xid` and payload; still connected at the end; no ERROR about handshake messages |
| A3b | `tests/31_a3b_packet_in.sh` | 5 | PACKET_INs arrive and (almost) every one gets a PACKET_OUT; no ERROR about your PACKET_OUTs; ping works |
| A3c | `tests/32_a3c_flow_mod.sh` | 5 | FLOW_MODs sent and none rejected; table-miss flow present; `dl_dst` flows with the right ports |
| A3d | `tests/33_a3d_learning.sh` | 15 | 0 leak; no `NORMAL`; no flow that floods; learned flows installed *after* the first PACKET_IN (reactive, not pre-programmed) |
| A4 | `tests/40_a4_proactive.sh` | 5 | ping works (yes, ARP!), one flow per host, no controller, no `NORMAL`, 0 leak *including the first packet* |
| B | `tests/50_report.sh` | 10 | `REPORT.md` tables complete, numbers match **your** results, all failure-mode cells filled, `ai-usage.md` filled |
| — | `tests/60_git.sh` | 0 | ≥ 3 commits of your own, `.gitignore` tracked, no litter — not scored, but still run |
| C1 | `tests/70_c_ring.sh` | 10 | 9-switch ring: pingall passes, unicast flows follow the shortest path, no leak, no storm |
| C2 | `tests/71_c_ring11.sh` | 10 | 11-switch ring with random host MACs: same checks — nothing hardcoded |

The A3 checks read the **capture**, not your log: what counts is what the
switch actually received and accepted. Absolute latencies are never graded —
they differ between laptops and the CI runner — but they are recorded, and
`REPORT.md` asks about them.

## 5. Things that will bite you

1. **An empty OpenFlow 1.3 table drops everything.** 100 % loss with no error
   is the symptom. Look at the flow table the test prints.
2. **Length fields must be right, everywhere.** The header length covers the
   whole message; `ofp_match.length` covers the OXM TLVs *but not* the padding
   that follows; the instruction length covers the instruction *and* its
   actions; the OUTPUT action is always 16 bytes. OVS answers a wrong length
   with `OFPT_ERROR BAD_LEN` — and then usually drops the connection.
3. **Padding to 8 bytes** after the match is not optional. An empty match is
   4 bytes long and occupies 8.
4. **ECHO.** OVS sends `ECHO_REQUEST` every two seconds in this lab
   (`inactivity_probe=2000`). Ignore one and the switch disconnects; your
   log will say "connection lost" a few seconds into every run.
5. **`actions=FLOOD` makes OVS learn nothing.** After A1, `fdb/show` is empty.
   Learning happens only under `NORMAL`, or in *your* controller.
6. **ARP.** Before h1 can ping h2 it broadcasts an ARP request. In A4 no
   `dl_dst=<host>` rule matches it. In A3 it is your first PACKET_IN.
7. **Never install a flow whose action is FLOOD** for an unknown destination.
   Flood the *packet* (PACKET_OUT), not the *flow*. The grader checks.
8. **The packet that caused the PACKET_IN is in your process, not in the
   switch.** The flow you install applies to the *next* packet; this one needs
   a PACKET_OUT or it is lost.
9. **Match on `eth_dst` only and MAC move will leave a stale flow.** The
   skeleton does exactly that on purpose. `REPORT.md` B.3 asks how you would
   fix it; the checkpoint asks you to do it — which means encoding two more
   OXM fields and a `FLOW_MOD` with `command=DELETE`.
10. **Your first packet is slow. Slower than the reference's.** Same messages,
    very different latency. `REPORT.md` A.2 asks why; the answer is one line
    of code and a classic TCP mechanism.

## 6. The in-person checkpoint and viva (60 % of the lab grade)

You will sit at a course VM with **your** repository at its state at the
deadline, no internet, no AI. Expect to:

- **predict** (on paper) how each mode reacts to a scenario the TA injects —
  a host re-plugged to another port, a new host appearing, a forwarding loop;
- **demonstrate** the actual behaviour with `make hold MODE=...` and
  `ovs-ofctl` / `fdb/show` / `tcpdump`;
- **modify your controller live** so it copes — this touches the match
  encoding and a `FLOW_MOD` you have not sent before;
- **read bytes**: the TA will point at an offset in one of your captured
  messages and ask what it is and what happens if it changes;
- **defend your report** — where the state lives in each mode, what
  `fail_mode` changes when the controller dies, why the first packet costs
  what it costs.

If you wrote `harness/controller.py` yourself and can explain every line,
nothing at the checkpoint will surprise you. If you cannot, the take-home
part will be re-examined.

## 7. Part C — Design Problem: Multi-Switch Shortest-Path Controller (20 points)

Your Part A controller manages **one** switch. Part C is a **design problem**:
nine switches in a ring, and your controller must figure everything out from
scratch. It is worth 20 of the 100 autograded points (C1 and C2, 10 each) and
it is the main preparation for the checkpoint.

### Requirements

1. **The controller knows nothing at boot** — it does not know which switches are connected to each other, where the hosts are, or what the topology looks like.
2. **Unicast packets must take the shortest path** — no detours. s1→s5 must be 4 hops, not 5.
3. **There must be no chance of a broadcast storm** — on a ring topology a naive flood loops forever. Your design must not allow a storm at any stage.
4. **Any host must be able to ping any other host** — including ARP.
5. **Once a path is established, every packet must stay on the data plane** — the controller no longer takes part in forwarding. Each unicast packet follows a flow installed on the switch and never reaches the controller.
6. **The design must scale to hosts being added arbitrarily** — you do not have to implement this, but your report must explain how your design handles a previously unseen host appearing on some switch.

### Topology

```
    9 switches in a ring, 9 hosts (h1..h9)

               h1                 Port layout (all switches):
               |                    port 1 = host
              s1                    port 2 = clockwise neighbour
             /    \                 port 3 = counter-clockwise
      h9---s9      s2---h2
           |        |             Max shortest path = 4 hops (floor(9/2))
      h8---s8      s3---h3
           |        |             s1→s5: clockwise  s1→s2→s3→s4→s5 = 4 hops ✓
      h7---s7      s4---h4        s1→s5: counter-CW s1→s9→s8→s7→s6→s5 = 5 hops ✗
             \    /
              s6--s5
              |   |
              h6  h5
```

### What you change

| File | What to do |
|---|---|
| `harness/sp_controller.py` | Implement `on_switch_ready()` and `on_packet_in()`. The select() loop, handshake, and OpenFlow encoding/decoding helpers are given — they are the same code from Part A3. Everything else (topology discovery, host learning, path computation, flow installation, broadcast handling) is your design. You may also rewrite the whole file from scratch if you prefer — the given structure is a convenience, not a requirement. |

`topo/ring_topo.py` and `topo/ring11_topo.py` are given and **must not be modified**.

### How to work

```bash
# Terminal 1: start your shortest-path controller
make shell
python3 harness/sp_controller.py -v

# Terminal 2: start the 9-switch ring (reuses the running controller)
make shell
python3 topo/ring_topo.py pingall           # 0% dropped = success
python3 topo/ring_topo.py cli               # interactive: try pingall, dump-flows
```

Inside the Mininet CLI: `pingall`, `sh ovs-ofctl -O OpenFlow13 dump-flows s1`,
`h1 traceroute -n 10.0.0.3`.

### The autograder

Your controller is tested on **two** topologies:

| Test | Topology | Switches | Host MACs | What it checks |
|---|---|---|---|---|
| C1 | `ring_topo.py` | 9 | sequential (`00:...:01`–`09`) | pingall, shortest-path flows, no unicast leak |
| C2 | `ring11_topo.py` | 11 | **random (different every run)** | same — your controller must not hardcode switch count or MAC patterns |

Your controller must discover the topology itself — do not assume N=9. You may
assume **N < 20**; the ring is never larger than that.

### What makes this a design problem

There are **no TODO markers** in `sp_controller.py`. You get two empty methods
and six requirements. How you satisfy them is up to you. Some things to think
about:

- How do you discover which switches are connected to each other? (Hint: LLDP.)
- How do you discover where hosts are? (Hint: they send traffic.)
- How do you compute shortest paths on a ring? (Hint: BFS.)
- How do you avoid broadcast storm when flooding on a ring?
- When do you install flows? How do you ensure unicast stays on the data plane?
- The 11-switch test uses random MACs. What does that break if you hardcode?

### Reference: LLDP TLV format

```
Ethernet header (14 bytes):
    dst:  01:80:c2:00:00:0e  (LLDP multicast)
    src:  <6 bytes, e.g. low bytes of dpid>
    type: 0x88cc

Each TLV:
    header: 2 bytes = uint16 where top 7 bits = type, low 9 bits = length
    value:  `length` bytes

TLV type 1 — Chassis ID:
    subtype byte (use 7 = "locally assigned") + dpid as 8 big-endian bytes
    → total value length = 1 + 8 = 9

TLV type 2 — Port ID:
    subtype byte (use 7) + port_no as 4 big-endian bytes
    → total value length = 1 + 4 = 5

TLV type 0 — End of LLDPDU:
    length = 0 → the header is just 0x0000 (2 zero bytes)
```

## 8. Submission

Push to your Classroom repository; every push is autograded and the result
appears as a Release on your repo. Your last push before the deadline counts.
Upload `REPORT.md` (as PDF, including your Wireshark screenshots for A.0) to
E3 as well — the repo copy is for the autograder's cross-check, the E3 copy
is what the TA reads and grades.
