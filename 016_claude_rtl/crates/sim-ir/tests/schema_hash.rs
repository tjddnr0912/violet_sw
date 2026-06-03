//! Golden #1 (pinned hash, 2-platform determinism contract) + Golden #2 (canonical string diff).
use vita_schema::{schema_hash, SchemaShape, ShapeRegistry};

/// blake3 of the SuspendState-closure canonical string. Locked PR1-B.
/// Flips iff a frozen field/variant/serde-attr moves -> all .velab invalidated.
const EXPECTED_HASH: &str = "6aceac696233b570655ececc76759a1c6e8c3494371c25e10feea1214e3714c6";

const GOLDEN_CANON: &str = include_str!("../../testdata/sim_ir_canonical.txt");

#[test]
fn schema_hash_is_pinned() {
    let got = hex::encode(schema_hash::<sim_ir::SuspendState>());
    assert_eq!(
        got, EXPECTED_HASH,
        "SCHEMA_HASH changed — a frozen sim-ir shape/serde-attr moved.\n\
         If intentional: all .velab invalid -> bump format_version + update both goldens."
    );
}

#[test]
fn canonical_string_golden() {
    let mut reg = ShapeRegistry::new();
    sim_ir::SuspendState::register(&mut reg);
    assert_eq!(
        reg.canonical_string(),
        GOLDEN_CANON,
        "canonical shape string drifted — see the exact changed registry line above"
    );
}
