//! Layer 3 (16): trace the actual serde derives with serde-reflection and diff the
//! resulting Registry (RON) against a committed golden. Catches wire drift that the
//! syn-attr Layer-1 path cannot see.
use serde_reflection::{Tracer, TracerConfig};

fn traced_registry_ron() -> String {
    let mut tracer = Tracer::new(TracerConfig::default());
    // Trace each enum type explicitly so all variants are discovered.
    tracer.trace_simple_type::<sim_ir::FourState>().unwrap();
    tracer.trace_simple_type::<sim_ir::EdgeKind>().unwrap();
    tracer.trace_simple_type::<sim_ir::RegionTag>().unwrap();
    tracer.trace_simple_type::<sim_ir::WakeCond>().unwrap();
    // Trace struct types.
    tracer.trace_simple_type::<sim_ir::ProcFlags>().unwrap();
    tracer.trace_simple_type::<sim_ir::Frame>().unwrap();
    tracer.trace_simple_type::<sim_ir::JoinState>().unwrap();
    tracer.trace_simple_type::<sim_ir::WakeKey>().unwrap();
    tracer.trace_simple_type::<sim_ir::SuspendState>().unwrap();
    let registry = tracer.registry().unwrap();
    ron::ser::to_string_pretty(&registry, ron::ser::PrettyConfig::default()).unwrap()
}

#[test]
fn serde_reflection_ron_golden() {
    let golden = include_str!("../../testdata/sim_ir_registry.ron");
    assert_eq!(
        traced_registry_ron().trim_end(),
        golden.trim_end(),
        "serde wire format drifted (Layer 3). Update sim_ir_registry.ron only if intentional."
    );
}
