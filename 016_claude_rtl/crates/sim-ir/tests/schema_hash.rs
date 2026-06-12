//! Golden #1: pinned SimIr root hash (M3 backbone, 2-platform determinism contract).
//! Golden #2: canonical-string diff. Plus a Process sub-pin (runtime-cluster regression).
use vita_schema::{schema_hash, SchemaShape, ShapeRegistry};

/// blake3 of the full SimIr-closure canonical string. Locked at
/// format_version 7 (2026-06-12: +BinOp CasezEq/CasexEq, +SysFuncId
/// Random/Urandom(Range)/CountOnes/OneHot(0)/IsUnknown/Stime/Fopen/
/// Sformatf/(Test|Value)Plusargs/Str{Len,GetC,Substr,ToUpper,ToLower,Cmp},
/// +SysTaskId Fclose/Fdisplay/Fwrite/Sformat/Readmem{B,H}/StrPutC,
/// +NetKind String — the Phase-2 system-task/string batch; the runtime
/// Process cluster is untouched, so its sub-pin holds).
const EXPECTED_SIMIR_HASH: &str =
    "fbbb9362b066ed118486cb77c4e3691eabadef7ed5b22623bed9c299891b970c";
/// Sub-pin: the runtime Process cluster (cheap regression signal; NOT the gate).
const EXPECTED_PROCESS_HASH: &str =
    "927e19344413644037635cfcebc50c76c08a413356b9463b5819f7979f1f486b";

const GOLDEN_CANON: &str = include_str!("../../testdata/sim_ir_canonical.txt");

#[test]
fn schema_hash_is_pinned() {
    assert_eq!(
        hex::encode(schema_hash::<sim_ir::SimIr>()),
        EXPECTED_SIMIR_HASH,
        "SCHEMA_HASH changed — a frozen sim-ir shape/serde-attr moved.\n\
         If intentional: all .velab invalid -> bump format_version + update both goldens."
    );
}

#[test]
fn process_subpin() {
    assert_eq!(
        hex::encode(schema_hash::<sim_ir::Process>()),
        EXPECTED_PROCESS_HASH
    );
}

#[test]
fn canonical_string_golden() {
    let mut reg = ShapeRegistry::new();
    sim_ir::SimIr::register(&mut reg);
    // Sanctioned regen switch for an INTENTIONAL format_version bump:
    //   REGEN_GOLDEN=1 cargo test -p sim-ir --test schema_hash -- --nocapture
    // rewrites the canonical golden and prints the two hashes to paste above.
    if std::env::var("REGEN_GOLDEN").is_ok() {
        std::fs::write("../testdata/sim_ir_canonical.txt", reg.canonical_string())
            .expect("write canonical golden");
        println!(
            "REGEN SimIr   = {}",
            hex::encode(schema_hash::<sim_ir::SimIr>())
        );
        println!(
            "REGEN Process = {}",
            hex::encode(schema_hash::<sim_ir::Process>())
        );
        return;
    }
    assert_eq!(reg.canonical_string(), GOLDEN_CANON);
}
