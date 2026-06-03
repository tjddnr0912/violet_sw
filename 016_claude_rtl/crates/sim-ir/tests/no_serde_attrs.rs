//! 16 §312: the frozen cluster must carry only `#[]` attr slots. If anyone adds a
//! serde attr to a frozen type, its local_shape() stops being all-`#[]` and the
//! hash flips — this guard makes that an explicit, named failure.
use vita_schema::SchemaShape;

fn assert_no_serde(name: &str, shape: &str) {
    assert!(
        !shape.contains("#[serde") && !slot_nonempty(shape),
        "{name} carries a serde attr; frozen cluster must be attr-free: {shape}"
    );
}

/// true if any `#[...]` slot has content between the brackets.
fn slot_nonempty(shape: &str) -> bool {
    let bytes = shape.as_bytes();
    let mut i = 0;
    while let Some(p) = shape[i..].find("#[") {
        let open = i + p + 2;
        if bytes.get(open) != Some(&b']') {
            return true;
        }
        i = open + 1;
    }
    false
}

#[test]
fn frozen_types_are_attr_free() {
    assert_no_serde("ProcFlags", sim_ir::ProcFlags::local_shape());
    assert_no_serde("RegionTag", sim_ir::RegionTag::local_shape());
    assert_no_serde("EdgeKind", sim_ir::EdgeKind::local_shape());
    assert_no_serde("FourState", sim_ir::FourState::local_shape());
    assert_no_serde("Frame", sim_ir::Frame::local_shape());
    assert_no_serde("WakeCond", sim_ir::WakeCond::local_shape());
    assert_no_serde("WakeKey", sim_ir::WakeKey::local_shape());
    assert_no_serde("JoinState", sim_ir::JoinState::local_shape());
    assert_no_serde("SuspendState", sim_ir::SuspendState::local_shape());
}
