//! $-task handlers (inlined for v1; HOOK: extract to hdl-builtins post-v1).
//! Handles $dumpfile/$dumpvars/$dumpoff/$dumpon/$dumpall → vcd-writer,
//! $display/$write/$monitor/$strobe formatting → stdout sink, $finish/$stop.

use std::io::Write;

use sim_ir::SysTaskId;
use vcd_writer::{IdCode, ScopeType};

use crate::sched::Scheduler;
use crate::state::{vcd_var_type, FmtCapture, MonitorState, SimState};
use crate::value::Value;

/// Control-flow signal back to the executor.
pub(crate) enum Ctl {
    Continue,
    Finish,
    Stop,
    /// Runtime `$fatal` (RunFatal): abort the run with `ExitClass::Fatal`.
    Fatal,
}

pub(crate) fn dispatch(
    sched: &mut Scheduler,
    which: SysTaskId,
    fmt: Option<u32>,
    args: &[u32],
    sid: u32,
) -> Ctl {
    // P1-1: `$fatal`/`$error`/`$warning`/`$info` lower as `Display` plus an
    // out-of-band severity entry keyed by StmtId — intercept BEFORE the normal
    // stdout print so the text reaches the DIAGNOSTIC stream only (doc-13).
    if let Some(sev) = sched.st.severities.get(&sid).copied() {
        return run_severity(sched, sev, fmt, args);
    }
    // P1-5: the b/o/h variants change the default radix of unformatted args.
    let radix = sched.st.radixes.get(&sid).copied();
    match which {
        // v5 (C)-③: dyn-array object methods. args[0] is always the HANDLE's
        // Signal expr (elaborate contract); a malformed handle is a defensive
        // no-op, never a panic.
        SysTaskId::DynNew => {
            let Some(net) = dyn_handle_net(sched, args.first()) else {
                return Ctl::Continue;
            };
            // `new[]` is dyn-array syntax: acting on a queue/assoc handle
            // would put a kind-mismatched object in the heap — defensive
            // warn+ignore (elaborate never emits it).
            if sched.st.ir.nets.get(net as usize).map(|nv| nv.kind)
                != Some(sim_ir::NetKind::DynArray)
            {
                dyn_warn_once(sched, net, "new[] on a non-dynamic-array handle (ignored)");
                return Ctl::Continue;
            }
            // n: X/Z degrades to EMPTY + warn-once; an explicit 0 is
            // legal-silent (IEEE §7.5.1). Cap at the static array cap class —
            // a huge n is a t-runtime OOM hazard exactly like P2-6.
            let nv = args.get(1).map(|&a| sched.eval(a));
            let n = match nv {
                Some(v) if v.has_xz() => {
                    dyn_warn_once(sched, net, "new[] size is X/Z; array degraded to empty");
                    0
                }
                Some(v) => {
                    // Same cap class as elaborate's MAX_ARRAY_LEN (P2-6): a
                    // runtime OOM is as silent-deadly as the t0 one. NO silent
                    // caps — a clamped n warns (once per net).
                    let raw = v.to_u64().unwrap_or(0);
                    if raw > crate::state::MAX_DYN_ELEMS as u64 {
                        dyn_warn_once(
                            sched,
                            net,
                            "new[] size exceeds the element cap (1<<24); clamped",
                        );
                    }
                    raw.min(crate::state::MAX_DYN_ELEMS as u64) as usize
                }
                None => 0,
            };
            let (w, signed) = sched
                .st
                .ir
                .nets
                .get(net as usize)
                .map(|nv| (nv.width.max(1), nv.signed))
                .unwrap_or((1, false));
            let mut elems = vec![Value::xs(w, signed); n];
            // copy form `new[n](src)`: prefix-copy from the src handle.
            if let Some(src_net) = dyn_handle_net(sched, args.get(2)) {
                if let Some(crate::state::DynObj::DynArray { elems: src }) =
                    sched.st.dyn_heap.get(&src_net)
                {
                    for (dst, s) in elems.iter_mut().zip(src.iter()) {
                        *dst = s.clone();
                    }
                }
            }
            sched
                .st
                .dyn_heap
                .insert(net, crate::state::DynObj::DynArray { elems });
            Ctl::Continue
        }
        SysTaskId::DynDelete => {
            if let Some(net) = dyn_handle_net(sched, args.first()) {
                sched.st.dyn_heap.remove(&net); // absent entry IS the empty object
            }
            Ctl::Continue
        }
        // v5 (C)-④: queue pushes. args = [handle, value]; the value is CAST
        // to the element type with assignment semantics (§5.5: evaluate at
        // max(element, self) width with the SOURCE's signedness, then truncate
        // — `push_back(300)` into a byte queue stores 44; iverilog live).
        SysTaskId::QPushBack | SysTaskId::QPushFront => {
            let Some(net) = dyn_handle_net(sched, args.first()) else {
                return Ctl::Continue;
            };
            let Some((w, kind)) = sched
                .st
                .ir
                .nets
                .get(net as usize)
                .map(|nv| (nv.width.max(1), nv.kind))
            else {
                return Ctl::Continue;
            };
            if kind != sim_ir::NetKind::Queue {
                dyn_warn_once(sched, net, "queue push on a non-queue handle (ignored)");
                return Ctl::Continue;
            }
            let v = match args.get(1) {
                Some(&a) => {
                    let sw = sched.st.wt.get(a);
                    sched.eval_ctx_top(a, w.max(sw.width), sw.signed).resize(w)
                }
                None => Value::xs(w, false),
            };
            // Cap BEFORE taking the entry borrow (the warn needs `&mut sched`).
            // No silent caps (P2-6 class): a runaway push loop is a runtime
            // OOM hazard — warn (once per net) and DROP the push.
            let len = sched.st.dyn_heap.get(&net).map(|o| o.len()).unwrap_or(0);
            if len >= crate::state::MAX_DYN_ELEMS {
                dyn_warn_once(
                    sched,
                    net,
                    "queue exceeds the element cap (1<<24); push dropped",
                );
                return Ctl::Continue;
            }
            // A missing entry IS the empty queue (lazy, like every dyn object).
            let entry =
                sched
                    .st
                    .dyn_heap
                    .entry(net)
                    .or_insert_with(|| crate::state::DynObj::Queue {
                        elems: std::collections::VecDeque::new(),
                    });
            if let crate::state::DynObj::Queue { elems } = entry {
                if which == SysTaskId::QPushFront {
                    elems.push_front(v);
                } else {
                    elems.push_back(v);
                }
            }
            Ctl::Continue
        }
        // v5 ⑤: `a.delete(k)` — args = [handle, key]. A MISSING key is a
        // SILENT no-op (IEEE §7.9); an X/Z key warns (invalid index, §7.8.6);
        // a non-assoc handle warns (hand-built IR only — ⑥ type-checks).
        SysTaskId::AssocDeleteKey => {
            if let Some(net) = dyn_handle_net(sched, args.first()) {
                let kind = sched.st.ir.nets.get(net as usize).map(|nv| nv.kind);
                if kind != Some(sim_ir::NetKind::Assoc) {
                    dyn_warn_once(sched, net, "assoc delete on a non-assoc handle (ignored)");
                    return Ctl::Continue;
                }
                match args.get(1).and_then(|&k| sched.assoc_key_of(k)) {
                    None => dyn_warn_once(sched, net, "assoc delete key is X/Z (ignored)"),
                    Some(k) => {
                        if let Some(crate::state::DynObj::Assoc { map }) =
                            sched.st.dyn_heap.get_mut(&net)
                        {
                            map.remove(&k);
                        }
                    }
                }
            }
            Ctl::Continue
        }
        SysTaskId::Display => {
            let mut s = format_args_str(sched, fmt, args, radix);
            s.push('\n');
            write_out(sched.st, &s);
            Ctl::Continue
        }
        SysTaskId::Write => {
            let s = format_args_str(sched, fmt, args, radix);
            write_out(sched.st, &s);
            Ctl::Continue
        }
        // $strobe: REGISTER a postponed capture (does NOT print now). It is
        // rendered with settled end-of-timestep values at `flush_postponed`,
        // then cleared (one-shot per call). Multiple strobes in one step print
        // in call order (FIFO push).
        SysTaskId::Strobe => {
            let time_mult = sched.st.cur_time_mult;
            sched.st.postponed.strobes.push(FmtCapture {
                fmt,
                args: args.to_vec(),
                time_mult,
                radix,
                scope: sched.st.cur_scope.clone(),
            });
            Ctl::Continue
        }
        // $monitor: REPLACE the global singleton (IEEE: at most one active
        // monitor in the whole sim). `last_vals = None` forces an establishment
        // print at the next postponed flush of THIS timestep, seeding the
        // baseline value list.
        SysTaskId::Monitor => {
            let time_mult = sched.st.cur_time_mult;
            sched.st.postponed.monitor = Some(MonitorState {
                cap: FmtCapture {
                    fmt,
                    args: args.to_vec(),
                    time_mult,
                    radix,
                    scope: sched.st.cur_scope.clone(),
                },
                last_vals: None,
                enabled: true,
            });
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
        SysTaskId::DumpFlush => {
            // IEEE §21.7.2.4: push buffered VCD bytes to the OS now (crash-safe
            // checkpoints for long runs). Errors surface at finalize (W4019).
            if let Some(w) = sched.st.vcd.as_mut() {
                let _ = w.flush();
            }
            Ctl::Continue
        }
        SysTaskId::DumpLimit => {
            // IEEE §21.7.2.5: byte budget; the writer emits a one-time
            // `$comment Dump limit reached $end` and drops further records.
            // X/Z or missing size → no-op (no budget installed).
            let size = args
                .first()
                .and_then(|&a| sched.eval(a).to_u64())
                .unwrap_or(0);
            if size > 0 {
                if let Some(w) = sched.st.vcd.as_mut() {
                    w.set_limit(size);
                }
            }
            Ctl::Continue
        }
    }
}

pub(crate) fn write_out(st: &mut SimState, text: &str) {
    let _ = st.out.write_all(text.as_bytes());
}

/// P1-1: execute a severity task (doc-13 §Severity). The user message renders
/// through the SAME `format_args_str` engine as `$display` (so `%0d`/defaults
/// behave identically) but is emitted as a `LogEvent::Diagnostic` — stderr in
/// production, never the stdout stream. Empty message ⇒ the code's title.
/// `$fatal` aborts (implicit `$finish`, `ExitClass::Fatal`); `$error` flags
/// `HadErrors` and continues; `$warning`/`$info` only print.
fn run_severity(
    sched: &mut Scheduler,
    sev: crate::SeverityKind,
    fmt: Option<u32>,
    args: &[u32],
) -> Ctl {
    use crate::SeverityKind as K;
    use diag::{Diagnostic, LogEvent, MsgCode, Severity, TimeStamp};
    let (severity, code) = match sev {
        K::Fatal => (Severity::Fatal, MsgCode::RunFatal),
        K::Error => (Severity::Error, MsgCode::RunUserError),
        K::Warning => (Severity::Warning, MsgCode::RunUserWarning),
        K::Info => (Severity::Info, MsgCode::RunUserInfo),
    };
    let mut message = format_args_str(sched, fmt, args, None);
    if message.is_empty() {
        message = code.title().to_string();
    }
    sched.st.sink.emit(LogEvent::Diagnostic(Diagnostic {
        severity,
        code,
        message,
        location: None,
        context: Vec::new(),
        sim_time: Some(TimeStamp {
            ticks: sched.st.now,
        }),
    }));
    match sev {
        K::Fatal => Ctl::Fatal,
        K::Error => {
            sched.st.had_error = true;
            Ctl::Continue
        }
        K::Warning | K::Info => Ctl::Continue,
    }
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
        Err(e) => {
            // P2-1: the main artifact must not vanish silently — warn (with the
            // path + OS error) and keep simulating without a waveform.
            use diag::{Diagnostic, LogEvent, MsgCode, Severity, TimeStamp};
            st.sink.emit(LogEvent::Diagnostic(Diagnostic {
                severity: Severity::Warning,
                code: MsgCode::RunVcdOpenFail,
                message: format!("cannot open VCD dump file '{path}': {e}"),
                location: None,
                context: Vec::new(),
                sim_time: Some(TimeStamp { ticks: st.now }),
            }));
            return;
        }
    };
    // P3-3/T0b: buffer the VCD sink (raw `File` was ~1 write syscall per record).
    // `finalize_vcd` flushes explicitly, so buffering never changes the bytes.
    // P4-T1: with `--threads ≥2` the buffered chunks go to a dedicated writer
    // thread (order-preserving bounded FIFO) — byte-identical, wall-clock only.
    let sink: crate::state::VcdSink = if st.threads >= 2 {
        Box::new(std::io::BufWriter::with_capacity(
            64 * 1024,
            crate::vcd_thread::ThreadedWriter::spawn(file),
        ))
    } else {
        Box::new(std::io::BufWriter::with_capacity(64 * 1024, file))
    };
    st.open_vcd(sink);

    let date = st.vcd_date.clone();
    let unit = st.timescale_unit.clone();
    let mut ids: Vec<Option<IdCode>> = vec![None; st.ir.nets.len()];
    // Hierarchical naming when the elaborate side table is present (one FQ name per
    // net); otherwise the legacy flat `top` scope + synthetic `n{i}`.
    let use_names = st.net_names.len() == st.ir.nets.len();
    {
        let nets = &st.ir.nets;
        let names = &st.net_names;
        let w = st.vcd.as_mut().unwrap();
        let _ = w.write_preamble(&date, &unit);
        if use_names {
            // Split each FQ name into (scope segments, leaf). Emit a correctly nested
            // $scope/$upscope tree by visiting nets in scope-sorted order and pushing
            // / popping as the scope prefix changes (classic sorted-leaf tree walk).
            let mut order: Vec<usize> = (0..nets.len()).collect();
            let segs: Vec<Vec<&str>> = names.iter().map(|s| s.split('.').collect()).collect();
            // sort by scope path (all but the leaf); stable → vars keep net order
            // within a scope.
            order.sort_by(|&a, &b| segs[a][..segs[a].len() - 1].cmp(&segs[b][..segs[b].len() - 1]));
            let mut cur: Vec<&str> = Vec::new();
            for &i in &order {
                let scope = &segs[i][..segs[i].len() - 1];
                let leaf = *segs[i].last().unwrap();
                // pop to the common prefix
                let common = cur
                    .iter()
                    .zip(scope.iter())
                    .take_while(|(a, b)| a == b)
                    .count();
                while cur.len() > common {
                    let _ = w.pop_scope();
                    cur.pop();
                }
                // push the remaining scope segments
                while cur.len() < scope.len() {
                    let seg = scope[cur.len()];
                    let _ = w.push_scope(ScopeType::Module, seg);
                    cur.push(seg);
                }
                // v5 (C): dyn handles have no $var form (variable length) —
                // never declared, so no initial dump and no change records.
                if matches!(
                    nets[i].kind,
                    sim_ir::NetKind::DynArray | sim_ir::NetKind::Queue | sim_ir::NetKind::Assoc
                ) {
                    continue;
                }
                let vt = vcd_var_type(nets[i].kind);
                if let Ok(id) = w.declare_var(vt, nets[i].width.max(1), leaf) {
                    ids[i] = Some(id);
                }
            }
            while !cur.is_empty() {
                let _ = w.pop_scope();
                cur.pop();
            }
        } else {
            let _ = w.push_scope(ScopeType::Module, "top");
            for (i, nv) in nets.iter().enumerate() {
                if matches!(
                    nv.kind,
                    sim_ir::NetKind::DynArray | sim_ir::NetKind::Queue | sim_ir::NetKind::Assoc
                ) {
                    continue; // dyn handles: no $var form (see above)
                }
                let vt = vcd_var_type(nv.kind);
                let name = format!("n{i}");
                if let Ok(id) = w.declare_var(vt, nv.width.max(1), &name) {
                    ids[i] = Some(id);
                }
            }
            let _ = w.pop_scope();
        }
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

pub(crate) fn format_args_str(
    sched: &Scheduler,
    fmt: Option<u32>,
    args: &[u32],
    radix: Option<u8>,
) -> String {
    let mut out = String::new();
    let mut argi = 0usize;
    if let Some(fmt_eid) = fmt {
        // FROZEN IR: `SysTask.fmt` is an ExprId pointing to a `Const{val}` whose
        // `val` is the format-string ConstId (verified against elaborate).
        let template = expr_const_string(sched.st, fmt_eid);
        render_template(sched, &template, args, &mut argi, &mut out);
    }
    // IEEE 1364-2005 §17.1 (P0-8): any argument NOT consumed by a format
    // string prints sequentially — a string-literal arg is itself a format
    // segment (its `%` specs consume the args that follow it); every other
    // arg prints in the default radix (a padded `%d` field; `%g` for a real).
    // Previously everything after the leading format string was silently
    // dropped, and a bare string arg printed as a packed-ASCII decimal.
    while argi < args.len() {
        let e = args[argi];
        argi += 1;
        if let Some(text) = str_const_of_expr(sched.st, e) {
            render_template(sched, &text, args, &mut argi, &mut out);
        } else {
            push_default_radix(&sched.eval(e), &mut out, radix);
        }
    }
    out
}

/// The argument ExprId IFF it is a string-literal constant (`ConstRepr::StrUtf8`).
fn str_const_of_expr(st: &SimState, eid: u32) -> Option<String> {
    if let sim_ir::Expr::Const { val } = &st.ir.exprs[eid as usize] {
        if st.ir.consts[*val as usize].repr == sim_ir::ConstRepr::StrUtf8 {
            return Some(const_string(st, *val));
        }
    }
    None
}

/// Default-radix rendering of an argument with no format spec: a padded `%d`
/// field (`%g` for a real) — or, under a b/o/h task variant (P1-5), the padded
/// `%b`/`%o`/`%h` form (same `fmt_radix` the explicit specs use; iverilog joins
/// these fields with no separator).
fn push_default_radix(v: &Value, out: &mut String, radix: Option<u8>) {
    if v.is_real {
        out.push_str(&fmt_real(v, 'g', None, None));
        return;
    }
    match radix {
        Some(2) => out.push_str(&fmt_radix(v, 1, false)),
        Some(8) => out.push_str(&fmt_radix(v, 3, false)),
        Some(16) => out.push_str(&fmt_radix(v, 4, false)),
        _ => {
            let s = fmt_dec(v);
            let fw = dec_field_width(v.width);
            if s.len() < fw {
                out.push_str(&" ".repeat(fw - s.len()));
            }
            out.push_str(&s);
        }
    }
}

/// iverilog-style `%v` strength form of bit 0: St0/St1/StX/HiZ (vitamin has no
/// strength model; the driven-strong prefix is the conventional rendering).
fn strength_form(v: &Value) -> &'static str {
    match v.get_vu(0) {
        (0, 0) => "St0",
        (1, 0) => "St1",
        (1, 1) => "HiZ",
        _ => "StX",
    }
}

fn render_template(
    sched: &Scheduler,
    template: &str,
    args: &[u32],
    argi: &mut usize,
    out: &mut String,
) {
    let mut chars = template.chars().peekable();

    while let Some(c) = chars.next() {
        if c != '%' {
            out.push(c);
            continue;
        }
        // optional width/flags: %0d, %5h, %8.2f …  (v1 records `0` for integer
        // specs; width/precision are threaded into the real `%f/%e/%g` formatters).
        let mut min_zero = false;
        let mut width_digits = String::new();
        while let Some(&d) = chars.peek() {
            if d == '0' && width_digits.is_empty() {
                min_zero = true;
                width_digits.push('0');
                chars.next();
            } else if d.is_ascii_digit() {
                width_digits.push(d);
                chars.next();
            } else {
                break;
            }
        }
        let mut prec_digits = String::new();
        let mut has_prec = false;
        if chars.peek() == Some(&'.') {
            has_prec = true;
            chars.next();
            while let Some(&d) = chars.peek() {
                if d.is_ascii_digit() {
                    prec_digits.push(d);
                    chars.next();
                } else {
                    break;
                }
            }
        }
        let field_width: Option<usize> = width_digits
            .trim_start_matches('0')
            .parse::<usize>()
            .ok()
            .or_else(|| {
                if width_digits.chars().all(|c| c == '0') && !width_digits.is_empty() {
                    Some(0)
                } else {
                    None
                }
            });
        let precision: Option<usize> = if has_prec {
            Some(prec_digits.parse::<usize>().unwrap_or(0))
        } else {
            None
        };
        let spec = chars.next().unwrap_or('%');
        match spec {
            '%' => out.push('%'),
            // P2-11: hierarchical scope of the EXECUTING process (was: always
            // the literal "top"). Strobe/monitor renders restore the
            // REGISTERING process's scope first (FmtCapture.scope).
            'm' => out.push_str(&sched.st.cur_scope),
            't' => {
                let v = next_arg(sched, args, argi);
                out.push_str(&fmt_dec(&v));
            }
            'd' | 'D' => {
                let v = next_arg(sched, args, argi);
                // IEEE 1364 %d: right-justify in a field width. `%0d` ⇒ minimal;
                // `%Nd` ⇒ width N; bare `%d` ⇒ the operand's default decimal width
                // (digit count of its max value). An X/Z prints as a right-justified
                // `x`/`z` in that field, like a numeric value.
                let s = fmt_dec(&v);
                let fw = if min_zero {
                    0
                } else {
                    field_width.unwrap_or_else(|| dec_field_width(v.width))
                };
                if s.len() < fw {
                    out.push_str(&" ".repeat(fw - s.len()));
                }
                out.push_str(&s);
            }
            'h' | 'H' | 'x' | 'X' => {
                let v = next_arg(sched, args, argi);
                out.push_str(&fmt_radix(&v, 4, min_zero));
            }
            'o' | 'O' => {
                let v = next_arg(sched, args, argi);
                out.push_str(&fmt_radix(&v, 3, min_zero));
            }
            'b' | 'B' => {
                let v = next_arg(sched, args, argi);
                out.push_str(&fmt_radix(&v, 1, min_zero));
            }
            'f' | 'F' | 'g' | 'G' | 'e' | 'E' => {
                let v = next_arg(sched, args, argi);
                out.push_str(&fmt_real(&v, spec, field_width, precision));
            }
            'c' => {
                let v = next_arg(sched, args, argi);
                out.push(char_of(&v));
            }
            's' => {
                let e = args.get(*argi).copied();
                *argi += 1;
                out.push_str(&arg_string(sched, e));
            }
            // P0-8③: the remaining IEEE specs CONSUME their argument — leaving
            // them unconsumed shifted every later spec onto the wrong arg.
            'v' | 'V' => {
                let v = next_arg(sched, args, argi);
                out.push_str(strength_form(&v));
            }
            // binary-dump specs: consume; vitamin emits no text for them (v1 —
            // the IEEE form writes raw bytes, useless in a text log).
            'u' | 'U' | 'z' | 'Z' => {
                let _ = next_arg(sched, args, argi);
            }
            // `%p` (SV assignment pattern): minimal-width value form (v1).
            'p' | 'P' => {
                let v = next_arg(sched, args, argi);
                out.push_str(&fmt_dec(&v));
            }
            other => {
                out.push('%');
                out.push(other);
            }
        }
    }
}

fn next_arg(sched: &Scheduler, args: &[u32], argi: &mut usize) -> Value {
    let e = args.get(*argi).copied();
    *argi += 1;
    e.map(|x| sched.eval(x)).unwrap_or_else(Value::x1)
}

fn any_unknown(v: &Value) -> bool {
    v.has_xz()
}

/// IEEE %d default field width = decimal digit count of an `n`-bit operand's max
/// value (`2^n − 1`): 1-bit→1, 8-bit→3, 32-bit→10. Computed exactly up to 128 bits,
/// then via `n·log10(2)` (a column-alignment hint; exactness beyond 128 is moot).
fn dec_field_width(n: u32) -> usize {
    if n == 0 {
        return 1;
    }
    if n <= 128 {
        let maxv: u128 = if n == 128 {
            u128::MAX
        } else {
            (1u128 << n) - 1
        };
        maxv.to_string().len()
    } else {
        (n as f64 * std::f64::consts::LOG10_2) as usize + 1
    }
}

/// %d: decimal; any X/Z → "x". A real ROUNDS half-away (saturating to i64
/// extremes; NaN → 0).
fn fmt_dec(v: &Value) -> String {
    if v.is_real {
        let x = v.to_f64().unwrap_or(0.0);
        // round half-away; large |x| SATURATES to i64::MAX/MIN; NaN.round() as i64 == 0.
        return format!("{}", x.round() as i64);
    }
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

/// `%f`/`%e`/`%g` of a real Value (the arg may be an integer promoted to real).
/// `width`/`prec` are the optional field-width / precision modifiers (`%8.2f`).
fn fmt_real(v: &Value, spec: char, width: Option<usize>, prec: Option<usize>) -> String {
    let x = v.to_f64().unwrap_or(0.0);
    let body = match spec {
        'f' | 'F' => format!("{:.*}", prec.unwrap_or(6), x), // default 6 fractional digits
        'e' | 'E' => fmt_real_e(x, prec),
        'g' | 'G' => format_g(x, prec),
        _ => format!("{x}"),
    };
    if let Some(w) = width {
        if body.len() < w {
            return format!("{}{}", " ".repeat(w - body.len()), body);
        }
    }
    body
}

/// %e → C/printf/LRM form: `prec` mantissa fraction digits (default 6), signed
/// exponent zero-padded to AT LEAST 2 digits (`1.500000e+03`). Non-finite passes
/// through as Rust prints it (`inf`/`-inf`/`NaN`).
fn fmt_real_e(x: f64, prec: Option<usize>) -> String {
    if !x.is_finite() {
        return format!("{x}"); // inf / -inf / NaN
    }
    let p = prec.unwrap_or(6);
    let s = format!("{x:.p$e}"); // e.g. "1.500000e3" or "1.234500e-5"
    let (mant, exp) = s.split_once('e').expect("rust {:e} always emits 'e'");
    let (sign, digits) = match exp.strip_prefix('-') {
        Some(d) => ('-', d),
        None => ('+', exp),
    };
    let padded = if digits.len() < 2 {
        format!("{digits:0>2}")
    } else {
        digits.to_string()
    };
    format!("{mant}e{sign}{padded}")
}

/// %g: shortest of %e/%f with trailing zeros stripped, per C/LRM. `prec` is the
/// total significant-digit precision P (default 6).
fn format_g(x: f64, prec: Option<usize>) -> String {
    if !x.is_finite() {
        return format!("{x}"); // inf / -inf / NaN
    }
    if x == 0.0 {
        return "0".to_string(); // both +0.0 and -0.0 → "0" under %g zero-strip
    }
    let p: i32 = prec.unwrap_or(6).max(1) as i32;
    // Decimal exponent AFTER rounding to P significant digits, derived from
    // Rust's deterministic `{:e}` formatter — NOT `log10` (a libm transcendental
    // not guaranteed 3-OS byte-identical, and which reports the PRE-rounding
    // exponent: `9.9999e5` at P=6 must select exp 6, not 5).
    let sci = format!("{:.*e}", (p - 1) as usize, x); // e.g. "1.50000e3"
    let exp: i32 = sci
        .split_once('e')
        .and_then(|(_, e)| e.parse().ok())
        .unwrap_or(0);
    if exp < -4 || exp >= p {
        // exponent form: reuse the already-rounded mantissa, LRM exponent normalize.
        let (mant, e) = sci.split_once('e').unwrap();
        let mant = strip_trailing_zeros(mant);
        let (sgn, dig) = match e.strip_prefix('-') {
            Some(d) => ('-', d),
            None => ('+', e),
        };
        let dig = if dig.len() < 2 {
            format!("{dig:0>2}")
        } else {
            dig.to_string()
        };
        format!("{mant}e{sgn}{dig}")
    } else {
        let prec = (p - 1 - exp).max(0) as usize;
        let body = format!("{x:.prec$}"); // fixed form
        strip_trailing_zeros(&body)
    }
}

/// Strip insignificant trailing zeros after a decimal point, and a bare trailing '.'.
fn strip_trailing_zeros(s: &str) -> String {
    if !s.contains('.') {
        return s.to_string();
    }
    let t = s.trim_end_matches('0');
    t.trim_end_matches('.').to_string()
}

/// %h/%o/%b: group bits per digit (1=bin,3=oct,4=hex), MSB-first; a group with
/// any X → 'x', any Z (no X) → 'z'.
fn fmt_radix(v: &Value, bits_per_digit: u32, min_zero: bool) -> String {
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
    // `%0h`/`%0b`/`%0o`: minimum width — strip leading zeros (keep ≥1 digit).
    // Plain `%h`/etc. keep the full vector width (leading zeros retained).
    if min_zero {
        let trimmed = s.trim_start_matches('0');
        return if trimmed.is_empty() {
            "0".to_string()
        } else {
            trimmed.to_string()
        };
    }
    s
}

fn char_of(v: &Value) -> char {
    // IEEE %c: the LOW 8 bits regardless of value width — a wide value with
    // high bits set must not degrade to NUL under the strict no-truncation
    // `to_u64`. X/Z keeps the old None→0 policy.
    if v.has_xz() {
        return '\0';
    }
    let byte = (v.val.first().copied().unwrap_or(0) & 0xFF) as u8;
    byte as char
}

/// v5 (C): resolve a dyn-method HANDLE argument (the ExprId of the handle's
/// whole-net `Signal`) to its NetId. Anything else → None (defensive no-op).
fn dyn_handle_net(sched: &Scheduler, arg: Option<&u32>) -> Option<u32> {
    let &eid = arg?;
    match sched.st.ir.exprs.get(eid as usize) {
        Some(sim_ir::Expr::Signal { net, word: None }) => Some(*net),
        _ => None,
    }
}

/// One W-RUN-DYN-DEGRADE per handle net (latched in `dyn_warned`) — a degraded
/// dyn op inside a loop must not spam the diagnostic stream.
fn dyn_warn_once(sched: &mut Scheduler, net: u32, msg: &str) {
    sched.st.dyn_warn_once_at(net, msg);
}
