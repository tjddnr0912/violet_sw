//! CI sync gate: the MsgCode enum and docs/preview/15 §0–9 body codes are 1:1.
//! Appendix A reserved codes are excluded (they are not yet enum variants).
use diag::MsgCode;

const DOC15: &str = include_str!("../../../docs/preview/15-error-code-reference.md");

/// Extract body mnemonics: lines `### VITA-... · `CODE` (sev)` before "## 부록 A".
fn doc_mnemonics() -> Vec<String> {
    let body = DOC15.split("## 부록 A").next().unwrap();
    let mut out = Vec::new();
    for line in body.lines() {
        let l = line.trim_start();
        if let Some(rest) = l.strip_prefix("### ") {
            // form: VITA-E0001 · `E-CLI-BAD-FLAG` (Error)
            if let Some(start) = rest.find('`') {
                if let Some(end) = rest[start + 1..].find('`') {
                    out.push(rest[start + 1..start + 1 + end].to_string());
                }
            }
        }
    }
    out
}

#[test]
fn msgcode_matches_doc15_body_one_to_one() {
    let mut doc: Vec<String> = doc_mnemonics();
    let mut enum_codes: Vec<String> =
        MsgCode::ALL.iter().map(|c| c.mnemonic().to_string()).collect();
    doc.sort();
    doc.dedup();
    enum_codes.sort();

    assert_eq!(enum_codes.len(), 36, "MsgCode must have exactly 36 body variants");
    assert_eq!(
        enum_codes, doc,
        "MsgCode enum and docs/preview/15 §0–9 diverged.\n\
         Adding a code requires a doc entry (and vice-versa)."
    );
}

#[test]
fn mnemonics_and_numbers_are_unique() {
    let mut m: Vec<&str> = MsgCode::ALL.iter().map(|c| c.mnemonic()).collect();
    let mut n: Vec<&str> = MsgCode::ALL.iter().map(|c| c.code_num()).collect();
    let (lm, ln) = (m.len(), n.len());
    m.sort(); m.dedup();
    n.sort(); n.dedup();
    assert_eq!(m.len(), lm, "duplicate mnemonic");
    assert_eq!(n.len(), ln, "duplicate VITA-#### number");
}
