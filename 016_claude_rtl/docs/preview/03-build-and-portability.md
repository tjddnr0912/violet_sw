# 03 · 빌드 · 이식성

> 설계 명세 §3·§5.2 기반.

---

## 빌드 철학

**원문 소스 → 각 OS에서 빌드.** 사전 빌드 바이너리 배포에 의존하지 않는다.

이 원칙이 의미하는 세 가지:

1. **순수 Rust 코어 + 최소/제로 C 의존성.** 외부 C 라이브러리 의존을 피해 3-OS 빌드 마찰을 제거한다.
2. **`cargo`가 유일한 빌드 진입점.** `cmake`, `make`, 별도 빌드 스크립트 없이 `cargo build`/`cargo test` 하나로 전체 워크스페이스가 빌드·테스트된다.
3. **MSRV 고정.** `rust-toolchain.toml`로 Rust 버전을 저장소에 고정해 재현성을 확보한다.

---

## Cargo Workspace 구조

spec §5.2에서 정의한 11개 크레이트를 단일 cargo workspace에 배치한다. 각 크레이트는 단일 책임 + 명확한 인터페이스로 분리해 독립 테스트가 가능하다.

```toml
# Cargo.toml (워크스페이스 루트)
[workspace]
members = [
    "crates/hdl-preprocess",  # 컴파일러 지시어 처리, 매크로 전개, include
    "crates/hdl-lexer",       # 토큰화 (언어별 토큰 집합)
    "crates/hdl-parser",      # 토큰 → AST (언어별)
    "crates/hdl-ast",         # 언어별 AST 타입 정의
    "crates/elaborate",       # 파라미터 해소·계층 평탄화·타입/연결성 검사 → IR
    "crates/sim-ir",          # 언어 중립 시뮬레이션 IR
    "crates/sim-engine",      # 이벤트 구동 커널, 스케줄러, 시간 모델
    "crates/hdl-builtins",    # 표준 $-system tasks/functions 라이브러리
    "crates/vcd-writer",      # IEEE 1364 VCD 직렬화
    "crates/diag",            # 진단/오류 리포팅 (소스 위치, 메시지)
    "crates/cli",             # vita 드라이버 (compile/elab/sim 서브커맨드)
]
resolver = "2"

[workspace.package]
edition = "2024"
rust-version = "1.80"     # 계획 MSRV — 채택 크레이트 MSRV에 따라 상향 조정
license = "MIT OR Apache-2.0"
repository = "https://github.com/your-org/vitamin"  # placeholder

[workspace.dependencies]
# 공통 의존성을 여기서 버전 고정 (각 크레이트는 workspace = true 로 참조)
logos = { version = "0.16", default-features = false }   # semver range: >=0.16.0, <0.17.0 (패치 업데이트 허용)
chumsky = { version = "0.13", default-features = false }
ariadne = "0.6"
```

### 크레이트 의존 방향

```
cli
 └─ 전부

hdl-builtins ──► sim-ir, sim-engine, vcd-writer
sim-engine   ──► sim-ir
elaborate    ──► hdl-ast, sim-ir, diag
hdl-parser   ──► hdl-lexer, hdl-ast
hdl-lexer    ──► hdl-preprocess
```

`diag`, `hdl-ast`, `sim-ir`는 최하위 leaf 크레이트다 — 다른 크레이트에 의존하지 않아 독립 테스트가 가장 쉽다.

---

## MSRV · Toolchain 고정

### `rust-toolchain.toml`

저장소 루트에 배치. `cargo build`·`rustup run` 실행 시 자동으로 이 버전을 사용한다.

```toml
# rust-toolchain.toml (저장소 루트)
[toolchain]
channel = "1.80.0"          # 계획 MSRV; stable 릴리스 고정
components = [
    "rustfmt",              # 코드 포맷
    "clippy",               # 린트
    "rust-src",             # IDE 지원용 (rust-analyzer)
]
targets = [
    "x86_64-unknown-linux-gnu",
    "aarch64-unknown-linux-gnu",
    "x86_64-apple-darwin",
    "aarch64-apple-darwin",
]
```

### MSRV 정책

- **현재 계획 MSRV: 1.80.** Rust 1.80은 `std::sync::LazyLock` 안정화를 포함한다 (참고: `let-else`는 1.65, `OnceLock`은 1.70에 각각 안정화됐다).
- **채택 크레이트가 높은 MSRV를 요구할 경우 상향.** 예: ariadne 0.6.0의 MSRV가 1.85이므로 ariadne를 채택하면 1.85로 조정.
- **MSRV 변경은 semver minor bump로 처리.** 패치 릴리스에서 MSRV를 올리지 않는다.
- **CI에서 MSRV 최소 버전으로 `cargo check` 실행** — `rust-toolchain.toml` 외에 별도 `toolchain: "1.80.0"` 잡을 매트릭스에 포함해 MSRV 회귀를 방지한다.

---

## 3-OS 매트릭스

| OS | 패키지 매니저 | Rust 설치 방법 | 비고 |
|---|---|---|---|
| Ubuntu LTS (22.04/24.04) | `apt` | `rustup` | 기준 플랫폼. CI `ubuntu-latest` 러너에서 상시 검증. glibc 2.35+ 대응. |
| RHEL 8/9 계열 | `dnf` | `rustup` | glibc 2.28+ (RHEL8) / 2.34+ (RHEL9) 호환. CI는 UBI(Universal Base Image) 컨테이너 사용 권장 (self-hosted 러너 없이도 재현 가능). RHEL8에서 `gcc` 링커 필요 시 `dnf install gcc` 사전 설치. |
| macOS Apple Silicon + Intel | `brew` (선택) | `rustup` | `aarch64-apple-darwin` + `x86_64-apple-darwin` 양 target 빌드 검증. universal binary(lipo)는 별도 후속 작업. CI는 `macos-latest`(Apple Silicon) 러너 사용. |

**공통 설치 흐름:**

```bash
# 1. rustup 설치 (모든 OS 동일)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# 2. 저장소 클론 후 빌드 (rust-toolchain.toml이 버전 자동 선택)
git clone https://github.com/your-org/vitamin
cd vitamin
cargo build --workspace
cargo test --workspace
```

---

## CI 매트릭스

GitHub Actions 기준. Ubuntu/macOS 네이티브 잡과 RHEL UBI 컨테이너 잡을 분리한다. 두 잡(`build-native`, `build-rhel`)은 병렬 실행된다 — `container:` 필드에 빈 문자열을 넣으면 Actions가 이미지 이름으로 해석해 오류가 발생하므로, 컨테이너가 필요 없는 러너와 필요한 러너는 별도 잡으로 구분한다.

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  # ── Ubuntu + macOS (네이티브 러너, 컨테이너 없음) ────────────────────────
  build-native:
    name: Build & Test (${{ matrix.os }})
    runs-on: ${{ matrix.os }}

    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]

    steps:
      - uses: actions/checkout@v4

      - name: Install Rust toolchain
        uses: dtolnay/rust-toolchain@v1
        with:
          # rust-toolchain.toml의 channel을 그대로 읽음
          toolchain: "1.80.0"
          components: rustfmt, clippy

      - name: Cache cargo registry
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target/
          key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}

      - name: Build (all crates)
        run: cargo build --workspace --locked

      - name: Test (all crates)
        run: cargo test --workspace --locked

      - name: Clippy
        run: cargo clippy --workspace -- -D warnings

      - name: Fmt check
        run: cargo fmt --all -- --check

  # ── RHEL9 UBI 컨테이너 (GitHub-hosted ubuntu 러너에서 실행) ──────────────
  build-rhel:
    name: Build & Test (RHEL9/UBI)
    runs-on: ubuntu-latest
    container: redhat/ubi9

    steps:
      - uses: actions/checkout@v4

      - name: Install C linker
        run: dnf install -y gcc

      - name: Install Rust toolchain
        uses: dtolnay/rust-toolchain@v1
        with:
          toolchain: "1.80.0"
          components: rustfmt, clippy

      - name: Cache cargo registry
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target/
          key: rhel9-cargo-${{ hashFiles('**/Cargo.lock') }}

      - name: Build (all crates)
        run: cargo build --workspace --locked

      - name: Test (all crates)
        run: cargo test --workspace --locked

  # ── MSRV 회귀 방지 잡 (Ubuntu만으로 충분) ───────────────────────────────
  msrv:
    name: MSRV check (Rust 1.80)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@v1
        with:
          toolchain: "1.80.0"
      - run: cargo check --workspace --locked
      # (cargo audit 단계는 별도 job으로 추후 추가)
```

**RHEL CI 전략 선택 근거:** `redhat/ubi9` 공개 이미지를 컨테이너로 실행하면 GitHub-hosted 러너(`ubuntu-latest`)에서도 RHEL9 glibc·패키지 환경을 재현할 수 있다. self-hosted 러너 구성 없이 CI를 유지할 수 있어 초기 단계에 실용적이다. 프로젝트가 성숙하면 RHEL8 호환을 위해 `redhat/ubi8`을 추가하거나 self-hosted 러너로 전환한다.

---

## 외부 의존성 정책

1. **순수 Rust crate 우선.** 동일 기능이 순수 Rust 크레이트로 충족된다면 C 바인딩 크레이트를 채택하지 않는다.
2. **C 라이브러리 의존은 최대한 회피.** 불가피할 경우:
   - `build.rs`에 명시적으로 기록.
   - 3-OS 빌드 검증을 CI에 추가.
   - 해당 의존성의 정적 링크 가능 여부 확인 (`*-sys` 크레이트 사용 시 vendored feature 선호).
3. **`Cargo.lock` 커밋.** 바이너리 크레이트(`cli`)의 `Cargo.lock`을 저장소에 포함해 CI에서 `--locked` 빌드를 사용한다. 라이브러리 크레이트의 lock 파일은 관례대로 `.gitignore`에 포함하지 않는다.
4. **의존성 감사.** `cargo audit`를 CI에 추가해 알려진 취약점을 주기적으로 점검한다.

---

## Sources

- 본 spec §3 — `/docs/superpowers/specs/2026-05-26-vitamin-rtl-simulator-design.md`
- 본 spec §5.2 — 위 동일 파일 (Cargo 워크스페이스·크레이트 표)
- `02-implementation-language.md` — MSRV 결정 맥락
- GitHub Actions 문서: https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners
- Red Hat UBI 이미지: https://catalog.redhat.com/software/containers/ubi9/ubi/615bcf606feffc5384e84400
- dtolnay/rust-toolchain action: https://github.com/dtolnay/rust-toolchain
