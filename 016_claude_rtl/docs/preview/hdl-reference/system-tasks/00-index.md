# 00 · System Tasks · Functions 인덱스

`$`로 시작하는 표준 빌트인은 본 프로젝트 `hdl-builtins` 크레이트가 구현한다.

## 카테고리 인덱스

| # | 파일 | 주요 항목 | Phase |
|---|---|---|---|
| 01 | [display-io](01-display-io.md) | `$display`/`$write`/`$monitor`/`$strobe` + b/o/h 변형 | 1 |
| 02 | file-io | `$fopen`/`$fclose`/`$fwrite`/`$fdisplay`/`$fread`/`$fscanf`/`$fgets`/`$sscanf`/`$sformat`/`$sformatf` | 2 |
| 03 | memory-load | `$readmemb`/`$readmemh`/`$writememb`/`$writememh` | 2 |
| 04 | [simulation-control](04-simulation-control.md) | `$finish`/`$stop`/`$exit` | 1 |
| 05 | [time-functions](05-time-functions.md) | `$time`/`$stime`/`$realtime` | 1 |
| 06 | conversion | `$signed`/`$unsigned`/`$rtoi`/`$itor`/`$bitstoreal`/`$realtobits` | 2 |
| 07 | bit-vector | `$bits`/`$clog2`/`$countones`/`$countbits`/`$onehot`/`$onehot0`/`$isunknown` | 2 |
| 08 | math | `$pow`/`$ln`/`$log10`/`$exp`/`$sqrt`/`$sin`/`$cos`/`$tan` 등 | 2 |
| 09 | random | `$random`/`$urandom`/`$urandom_range`/`$dist_*` | 2 |
| 10 | vcd-dump | `$dumpfile`/`$dumpvars`/`$dumpon`/`$dumpoff`/`$dumpall`/`$dumpflush`/`$dumplimit` | 1 |
| 11 | assertion-sampling | `$past`/`$rose`/`$fell`/`$stable`/`$changed`/`$sampled`/`$assertoff`/`$asserton`/`$assertkill` | 2 |
| 12 | introspection | `$typename`/`$cast`/`$isunbounded`/`$size`/`$left`/`$right`/`$low`/`$high`/`$increment` | 2 |
| 13 | misc | `$value$plusargs`/`$test$plusargs`/`$system` 등 | 2 |

## Phase 1 핵심 셋 (MVP 1일차부터)

다음 태스크는 가장 단순한 RTL 테스트벤치를 실행하기 위한 최소 요건이다.

- **display**: `$display`, `$write`, `$monitor`, `$strobe`
- **time**: `$time`, `$realtime`
- **control**: `$finish`, `$stop`
- **dump**: `$dumpfile`, `$dumpvars`, `$dumpon`, `$dumpoff`, `$dumpall`

이 셋이 없으면 Hello-World 수준의 시뮬레이션도 완료 확인이 불가능하다.
`$finish` 없이는 시뮬이 끝나지 않고, `$display` 없이는 결과를 볼 수 없다.

## Phase 2 확장

Phase 1 이후 파일 I/O, 메모리 초기화, 비트 연산 함수, 수학 함수, 난수 생성을
순차적으로 추가한다. 각 카테고리는 별도 파일로 관리하며, 위 인덱스의 파일 이름으로
cross-link된다.

## Phase 3 / 후속

SV-only assertion sampling (`$past`, `$rose` 등)과 확장 VCD 태스크
(`$dumpports*` 등)는 현재 비목표. 표준 준수 범위가 합성 가능 RTL 서브셋을
넘어선 검증 전용 기능은 별도 로드맵에서 결정한다.

## Sources

- 본 spec §9 (Phase별 system tasks 목록)
- IEEE 1800-2017 §20, IEEE 1364-2005 §17
- research-log: [system-tasks-display-time-2026-05-28.md](../../research-log/system-tasks-display-time-2026-05-28.md)
