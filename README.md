# Lab 2 — SDN: Open vSwitch + Your Own Learning-Switch Controller

**SDNFV (CSIC30127), 115-1 — NYCU Institute of Network Engineering**

> **Grading.** This lab is worth 100 autograded points (the take-home part,
> 40 % of the lab grade — AI tools allowed) plus an **in-person checkpoint and
> viva** (60 % of the lab grade — proctored, no personal AI). Every point of the
> take-home part is visible: `make test` runs exactly what the autograder runs.
>
> **You may use AI tools for the take-home part.** Record how in `ai-usage.md`.
> You are still responsible for being able to explain every line you submit —
> the viva runs on *your* controller.

---

## 1. What this lab is about

A learning switch is the simplest piece of network logic there is: remember
which port each source MAC came from, then send frames for that MAC out of that
port only. The interesting question is **where that logic runs**. You will make
the *same* switch forward the *same* traffic in four different ways:

| Mode | Who decides | Where the state lives | You write |
|---|---|---|---|
| **A1 flood** (hub) | nobody | nowhere | one OpenFlow rule |
| **A2 normal** (reactive, in the switch) | OVS's built-in L2 pipeline | the switch FDB | one OpenFlow rule |
| **A3 controller** (reactive, in *your* program) | your Python controller, on every packet-in | controller memory + explicit flows it installs | an OpenFlow 1.3 app |
| **A4 proactive** | you, before the first packet | the OpenFlow table | one rule per host |

Topology (`topo/lab2_topo.py`, given):

```
        ┌───────────────── container "lab2" ─────────────────┐
        │                                                    │
        │   h1 ─── port 1 ┐                                  │
        │   h2 ─── port 2 ┼─ s1  (OVS, userspace datapath,   │
        │   h3 ─── port 3 ┘       OpenFlow 1.3, fail_mode    │
        │                         secure, EMPTY table)       │
        │                                                    │
        │   osken-manager harness/controller.py  (A3 only)   │
        └────────────────────────────────────────────────────┘
```

**h3 is the eavesdropper.** It never sends anything. Every h1↔h2 ICMP packet
that shows up on h3's interface is *leaked* unicast — the single number that
separates a hub from a switch.

The switch starts with **no controller and an empty flow table**. An
OpenFlow 1.3 switch drops everything that matches no flow. Nothing works until
your code says how.

## 2. What you have to change

| File | What to do |
|---|---|
| `harness/modes.py` | Three functions, three `TODO`s: `flood()`, `normal()`, `proactive()`. Each installs OpenFlow rules with `ovs-ofctl` (helper `ofctl()` is given). |
| `harness/controller.py` | An [os-ken](https://os-ken.readthedocs.io/) app with four `TODO`s: table-miss entry, learn, decide, install flow. The packet-out and the skeleton are given. |
| `REPORT.md` | Fill in the tables from your own `results/*.json` and answer the questions. Keep the table row labels — the grader parses them. |
| `ai-usage.md` | Say how you used AI tools (or that you did not). |

Everything else — `Dockerfile`, `docker-compose.yml`, `Makefile`, `topo/`,
`harness/run_mode.py`, `tests/`, `.github/` — is given and **must not be
modified**. The autograder restores `.github/` and checks the integrity of the
rest on every submission; editing a test to make it pass is an academic
integrity violation and gains nothing.

## 3. How to work

```bash
make up          # build + start the container (same as Lab 0)
make a1          # run + grade one part at a time: a1 a2 a3 a4
make report      # cross-check REPORT.md against your results
make test        # everything, in autograder order
make hold MODE=controller   # bring a mode up and stay in the Mininet CLI
make shell       # a shell inside the container
make clean       # tear down, delete results/
```

Each `make aN` runs `harness/run_mode.py <mode>` **inside the container**: it
builds the topology, applies your mode, has h3 sniff, pings h1→h2 six times,
and writes `results/<mode>.json` plus a one-line summary and the flow table.
Then `.github/grade/lab2_grade.py <mode>` reads that JSON and prints
`PASS`/`FAIL` lines **with hints**. Read the hints. They were written for the
exact mistake you are about to make.

> **On Windows, work inside WSL 2** — not Git Bash and not PowerShell (see the
> Lab 0 README for why). Docker Desktop with the WSL 2 backend is fine.

### Running the controller by hand

`run_mode.py controller` starts your app under `osken-manager` for you and
stops it afterwards. When you are debugging it is easier to see its log live:

```bash
make shell
osken-manager --ofp-tcp-listen-port 6653 harness/controller.py     # terminal 1
python3 harness/run_mode.py controller --hold                      # terminal 2
```

`run_mode.py` will reuse a controller that is already listening on 6653.
Inside the Mininet CLI: `h1 ping -c 3 h2`, `sh ovs-ofctl -O OpenFlow13 dump-flows s1`,
`sh ovs-appctl fdb/show s1`, `h3 tcpdump -nn -c 5 icmp`.

### If you are new to any of these

- **OpenFlow 1.3 with `ovs-ofctl`** — `man ovs-ofctl`, section *Flow Syntax*;
  <https://docs.openvswitch.org/en/latest/faq/openflow/>
- **os-ken** (maintained fork of Ryu; Ryu docs apply, replace `ryu` with
  `os_ken`) — <https://os-ken.readthedocs.io/en/latest/>, in particular the
  *Writing Your OS-Ken Application* walkthrough of a switching hub.
- **Why a table-miss entry** — OpenFlow Switch Specification 1.3, §5.4.
- **OVS MAC learning / NORMAL** — <https://docs.openvswitch.org/en/latest/faq/openflow/>
  ("What does the NORMAL action do?") and `ovs-appctl fdb/show`.

## 4. The checks (100 points)

| # | Check | Points | What it really tests |
|---|---|---|---|
| — | policy: repo layout / protected files unchanged | 5 + 5 | Base rules, same as Lab 0 |
| — | environment builds and starts | 15 | `make up` |
| 0 | `tests/00_env.sh` | 0 | container is up, tools and `os_ken` importable, repo mounted |
| A1 | `tests/10_a1_flood.sh` | 10 | ping works **and** h3 sees the traffic; a flood action is installed |
| A2 | `tests/20_a2_normal.sh` | 10 | ping works, `NORMAL` in use, FDB learned h1/h2, **0 leak**, no hand-written `dl_dst` flows |
| A3 | `tests/30_a3_controller.sh` | 25 | switch connected; table-miss → controller; packet-ins > 0; explicit `dl_dst` flows with the right ports; no flow that floods; 0 leak; **first-packet RTT stands out against A4** (the measurable cost of reactive learning) |
| A4 | `tests/40_a4_proactive.sh` | 10 | ping works (yes, ARP!), one flow per host, no controller, no `NORMAL`, 0 leak *including the first packet* |
| B | `tests/50_report.sh` | 10 | `REPORT.md` tables complete, numbers match **your** `results/*.json`, all failure-mode cells filled, `ai-usage.md` filled |
| — | `tests/60_git.sh` | 10 | ≥ 3 commits of your own, `.gitignore` tracked, no litter |

Grading is **relational**: leak in flood must be larger than in the other
modes; your controller's first-packet penalty must stand out against the
proactive table. Absolute numbers differ between laptops and the CI runner and
are never compared to a fixed value.

## 5. Things that will bite you

1. **An empty OpenFlow 1.3 table drops everything.** 100 % loss with no
   error is the symptom. Look at the flow table the test prints.
2. **`actions=FLOOD` makes OVS learn nothing.** After A1, `fdb/show` is empty.
   Learning happens only under `NORMAL`, or in *your* controller. This is a
   real trap: "read the FDB and program flows from it" is not a controller.
3. **ARP.** Before h1 can ping h2 it broadcasts an ARP request to
   `ff:ff:ff:ff:ff:ff`. In A4 no `dl_dst=<host>` rule matches it. Think about
   what the table still needs. In A3 the same packet is your first packet-in.
4. **Never install a flow whose action is FLOOD** for an unknown destination.
   Flood the *packet* (PacketOut), not the *flow* — otherwise the switch keeps
   flooding that destination forever and your controller never learns where it
   is. The grader checks for this.
5. **The packet that caused the packet-in is in the controller, not in the
   switch.** The flow you install applies to the *next* packet; you still have
   to send *this* one with a PacketOut (given in the skeleton — understand it).
6. **Match on `eth_dst` only, and MAC move will leave a stale flow.** The
   skeleton does exactly that on purpose. `REPORT.md` B.3 asks how you would
   fix it; the checkpoint asks you to actually do it.

## 6. The in-person checkpoint and viva (60 % of the lab grade)

You will sit at a course VM with **your** repository at its state at the
deadline, no internet, no AI. Expect to:

- **predict** (on paper) how each mode reacts to a scenario the TA injects —
  a host re-plugged to another port, a new host appearing, a forwarding loop;
- **demonstrate** the actual behaviour with `make hold MODE=...` and
  `ovs-ofctl` / `fdb/show` / `tcpdump`;
- **modify your controller live** so it copes (this is where §5 item 6 and
  `REPORT.md` B.3 pay off);
- **defend your report** — where the state lives in each mode, what
  `fail_mode` changes when the controller dies, and why A3 is SDN while A2 is
  not.

If you did the take-home part yourself and can explain every line of
`harness/controller.py`, nothing at the checkpoint will surprise you. If you
cannot, the take-home part will be re-examined.

## 7. Submission

Push to your Classroom repository; every push is autograded and the result
appears as a Release on your repo. Your last push before the deadline counts.
Upload `REPORT.md` (as PDF) to E3 as well — the repo copy is for the
autograder's cross-check, the E3 copy is what the TA reads and grades.
