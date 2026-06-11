//! Operational infrastructure (ROADMAP §2-7): `--dump-filelist`, filelist
//! canonical-source dedup (the E8003 family's silent-dedup arm), and the
//! RULE-V composite_input_hash recording at vcmp/velab.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn tdir() -> std::path::PathBuf {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_ops_{}_{n}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    d
}

fn vita(args: &[&str]) -> (String, String, bool) {
    let out = Command::new(env!("CARGO_BIN_EXE_vita"))
        .args(args)
        .output()
        .expect("failed to run vita");
    (
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
        out.status.success(),
    )
}

#[test]
fn dump_filelist_prints_effective_inputs_and_exits() {
    let d = tdir();
    let a = d.join("a.sv");
    let b = d.join("b.sv");
    std::fs::write(&a, "module a; endmodule\n").unwrap();
    std::fs::write(&b, "module b; endmodule\n").unwrap();
    let f = d.join("build.f");
    std::fs::write(
        &f,
        format!(
            "-D W=8\n+incdir+{}\n{}\n{}\n",
            d.display(),
            a.display(),
            b.display()
        ),
    )
    .unwrap();
    let (out, err, ok) = vita(&["-f", f.to_str().unwrap(), "--dump-filelist"]);
    assert!(ok, "dump must succeed; stderr:\n{err}");
    let expect = format!(
        "source {}\nsource {}\ndefine W=8\nincdir {}\n",
        a.display(),
        b.display(),
        d.display()
    );
    assert_eq!(out, expect, "deterministic effective-input dump");
}

#[test]
fn filelist_duplicate_source_dedups_to_first() {
    // The same canonical file twice in one expansion would double-compile the
    // module (a confusing downstream E-DUP-UNIT) — the expansion dedups it
    // (doc-15 E8003 silent-dedup arm; the CONFLICT arm waits on sticky ctx).
    let d = tdir();
    let a = d.join("dup.sv");
    std::fs::write(
        &a,
        "module t; initial begin $display(\"once\"); $finish; end endmodule\n",
    )
    .unwrap();
    let f = d.join("dup.f");
    std::fs::write(&f, format!("{}\n{}\n", a.display(), a.display())).unwrap();
    let (out, err, ok) = vita(&["-f", f.to_str().unwrap()]);
    assert!(ok, "dedup'd run must succeed; stderr:\n{err}");
    assert!(
        out.lines().filter(|l| *l == "once").count() == 1,
        "module must run exactly once; got:\n{out}"
    );
    assert!(
        !err.contains("E-DUP-UNIT") && !err.contains("declared"),
        "no duplicate-unit error after dedup; got:\n{err}"
    );
}

#[test]
fn composite_input_hash_is_recorded_in_vu_and_velab() {
    let d = tdir();
    let src = d.join("c.sv");
    std::fs::write(
        &src,
        "module t; initial begin $display(\"hi\"); $finish; end endmodule\n",
    )
    .unwrap();
    let vu = d.join("c.vu");
    let velab = d.join("c.velab");
    let (_, err, ok) = vita(&["vcmp", src.to_str().unwrap(), "-o", vu.to_str().unwrap()]);
    assert!(ok, "vcmp: {err}");
    let (_, err, ok) = vita(&["velab", vu.to_str().unwrap(), "-o", velab.to_str().unwrap()]);
    assert!(ok, "velab: {err}");

    // .vu records a non-zero digest of its raw input surface.
    let vu_bytes = std::fs::read(&vu).unwrap();
    let (vu_header, _) = vita_artifact::read_vu(&vu_bytes).unwrap();
    assert_ne!(
        vu_header.composite_input_hash, [0u8; 32],
        ".vu composite must be recorded"
    );

    // .velab records EXACTLY the blake3 of the .vu bytes it consumed.
    let velab_bytes = std::fs::read(&velab).unwrap();
    let (ve_header, _) = vita_artifact::read_velab(&velab_bytes).unwrap();
    assert_eq!(
        ve_header.composite_input_hash,
        *blake3::hash(&vu_bytes).as_bytes(),
        ".velab composite = blake3(consumed .vu)"
    );
}
