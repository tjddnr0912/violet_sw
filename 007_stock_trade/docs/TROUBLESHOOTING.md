# Troubleshooting

## API Rate Limit (EGW00201)

증상: `초당 거래건수를 초과하였습니다`

| 모드 | API 제한 | 적용 딜레이 | 초당 호출 |
|------|----------|-------------|----------|
| 모의투자 | 5건/초 | 500ms | ~2건 |
| 실전투자 | 20건/초 | 100ms | ~10건 |

관련: `src/quant_modules/order_executor.py` (`API_DELAY_VIRTUAL`, `API_DELAY_REAL`)

## 텔레그램 네트워크 에러 (httpx.ConnectError)

원인: 네트워크 연결 문제 (토큰 충돌 아님).
해결: 자동 복구 - 최대 10회 재시도 + 스레드 자동 재시작.

## 텔레그램 Conflict 에러 (409)

증상: `terminated by other getUpdates request`
원인: 이전 봇 세션 미종료 상태에서 새 세션 시작.
해결: 자동 복구 - Conflict 감지 시 10+5n초 딜레이 후 재시도.

예방: `run_quant.sh daemon`은 SIGTERM graceful shutdown + `drop_pending_updates=True`.

## 총자산 과대 표시 (T+2 결제)

증상: 매수 발생일 총자산/수익률 비정상적 표시.
원인: `cash(dnca_tot_amt)` + `scts_evlu` 계산 시 T+2 결제 미반영으로 이중 계산.
해결: `nass_amt`(순자산) 사용.

수정 패턴 (5곳 통일):
```
Before: total_assets = cash + scts_evlu  ← 결제 전 예수금 이중 계산
After:  total_assets = nass              ← 순자산 (미결제 반영)
        cash = nass - scts_evlu          ← 실질 현금 (역산)
```

## pykrx 스크리닝 실패

증상: `유니버스: 0개`, `KeyError`
원인: KRX 웹사이트 API 응답 형식 변경 → pykrx 1.0.x 호환성 문제.
해결: `pip install pykrx>=1.2.3`

폴백 동작:
1. KIS API로 시가총액 상위 30개 조회
2. pykrx로 KOSPI200 확장 시도
3. 실패 시 → KIS 30개로 진행

## 긴급 리밸런싱 무한 반복

증상: 매일 08:30에 "긴급 리밸런싱 트리거" 반복.
원인: 긴급 리밸런싱이 월초 중복 방지 로직 우회.
해결: `last_urgent_rebalance_month`로 별도 추적, 월 1회 제한.

| 유형 | 추적 변수 | 제한 |
|------|----------|------|
| 월초 리밸런싱 | `last_rebalance_month` | 월 1회 |
| 긴급 리밸런싱 | `last_urgent_rebalance_month` | 월 1회 |

## 휴장일 오판단

증상: 평일인데 휴장일로 판단하여 봇 미동작.
원인: pykrx가 자정에 당일 거래 데이터 조회 시 데이터 없음.

판단 우선순위:
1. 주말(토/일) → 휴장
2. KNOWN_HOLIDAYS (하드코딩) → 휴장
3. 오늘/미래 → 평일이면 거래일로 가정
4. 과거 → pykrx 실제 확인

참고: KIS 휴장일조회(CTCA0903R)는 실전투자에서만 지원.

## 긴급 정지 해제

```
/clear_emergency
/start_trading
```
