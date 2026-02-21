# Telegram Commands

## 시스템 제어

| 명령어 | 설명 |
|--------|------|
| `/start_trading` | 자동매매 시작 |
| `/stop_trading` | 자동매매 중지 |
| `/pause` | 일시 정지 |
| `/resume` | 재개 |
| `/emergency_stop` | 긴급 정지 |
| `/clear_emergency` | 긴급 정지 해제 |

## 수동 실행

| 명령어 | 설명 |
|--------|------|
| `/run_screening` | 스크리닝 즉시 실행 |
| `/run_rebalance` | 리밸런싱 즉시 실행 |
| `/run_optimize` | 가중치 최적화 |

## 설정 변경

| 명령어 | 설명 |
|--------|------|
| `/set_dryrun on\|off` | Dry-run 모드 |
| `/set_target [N]` | 목표 종목 수 |
| `/set_stoploss [N]` | 손절 비율(%) |

## 조회

| 명령어 | 설명 |
|--------|------|
| `/status` | 시스템 상태 |
| `/positions` | 보유 포지션 |
| `/balance` | 계좌 잔고 |
| `/logs` | 최근 로그 |
| `/report` | 일일 리포트 |

## 포지션 관리

| 명령어 | 설명 |
|--------|------|
| `/close [종목코드]` | 특정 종목 청산 |
| `/close_all` | 전체 청산 |

## 분석

| 명령어 | 설명 |
|--------|------|
| `/screening` | 스크리닝 결과 조회 |
| `/signal [종목코드]` | 기술적 분석 |
| `/price [종목코드]` | 현재가 조회 |

## 새 명령어 추가 방법

1. `src/telegram/bot.py`에 `cmd_XXX` 메서드 추가
2. `build_application()`에 핸들러 등록
3. `cmd_help()` 업데이트
4. 필요시 `SystemController`에 기능 추가
