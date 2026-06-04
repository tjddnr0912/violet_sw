//! vita multicall driver — thin wrapper. Parses argv, dispatches on the
//! `argv[0]` basename (`vita` one-shot vs `vcmp`/`velab`/`vrun` staged stubs),
//! and exits with the pipeline's exit code. All real logic lives in `cli::run`
//! so it is unit-testable without spawning a process.
fn main() {
    let argv: Vec<String> = std::env::args().collect();
    let code = cli::run(&argv);
    std::process::exit(code);
}
