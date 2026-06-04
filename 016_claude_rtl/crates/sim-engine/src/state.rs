//! Engine state: the net value table (+ previous-delta snapshot for edges),
//! VCD wiring, and the single net-write choke point with change detection.

use std::io::Write;

use sim_ir::{BitPacked, Lvalue, NetKind, SelKind, SimIr};
use vcd_writer::{IdCode, VarType, VcdWriter};

use crate::eval::NetReader;
use crate::value::{nwords, Value};

/// A boxed `Write` sink for the VCD. v1 production uses a `File`; tests use an
/// in-memory buffer captured via an `Rc<RefCell<Vec<u8>>>` adapter.
pub(crate) type VcdSink = Box<dyn Write>;

/// One net's runtime storage. The current value occupies `array_len * width`
/// bits laid out word `w` at `[w*width .. w*width+width)`.
pub(crate) struct NetSlot {
    pub cur: BitPacked,
    pub prev: BitPacked,
    pub width: u32,
    pub array_len: u32,
    pub signed: bool,
    pub vcd_id: Option<IdCode>,
}

pub(crate) struct SimState<'a> {
    pub ir: &'a SimIr,
    pub now: u64,
    pub nets: Vec<NetSlot>,
    /// IEEE 1364-2005 self-width side table — built once, immutable for the run.
    pub wt: crate::width::WidthTable,

    // ── VCD ──
    pub vcd: Option<VcdWriter<VcdSink>>,
    pub vcd_path: Option<String>,
    pub dump_pending_path: Option<String>,
    pub vcd_path_override: Option<String>,
    pub dumping: bool,
    pub timescale_unit: String,
    pub vcd_date: String,

    // ── stdout for $display/$write (boxed sink, deterministic) ──
    pub out: Box<dyn Write + 'a>,

    // ── status flags ──
    pub finished: bool,
    pub had_error: bool,
    pub had_fatal: bool,
}

impl<'a> SimState<'a> {
    pub fn new(
        ir: &'a SimIr,
        out: Box<dyn Write + 'a>,
        timescale_unit: String,
        vcd_date: String,
        vcd_path_override: Option<String>,
    ) -> Self {
        let nets = ir
            .nets
            .iter()
            .map(|nv| {
                let alen = nv.array_len.max(1);
                let total = (nv.width as usize) * (alen as usize);
                let init = expand_init(&nv.init, nv.width, alen, total);
                NetSlot {
                    cur: init.clone(),
                    prev: init,
                    width: nv.width,
                    array_len: alen,
                    signed: nv.signed,
                    vcd_id: None,
                }
            })
            .collect();
        let wt = crate::width::WidthTable::build(ir); // single forward pass
        SimState {
            ir,
            now: 0,
            nets,
            wt,
            vcd: None,
            vcd_path: None,
            dump_pending_path: None,
            vcd_path_override,
            dumping: false,
            timescale_unit,
            vcd_date,
            out,
            finished: false,
            had_error: false,
            had_fatal: false,
        }
    }

    // ── reads ────────────────────────────────────────────────────────────

    /// Whole-net value as a `BitPacked` slice for the requested array word.
    fn net_word_packed(&self, net: u32, word: Option<u32>) -> BitPacked {
        let slot = &self.nets[net as usize];
        let w = word.unwrap_or(0).min(slot.array_len.saturating_sub(1));
        slice_word(&slot.cur, slot.width, w)
    }

    // ── writes (single choke point) ──────────────────────────────────────

    /// Write `value` (any width) into the LHS chunks of `lhs`, MSB-first source
    /// consumption (Verilog concat-LHS). Returns true if ANY bit changed.
    pub fn write_lvalue(&mut self, lhs: &Lvalue, value: Value) -> bool {
        // Total destination bit width = sum of chunk widths.
        let total: u32 = lhs.chunks.iter().map(|c| self.chunk_width(c)).sum();
        let src = value.resize(total.max(1));
        let mut changed = false;
        let mut src_hi = total; // next source bit (exclusive top)
        for chunk in &lhs.chunks {
            let cw = self.chunk_width(chunk);
            let take_lo = src_hi.saturating_sub(cw);
            // slice src[take_lo .. src_hi) → low-aligned chunk value
            let mut piece = Value::zeros(cw.max(1), false);
            piece.width = cw;
            for i in 0..cw {
                let (v, u) = src.get_vu(take_lo + i);
                piece.set_vu(i, v, u);
            }
            src_hi = take_lo;
            changed |= self.write_chunk(chunk, &piece);
        }
        changed
    }

    /// Width (in bits) a single lvalue chunk writes.
    fn chunk_width(&self, c: &sim_ir::LvalChunk) -> u32 {
        match c.kind {
            // whole-net write: offset/width None.
            SelKind::Bit => {
                if c.offset.is_none() && c.width.is_none() {
                    self.nets[c.net as usize].width
                } else {
                    1
                }
            }
            SelKind::PartConst | SelKind::PartIdxUp | SelKind::PartIdxDown => {
                // `c.width` is an ExprId (frozen IR: a const-expr edge like
                // `Add(Sub(msb,lsb),1)`), NOT a literal — fold it to its value.
                c.width
                    .and_then(|eid| crate::width::const_u32_of_expr(self.ir, eid))
                    .unwrap_or_else(|| self.nets[c.net as usize].width)
            }
        }
    }

    /// Total destination bit-width of an lvalue (Σ chunk widths). Used to seed
    /// the RHS context width. Does NOT compute a sign — lhs sign never
    /// propagates (IEEE 1364-2005 assignment rule, §5.5).
    pub(crate) fn lvalue_width(&self, lhs: &Lvalue) -> u32 {
        lhs.chunks
            .iter()
            .map(|c| self.chunk_width(c))
            .sum::<u32>()
            .max(1)
    }

    /// Write a low-aligned `piece` into the destination chunk. Returns changed.
    fn write_chunk(&mut self, c: &sim_ir::LvalChunk, piece: &Value) -> bool {
        let net = c.net as usize;
        let word = c
            .word
            .unwrap_or(0)
            .min(self.nets[net].array_len.saturating_sub(1));
        let net_w = self.nets[net].width;
        let base = word * net_w; // bit offset of this array element

        // `c.offset`/`c.width` are ExprIds (const-expr edges), NOT literals.
        // Fold them to values. A non-const offset (dynamic LHS index like
        // `a[i] <= x`) does not fold here — that is a deferred v1 feature
        // (the write path has no runtime EvalCtx); it defaults to offset 0.
        let ir = self.ir;
        let fold = |eid: u32| crate::width::const_u32_of_expr(ir, eid);
        let (off, width) = match c.kind {
            SelKind::Bit => {
                if c.offset.is_none() && c.width.is_none() {
                    (0, net_w) // whole net
                } else {
                    (c.offset.and_then(fold).unwrap_or(0), 1)
                }
            }
            SelKind::PartConst | SelKind::PartIdxUp => (
                c.offset.and_then(fold).unwrap_or(0),
                c.width.and_then(fold).unwrap_or(net_w),
            ),
            SelKind::PartIdxDown => {
                let w = c.width.and_then(fold).unwrap_or(net_w);
                (
                    c.offset
                        .and_then(fold)
                        .unwrap_or(0)
                        .saturating_sub(w.saturating_sub(1)),
                    w,
                )
            }
        };

        let mut changed = false;
        let slot = &mut self.nets[net];
        for i in 0..width {
            let dst = off + i;
            if dst >= net_w {
                continue; // out-of-range bit drop (v1 RunRange simplification)
            }
            let (v, u) = piece.get_vu(i);
            if set_bit(&mut slot.cur, base + dst, v, u) {
                changed = true;
            }
        }
        if changed {
            self.emit_vcd_change(net as u32);
        }
        changed
    }

    /// Emit a VCD value_change for a net that changed (array word 0 in v1 VCD).
    fn emit_vcd_change(&mut self, net: u32) {
        if !self.dumping {
            return;
        }
        let i = net as usize;
        let (id, width) = match self.nets[i].vcd_id {
            Some(id) => (id, self.nets[i].width),
            None => return,
        };
        let packed = slice_word(&self.nets[i].cur, width, 0);
        if let Some(w) = self.vcd.as_mut() {
            let _ = w.set_time(self.now);
            let _ = w.value_change(id, &packed, width);
        }
    }

    // ── edge support ─────────────────────────────────────────────────────

    /// Snapshot cur → prev for every net (called at start of each new time).
    pub fn snapshot_prev(&mut self) {
        for slot in &mut self.nets {
            slot.prev.clone_from(&slot.cur);
        }
    }

    // ── VCD lifecycle (driven by $dumpfile/$dumpvars) ────────────────────

    pub fn open_vcd(&mut self, sink: VcdSink) {
        self.vcd = Some(VcdWriter::new(sink));
    }

    pub fn finalize_vcd(&mut self) {
        if let Some(w) = self.vcd.as_mut() {
            let _ = w.flush();
        }
    }
}

impl<'a> NetReader for SimState<'a> {
    fn read_net(&self, net: u32, word: Option<u32>) -> Value {
        let slot = &self.nets[net as usize];
        let packed = self.net_word_packed(net, word);
        Value::from_packed(&packed, slot.width, slot.signed)
    }
}

// ── free helpers ───────────────────────────────────────────────────────────

/// NetKind → VCD VarType.
pub(crate) fn vcd_var_type(kind: NetKind) -> VarType {
    match kind {
        NetKind::Reg => VarType::Reg,
        NetKind::Integer => VarType::Integer,
        NetKind::Wire | NetKind::Logic => VarType::Wire,
    }
}

/// Build a net's storage from its declared init. For scalars the init IS the
/// value; for arrays the init plane is replicated per word (elaborate emits one
/// init plane; v1 broadcasts it to every element).
fn expand_init(init: &BitPacked, width: u32, array_len: u32, total_bits: usize) -> BitPacked {
    let total_words = nwords(total_bits as u32).max(1);
    if array_len <= 1 {
        let mut val = init.val.clone();
        let mut unk = init.unk.clone();
        val.resize(total_words, 0);
        unk.resize(total_words, 0);
        return BitPacked { val, unk };
    }
    // broadcast the width-wide init to each element
    let mut out = BitPacked {
        val: vec![0; total_words],
        unk: vec![0; total_words],
    };
    let elem = Value::from_packed(init, width, false);
    for w in 0..array_len {
        let base = w * width;
        for i in 0..width {
            let (v, u) = elem.get_vu(i);
            set_bit(&mut out, base + i, v, u);
        }
    }
    out
}

/// Slice `width` bits starting at word `word`*width from a packed store.
fn slice_word(store: &BitPacked, width: u32, word: u32) -> BitPacked {
    let base = word * width;
    let mut tmp = Value::zeros(width.max(1), false);
    tmp.width = width;
    for i in 0..width {
        let (v, u) = bit_of(store, base + i);
        tmp.set_vu(i, v, u);
    }
    tmp.into_bitpacked(width)
}

#[inline]
fn bit_of(b: &BitPacked, i: u32) -> (u64, u64) {
    let w = (i / 64) as usize;
    let s = i % 64;
    let v = b.val.get(w).map_or(0, |x| (x >> s) & 1);
    let u = b.unk.get(w).map_or(0, |x| (x >> s) & 1);
    (v, u)
}

/// Set bit `i` of a packed store to (v,u); grow as needed; return true if changed.
#[inline]
fn set_bit(b: &mut BitPacked, i: u32, v: u64, u: u64) -> bool {
    let w = (i / 64) as usize;
    let s = i % 64;
    while b.val.len() <= w {
        b.val.push(0);
    }
    while b.unk.len() <= w {
        b.unk.push(0);
    }
    let ov = (b.val[w] >> s) & 1;
    let ou = (b.unk[w] >> s) & 1;
    if ov == v && ou == u {
        return false;
    }
    b.val[w] = (b.val[w] & !(1 << s)) | ((v & 1) << s);
    b.unk[w] = (b.unk[w] & !(1 << s)) | ((u & 1) << s);
    true
}

/// Scalar (bit0) 4-state of a net's current value — for edge detection.
pub(crate) fn scalar_bit0(b: &BitPacked) -> sim_ir::FourState {
    let v = b.val.first().copied().unwrap_or(0) & 1;
    let u = b.unk.first().copied().unwrap_or(0) & 1;
    match (v, u) {
        (0, 0) => sim_ir::FourState::Zero,
        (1, 0) => sim_ir::FourState::One,
        (0, 1) => sim_ir::FourState::X,
        _ => sim_ir::FourState::Z,
    }
}
