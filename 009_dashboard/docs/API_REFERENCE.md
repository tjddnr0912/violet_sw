# API Reference

## 인증

v2 API는 API Key 인증 필요 (환경변수 `DASHBOARD_API_KEY` 비어있으면 비활성화).

| 방식 | 예시 |
|------|------|
| 헤더 | `X-API-Key: <key>` |
| 쿼리 | `?api_key=<key>` |

## Health Check

```
GET /health
→ {"status": "ok"}
```

## v1 API (인증 없음)

기존 웹 대시보드 호환용.

| 엔드포인트 | 설명 |
|------------|------|
| `GET /api/summary` | 포트폴리오 요약 |
| `GET /api/stock/positions` | 주식 포지션 |
| `GET /api/crypto/regime` | 암호화폐 레짐 |
| `GET /api/crypto/trades` | 암호화폐 거래 내역 (최근 20건) |
| `GET /api/crypto/performance` | 암호화폐 성과 통계 |

## v2 API (API Key 인증, iOS 앱용)

통일 응답 형식:
```json
{
  "status": "ok",
  "data": { ... },
  "timestamp": "2026-02-21T10:00:00"
}
```

### 통합

| 엔드포인트 | 설명 |
|------------|------|
| `GET /api/v2/summary` | 통합 요약 (stock + crypto + system_status) |

### 암호화폐

| 엔드포인트 | 파라미터 | 설명 |
|------------|----------|------|
| `GET /api/v2/crypto/regime` | - | 시장 레짐 상세 (ATR% 포함) |
| `GET /api/v2/crypto/trades` | `limit` (기본 20) | 거래 내역 |
| `GET /api/v2/crypto/performance` | - | 성과 통계 (승률, 총수익 등) |
| `GET /api/v2/crypto/coins` | - | 코인별 성과 요약 |
| `GET /api/v2/crypto/coins/<coin>/trades` | `limit` (기본 20) | 특정 코인 거래 내역 |
| `GET /api/v2/crypto/price/<coin>` | - | 실시간 시세 (Bithumb API) |
| `GET /api/v2/crypto/chart/<coin>` | `interval` (5m/30m/1h/6h/1d, 기본 1h) | 캔들스틱 차트 (최근 100개) |

### 한국주식

| 엔드포인트 | 파라미터 | 설명 |
|------------|----------|------|
| `GET /api/v2/stock/positions` | - | 현재 포지션 (손익 계산 포함) |
| `GET /api/v2/stock/daily` | `days` (기본 30) | 일일 자산 변동 히스토리 |
| `GET /api/v2/stock/transactions` | `limit` (기본 20) | 거래 내역 |

### 시스템

| 엔드포인트 | 설명 |
|------------|------|
| `GET /api/v2/system/status` | 봇 상태 (장 시간 인식, daemon_running, market_status) |

## 웹 페이지 라우트

| 경로 | 설명 |
|------|------|
| `/` | 메인 대시보드 |
| `/stock` | 주식 상세 |
| `/crypto` | 암호화폐 상세 |
| `/embed` | iframe 임베드용 간소화 |
