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
    'candlestick_interval': '24h',  # 캔들스틱 간격 ('1h', '6h', '12h', '24h')
    'short_ma_window': 5,   # 단기 이동평균선 기간 (캔들 개수)
    'long_ma_window': 20,   # 장기 이동평균선 기간 (캔들 개수)
    'rsi_period': 14,       # RSI 기간 (캔들 개수)
    'rsi_overbought': 70,   # RSI 과매수 기준
    'rsi_oversold': 30,     # RSI 과매도 기준
    'rsi_buy_threshold': 30,  # GUI RSI 매수 임계값
    'rsi_sell_threshold': 70, # GUI RSI 매도 임계값
    'analysis_period': 20,    # GUI 분석 기간 (캔들 수)
    'volume_threshold': 1.5, # 거래량 임계값 (평균 대비 배수)

    # 간격별 권장 지표 설정
    'interval_presets': {
        '1h': {  # 1시간 봉 - 단기 트레이딩
            'short_ma_window': 7,
            'long_ma_window': 25,
            'rsi_period': 14,
            'analysis_period': 30,
        },
        '6h': {  # 6시간 봉 - 중기 트레이딩
            'short_ma_window': 5,
            'long_ma_window': 15,
            'rsi_period': 14,
            'analysis_period': 20,
        },
        '12h': {  # 12시간 봉 - 중장기 트레이딩
            'short_ma_window': 5,
            'long_ma_window': 15,
            'rsi_period': 14,
            'analysis_period': 20,
        },
        '24h': {  # 24시간 봉 - 장기 트레이딩
            'short_ma_window': 5,
            'long_ma_window': 20,
            'rsi_period': 14,
            'analysis_period': 20,
        },
    }
}

# 스케줄링 설정
SCHEDULE_CONFIG = {
    'check_interval_minutes': 30,  # 시장 체크 간격 (분) - 캔들 간격과 동기화 권장
    'daily_check_time': '09:05',   # 일일 체크 시간
    'enable_night_trading': False, # 야간 거래 여부
    'night_start_hour': 22,        # 야간 거래 시작 시간
    'night_end_hour': 6,           # 야간 거래 종료 시간

    # 캔들 간격별 권장 체크 주기 (분)
    'interval_check_periods': {
        '1h': 15,    # 1시간 봉 → 15분마다 체크
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
