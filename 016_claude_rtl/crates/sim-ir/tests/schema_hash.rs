//! Golden #1: pinned SimIr root hash (M3 backbone, 2-platform determinism contract).
//! Golden #2: canonical-string diff. Plus a Process sub-pin (runtime-cluster regression).
use vita_schema::{schema_hash, SchemaShape, ShapeRegistry};

/// blake3 of the full SimIr-closure canonical string. Locked at
/// format_version 10 (2026-06-23: +1 SysTaskId variant `ClassRandomize` for
/// N7-REST `obj.randomize()`). SysTaskId is reached from SimIr via the Stmt
/// arena, so the root hash flips; the Process cluster reaches it only through
/// arena INDICES (u32), so its sub-pin is UNCHANGED this bump. (2026-06-18 v9:
/// +13 SysFuncId + 5 SysTaskId for the file-read/$dist_*/$cast/$writemem*/
/// $monitoron-off family.)
const EXPECTED_SIMIR_HASH: &str =
    "0cff11673f50bf2d6c74faffc7615fa1d65d28a941db8d66eb936c7df8a3a50a";
/// Sub-pin: the runtime Process cluster (cheap regression signal; NOT the gate).
const EXPECTED_PROCESS_HASH: &str =
    "61db2e207ed69c2ff1dbf3fc0473b7ed9906fbeb6c42128ef9edf382b081f277";

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
