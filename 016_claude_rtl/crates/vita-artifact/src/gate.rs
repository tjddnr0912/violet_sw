use diag::MsgCode;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArtifactError {
    pub code: MsgCode,
    pub message: String,
}

impl ArtifactError {
    pub fn format(msg: &str) -> Self {
        ArtifactError { code: MsgCode::ArtFormatMismatch, message: msg.to_string() }
    }
}

pub struct ToolContext;

pub fn verify_header(_h: &crate::VelabHeader, _t: &ToolContext) -> Result<(), ArtifactError> {
    Ok(())
}
