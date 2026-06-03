//! velab artifact header (doc-14 §1) — written/decoded independently of the body.
use serde::{Deserialize, Serialize};

use crate::gate::ArtifactError;

/// 8-byte magic prefix (doc-14 §1 "VELAB\0", padded to 8).
pub const MAGIC_VELAB: [u8; 8] = *b"VELAB\0\0\0";

/// Container format version. Bumped whenever the header layout changes.
pub const CURRENT_FORMAT_VERSION: u32 = 1;

/// Build provenance (Layer 2). Stamped for traceability, NEVER a staleness key.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Provenance {
    pub tool_version: String,
    pub git_sha: Option<String>,
    pub dirty: bool,
    pub profile: String,
}

impl Provenance {
    /// Capture from build-time env (no build.rs — option_env!/env!/cfg!).
    pub fn capture() -> Self {
        Provenance {
            tool_version: env!("CARGO_PKG_VERSION").to_string(),
            git_sha: option_env!("VITA_GIT_SHA").map(str::to_string),
            dirty: option_env!("VITA_GIT_DIRTY").is_some_and(|v| v == "1" || v == "true"),
            profile: if cfg!(debug_assertions) { "debug" } else { "release" }.to_string(),
        }
    }
}

/// velab header (doc-14 §1). Decodable before the body.
///
/// `composite_input_hash`/`consumed`/`worklib_manifest_hash` are stamped and
/// round-tripped here, but their RULE-V live-recheck gate (`E-ART-STALE-UPSTREAM`)
/// is deferred to a later PR.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VelabHeader {
    pub format_version: u32,
    pub schema_hash: [u8; 32],
    pub composite_input_hash: [u8; 32],
    pub global_time_precision: i64,
    pub consumed: Vec<(String, [u8; 32])>,
    pub worklib_manifest_hash: [u8; 32],
    pub uses_dump: bool,
    pub tool_semver_major: u32,
    pub provenance: Provenance,
}

/// Serialize as `MAGIC_VELAB ++ postcard(header) ++ body`.
pub fn write_velab(header: &VelabHeader, body: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(8 + 64 + body.len());
    out.extend_from_slice(&MAGIC_VELAB);
    let header_bytes =
        postcard::to_stdvec(header).expect("postcard header encode is infallible for owned data");
    out.extend_from_slice(&header_bytes);
    out.extend_from_slice(body);
    out
}

/// Check magic, then decode the header ALONE (body untouched). Returns the header
/// and the trailing body slice. A bad magic or undecodable header is a hard
/// `E-ART-FORMAT-MISMATCH` (doc-15) — the body is never deserialized.
pub fn read_velab(bytes: &[u8]) -> Result<(VelabHeader, &[u8]), ArtifactError> {
    if bytes.len() < MAGIC_VELAB.len() || bytes[..MAGIC_VELAB.len()] != MAGIC_VELAB {
        return Err(ArtifactError::format("bad or missing VELAB magic"));
    }
    let after_magic = &bytes[MAGIC_VELAB.len()..];
    let (header, body) = postcard::take_from_bytes::<VelabHeader>(after_magic)
        .map_err(|e| ArtifactError::format(&format!("undecodable velab header: {e}")))?;
    Ok((header, body))
}
