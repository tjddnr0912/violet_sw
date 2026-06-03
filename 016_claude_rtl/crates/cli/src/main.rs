//! vita multicall driver — stub (PR1-B). argv[0] basename dispatch lands later.
fn main() {
    let arg0 = std::env::args_os().next();
    let applet = arg0
        .as_deref()
        .and_then(|s| std::path::Path::new(s).file_stem())
        .and_then(|s| s.to_str())
        .unwrap_or("vita")
        .to_string();
    eprintln!("vitamin: {applet}: not implemented yet (PR1-B scaffold)");
    std::process::exit(3);
}
