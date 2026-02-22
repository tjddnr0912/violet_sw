# CLAUDE.md - 009_dashboard + 010_ios_dashboard

Trading Dashboard 웹 서버(Flask) + iOS 앱(SwiftUI).
005_money(암호화폐)와 007_stock_trade(한국주식) 데이터를 통합 조회.

## 실행

```bash
cd 009_dashboard
source venv/bin/activate
python app.py              # localhost:5001
```

`start_all_bots.sh` Tab 6에서 자동 실행됨. Foreground 프로세스로 탭 종료 시 서버도 종료.

## 구조 요약

| 디렉토리 | 역할 |
|-----------|------|
| `009_dashboard/` | Flask 백엔드 (app.py + data_loader.py) |
| `010_ios_dashboard/` | SwiftUI iOS 앱 (MVVM, xcodegen) |

## 핵심 참조

- **포트**: 5001 (macOS ControlCenter가 5000 사용)
- **인증**: `DASHBOARD_API_KEY` 환경변수 (비어있으면 비활성화)
- **v1 API**: 인증 없음, 기존 호환 (`/api/summary` 등)
- **v2 API**: API Key 인증, iOS 앱용 (`/api/v2/*`)

## 데이터 소스 (읽기 전용)

| 키 | 파일 |
|----|------|
| stock_engine | `007_stock_trade/data/quant/engine_state.json` |
| stock_daily | `007_stock_trade/data/quant/daily_history.json` |
| stock_transactions | `007_stock_trade/data/quant/transaction_journal.json` |
| crypto_factors | `005_money/logs/dynamic_factors_v3.json` |
| crypto_history | `005_money/logs/performance_history_v3.json` |

## 상세 문서

- [API 레퍼런스](docs/API_REFERENCE.md) - 전체 엔드포인트 목록 및 인증
- [아키텍처](docs/ARCHITECTURE.md) - 프로젝트 구조, 데이터 흐름, 기술 스택
- [진행 상태](docs/STATUS.md) - 완료/미완료 작업 추적
- [iOS 앱](../010_ios_dashboard/CLAUDE.md) - SwiftUI 앱 문서
