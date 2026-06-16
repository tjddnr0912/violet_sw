//! SVA action-block sampled values + sequence local-variable rejection (Phase-3
//! slice A2). The `pass` / `else fail` action statements of a concurrent assertion
//! may reference the sampled-value functions `$past`/`$rose`/`$fell`/`$stable`; these
//! are rewritten to the SAME synthesized prev-registers the property body uses, so
//! e.g. `… else $error("d was %0d", $past(d));` prints the prior-clock value — a pure
//! AST rewrite (IR-0, sim-ir frozen, format_version 8). Sequence/property LOCAL
//! VARIABLES (`int x; (a, x=d) |=> (b==x)`) need per-attempt thread storage that is
//! not synthesizable to a single register, so they are LOUD with a targeted message.
//!
//! iverilog 13.0 rejects concurrent assertions entirely (NULL oracle) → hand-IEEE.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> (String, String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_svaab_{}_{n}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    let f = d.join("t.sv");
    std::fs::write(&f, src).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_vita"))
        .arg(f.to_str().unwrap())
        .current_dir(&d)
        .output()
        .expect("run vita");
    (
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
        out.status.code(),
    )
}

// ── sampled value in the fail (else) action ────────────────────────────────

#[test]
fn fail_action_past_resolves_to_prev_reg() {
    // `… else $error("PASTD=%0d", $past(d));` — $past(d) must resolve to the shared
    // prev-register (NOT the generic "unsupported system function" E3009). On a
    // violation the $error must run and print the prior-clock d.
    let (out, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         reg [7:0] d=8'd5;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) a |=> b) else $error(\"PASTD=%0d\", $past(d));\n\
         initial begin #8 a=1; #10 a=0; b=0; #20 $finish; end\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(1),
        "the |=> violation must fire the action. stderr:\n{err}\nout:\n{out}"
    );
    let all = format!("{err}{out}");
    assert!(
        all.contains("PASTD="),
        "the action's $error (with $past(d)) must run, not E3009:\n{err}\n{out}"
    );
    assert!(
        !all.contains("unsupported system function"),
        "$past in the action must not hit the generic unsupported-sysfunc error:\n{err}"
    );
}

#[test]
fn pass_action_rose_resolves_to_prev_reg() {
    // A pass action with $rose(a): `… |-> b $display("ROSEA=%b", $rose(a));`. On a
    // non-vacuous success the pass action runs; $rose(a) shares the antecedent's prev_a.
    let (out, err, code) = run("module top;\n\
         reg clk=0, a=0, b=1;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) a |-> b) $display(\"ROSEA=%b\", $rose(a)); \n\
         initial begin #8 a=1; #20 $finish; end\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(0),
        "a |-> b with b=1 holds → clean; the pass action just prints. stderr:\n{err}\nout:\n{out}"
    );
    assert!(
        out.contains("ROSEA="),
        "the pass action's $display (with $rose(a)) must run:\n{out}"
    );
}

#[test]
fn action_past_dedups_onto_body_prev_reg() {
    // $past(a) appears in BOTH the antecedent and the action: they must share ONE
    // prev_a (no double sampling). Behaviorally this just needs to elaborate and run.
    let (out, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) $past(a) |=> b) else $error(\"PA=%b\", $past(a));\n\
         initial begin #8 a=1; #10 a=0; b=0; #20 $finish; end\n\
         endmodule\n");
    let all = format!("{err}{out}");
    assert!(
        !all.contains("unsupported system function"),
        "$past(a) in antecedent + action must both resolve:\n{err}\n{out}"
    );
    // It may or may not fire depending on the trace, but never E3009.
    assert!(
        code == Some(0) || code == Some(1),
        "expected a clean elaborate (exit 0/1), got {code:?}:\n{err}"
    );
}

#[test]
fn plain_action_block_without_sampled_is_unaffected() {
    // BYTE-IDENTITY guard: an action block with NO sampled fn must keep working
    // exactly as before A2 (the rewrite is a structural no-op that allocates no nets).
    let (out, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) a |-> b) else $error(\"plain fail\");\n\
         initial begin #8 a=1; b=0; #20 $finish; end\n\
         endmodule\n");
    assert_eq!(code, Some(1), "plain action still fires. {err}{out}");
    assert!(
        format!("{err}{out}").contains("plain fail"),
        "the plain $error must run:\n{err}\n{out}"
    );
}

// ── sequence/property local variables → LOUD (clear message) ───────────────

#[test]
fn typed_local_variable_decl_is_loud_with_clear_message() {
    // `property p; int x; @(posedge clk) …` — a typed local-var decl at the property
    // body start must produce a TARGETED 'local variables unsupported' message, not
    // the generic "'@(...)' clocking event" cascade.
    let (_o, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         reg [7:0] d=0;\n\
         always #5 clk=~clk;\n\
         property p; int x; @(posedge clk) a |=> b; endproperty\n\
         initial assert property(p);\n\
         initial #20 $finish;\n\
         endmodule\n");
    assert_eq!(code, Some(1), "a local-var decl must be loud. {err}");
    assert!(
        err.to_lowercase().contains("local variable"),
        "the message must name local variables as unsupported:\n{err}"
    );
}

#[test]
fn keyword_typed_local_variable_decl_is_loud() {
    // Same, but a KEYWORD type (`logic`) — exercises the net_var_kind detection path.
    let (_o, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         always #5 clk=~clk;\n\
         property p; logic x; @(posedge clk) a |=> b; endproperty\n\
         initial assert property(p);\n\
         initial #20 $finish;\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(1),
        "a keyword-typed local-var decl must be loud. {err}"
    );
    assert!(
        err.to_lowercase().contains("local variable"),
        "the message must name local variables as unsupported:\n{err}"
    );
}

#[test]
fn multiple_typed_local_var_decls_recover_cleanly() {
    // REVIEW (recovery lens, 2026-06-16): the skip-to-@ must clear MULTIPLE local-var
    // decls and land on the real `@(clk)` — not stop on the first decl's `;` and
    // cascade. A clean recovery means the property body parses (no leftover-decl
    // "expected `endproperty`" cascade), with only the one targeted diagnostic.
    let (_o, err, code) = run("module top;\n\
         reg clk=0, a=1, b=1;\n\
         always #5 clk=~clk;\n\
         property p; int x; int y; @(posedge clk) a |-> b; endproperty\n\
         initial assert property(p);\n\
         initial begin #20 $finish; end\n\
         endmodule\n");
    assert_eq!(code, Some(1), "local-var decls must be loud. {err}");
    assert!(
        err.to_lowercase().contains("local variable"),
        "the targeted message must appear:\n{err}"
    );
    assert!(
        !err.contains("endproperty") && !err.contains("clocking event"),
        "recovery must clear BOTH decls and reach @(clk) — no cascade:\n{err}"
    );
}

#[test]
fn match_item_assignment_is_loud_with_clear_message() {
    // Inline `(a, x=d)` match-item local-variable assignment in a sequence primary
    // must produce the local-var message, not the generic `')'` cascade.
    let (_o, err, code) = run("module top;\n\
         reg clk=0, a=0, b=0;\n\
         reg [7:0] d=0, x=0;\n\
         always #5 clk=~clk;\n\
         initial assert property(@(posedge clk) (a, x=d) |=> b);\n\
         initial #20 $finish;\n\
         endmodule\n");
    assert_eq!(
        code,
        Some(1),
        "a match-item local-var assignment must be loud. {err}"
    );
    assert!(
        err.to_lowercase().contains("local variable"),
        "the message must name local variables as unsupported:\n{err}"
    );
}
