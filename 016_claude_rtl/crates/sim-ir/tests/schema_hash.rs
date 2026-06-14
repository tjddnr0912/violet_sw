//! Golden #1: pinned SimIr root hash (M3 backbone, 2-platform determinism contract).
//! Golden #2: canonical-string diff. Plus a Process sub-pin (runtime-cluster regression).
use vita_schema::{schema_hash, SchemaShape, ShapeRegistry};

/// blake3 of the full SimIr-closure canonical string. Locked at
/// format_version 8 (2026-06-14: +WaitCause::Fork unit variant — `wait fork;`
/// IR. The Process cluster reaches WaitCause via SuspendState, so its sub-pin
/// ALSO flips this bump — that is expected, not corruption). Shape-only bump;
/// the wait-fork / SVA features land in follow-on slices.
const EXPECTED_SIMIR_HASH: &str =
    "093e32ff7b5946f880b591949c97c6a7afc3a5e69ace88ed1a32e035f25930d3";
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
