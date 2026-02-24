# Changelog

## 2026-02-24: engine_state ↔ KIS 포지션 동기화 버그 수정

engine_state.json이 실제 KIS 증권사 잔고와 불일치하는 버그 수정.

- `sync_positions_from_kis()` 강화: 3-way 동기화 (추가/업데이트/제거)
  - 수량 불일치 + 평단가 불일치(>1원) 모두 KIS 기준으로 보정
  - KIS에 없는 stale 포지션 자동 제거
  - `_position_lock`으로 thread safety 확보
  - 현금 동기화: `parse_balance()` 사용 (T+2 대응)
  - `quiet` 파라미터 추가 (자동 동기화 시 알림 생략)
- `generate_rebalance_orders()`: 리밸런싱 전 KIS 동기화 자동 호출
- `start()`: 엔진 시작 시 항상 KIS 동기화 (기존: 포지션 0개일 때만)
- `add_position()`: 동일 종목 매수 시 수량 합산 + 평균단가 계산 (기존: 덮어쓰기)
- `/sync_positions` 텔레그램 응답 개선 (added/updated/removed 표시)

## 2026-02-21: 코드베이스 모듈화 리팩토링

| 파일 | Before | After |
|------|--------|-------|
| `quant_engine.py` | 1,664줄 | ~980줄 (-41%) |
| `bot.py` | 1,653줄 | ~330줄 (-80%) |

8단계 리팩토링:
1. **Balance 헬퍼**: `balance_helpers.py` - nass 기반 T+2 대응 통합 (5곳 중복 제거)
2. **API 딜레이 상수 통합**: `order_executor.py`에서 import
3. **손절/익절 트리거 통합**: `_trigger_sell_with_retry()` 공통 추출
4. **리포트 모듈**: `report_generator.py` - daily/monthly 리포트 이관
5. **bot.py 커맨드 분리**: `commands/` Mixin 5개 + `with_error_handling` 데코레이터
6. **포지션 모니터**: `position_monitor.py` - 모니터링/손절/익절 이관
7. **스케줄 핸들러**: `schedule_handler.py` - 스케줄 이벤트 이관
8. **트래커 베이스**: `tracker_base.py` - JSON 로드/세이브 공통 패턴

## 2026-02-20: 월간 리포트 수정 + 리밸런싱 알림 + 기간별 체결 조회

- 월간 리포트/`/capital` 총자산 이중 카운팅 수정 (`total_eval` → `scts_evlu`)
- 리밸런싱 실시간 진행상황 알림 (threading.Lock + asyncio.to_thread)
- `/orders [N]` 기간별 체결 내역 조회 (최대 90일, 페이지네이션)
- 총자산 T+2 결제 이중 계산 수정 (`nass_amt` 사용, 5곳 통일)

## 2026-02-19: 주간 장부 점검 (Weekly Reconciliation)

- `reconcile_latest_snapshot()` - KIS 실잔고 대조, 편차 >1% 시 보정
- 토요일 10:00 자동 실행 / `/reconcile` 수동 점검

## 2026-02-14: 사용자 친화적 에러 메시지

- `error_formatter.py` - 에러 분류 + HTML 포맷 (상황/조치/안심)
- 텔레그램 봇 9곳, 엔진 2곳, 자동관리자 2곳 적용
- 데몬 터미널: WARNING 이상만 표시

## 2026-02-09: 일별 자산 추적 및 거래 일지

- `daily_tracker.py` - 일별 스냅샷 + 영구 거래 일지
- `data/quant/daily_history.json`, `transaction_journal.json`
- `/history [N]`, `/trades [N]`, `/capital` 명령어

## 2026-01-27: pykrx 호환성 + 긴급 리밸런싱 버그

- pykrx 1.0.51 → 1.2.3 업그레이드 (KRX API 변경 대응)
- 긴급 리밸런싱 `last_urgent_rebalance_month` 별도 추적
