"""Lab 2, Part A3 -- your own learning-switch controller (OpenFlow 1.3, os-ken).

This is the SDN version of A2: the *same* MAC-learning algorithm, but the
decision is made here, in a separate program, and pushed into the switch as
explicit flow entries. The switch itself learns nothing.

How it runs: harness/run_mode.py starts this file under `osken-manager`, points
s1 at tcp:127.0.0.1:6653 and waits for a flow to appear. You can also run it by
hand inside the container:

    osken-manager --ofp-tcp-listen-port 6653 harness/controller.py
    python3 harness/run_mode.py controller --hold      # in a second shell

Docs: https://os-ken.readthedocs.io/  (os-ken is the maintained fork of Ryu;
Ryu tutorials apply almost verbatim -- replace `ryu` with `os_ken`.)
"""
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.lib.packet import ethernet, ether_types, packet
from os_ken.ofproto import ofproto_v1_3


class LearningSwitch(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # {datapath_id: {mac: port}} -- the control-plane copy of the FDB.
        self.mac_to_port = {}

    # ------------------------------------------------------------------
    # Switch connected: make sure unknown traffic reaches us.
    # ------------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_switch_features(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        # TODO 1 -- table-miss entry.
        #   An OpenFlow 1.3 switch DROPS anything that matches no flow. Install
        #   a lowest-priority flow that matches everything and sends the packet
        #   to the controller (OFPP_CONTROLLER, OFPCML_NO_BUFFER), otherwise
        #   this controller will never see a single packet.
        self.logger.info("switch dpid=%s connected", dp.id)

    # ------------------------------------------------------------------
    # A packet the switch could not handle.
    # ------------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def on_packet_in(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match["in_port"]
        eth = packet.Packet(msg.data).get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return                                          # ignore LLDP

        table = self.mac_to_port.setdefault(dp.id, {})

        # TODO 2 -- learn.
        #   Remember which port this source MAC was seen on.

        # TODO 3 -- decide.
        #   If we know the destination MAC, send only to its port; otherwise
        #   flood (OFPP_FLOOD). Store the choice in out_port.
        out_port = ofp.OFPP_FLOOD
        actions = [parser.OFPActionOutput(out_port)]

        # TODO 4 -- install a flow so the *next* packet to this destination
        #   never comes to the controller. Only do this when out_port is a
        #   real port (never install a flow that floods -- think about why).
        #   Match on eth_dst; priority above the table-miss; idle_timeout=60.
        #   self.add_flow(...) below is the helper to use.

        # Finally forward *this* packet (it is sitting in the controller, not
        # in the switch -- the flow you just installed does not apply to it).
        out = parser.OFPPacketOut(datapath=dp, buffer_id=ofp.OFP_NO_BUFFER,
                                  in_port=in_port, actions=actions, data=msg.data)
        dp.send_msg(out)
        self.logger.info("packet_in in_port=%s src=%s dst=%s -> out=%s",
                         in_port, eth.src, eth.dst, out_port)

    # ------------------------------------------------------------------
    def add_flow(self, dp, priority, match, actions, idle_timeout=0):
        """Helper: send one OFPFlowMod (ADD) with APPLY_ACTIONS."""
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=priority, match=match,
                                      instructions=inst, idle_timeout=idle_timeout))
