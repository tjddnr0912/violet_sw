//! SYS-INTRO array-query / dimension introspection const-folds (Medium bundle
//! rank 2): $size/$left/$right/$low/$high/$increment/$dimensions/
//! $unpacked_dimensions/$isunbounded. Pure IR-0 elaborate const-folds (the
//! argument is a TYPE/net reference, not evaluated). Previously these system
//! FUNCTIONS were E3009-LOUD, which killed the WHOLE design — so folding them is
//! both a feature and a robustness fix.
//!
//! Oracle: iverilog 13.0 (every value verified live). $typename is DEFERRED
//! (stays loud); iverilog rejects $isunbounded/$typename so those are hand-IEEE.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(body: &str) -> (String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_si_{}_{n}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    let f = d.join("t.sv");
    std::fs::write(&f, body).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_vita"))
        .arg(f.to_str().unwrap())
        .current_dir(&d)
        .output()
        .expect("run vita");
    (
        String::from_utf8_lossy(&out.stdout).into_owned(),
        out.status.code(),
    )
}

fn disp(decls: &str, fmt: &str, args: &str) -> String {
    run(&format!(
        "module t;\n{decls}\ninitial $display(\"R {fmt}\", {args});\nendmodule\n"
    ))
    .0
}

#[test]
fn packed_vector_descending() {
    // reg [7:0] v: bits=8 size=8 left=7 right=0 low=0 high=7 incr=1 dims=1.
    let out = disp(
        "reg [7:0] v;",
        "%0d %0d %0d %0d %0d %0d %0d %0d",
        "$bits(v),$size(v),$left(v),$right(v),$low(v),$high(v),$increment(v),$dimensions(v)",
    );
    assert!(out.contains("R 8 8 7 0 0 7 1 1"), "{out}");
}

#[test]
fn packed_vector_ascending_increment_is_negative() {
    // reg [0:7] a: ascending => left=0 right=7 low=0 high=7 increment=-1.
    let out = disp(
        "reg [0:7] a;",
        "%0d %0d %0d %0d %0d %0d",
        "$size(a),$left(a),$right(a),$low(a),$high(a),$increment(a)",
    );
    assert!(out.contains("R 8 0 7 0 7 -1"), "{out}");
}

#[test]
fn unpacked_array_dimensions() {
    // reg [3:0] mem [0:7]: dim1 = unpacked [0:7], dim2 = packed [3:0].
    let out = disp(
        "reg [3:0] mem [0:7];",
        "%0d %0d %0d %0d %0d %0d",
        "$size(mem),$left(mem),$right(mem),$dimensions(mem),$unpacked_dimensions(mem),$size(mem,2)",
    );
    assert!(out.contains("R 8 0 7 2 1 4"), "{out}");
}

#[test]
fn multidim_array_dimension_order() {
    // reg [7:0] g [0:3][0:1]: dim1=[0:3]=4, dim2=[0:1]=2, dim3=packed[7:0]=8.
    let out = disp(
        "reg [7:0] g [0:3][0:1];",
        "%0d %0d %0d %0d %0d",
        "$dimensions(g),$unpacked_dimensions(g),$size(g,1),$size(g,2),$size(g,3)",
    );
    assert!(out.contains("R 3 2 4 2 8"), "{out}");
}

#[test]
fn scalar_has_zero_dimensions_and_x_query() {
    // A true scalar `reg s` has 0 dimensions; a dim query (e.g. $size) => X.
    let out = disp(
        "reg s;",
        "%0d %0d %0d %0d",
        "$dimensions(s),$bits(s),$size(s),$left(s)",
    );
    assert!(out.contains("R 0 1 x x"), "{out}");
}

#[test]
fn one_bit_vector_is_distinct_from_scalar() {
    // reg [0:0] z is a 1-DIMENSION vector (dims=1, size=1) — net metadata alone
    // cannot tell it from a scalar, but the decl-time descriptor can.
    let out = disp(
        "reg [0:0] z;",
        "%0d %0d %0d",
        "$dimensions(z),$size(z),$left(z)",
    );
    assert!(out.contains("R 1 1 0"), "{out}");
}

#[test]
fn isunbounded_folds_to_zero() {
    let out = disp("reg [7:0] v;", "%0d", "$isunbounded(v)");
    assert!(out.contains("R 0"), "{out}");
}

#[test]
fn size_out_of_range_dimension_is_x() {
    let out = disp("reg [3:0] mem [0:7];", "%0d", "$size(mem,3)");
    assert!(out.contains("R x"), "{out}");
}

#[test]
fn integer_has_implicit_32bit_dimension() {
    // integer carries an implicit [31:0] packed dim (adversarial-review regression
    // fix: was folding to 0-dim X). iverilog: $size=32 $left=31 $right=0 $dims=1.
    let out = disp(
        "integer ii;",
        "%0d %0d %0d %0d",
        "$size(ii),$left(ii),$right(ii),$dimensions(ii)",
    );
    assert!(out.contains("R 32 31 0 1"), "{out}");
}

#[test]
fn time_has_implicit_64bit_dimension() {
    let out = disp(
        "time tt;",
        "%0d %0d %0d",
        "$size(tt),$left(tt),$dimensions(tt)",
    );
    assert!(out.contains("R 64 63 1"), "{out}");
}

#[test]
fn integer_array_dimensions() {
    // integer mem [0:3]: dim1 = unpacked [0:3] (4), dim2 = implicit [31:0] (32).
    let out = disp(
        "integer mem [0:3];",
        "%0d %0d %0d",
        "$dimensions(mem),$size(mem,1),$size(mem,2)",
    );
    assert!(out.contains("R 2 4 32"), "{out}");
}

#[test]
fn real_is_dimensionless() {
    // real/realtime are genuinely 0-dimensional (NOT a 64-bit vector) — iverilog
    // parity: $dimensions=0 even though $bits=64. (Guards the integer/time fix
    // from over-reaching to real.)
    let out = disp("real rr;", "%0d %0d", "$dimensions(rr),$bits(rr)");
    assert!(out.contains("R 0 64"), "{out}");
}

#[test]
fn packed_multidim_port_dimensions() {
    // ANSI packed multi-dim port (adversarial-review regression fix: was folding
    // to a single 32-bit dim). input [3:0][7:0] mp => dim1=[3:0]=4, dim2=[7:0]=8.
    let out = run("module t(input [3:0][7:0] mp);\n\
         initial $display(\"R %0d %0d %0d %0d %0d\",\
         $dimensions(mp),$size(mp,1),$size(mp,2),$left(mp,1),$left(mp,2));\n\
         endmodule\n")
    .0;
    assert!(out.contains("R 2 4 8 3 7"), "{out}");
}

#[test]
fn typename_is_deferred_loud() {
    // $typename is deferred (string formatting, hand-IEEE) — stays a clean loud
    // E3009, not a silent wrong value.
    let (out, code) =
        run("module t; reg [7:0] v; initial $display(\"%s\", $typename(v)); endmodule\n");
    assert!(
        out.contains("VITA-E3009") || code == Some(1),
        "typename should be loud: {out} code={code:?}"
    );
}
