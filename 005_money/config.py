# ⚠️ 보안 경고: API 키는 환경변수로 설정하세요!
#
# 방법 1) 환경변수 설정 (권장):
#   export BITHUMB_CONNECT_KEY="실제_Connect_Key"
#   export BITHUMB_SECRET_KEY="실제_Secret_Key"
#
# 방법 2) .env 파일 사용 (python-dotenv 필요):
#   .env 파일에 키를 저장하고 .gitignore에 .env 추가
#
# ⚠️ 이 파일에 실제 API 키를 직접 입력하지 마세요!
# ⚠️ 만약 실수로 입력했다면 config.py를 .gitignore에 추가하세요!

import os
from typing import Dict, Any

# 빗썸 API 정보
BITHUMB_CONNECT_KEY = os.getenv("BITHUMB_CONNECT_KEY", "YOUR_CONNECT_KEY")
BITHUMB_SECRET_KEY = os.getenv("BITHUMB_SECRET_KEY", "YOUR_SECRET_KEY")

# 거래 설정
TRADING_CONFIG = {
    'target_ticker': 'BTC',
    'trade_amount_krw': 10000,  # 거래 금액 (원)
    'min_trade_amount': 5000,   # 최소 거래 금액
    'max_trade_amount': 100000, # 최대 거래 금액
    'stop_loss_percent': 5.0,   # 손절매 비율 (%)
    'take_profit_percent': 10.0, # 익절 비율 (%)
    'trading_fee_rate': 0.0025,  # 거래 수수료율 (0.25%)
}

# 전략 설정
STRATEGY_CONFIG = {
    # 기본 설정 - DEFAULT: 1h (1시간봉)
    'candlestick_interval': '1h',  # 캔들스틱 간격 ('30m', '1h', '6h', '12h', '24h')
    'short_ma_window': 20,   # 단기 이동평균선 기간 (캔들 개수)
    'long_ma_window': 50,   # 장기 이동평균선 기간 (캔들 개수)
    'rsi_period': 14,       # RSI 기간 (캔들 개수)
    'rsi_overbought': 70,   # RSI 과매수 기준
    'rsi_oversold': 30,     # RSI 과매도 기준
    'rsi_buy_threshold': 30,  # GUI RSI 매수 임계값
    'rsi_sell_threshold': 70, # GUI RSI 매도 임계값
    'analysis_period': 100,    # GUI 분석 기간 (캔들 수) - 1h 기준 100시간
    'volume_threshold': 1.5, # 거래량 임계값 (평균 대비 배수)

    # 엘리트 전략: MACD 파라미터 (1시간봉 최적화)
    'macd_fast': 8,         # MACD 단기 EMA (기본: 8시간)
    'macd_slow': 17,        # MACD 장기 EMA (기본: 17시간)
    'macd_signal': 9,       # MACD 시그널선 EMA (기본: 9시간)

    # 엘리트 전략: ATR 파라미터 (변동성 측정)
    'atr_period': 14,       # ATR 계산 기간 (14시간)
    'atr_stop_multiplier': 2.0,  # ATR 기반 손절 배수

    # 엘리트 전략: Stochastic 파라미터
    'stoch_k_period': 14,   # Stochastic %K 기간
    'stoch_d_period': 3,    # Stochastic %D 기간 (K의 이동평균)

    # 엘리트 전략: ADX 파라미터 (추세 강도)
    'adx_period': 14,       # ADX 계산 기간
    'adx_trending_threshold': 25,   # 추세장 판단 기준 (ADX > 25)
    'adx_ranging_threshold': 15,    # 횡보장 판단 기준 (ADX < 15)

    # 엘리트 전략: Bollinger Bands 파라미터
    'bb_period': 20,        # 볼린저 밴드 기간
    'bb_std': 2.0,          # 볼린저 밴드 표준편차 (암호화폐는 2.5 권장)

    # 엘리트 전략: Volume 파라미터
    'volume_window': 20,    # 거래량 평균 계산 윈도우

    # 엘리트 전략: 신호 가중치 (합계 = 1.0)
    'signal_weights': {
        'macd': 0.35,       # MACD 신호 가중치 (추세 지표 - 가장 높음)
        'ma': 0.25,         # 이동평균 가중치 (추세 확인)
        'rsi': 0.20,        # RSI 가중치 (과매수/과매도 필터)
        'bb': 0.10,         # 볼린저밴드 가중치 (평균회귀)
        'volume': 0.10      # 거래량 가중치 (확인용)
    },

    # 엘리트 전략: 신호 임계값
    'confidence_threshold': 0.6,  # 최소 신뢰도 (0.0~1.0)
    'signal_threshold': 0.5,      # 최소 신호 강도 (-1.0~1.0)

    # 엘리트 전략: 리스크 관리
    'max_daily_loss_pct': 3.0,    # 일일 최대 손실률 (%)
    'max_consecutive_losses': 3,   # 최대 연속 손실 횟수
    'max_daily_trades': 5,         # 일일 최대 거래 횟수
    'position_risk_pct': 1.0,      # 거래당 위험 비율 (계좌의 %)

    # 간격별 권장 지표 설정 (엘리트 전략 최적화)
    'interval_presets': {
        '30m': {  # 30분봉 - 단기 스윙 트레이딩 (NEW)
            'short_ma_window': 20,      # 10시간
            'long_ma_window': 50,       # 25시간
            'rsi_period': 9,            # 4.5시간 (빠른 반응)
            'bb_period': 20,            # 10시간
            'bb_std': 2.5,              # 암호화폐 높은 변동성 반영
            'macd_fast': 8,             # 4시간
            'macd_slow': 17,            # 8.5시간
            'macd_signal': 9,           # 4.5시간
            'atr_period': 14,           # 7시간
            'stoch_k_period': 14,       # 7시간
            'stoch_d_period': 3,        # 1.5시간
            'adx_period': 14,           # 7시간
            'volume_window': 20,        # 10시간
            'analysis_period': 100,     # 50시간 (충분한 데이터)
        },
        '1h': {  # 1시간 봉 - 중단기 트레이딩 (DEFAULT, 엘리트 전략 최적화)
            'short_ma_window': 20,      # 20시간
            'long_ma_window': 50,       # 50시간 (약 2일)
            'rsi_period': 14,           # 14시간
            'bb_period': 20,            # 20시간
            'bb_std': 2.0,              # 표준 편차 (암호화폐는 2.5도 가능)
            'macd_fast': 8,             # 8시간
            'macd_slow': 17,            # 17시간
            'macd_signal': 9,           # 9시간
            'atr_period': 14,           # 14시간
            'stoch_k_period': 14,       # 14시간
            'stoch_d_period': 3,        # 3시간
            'adx_period': 14,           # 14시간
            'volume_window': 20,        # 20시간
            'analysis_period': 100,     # 100시간 (약 4일)
        },
        '6h': {  # 6시간 봉 - 중기 트레이딩
            'short_ma_window': 10,      # 60시간 (2.5일)
            'long_ma_window': 30,       # 180시간 (7.5일)
            'rsi_period': 14,           # 84시간 (3.5일)
            'bb_period': 20,            # 120시간 (5일)
            'bb_std': 2.0,
            'macd_fast': 12,            # 72시간 (3일)
            'macd_slow': 26,            # 156시간 (6.5일)
            'macd_signal': 9,           # 54시간 (2.25일)
            'atr_period': 14,           # 84시간
            'stoch_k_period': 14,
            'stoch_d_period': 3,
            'adx_period': 14,
            'volume_window': 10,
            'analysis_period': 50,      # 300시간 (12.5일)
        },
        '12h': {  # 12시간 봉 - 중장기 트레이딩
            'short_ma_window': 7,       # 84시간 (3.5일)
            'long_ma_window': 25,       # 300시간 (12.5일)
            'rsi_period': 14,           # 168시간 (7일)
            'bb_period': 20,            # 240시간 (10일)
            'bb_std': 2.0,
            'macd_fast': 12,            # 144시간 (6일)
            'macd_slow': 26,            # 312시간 (13일)
            'macd_signal': 9,           # 108시간 (4.5일)
            'atr_period': 14,
            'stoch_k_period': 14,
            'stoch_d_period': 3,
            'adx_period': 14,
            'volume_window': 10,
            'analysis_period': 40,      # 480시간 (20일)
        },
        '24h': {  # 24시간 봉 - 장기 트레이딩
            'short_ma_window': 5,       # 5일
            'long_ma_window': 20,       # 20일
            'rsi_period': 14,           # 14일
            'bb_period': 20,            # 20일
            'bb_std': 2.0,
            'macd_fast': 12,            # 12일
            'macd_slow': 26,            # 26일
            'macd_signal': 9,           # 9일
            'atr_period': 14,           # 14일
            'stoch_k_period': 14,
            'stoch_d_period': 3,
            'adx_period': 14,
            'volume_window': 10,
            'analysis_period': 30,      # 30일
        },
    }
}

# 스케줄링 설정
SCHEDULE_CONFIG = {
    'check_interval_minutes': 15,  # 시장 체크 간격 (분) - 1h 기본값에 맞춤
    'daily_check_time': '09:05',   # 일일 체크 시간
    'enable_night_trading': False, # 야간 거래 여부
    'night_start_hour': 22,        # 야간 거래 시작 시간
    'night_end_hour': 6,           # 야간 거래 종료 시간

    # 캔들 간격별 권장 체크 주기 (분)
    'interval_check_periods': {
        '30m': 10,   # 30분 봉 → 10분마다 체크
        '1h': 15,    # 1시간 봉 → 15분마다 체크 (DEFAULT)
        '6h': 60,    # 6시간 봉 → 1시간마다 체크
        '12h': 120,  # 12시간 봉 → 2시간마다 체크
        '24h': 240,  # 24시간 봉 → 4시간마다 체크
    }
}

# 로깅 설정
LOGGING_CONFIG = {
    'log_level': 'INFO',
    'log_dir': 'logs',
    'max_log_files': 30,    # 최대 로그 파일 수
    'enable_console_log': True,
    'enable_file_log': True,
}

# 안전 설정
SAFETY_CONFIG = {
    'dry_run': False,         # 모의 거래 모드 (실제 거래 X)
    'test_mode': False,      # 테스트 모드 (거래 내역 기록 안함)
    'max_daily_trades': 10, # 일일 최대 거래 횟수
    'emergency_stop': False, # 긴급 정지
    'balance_check_interval': 60, # 잔고 체크 간격 (분)
}

def validate_config() -> bool:
    """설정값 검증"""
    # API 키 확인 - 모의 거래 모드에서는 필수가 아님
    if BITHUMB_CONNECT_KEY == "YOUR_CONNECT_KEY" or BITHUMB_SECRET_KEY == "YOUR_SECRET_KEY":
        if SAFETY_CONFIG['dry_run']:
            print("⚠️ 경고: API 키가 설정되지 않았습니다. 모의 거래 모드로 실행됩니다.")
        else:
            print("❌ 오류: 실제 거래 모드에서는 API 키가 필요합니다.")
            print("   config.py에서 API 키를 설정하거나 dry_run: True로 변경하세요.")
            return False

    # 거래 금액 검증
    if TRADING_CONFIG['trade_amount_krw'] < TRADING_CONFIG['min_trade_amount']:
        print("⚠️ 경고: 거래 금액이 최소 거래 금액보다 작습니다.")
        return False

    return True

def get_config() -> Dict[str, Any]:
    """전체 설정 반환"""
    return {
        'trading': TRADING_CONFIG,
        'strategy': STRATEGY_CONFIG,
        'schedule': SCHEDULE_CONFIG,
        'logging': LOGGING_CONFIG,
        'safety': SAFETY_CONFIG,
        'api': {
            'connect_key': BITHUMB_CONNECT_KEY,
            'secret_key': BITHUMB_SECRET_KEY
        }
    }
