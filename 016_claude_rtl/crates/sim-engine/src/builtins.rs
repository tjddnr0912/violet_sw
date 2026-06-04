//! $-task handlers (inlined for v1; HOOK: extract to hdl-builtins post-v1).
//! Handles $dumpfile/$dumpvars/$dumpoff/$dumpon/$dumpall → vcd-writer,
//! $display/$write/$monitor/$strobe formatting → stdout sink, $finish/$stop.

use std::io::Write;

use sim_ir::SysTaskId;
use vcd_writer::{IdCode, ScopeType};

use crate::sched::Scheduler;
use crate::state::{vcd_var_type, SimState};
use crate::value::Value;

/// Control-flow signal back to the executor.
pub(crate) enum Ctl {
    Continue,
    Finish,
    Stop,
    /// Reserved: runtime $fatal (RunFatal). No frozen SysTaskId emits it in v1;
    /// kept so the executor's match is total and future $fatal lowering plugs in.
    #[allow(dead_code)]
    Fatal,
}

pub(crate) fn dispatch(
    sched: &mut Scheduler,
    which: SysTaskId,
    fmt: Option<u32>,
    args: &[u32],
) -> Ctl {
    match which {
        SysTaskId::Display => {
            let mut s = format_args_str(sched, fmt, args);
            s.push('\n');
            write_out(sched.st, &s);
            Ctl::Continue
        }
        SysTaskId::Write => {
            let s = format_args_str(sched, fmt, args);
            write_out(sched.st, &s);
            Ctl::Continue
        }
        // v1: $monitor/$strobe render immediately like $display (Monitor-region
        // scheduling deferred).
        SysTaskId::Monitor | SysTaskId::Strobe => {
            let mut s = format_args_str(sched, fmt, args);
            s.push('\n');
            write_out(sched.st, &s);
            Ctl::Continue
        }
        SysTaskId::Finish => Ctl::Finish,
        SysTaskId::Stop => Ctl::Stop,
        SysTaskId::DumpFile => {
            let name = arg_string(sched, args.first().copied());
            sched.st.dump_pending_path = Some(name);
            Ctl::Continue
        }
        SysTaskId::DumpVars => {
            dumpvars(sched.st);
            Ctl::Continue
        }
        SysTaskId::DumpOff => {
            if let Some(w) = sched.st.vcd.as_mut() {
                let _ = w.set_time(sched.st.now);
                let _ = w.dump_off();
            }
            sched.st.dumping = false;
            Ctl::Continue
        }
        SysTaskId::DumpOn => {
            dump_on(sched.st);
            Ctl::Continue
        }
        SysTaskId::DumpAll => {
            dump_all(sched.st);
            Ctl::Continue
        }
    }
}

fn write_out(st: &mut SimState, text: &str) {
    let _ = st.out.write_all(text.as_bytes());
}

// ── $dumpvars: declare all nets, header, initial dump ──────────────────────

fn dumpvars(st: &mut SimState) {
    let path = st
        .vcd_path_override
        .clone()
        .or_else(|| st.dump_pending_path.clone())
        .unwrap_or_else(|| "dump.vcd".to_string());

    let file = match std::fs::File::create(&path) {
        Ok(f) => f,
        Err(_) => return, // cannot open: silently skip (v1)
    };
    st.open_vcd(Box::new(file));

    let date = st.vcd_date.clone();
    let unit = st.timescale_unit.clone();
    let mut ids: Vec<Option<IdCode>> = vec![None; st.ir.nets.len()];
    {
        let w = st.vcd.as_mut().unwrap();
        let _ = w.write_preamble(&date, &unit);
        let _ = w.push_scope(ScopeType::Module, "top");
        for (i, nv) in st.ir.nets.iter().enumerate() {
            let vt = vcd_var_type(nv.kind);
            let name = format!("n{i}");
            if let Ok(id) = w.declare_var(vt, nv.width.max(1), &name) {
                ids[i] = Some(id);
            }
        }
        let _ = w.pop_scope();
        let _ = w.write_header();
    }
    for (i, id) in ids.iter().enumerate() {
        st.nets[i].vcd_id = *id;
    }

    // initial dump of every net (array word 0 in v1).
    let snap: Vec<(IdCode, sim_ir::BitPacked, u32)> = st
        .nets
        .iter()
        .filter_map(|slot| {
            slot.vcd_id.map(|id| {
                let w = slot.width;
                (id, word0(&slot.cur, w), w)
            })
        })
        .collect();
    {
        let w = st.vcd.as_mut().unwrap();
        let _ = w.dump_initial(snap.iter().map(|(id, b, wd)| (*id, b, *wd)));
        let _ = w.set_time(st.now);
    }
    st.dumping = true;
    st.vcd_path = Some(path);
}

fn dump_on(st: &mut SimState) {
    st.dumping = true;
    let snap = full_snapshot(st);
    let now = st.now;
    if let Some(w) = st.vcd.as_mut() {
        let _ = w.set_time(now);
        let _ = w.dump_on(snap.iter().map(|(id, b, wd)| (*id, b, *wd)));
    }
}

fn dump_all(st: &mut SimState) {
    let snap = full_snapshot(st);
    let now = st.now;
    if let Some(w) = st.vcd.as_mut() {
        let _ = w.set_time(now);
        let _ = w.dump_all(snap.iter().map(|(id, b, wd)| (*id, b, *wd)));
    }
}

fn full_snapshot(st: &SimState) -> Vec<(IdCode, sim_ir::BitPacked, u32)> {
    st.nets
        .iter()
        .filter_map(|slot| {
            slot.vcd_id
                .map(|id| (id, word0(&slot.cur, slot.width), slot.width))
        })
        .collect()
}

/// Extract array-word-0 (`width` bits) from a packed net store.
fn word0(store: &sim_ir::BitPacked, width: u32) -> sim_ir::BitPacked {
    let mut v = Value::zeros(width.max(1), false);
    v.width = width;
    for i in 0..width {
        let w = (i / 64) as usize;
        let s = i % 64;
        let bv = store.val.get(w).map_or(0, |x| (x >> s) & 1);
        let bu = store.unk.get(w).map_or(0, |x| (x >> s) & 1);
        v.set_vu(i, bv, bu);
    }
    v.into_bitpacked(width)
}

// ── argument / const string helpers ────────────────────────────────────────

/// Read a string from a $dumpfile/$display arg ExprId → Const{StrUtf8} → bytes.
fn arg_string(sched: &Scheduler, eid: Option<u32>) -> String {
    let Some(eid) = eid else { return String::new() };
    if let sim_ir::Expr::Const { val } = &sched.st.ir.exprs[eid as usize] {
        return const_string(sched.st, *val);
    }
    // non-const arg: render its value as decimal (best-effort)
    fmt_dec(&sched.eval(eid))
}

/// Resolve an ExprId that is a `Const{val}` into its const string (format str).
fn expr_const_string(st: &SimState, eid: u32) -> String {
    if let sim_ir::Expr::Const { val } = &st.ir.exprs[eid as usize] {
        const_string(st, *val)
    } else {
        String::new()
    }
}

/// Decode a `ConstVal` (StrUtf8 → bytes LSB-first; numeric → packed bytes).
fn const_string(st: &SimState, cid: u32) -> String {
    let c = &st.ir.consts[cid as usize];
    let nbytes = ((c.width + 7) / 8) as usize;
    let mut bytes = Vec::with_capacity(nbytes);
    for b in 0..nbytes {
        let bit = (b as u32) * 8;
        let w = (bit / 64) as usize;
        let s = bit % 64;
        let byte = if s <= 56 {
            (c.bits.val.get(w).copied().unwrap_or(0) >> s) as u8
        } else {
            let lo = c.bits.val.get(w).copied().unwrap_or(0) >> s;
            let hi = c.bits.val.get(w + 1).copied().unwrap_or(0) << (64 - s);
            (lo | hi) as u8
        };
        bytes.push(byte);
    }
    // StrUtf8 packs LSB-byte-first AND in source order: byte 0 (the LSB) is the
    // FIRST character of the string (verified against elaborate: "a=%d" →
    // 0x64253D61 → LSB bytes 'a','=','%','d'). No reversal needed.
    while bytes.last() == Some(&0) {
        bytes.pop();
    }
    String::from_utf8_lossy(&bytes).into_owned()
}

// ── $display format engine (4-state aware) ─────────────────────────────────

fn format_args_str(sched: &Scheduler, fmt: Option<u32>, args: &[u32]) -> String {
    let Some(fmt_eid) = fmt else {
        // bare args → space-joined decimals
        return args
            .iter()
            .map(|&e| fmt_dec(&sched.eval(e)))
            .collect::<Vec<_>>()
            .join(" ");
    };
    // FROZEN IR: `SysTask.fmt` is an ExprId pointing to a `Const{val}` whose
    // `val` is the format-string ConstId (verified against elaborate).
    let template = expr_const_string(sched.st, fmt_eid);
    let mut out = String::new();
    let mut argi = 0usize;
    let mut chars = template.chars().peekable();

    while let Some(c) = chars.next() {
        if c != '%' {
            out.push(c);
            continue;
        }
        // optional width/flags: %0d, %5h …  (v1 records `0`, ignores explicit width)
        let mut min_zero = false;
        while let Some(&d) = chars.peek() {
            if d == '0' {
                min_zero = true;
                chars.next();
            } else if d.is_ascii_digit() {
                chars.next();
            } else {
                break;
            }
        }
        let spec = chars.next().unwrap_or('%');
        match spec {
            '%' => out.push('%'),
            'm' => out.push_str("top"),
            't' => {
                let v = next_arg(sched, args, &mut argi);
                out.push_str(&fmt_dec(&v));
            }
            'd' | 'D' => {
                let v = next_arg(sched, args, &mut argi);
                out.push_str(&fmt_dec(&v));
            }
            'h' | 'H' | 'x' | 'X' => {
                let v = next_arg(sched, args, &mut argi);
                out.push_str(&fmt_radix(&v, 4, min_zero));
            }
            'o' | 'O' => {
                let v = next_arg(sched, args, &mut argi);
                out.push_str(&fmt_radix(&v, 3, min_zero));
            }
            'b' | 'B' => {
                let v = next_arg(sched, args, &mut argi);
                out.push_str(&fmt_radix(&v, 1, min_zero));
            }
            'c' => {
                let v = next_arg(sched, args, &mut argi);
                out.push(char_of(&v));
            }
            's' => {
                let e = args.get(argi).copied();
                argi += 1;
                out.push_str(&arg_string(sched, e));
            }
            other => {
                out.push('%');
                out.push(other);
            }
        }
    }
    out
}

fn next_arg(sched: &Scheduler, args: &[u32], argi: &mut usize) -> Value {
    let e = args.get(*argi).copied();
    *argi += 1;
    e.map(|x| sched.eval(x)).unwrap_or_else(Value::x1)
}

fn any_unknown(v: &Value) -> bool {
    v.has_xz()
}

/// %d: decimal; any X/Z → "x".
fn fmt_dec(v: &Value) -> String {
    if any_unknown(v) {
        return "x".to_string();
    }
    let mut acc: u128 = 0;
    for i in 0..v.width.min(128) {
        let (b, _) = v.get_vu(i);
        if b == 1 {
            acc |= 1u128 << i;
        }
    }
    if v.signed && v.width >= 1 && v.width <= 64 {
        if let Some(s) = v.to_i128_signed() {
            return s.to_string();
        }
    }
    acc.to_string()
}

/// %h/%o/%b: group bits per digit (1=bin,3=oct,4=hex), MSB-first; a group with
/// any X → 'x', any Z (no X) → 'z'.
fn fmt_radix(v: &Value, bits_per_digit: u32, _min_zero: bool) -> String {
    if v.width == 0 {
        return "0".to_string();
    }
    let ndig = (v.width + bits_per_digit - 1) / bits_per_digit;
    let mut s = String::new();
    for d in (0..ndig).rev() {
        let base = d * bits_per_digit;
        let mut val = 0u32;
        let mut has_x = false;
        let mut has_z = false;
        for k in 0..bits_per_digit {
            let bi = base + k;
            if bi >= v.width {
                continue;
            }
            let (b, u) = v.get_vu(bi);
            match (b, u) {
                (_, 0) => {
                    if b == 1 {
                        val |= 1 << k;
                    }
                }
                (0, 1) => has_x = true,
                (1, 1) => has_z = true,
                _ => {}
            }
        }
        s.push(if has_x {
            'x'
        } else if has_z {
            'z'
        } else {
            std::char::from_digit(val, 16).unwrap()
        });
    }
    s
}

fn char_of(v: &Value) -> char {
    let byte = (v.to_u64().unwrap_or(0) & 0xFF) as u8;
    byte as char
}
