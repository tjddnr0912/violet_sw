//! elaborate v1 tests — build a small hdl-ast by hand, elaborate, assert SimIr.

use std::cell::RefCell;

use diag::{LogEvent, LogSink};
use hdl_ast as ast;

use super::*;
use crate::literal::parse_int_literal;

// ── a collecting LogSink (interior mutability: emit takes &self) ──
#[derive(Default)]
struct CollectSink {
    events: RefCell<Vec<LogEvent>>,
}
impl LogSink for CollectSink {
    fn emit(&self, event: LogEvent) {
        self.events.borrow_mut().push(event);
    }
}
impl CollectSink {
    fn n_diags(&self) -> usize {
        self.events
            .borrow()
            .iter()
            .filter(|e| matches!(e, LogEvent::Diagnostic(_)))
            .count()
    }
}

// ── tiny AST builders ──
const SP: ast::Span = ast::Span { lo: 0, hi: 0 };

fn ident(name: &str) -> ast::Ident {
    ast::Ident {
        name: name.to_string(),
        span: SP,
    }
}
fn hpath(name: &str) -> ast::HierPath {
    ast::HierPath {
        segments: vec![ident(name)],
        span: SP,
    }
}
fn ex(kind: ast::ExprKind) -> ast::Expr {
    ast::Expr { kind, span: SP }
}
fn id_expr(name: &str) -> ast::Expr {
    ex(ast::ExprKind::Ident(hpath(name)))
}
fn lit(raw: &str, kind: ast::IntLitKind) -> ast::Expr {
    ex(ast::ExprKind::IntLit {
        kind,
        raw: raw.to_string(),
    })
}
fn dec(n: &str) -> ast::Expr {
    lit(n, ast::IntLitKind::Decimal)
}
fn binop(op: ast::BinOp, l: ast::Expr, r: ast::Expr) -> ast::Expr {
    ex(ast::ExprKind::Binary {
        op,
        lhs: Box::new(l),
        rhs: Box::new(r),
    })
}

/// `wire [msb:lsb] names...;` (msb/lsb are decimal literals)
fn wire_vec(msb: u32, lsb: u32, names: &[&str]) -> ast::ModuleItem {
    netvar(ast::NetVarKind::Wire, Some((msb, lsb)), false, names)
}
fn netvar(
    kind: ast::NetVarKind,
    range: Option<(u32, u32)>,
    signed: bool,
    names: &[&str],
) -> ast::ModuleItem {
    let range = range.map(|(m, l)| ast::Range {
        msb: dec(&m.to_string()),
        lsb: dec(&l.to_string()),
        span: SP,
    });
    ast::ModuleItem::NetVar(ast::NetVarDecl {
        kind,
        signed,
        range,
        names: names
            .iter()
            .map(|n| ast::DeclName {
                name: ident(n),
                unpacked: Vec::new(),
                init: None,
                span: SP,
            })
            .collect(),
        span: SP,
    })
}

/// `assign <lhs> = <rhs>;`
fn cont_assign(lhs: ast::Lvalue, rhs: ast::Expr) -> ast::ModuleItem {
    ast::ModuleItem::ContAssign(ast::ContinuousAssign {
        delay: None,
        assigns: vec![(lhs, rhs)],
        span: SP,
    })
}
fn lv_id(name: &str) -> ast::Lvalue {
    ast::Lvalue::Ident(hpath(name))
}

fn module(name: &str, body: Vec<ast::ModuleItem>) -> ast::SourceUnit {
    ast::SourceUnit {
        items: vec![ast::TopItem::Module(ast::ModuleDecl {
            is_macromodule: false,
            name: ident(name),
            params: Vec::new(),
            ports: ast::PortList::None,
            body,
            span: SP,
        })],
        span: SP,
    }
}

fn elab_ok(unit: &ast::SourceUnit) -> ir::SimIr {
    let sink = CollectSink::default();
    let ir = elaborate(unit, &sink);
    assert_eq!(sink.n_diags(), 0, "unexpected diagnostics");
    ir.expect("elaborate returned None on clean input")
}

// ───────────────────────── 1. driver / nets ─────────────────────────
#[test]
fn t1_nets_in_decl_order_and_self_instance() {
    // module m; wire [7:0] a,b,y; assign y = a & b | 8'hF0;
    let unit = module(
        "m",
        vec![
            wire_vec(7, 0, &["a", "b", "y"]),
            cont_assign(
                lv_id("y"),
                binop(
                    ast::BinOp::BitOr,
                    binop(ast::BinOp::BitAnd, id_expr("a"), id_expr("b")),
                    lit("8'hF0", ast::IntLitKind::Sized),
                ),
            ),
        ],
    );
    let s = elab_ok(&unit);

    // nets a,b,y in order, all width 8.
    assert_eq!(s.nets.len(), 3);
    for n in &s.nets {
        assert_eq!(n.width, 8);
        assert_eq!(n.msb, 7);
        assert_eq!(n.lsb, 0);
        assert_eq!(n.kind, ir::NetKind::Wire);
    }
    // one self-instance covering all 3 nets.
    assert_eq!(s.instances.len(), 1);
    assert_eq!(s.instances[0].first_net, 0);
    assert_eq!(s.instances[0].net_count, 3);
    assert!(s.instances[0].parent.is_none());

    // exactly one cont_assign onto net y (=2).
    assert_eq!(s.cont_assigns.len(), 1);
    let ca = &s.cont_assigns[0];
    assert_eq!(ca.lhs.chunks.len(), 1);
    assert_eq!(ca.lhs.chunks[0].net, 2); // y is the 3rd net
    assert!(ca.delay.is_none());

    // rhs is the top Binary(BitOr,...). Walk the arena root.
    let root = &s.exprs[ca.rhs as usize];
    match root {
        ir::Expr::Binary {
            op: ir::BinOp::BitOr,
            lhs,
            rhs,
        } => {
            // lhs = Binary(BitAnd, Signal a, Signal b)
            match &s.exprs[*lhs as usize] {
                ir::Expr::Binary {
                    op: ir::BinOp::BitAnd,
                    lhs: l2,
                    rhs: r2,
                } => {
                    assert!(matches!(
                        s.exprs[*l2 as usize],
                        ir::Expr::Signal { net: 0, word: None }
                    ));
                    assert!(matches!(
                        s.exprs[*r2 as usize],
                        ir::Expr::Signal { net: 1, word: None }
                    ));
                }
                other => panic!("expected BitAnd, got {other:?}"),
            }
            // rhs = Const 8'hF0
            match &s.exprs[*rhs as usize] {
                ir::Expr::Const { val } => {
                    let cv = &s.consts[*val as usize];
                    assert_eq!(cv.width, 8);
                    assert_eq!(cv.bits.val[0], 0xF0);
                    assert_eq!(cv.bits.unk[0], 0x00);
                }
                other => panic!("expected Const, got {other:?}"),
            }
        }
        other => panic!("expected BitOr root, got {other:?}"),
    }
}

// ───────────────────────── 2. post-order is fixed ─────────────────────────
#[test]
fn t2_postorder_indices_children_before_parent() {
    // y = a + b  → arena: [Signal a, Signal b, Binary] (root index 2).
    let unit = module(
        "m",
        vec![
            wire_vec(0, 0, &["a", "b", "y"]),
            cont_assign(
                lv_id("y"),
                binop(ast::BinOp::Add, id_expr("a"), id_expr("b")),
            ),
        ],
    );
    let s = elab_ok(&unit);
    assert_eq!(s.exprs.len(), 3);
    assert!(matches!(s.exprs[0], ir::Expr::Signal { net: 0, .. }));
    assert!(matches!(s.exprs[1], ir::Expr::Signal { net: 1, .. }));
    let root = s.cont_assigns[0].rhs;
    assert_eq!(root, 2);
    assert!(matches!(
        s.exprs[2],
        ir::Expr::Binary {
            op: ir::BinOp::Add,
            lhs: 0,
            rhs: 1
        }
    ));
}

// ───────────────────────── 3. reg default init = all-X ─────────────────────────
#[test]
fn t3_reg_default_init_is_x_wire_is_z() {
    let unit = module(
        "m",
        vec![
            netvar(ast::NetVarKind::Reg, Some((3, 0)), false, &["r"]),
            wire_vec(3, 0, &["w"]),
        ],
    );
    let s = elab_ok(&unit);
    // reg r: all-X → val 0, unk 0xF (4 bits)
    let r = &s.nets[0];
    assert_eq!(r.kind, ir::NetKind::Reg);
    assert_eq!(r.init.val[0], 0x0);
    assert_eq!(r.init.unk[0], 0xF);
    // wire w: all-Z → val 0xF, unk 0xF
    let w = &s.nets[1];
    assert_eq!(w.init.val[0], 0xF);
    assert_eq!(w.init.unk[0], 0xF);
}

// ───────────────────────── 4. integer is fixed 32-bit signed ─────────────────────────
#[test]
fn t4_integer_is_32bit_signed() {
    let unit = module(
        "m",
        vec![netvar(ast::NetVarKind::Integer, None, false, &["i"])],
    );
    let s = elab_ok(&unit);
    let i = &s.nets[0];
    assert_eq!(i.kind, ir::NetKind::Integer);
    assert_eq!(i.width, 32);
    assert_eq!(i.msb, 31);
    assert_eq!(i.lsb, 0);
    assert!(i.signed);
}

// ───────────────────────── 5. const dedup ─────────────────────────
#[test]
fn t5_const_dedup() {
    // y = a & 8'hFF | 8'hFF  → the two 8'hFF literals share ONE const slot.
    let unit = module(
        "m",
        vec![
            wire_vec(7, 0, &["a", "y"]),
            cont_assign(
                lv_id("y"),
                binop(
                    ast::BinOp::BitOr,
                    binop(
                        ast::BinOp::BitAnd,
                        id_expr("a"),
                        lit("8'hFF", ast::IntLitKind::Sized),
                    ),
                    lit("8'hFF", ast::IntLitKind::Sized),
                ),
            ),
        ],
    );
    let s = elab_ok(&unit);
    // exactly one ConstVal in the pool (8'hFF), even though two Const exprs.
    assert_eq!(s.consts.len(), 1);
    assert_eq!(s.consts[0].bits.val[0], 0xFF);
    let n_const_exprs = s
        .exprs
        .iter()
        .filter(|e| matches!(e, ir::Expr::Const { .. }))
        .count();
    assert_eq!(n_const_exprs, 2);
}

// ───────────────────────── 6. part-select RHS ─────────────────────────
#[test]
fn t6_part_select_rhs() {
    // y = a[5:2]
    let unit = module(
        "m",
        vec![
            wire_vec(7, 0, &["a"]),
            wire_vec(3, 0, &["y"]),
            cont_assign(
                lv_id("y"),
                ex(ast::ExprKind::PartSelect {
                    base: Box::new(id_expr("a")),
                    msb: Box::new(dec("5")),
                    lsb: Box::new(dec("2")),
                }),
            ),
        ],
    );
    let s = elab_ok(&unit);
    let root = &s.exprs[s.cont_assigns[0].rhs as usize];
    match root {
        ir::Expr::Select {
            base,
            offset,
            width,
            kind: ir::SelKind::PartConst,
        } => {
            // base is Signal a (net 0)
            assert!(matches!(
                s.exprs[*base as usize],
                ir::Expr::Signal { net: 0, .. }
            ));
            // offset is Const 2
            assert!(matches!(s.exprs[*offset as usize], ir::Expr::Const { .. }));
            // width is a (msb - lsb) + 1 Binary(Add) tree
            assert!(matches!(
                s.exprs[*width as usize],
                ir::Expr::Binary {
                    op: ir::BinOp::Add,
                    ..
                }
            ));
        }
        other => panic!("expected PartConst Select, got {other:?}"),
    }
}

// ───────────────────────── 7. concat LHS contassign ─────────────────────────
#[test]
fn t7_concat_lhs() {
    // {cout, sum} = a  → two LvalChunks (cout MSB-first, then sum).
    let unit = module(
        "m",
        vec![
            wire_vec(0, 0, &["cout"]),
            wire_vec(7, 0, &["sum", "a"]),
            cont_assign(
                ast::Lvalue::Concat {
                    parts: vec![lv_id("cout"), lv_id("sum")],
                    span: SP,
                },
                id_expr("a"),
            ),
        ],
    );
    let s = elab_ok(&unit);
    let lhs = &s.cont_assigns[0].lhs;
    assert_eq!(lhs.chunks.len(), 2);
    assert_eq!(lhs.chunks[0].net, 0); // cout
    assert_eq!(lhs.chunks[1].net, 1); // sum
                                      // both are whole-net chunks (offset/width None).
    assert!(lhs.chunks[0].offset.is_none());
    assert!(lhs.chunks[1].offset.is_none());
}

// ───────────────────────── 8. concat RHS + replicate ─────────────────────────
#[test]
fn t8_concat_and_replicate_rhs() {
    // y = {2{a}, b}  → Concat[ Replicate{2,Concat[a]}, b ]
    let unit = module(
        "m",
        vec![
            wire_vec(0, 0, &["a", "b"]),
            wire_vec(2, 0, &["y"]),
            cont_assign(
                lv_id("y"),
                ex(ast::ExprKind::Concat {
                    parts: vec![
                        ex(ast::ExprKind::Replicate {
                            count: Box::new(dec("2")),
                            value: vec![id_expr("a")],
                        }),
                        id_expr("b"),
                    ],
                }),
            ),
        ],
    );
    let s = elab_ok(&unit);
    let root = &s.exprs[s.cont_assigns[0].rhs as usize];
    match root {
        ir::Expr::Concat { parts } => {
            assert_eq!(parts.len(), 2);
            // part 0 is a Replicate whose value is a 1-part Concat
            match &s.exprs[parts[0] as usize] {
                ir::Expr::Replicate { count, value } => {
                    assert!(matches!(s.exprs[*count as usize], ir::Expr::Const { .. }));
                    match &s.exprs[*value as usize] {
                        ir::Expr::Concat { parts: rp } => {
                            assert_eq!(rp.len(), 1);
                            assert!(matches!(
                                s.exprs[rp[0] as usize],
                                ir::Expr::Signal { net: 0, .. }
                            ));
                        }
                        other => panic!("replicate value not Concat: {other:?}"),
                    }
                }
                other => panic!("part0 not Replicate: {other:?}"),
            }
            // part 1 is Signal b
            assert!(matches!(
                s.exprs[parts[1] as usize],
                ir::Expr::Signal { net: 1, .. }
            ));
        }
        other => panic!("expected Concat root, got {other:?}"),
    }
}

// ───────────────────────── 9. unresolved name → error + None ─────────────────────────
#[test]
fn t9_unresolved_name_errors() {
    // y = z  (z undeclared)
    let unit = module(
        "m",
        vec![
            wire_vec(0, 0, &["y"]),
            cont_assign(lv_id("y"), id_expr("z")),
        ],
    );
    let sink = CollectSink::default();
    let out = elaborate(&unit, &sink);
    assert!(out.is_none(), "should fail on unresolved name");
    // exactly one diagnostic, code ElabUnresolvedName.
    let events = sink.events.borrow();
    let diags: Vec<_> = events
        .iter()
        .filter_map(|e| match e {
            LogEvent::Diagnostic(d) => Some(d),
            _ => None,
        })
        .collect();
    assert_eq!(diags.len(), 1);
    assert_eq!(diags[0].code, MsgCode::ElabUnresolvedName);
}

// ───────────────────────── 10. procedural block → unsupported ─────────────────────────
#[test]
fn t10_procedural_block_unsupported() {
    let proc = ast::ModuleItem::Proc(ast::ProceduralBlock {
        kind: ast::ProcKind::Always,
        sensitivity: None,
        body: Box::new(ast::Stmt::Null(SP)),
        span: SP,
    });
    let unit = module("m", vec![wire_vec(0, 0, &["a"]), proc]);
    let sink = CollectSink::default();
    let out = elaborate(&unit, &sink);
    assert!(out.is_none());
    let events = sink.events.borrow();
    let codes: Vec<_> = events
        .iter()
        .filter_map(|e| match e {
            LogEvent::Diagnostic(d) => Some(d.code),
            _ => None,
        })
        .collect();
    assert!(codes.contains(&MsgCode::ElabUnsupported));
}

// ───────────────────────── 11. literal-parse planes ─────────────────────────
#[test]
fn t11_literal_4state_planes() {
    // 4'b10xz : bit0=z=(1,1) bit1=x=(0,1) bit2=0=(0,0) bit3=1=(1,0)
    //   val: b0=1,b1=0,b2=0,b3=1 → 0b1001 = 0x9
    //   unk: b0=1,b1=1,b2=0,b3=0 → 0b0011 = 0x3
    let cv = parse_int_literal("4'b10xz", ast::IntLitKind::Sized).unwrap();
    assert_eq!(cv.width, 4);
    assert!(!cv.signed);
    assert_eq!(cv.bits.val[0], 0x9);
    assert_eq!(cv.bits.unk[0], 0x3);

    // 8'hF0 : clean 2-state
    let cv = parse_int_literal("8'hF0", ast::IntLitKind::Sized).unwrap();
    assert_eq!(cv.bits.val[0], 0xF0);
    assert_eq!(cv.bits.unk[0], 0x00);

    // 4'sd5 : signed decimal, width 4
    let cv = parse_int_literal("4'sd5", ast::IntLitKind::Sized).unwrap();
    assert!(cv.signed);
    assert_eq!(cv.bits.val[0], 0x5);
    assert_eq!(cv.bits.unk[0], 0x0);

    // 4'bx : x-extends to 4 bits → val 0, unk 0xF
    let cv = parse_int_literal("4'bx", ast::IntLitKind::Sized).unwrap();
    assert_eq!(cv.bits.val[0], 0x0);
    assert_eq!(cv.bits.unk[0], 0xF);

    // 8'hzz : all-Z → val 0xFF, unk 0xFF
    let cv = parse_int_literal("8'hzz", ast::IntLitKind::Sized).unwrap();
    assert_eq!(cv.bits.val[0], 0xFF);
    assert_eq!(cv.bits.unk[0], 0xFF);

    // 4'bz0 : §3.5.1 z-extension. b0=0=(0,0), b1=z=(1,1), extend b2,b3 = z=(1,1)
    //   val: b0=0,b1=1,b2=1,b3=1 → 0xE ; unk: 0,1,1,1 → 0xE
    let cv = parse_int_literal("4'bz0", ast::IntLitKind::Sized).unwrap();
    assert_eq!(cv.bits.val[0], 0xE);
    assert_eq!(cv.bits.unk[0], 0xE);

    // plain decimal 42 → 32-bit signed, val 0x2A
    let cv = parse_int_literal("42", ast::IntLitKind::Decimal).unwrap();
    assert_eq!(cv.width, 32);
    assert!(cv.signed);
    assert_eq!(cv.bits.val[0], 0x2A);
    assert_eq!(cv.bits.unk[0], 0x0);

    // unsized 'hFF → 32-bit unsigned, zero-extended
    let cv = parse_int_literal("'hFF", ast::IntLitKind::UnsizedBased).unwrap();
    assert_eq!(cv.width, 32);
    assert!(!cv.signed);
    assert_eq!(cv.bits.val[0], 0xFF);

    // 32'hDEAD_BEEF → underscore stripped
    let cv = parse_int_literal("32'hDEAD_BEEF", ast::IntLitKind::Sized).unwrap();
    assert_eq!(cv.bits.val[0], 0xDEAD_BEEF);
    assert_eq!(cv.bits.unk[0], 0x0);

    // SV single-char fill 'x → all-X over 32 bits
    let cv = parse_int_literal("'x", ast::IntLitKind::UnsizedBased).unwrap();
    assert_eq!(cv.bits.val[0], 0x0);
    assert_eq!(cv.bits.unk[0], 0xFFFF_FFFF);
}

// ───────────────────────── 12. determinism: identical input → identical IR ─────────────────────────
#[test]
fn t12_determinism_repeatable() {
    let build = || {
        module(
            "m",
            vec![
                wire_vec(7, 0, &["a", "b", "y"]),
                cont_assign(
                    lv_id("y"),
                    binop(
                        ast::BinOp::BitOr,
                        binop(ast::BinOp::BitAnd, id_expr("a"), id_expr("b")),
                        lit("8'hF0", ast::IntLitKind::Sized),
                    ),
                ),
            ],
        )
    };
    let s1 = elab_ok(&build());
    let s2 = elab_ok(&build());
    // structural equality (sim-ir derives PartialEq) — same arena, same order.
    assert_eq!(s1, s2);
}

// ───────────────────────── 13. bit-select LHS ─────────────────────────
#[test]
fn t13_bit_select_lhs() {
    // a[3] = b
    let unit = module(
        "m",
        vec![
            wire_vec(7, 0, &["a"]),
            wire_vec(0, 0, &["b"]),
            cont_assign(
                ast::Lvalue::BitSelect {
                    base: Box::new(lv_id("a")),
                    index: Box::new(dec("3")),
                    span: SP,
                },
                id_expr("b"),
            ),
        ],
    );
    let s = elab_ok(&unit);
    let chunk = &s.cont_assigns[0].lhs.chunks[0];
    assert_eq!(chunk.net, 0); // a
    assert_eq!(chunk.kind, ir::SelKind::Bit);
    assert!(chunk.word.is_none()); // a is scalar array (len 1) → bit select
    assert!(chunk.offset.is_some());
    assert!(chunk.width.is_some());
}

// ── array (memory) builder: `reg [bw:0] name [0:depth-1];` ──
fn reg_mem(bit_msb: u32, depth_msb: u32, name: &str) -> ast::ModuleItem {
    ast::ModuleItem::NetVar(ast::NetVarDecl {
        kind: ast::NetVarKind::Reg,
        signed: false,
        range: Some(ast::Range {
            msb: dec(&bit_msb.to_string()),
            lsb: dec("0"),
            span: SP,
        }),
        names: vec![ast::DeclName {
            name: ident(name),
            unpacked: vec![ast::Dim::Range(ast::Range {
                msb: dec(&depth_msb.to_string()),
                lsb: dec("0"),
                span: SP,
            })],
            init: None,
            span: SP,
        }],
        span: SP,
    })
}

// ───────────────────────── 14. RHS memory word-select → Signal{word} ─────────────────────────
#[test]
fn t14_rhs_memory_word_select_is_signal_word() {
    // reg [7:0] mem [0:3]; wire [7:0] y; assign y = mem[2];
    // mem[2] on the RHS MUST lower to Signal{net, word:Some(2)} — symmetric with
    // the LHS — NOT Select{kind:Bit} (which would read bit 2 of the whole memory).
    let unit = module(
        "m",
        vec![
            reg_mem(7, 3, "mem"),
            wire_vec(7, 0, &["y"]),
            cont_assign(
                lv_id("y"),
                ex(ast::ExprKind::BitSelect {
                    base: Box::new(id_expr("mem")),
                    index: Box::new(dec("2")),
                }),
            ),
        ],
    );
    let s = elab_ok(&unit);
    // mem is net 0 with array_len 4.
    assert_eq!(s.nets[0].array_len, 4);
    let root = &s.exprs[s.cont_assigns[0].rhs as usize];
    assert!(
        matches!(
            root,
            ir::Expr::Signal {
                net: 0,
                word: Some(2)
            }
        ),
        "RHS mem[2] must be Signal{{net:0, word:Some(2)}}, got {root:?}"
    );
    // and there is NO Select{kind:Bit} in the arena for this read.
    assert!(
        !s.exprs.iter().any(|e| matches!(
            e,
            ir::Expr::Select {
                kind: ir::SelKind::Bit,
                ..
            }
        )),
        "memory word read must not emit a bit Select"
    );

    // LHS symmetry: `mem[1] = y` → LvalChunk{word:Some(1)}.
    let unit2 = module(
        "m",
        vec![
            reg_mem(7, 3, "mem"),
            wire_vec(7, 0, &["y"]),
            cont_assign(
                ast::Lvalue::BitSelect {
                    base: Box::new(lv_id("mem")),
                    index: Box::new(dec("1")),
                    span: SP,
                },
                id_expr("y"),
            ),
        ],
    );
    let s2 = elab_ok(&unit2);
    let chunk = &s2.cont_assigns[0].lhs.chunks[0];
    assert_eq!(chunk.net, 0);
    assert_eq!(chunk.word, Some(1));
    assert!(chunk.offset.is_none() && chunk.width.is_none());
}

// ───────────────────────── 15. duplicate net name → error ─────────────────────────
#[test]
fn t15_duplicate_net_name_errors() {
    // wire a; wire [7:0] a;  → second `a` is a duplicate decl.
    let unit = module("m", vec![wire_vec(0, 0, &["a"]), wire_vec(7, 0, &["a"])]);
    let sink = CollectSink::default();
    let out = elaborate(&unit, &sink);
    assert!(out.is_none(), "duplicate decl must fail elaboration");
    // exactly one net survives (the orphan is NOT pushed → net_count stays 1).
    let events = sink.events.borrow();
    let diags: Vec<_> = events
        .iter()
        .filter_map(|e| match e {
            LogEvent::Diagnostic(d) => Some(d),
            _ => None,
        })
        .collect();
    assert_eq!(diags.len(), 1);
    assert_eq!(diags[0].code, MsgCode::ElabUnsupported);
}

// ───────────────────────── 16. whole-net multidriver → error ─────────────────────────
#[test]
fn t16_whole_net_multidriver_errors() {
    // wire a,b,y; assign y = a; assign y = b;  → y double-driven.
    let unit = module(
        "m",
        vec![
            wire_vec(0, 0, &["a", "b", "y"]),
            cont_assign(lv_id("y"), id_expr("a")),
            cont_assign(lv_id("y"), id_expr("b")),
        ],
    );
    let sink = CollectSink::default();
    let out = elaborate(&unit, &sink);
    assert!(out.is_none(), "multidriver must fail elaboration");
    let events = sink.events.borrow();
    let codes: Vec<_> = events
        .iter()
        .filter_map(|e| match e {
            LogEvent::Diagnostic(d) => Some(d.code),
            _ => None,
        })
        .collect();
    assert!(codes.contains(&MsgCode::ElabMultidriver));
}

// ───────────────────────── 17. hostile declared width → no panic, ElabUnsupported ─────────────────────────
#[test]
fn t17_huge_width_no_panic() {
    // wire [4294967295:0] big;  → width = u32::MAX + 1 would overflow/OOM.
    // Must be rejected with ElabUnsupported, NOT panic.
    let unit = module(
        "m",
        vec![netvar(
            ast::NetVarKind::Wire,
            Some((u32::MAX, 0)),
            false,
            &["big"],
        )],
    );
    let sink = CollectSink::default();
    let out = elaborate(&unit, &sink); // must return (not panic)
    assert!(out.is_none());
    let events = sink.events.borrow();
    let codes: Vec<_> = events
        .iter()
        .filter_map(|e| match e {
            LogEvent::Diagnostic(d) => Some(d.code),
            _ => None,
        })
        .collect();
    assert!(codes.contains(&MsgCode::ElabUnsupported));
}

// ───────────────────────── 18. descending-range part-select guard ─────────────────────────
#[test]
fn t18_ascending_part_select_unsupported() {
    // wire [7:0] a; wire [3:0] y; assign y = a[2:5];  (msb<lsb → ascending)
    let unit = module(
        "m",
        vec![
            wire_vec(7, 0, &["a"]),
            wire_vec(3, 0, &["y"]),
            cont_assign(
                lv_id("y"),
                ex(ast::ExprKind::PartSelect {
                    base: Box::new(id_expr("a")),
                    msb: Box::new(dec("2")), // msb < lsb
                    lsb: Box::new(dec("5")),
                }),
            ),
        ],
    );
    let sink = CollectSink::default();
    let out = elaborate(&unit, &sink);
    assert!(out.is_none());
    let events = sink.events.borrow();
    let codes: Vec<_> = events
        .iter()
        .filter_map(|e| match e {
            LogEvent::Diagnostic(d) => Some(d.code),
            _ => None,
        })
        .collect();
    assert!(codes.contains(&MsgCode::ElabUnsupported));
}
