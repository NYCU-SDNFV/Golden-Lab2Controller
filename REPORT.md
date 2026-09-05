# Lab 2 Report — SDN: OVS + a learning-switch controller

**Student ID:** TODO  **Name:** TODO

> Keep the table layouts exactly as they are (the autograder parses the row
> labels). Replace every TODO. Numbers must come from *your* `results/*.json`;
> the grader cross-checks them. Write in English.

## Part A — the four modes, measured

Fill in from `results/<mode>.json` (`make a1` … `make a4` print the same numbers).

| Mode       | OpenFlow flows | FDB entries | leak to h3 (ICMP pkts) | first-RTT ratio | packet-ins |
|------------|----------------|-------------|------------------------|-----------------|------------|
| flood      | TODO           | TODO        | TODO                   | TODO            | TODO       |
| normal     | TODO           | TODO        | TODO                   | TODO            | TODO       |
| controller | TODO           | TODO        | TODO                   | TODO            | TODO       |
| proactive  | TODO           | TODO        | TODO                   | TODO            | TODO       |

**A.1 Where does the forwarding state live in each mode?** (switch FDB / OpenFlow table / controller memory / nowhere) — one line per mode, and say *who* wrote it there.

TODO

**A.2 The first packet.** Explain the *first-RTT ratio* column: why does the `controller` row differ from `proactive`, and what exactly happens to the first ICMP request in each of the four modes? Use the `packet-ins` column and `results/controller.log`.

TODO

**A.3 Why is A3 "SDN" while A2 (NORMAL) is not?** Both learn MACs and both reach 0 leak. Point at the specific difference in *where the decision is made* and *what you can change*.

TODO

## Part B — design judgement and failure modes

**B.1 Which mode for which network?** For each of: (a) a fixed 3-node lab bench, (b) a campus access network where laptops move, (c) a datacenter pod with a policy requirement ("host X may only talk to Y") — pick a mode and defend it with numbers from your table (flows, leak, first-packet cost, state location). A wrong pick with good reasoning scores better than a right pick with none.

TODO

**B.2 Failure modes.** Predict the behaviour of each mode. You are strongly encouraged to *test* at least one cell with `make hold MODE=<mode>` and describe what you saw — the checkpoint will ask you to do exactly this live.

| Scenario         | flood | normal (NORMAL) | controller (yours) / proactive |
|------------------|-------|-----------------|--------------------------------|
| MAC move         | TODO  | TODO            | TODO                           |
| MAC flooding     | TODO  | TODO            | TODO                           |
| controller down  | TODO  | TODO            | TODO                           |

*MAC move* = a host is re-plugged into another switch port. *MAC flooding* = an attacker sends frames from thousands of random source MACs. *Controller down* = the controller process dies while hosts keep talking (think about `fail_mode` `secure` vs `standalone`).

**B.3 What would you change in your controller** so that MAC move does *not* leave a stale flow behind? Describe the mechanism (you do not have to implement it — yet).

TODO
