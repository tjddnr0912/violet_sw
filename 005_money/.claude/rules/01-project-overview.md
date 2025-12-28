# 01. 프로젝트 개요

## 프로젝트 목적

빗썸(Bithumb) 거래소에서 암호화폐 자동매매를 수행하는 트레이딩 봇입니다.

## 버전 히스토리

| 버전 | 상태 | 전략 | 특징 |
|------|------|------|------|
| Ver1 | 레거시 | Elite 8-Indicator | 8개 지표 가중 신호 |
| Ver2 | 개발중 | Backtrader 기반 | 백테스팅 프레임워크 |
| **Ver3** | **현재 사용** | Portfolio Multi-Coin | 멀티코인, 레짐 기반 |

## Ver3 핵심 특징

### 1. 6단계 시장 레짐 분류
- EMA50/EMA200 차이와 ADX로 시장 상태 판단
- 레짐별 차별화된 전략 적용 (추세추종 vs 평균회귀)

### 2. 듀얼 타임프레임 분석
- Daily: 레짐 판단
- 4H: 진입 신호 확인

### 3. 동적 파라미터 시스템
- 변동성(ATR%)에 따른 파라미터 자동 조정
- 다주기 업데이트 (실시간/4H/Daily/Weekly/Monthly)

### 4. 포트폴리오 관리
- 멀티코인 동시 모니터링 (기본: BTC, ETH, XRP)
- 최대 포지션 수 제한
- 코인별 독립적 분석

## 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.13+ |
| 데이터 처리 | pandas, numpy |
| 차트 | matplotlib |
| GUI | Tkinter |
| API | requests (REST) |
| 알림 | python-telegram-bot |
| 스케줄링 | schedule |

## 실행 환경

```
macOS / Linux 권장
Python 3.13+
Virtual Environment (.venv)
```

## 핵심 의존성

```
pandas>=2.0.0
numpy>=1.24.0
matplotlib>=3.7.0
requests>=2.28.0
schedule>=1.2.0
python-telegram-bot>=20.0
python-dotenv>=1.0.0
```
