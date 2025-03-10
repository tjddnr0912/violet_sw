//-----------------------------------------------------------------------------
// The confidential and proprietary information contained in this file may
// only be used by a person authorised under and to the extent permitted
// by a subsisting licensing agreement from ARM Limited or its affiliates.
//
//            (C) COPYRIGHT 2012-2018 ARM Limited or its affiliates.
//                ALL RIGHTS RESERVED
//
// This entire notice must be reproduced on all copies of this file
// and copies of this file may only be made by a person if such person is
// permitted to do so under the terms of a subsisting license agreement
// from ARM Limited or its affiliates.
//
//            Release Information : ANANKE-MP070-r2p0-00rel0
//
//-----------------------------------------------------------------------------
// SystemVerilog-2012 (IEEE Std 1800-2012)
//-----------------------------------------------------------------------------


`include "ananke_params.sv"

module ananke_cpu  #(
                    parameter NUM_THREADS            = 40
                    parameter ASYNC_BRIDGE           = 10) (
  input  wire                                                                   clk,
  input  wire                                                                   nwarmreset,
  input  wire                                                                   ndbgreset,
  input  wire                                                                   dftcgen,
  input  wire                                                                   dftrstdisable,
  input  wire                                                                   dftramhold,
  input  wire                                                                   dftmcphold,
  input  wire  [NUM_THREADS-1:0]                                                cb_cfgend_i,
  input  wire                                                                   cb_cryptodisable_i,
  input  wire                                                                   cb_vinithi_i,
  input  wire                                                                   cb_cfgte_i,
  input  wire [7-1:0]                                                             cb_clusteridaff2_i,
  input  wire [7:0]                                                             cb_clusteridaff3_i,
  input  wire [3:0]                                                             cb_coreid_i,
  input  wire                                                                   cb_aa64naa32_i,
  input  wire [39:2]                                                            cb_rvbaraddr0_i,
  input  wire                                                                   cb_nfiq_i,
  input  wire                                                                   cb_nirq_i,
  input  wire                                                                   cb_nvfiq_i,
  input  wire                                                                   cb_nvirq_i,
  output wire                                                                   cpu_nvcpumntirq_o,
  output wire                                                                   cpu_elastopclock_o,
  input  wire                                                                   cb_dbgconnected_i,
  input  wire                                                                   cb_giccdisable_i,
  output wire                                                                   cpu_iritready_o,
  input  wire                                                                   cb_iritvalid_i,
  input  wire [15:0]                                                            cb_iritdata_i,
  input  wire                                                                   cb_iritlast_i,
  input  wire                                                                   cb_iritdest_i,
  input  wire                                                                   cb_icctready_i,
  output wire                                                                   cpu_icctvalid_o,
  output wire [15:0]                                                            cpu_icctdata_o,
  output wire                                                                   cpu_icctlast_o,
  output wire                                                                   cpu_icctid_o,
  output wire                                                                   cpu_wfireq_o,
  input  wire  [NUM_THREADS-1:0]                                                cb_wfiack_i,
  output wire                                                                   cpu_wfereq_o,
  input  wire  [NUM_THREADS-1:0]                                                cb_wfeack_i,
  output wire                                                                   cpu_wfxwake_o,
  output wire                                                                   cpu_intfidle_o,
  output wire                                                                   cpu_dbgidle_o,
  input  wire                                                                   cb_dbgconreq_i,
  output wire                                                                   cpu_dbgconack_o,
  input  wire                                                                   cb_hwflushreq_i,
  output wire                                                                   cpu_hwflushack_o,
  input  wire                                                                   cb_discacheinvld_i,
  output wire                                                                   cpu_dbgrstreq_o,
  input  wire  [NUM_THREADS-1:0]                                                cb_eventi_i,
  output wire                                                                   cpu_evento_o,
  input  wire                                                                   cb_neonqreqn_i,
  output wire                                                                   cpu_neonqacceptn_o,
  output wire                                                                   cpu_neonqdeny_o,
  output wire                                                                   cpu_neonqactive_o,
  output wire                                                                   cpu_warmrstreq_o,
  output wire                                                                   cpu_dbgnopwrdwn_o,
  output wire                                                                   cpu_srreq_o,
  input  wire                                                                   cb_srack_i,
  output wire                                                                   cpu_srdest_o,
  output wire [6:0]                                                             cpu_sraddr_o,
  output wire                                                                   cpu_srwrite_o,
  output wire [63:0]                                                            cpu_srwdata_o,
  input  wire [63:0]                                                            cb_srrdata_i,
  output wire                                                                   cpu_nerrirq_o,
  output wire                                                                   cpu_nfaultirq_o,
  input  wire                                                                   cb_broadcastcachemaintpou_i,
  output wire                                                                   cpu_txsactive_o,
  output wire                                                                   cpu_txreqflitpend_o,
  output wire                                                                   cpu_txreqflitv_o,
  input  wire                                                                   cb_txreqlcrdv_i,
  output wire                                                                   cpu_txrspflitpend_o,
  output wire                                                                   cpu_txrspflitv_o,
  input  wire                                                                   cb_txrsplcrdv_i,
  output wire                                                                   cpu_txdatflitpend_o,
  output wire                                                                   cpu_txdatflitv_o,
  input  wire                                                                   cb_txdatlcrdv_i,
  input  wire                                                                   cb_rxsnpflitpend_i,
  input  wire                                                                   cb_rxsnpflitv_i,
  output wire                                                                   cpu_rxsnplcrdv_o,
  input  wire                                                                   cb_rxrspflitpend_i,
  input  wire                                                                   cb_rxrspflitv_i,
  output wire                                                                   cpu_rxrsplcrdv_o,
  input  wire                                                                   cb_rxdatflitpend_i,
  input  wire                                                                   cb_rxdatflitv_i,
  output wire                                                                   cpu_rxdatlcrdv_o,
  output wire                                                                   cpu_ncommirq_o,
  output wire                                                                   cpu_npmuirq_o,
  input  wire                                                                   cb_pseldc_i,
  input  wire [16:2]                                                            cb_paddrdc_i,
  input  wire                                                                   cb_penabledc_i,
  input  wire                                                                   cb_pwritedc_i,
  input  wire [31:0]                                                            cb_pwdatadc_i,
  output wire [31:0]                                                            cpu_prdatadc_o,
  output wire                                                                   cpu_preadydc_o,
  output wire                                                                   cpu_pslverrdc_o,
  output wire                                                                   cpu_pselcd_o,
  output wire [4:2]                                                             cpu_paddrcd_o,
  output wire                                                                   cpu_penablecd_o,
  output wire                                                                   cpu_pwritecd_o,
  output wire [7:0]                                                             cpu_pwdatacd_o,
  input  wire                                                                   cb_preadycd_i,
  input  wire                                                                   cb_pslverrcd_i,
  input  wire [63:0]                                                            cb_tsvalueb_i,
  input  wire                                                                   cb_atready_i,
  input  wire                                                                   cb_afvalid_i,
  output wire [31:0]                                                            cpu_atdata_o,
  output wire                                                                   cpu_atvalid_o,
  output wire [1:0]                                                             cpu_atbytes_o,
  output wire                                                                   cpu_afready_o,
  output wire [6:0]                                                             cpu_atid_o,
  output wire                                                                   cpu_etmenabled_o,
  input  wire                                                                   cb_syncreq_i,
  input  wire                                                                   cb_dbgen_i,
  input  wire                                                                   cb_niden_i,
  input  wire                                                                   cb_spiden_i,
  input  wire                                                                   cb_spniden_i,
  input  wire                                                                   cb_mbistreq_i,
  input  wire                                                                   cb_l3present_i,
  input  wire [2:0]                                                             cb_l3size_i,
  input  wire                                                                   cb_pmusnapshotreq_i,
  output wire [0:0]                                                             cpu_coreinstrret_o,
  output wire [0:0]                                                             cpu_eventstrmdisable_o,
  output wire                                                                   cpu_pmusnapshotack_o

);



endmodule 

