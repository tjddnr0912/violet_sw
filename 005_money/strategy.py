import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple
from bithumb_api import get_candlestick, get_ticker
from logger import TradingLogger
from datetime import datetime, timedelta
import config

def calculate_moving_average(df: pd.DataFrame, window: int) -> pd.Series:
    """
    주어진 데이터프레임과 윈도우 크기를 사용하여 이동평균을 계산합니다.

    :param df: 시세 정보 DataFrame (종가 'close' 컬럼 필요)
    :param window: 이동평균을 계산할 기간(일)
    :return: 이동평균선 데이터 (pandas Series)
    """
    return df['close'].rolling(window=window).mean()

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    RSI(Relative Strength Index) 계산
    """
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_bollinger_bands(df: pd.DataFrame, window: int = 20, num_std: float = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    볼린저 밴드 계산
    """
    ma = df['close'].rolling(window=window).mean()
    std = df['close'].rolling(window=window).std()

    upper_band = ma + (std * num_std)
    lower_band = ma - (std * num_std)

    return upper_band, ma, lower_band

def calculate_volume_ratio(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """
    거래량 비율 계산 (현재 거래량 / 평균 거래량)
    """
    avg_volume = df['volume'].rolling(window=window).mean()
    return df['volume'] / avg_volume

class TradingStrategy:
    def __init__(self, logger: TradingLogger = None, config_manager=None):
        self.logger = logger or TradingLogger()
        self.config_manager = config_manager
        self.strategy_config = config.STRATEGY_CONFIG

    def get_current_config(self):
        """현재 설정 가져오기 (동적 설정 우선)"""
        if self.config_manager:
            return self.config_manager.get_config()
        return {
            'strategy': self.strategy_config,
            'trading': config.TRADING_CONFIG
        }

    def _get_indicator_config_for_interval(self, interval: str) -> Dict[str, int]:
        """
        캔들 간격에 맞는 지표 설정 반환
        :param interval: 캔들스틱 간격 ('1h', '6h', '12h', '24h')
        :return: 지표 설정 딕셔너리
        """
        # 간격별 프리셋이 있으면 사용
        presets = self.strategy_config.get('interval_presets', {})
        if interval in presets:
            return presets[interval]

        # 프리셋이 없으면 기본값 사용
        return {
            'short_ma_window': self.strategy_config['short_ma_window'],
            'long_ma_window': self.strategy_config['long_ma_window'],
            'rsi_period': self.strategy_config['rsi_period'],
            'analysis_period': self.strategy_config.get('analysis_period', 20)
        }

    def analyze_market_data(self, ticker: str, interval: str = None) -> Optional[Dict[str, Any]]:
        """
        시장 데이터 분석
        :param ticker: 코인 티커 (예: 'BTC')
        :param interval: 캔들스틱 간격 ('1h', '6h', '12h', '24h'). None이면 config에서 가져옴
        """
        try:
            # interval이 지정되지 않으면 config에서 가져오기
            if interval is None:
                interval = self.strategy_config.get('candlestick_interval', '24h')

            # 간격에 맞는 지표 설정 적용
            indicator_config = self._get_indicator_config_for_interval(interval)

            # 가격 데이터 가져오기
            price_data = get_candlestick(ticker, interval)
            if price_data is None or len(price_data) < indicator_config['long_ma_window']:
                self.logger.log_error(f"데이터가 부족합니다: {ticker} (interval: {interval})")
                return None

            # 기술적 지표 계산 (간격에 맞는 설정 사용)
            price_data['short_ma'] = calculate_moving_average(
                price_data, indicator_config['short_ma_window']
            )
            price_data['long_ma'] = calculate_moving_average(
                price_data, indicator_config['long_ma_window']
            )
            price_data['rsi'] = calculate_rsi(
                price_data, indicator_config['rsi_period']
            )

            upper_bb, middle_bb, lower_bb = calculate_bollinger_bands(price_data)
            price_data['bb_upper'] = upper_bb
            price_data['bb_middle'] = middle_bb
            price_data['bb_lower'] = lower_bb

            price_data['volume_ratio'] = calculate_volume_ratio(price_data)

            # 현재 가격 정보
            current_price = price_data['close'].iloc[-1]
            current_volume = price_data['volume'].iloc[-1]

            # 분석 결과
            analysis = {
                'ticker': ticker,
                'interval': interval,  # 사용된 캔들 간격 추가
                'timestamp': datetime.now().isoformat(),
                'current_price': current_price,
                'current_volume': current_volume,
                'short_ma': price_data['short_ma'].iloc[-1],
                'long_ma': price_data['long_ma'].iloc[-1],
                'rsi': price_data['rsi'].iloc[-1],
                'bb_position': (current_price - price_data['bb_lower'].iloc[-1]) /
                              (price_data['bb_upper'].iloc[-1] - price_data['bb_lower'].iloc[-1]),
                'volume_ratio': price_data['volume_ratio'].iloc[-1],
                'price_change_24h': ((current_price - price_data['close'].iloc[-24]) /
                                   price_data['close'].iloc[-24]) * 100 if len(price_data) >= 24 else 0,
                # 사용된 지표 설정 정보 추가
                'indicator_config': {
                    'short_ma_window': indicator_config['short_ma_window'],
                    'long_ma_window': indicator_config['long_ma_window'],
                    'rsi_period': indicator_config['rsi_period']
                }
            }

            return analysis

        except Exception as e:
            self.logger.log_error(f"시장 데이터 분석 오류: {ticker}", e)
            return None

    def generate_signals(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        거래 신호 생성 (동적 설정 적용 및 선택된 지표만 사용)
        """
        current_config = self.get_current_config()
        strategy_config = current_config.get('strategy', self.strategy_config)

        # 활성화된 지표 가져오기 (기본값: 모두 활성화)
        enabled_indicators = strategy_config.get('enabled_indicators', {
            'ma': True,
            'rsi': True,
            'bb': True,
            'volume': True
        })

        signals = {
            'ma_signal': 0,     # -1: 매도, 0: 중립, 1: 매수
            'rsi_signal': 0,
            'bb_signal': 0,
            'volume_signal': 0,
            'overall_signal': 0,
            'confidence': 0.0
        }

        # 이동평균 신호 (활성화된 경우에만)
        if enabled_indicators.get('ma', True):
            if analysis['short_ma'] > analysis['long_ma']:
                signals['ma_signal'] = 1
            elif analysis['short_ma'] < analysis['long_ma']:
                signals['ma_signal'] = -1

        # RSI 신호 (활성화된 경우에만, 동적 임계값 사용)
        if enabled_indicators.get('rsi', True):
            rsi = analysis['rsi']
            rsi_buy_threshold = strategy_config.get('rsi_buy_threshold', 30)
            rsi_sell_threshold = strategy_config.get('rsi_sell_threshold', 70)

            if rsi <= rsi_buy_threshold:
                signals['rsi_signal'] = 1  # 과매도 -> 매수
            elif rsi >= rsi_sell_threshold:
                signals['rsi_signal'] = -1  # 과매수 -> 매도

        # 볼린저 밴드 신호 (활성화된 경우에만)
        if enabled_indicators.get('bb', True):
            bb_pos = analysis['bb_position']
            if bb_pos < 0.2:  # 하단 근처
                signals['bb_signal'] = 1
            elif bb_pos > 0.8:  # 상단 근처
                signals['bb_signal'] = -1

        # 거래량 신호 (활성화된 경우에만)
        if enabled_indicators.get('volume', True):
            if analysis['volume_ratio'] > self.strategy_config['volume_threshold']:
                signals['volume_signal'] = 1

        # 종합 신호 계산 (활성화된 지표만 합산)
        signal_sum = (signals['ma_signal'] + signals['rsi_signal'] +
                     signals['bb_signal'] + signals['volume_signal'])

        # 활성화된 지표 개수 계산
        enabled_count = sum(1 for key, value in enabled_indicators.items() if value)

        # 최소 활성화 지표 개수 확인 (안전장치)
        if enabled_count < 2:
            self.logger.logger.warning("경고: 활성화된 지표가 2개 미만입니다. 최소 2개 이상의 지표를 선택하세요.")
            signals['overall_signal'] = 0  # 관망
            signals['confidence'] = 0.0
            return signals

        # 신뢰도 계산 시 활성화된 지표 개수 기준으로 계산
        if signal_sum >= 2:
            signals['overall_signal'] = 1  # 매수
            signals['confidence'] = min(abs(signal_sum) / enabled_count, 1.0)
        elif signal_sum <= -2:
            signals['overall_signal'] = -1  # 매도
            signals['confidence'] = min(abs(signal_sum) / enabled_count, 1.0)
        else:
            signals['overall_signal'] = 0  # 관망
            signals['confidence'] = 0.3

        return signals

    def decide_action(self, ticker: str) -> Tuple[str, Dict[str, Any]]:
        """
        종합적 분석을 통한 매매 결정
        """
        # 시장 데이터 분석
        analysis = self.analyze_market_data(ticker)
        if not analysis:
            return "HOLD", {}

        # 신호 생성
        signals = self.generate_signals(analysis)

        # 결정 로직
        action = "HOLD"
        reason = "추세 유지"

        if signals['overall_signal'] == 1 and signals['confidence'] > 0.6:
            action = "BUY"
            reason = f"매수 신호 감지 (신뢰도: {signals['confidence']:.2f})"
        elif signals['overall_signal'] == -1 and signals['confidence'] > 0.6:
            action = "SELL"
            reason = f"매도 신호 감지 (신뢰도: {signals['confidence']:.2f})"

        # 로깅
        self.logger.log_strategy_analysis(ticker, {
            'analysis': analysis,
            'signals': signals,
            'action': action,
            'reason': reason
        })

        self.logger.log_trade_decision(ticker, action, reason, analysis)

        return action, {'analysis': analysis, 'signals': signals, 'reason': reason}

    def check_stop_loss_take_profit(self, ticker: str, current_price: float,
                                   holdings: float, avg_buy_price: float) -> Tuple[str, str]:
        """
        손절/익절 조건 확인

        Args:
            ticker: 거래 코인
            current_price: 현재 가격
            holdings: 보유 수량
            avg_buy_price: 평균 매수가

        Returns:
            Tuple[action, reason]: 거래 액션과 이유
        """
        if holdings <= 0 or avg_buy_price <= 0:
            return "HOLD", "보유 물량 없음"

        current_config = self.get_current_config()
        trading_config = current_config.get('trading', {})

        stop_loss_percent = trading_config.get('stop_loss_percent', 5.0)
        take_profit_percent = trading_config.get('take_profit_percent', 3.0)

        # 수익률 계산
        profit_percent = ((current_price - avg_buy_price) / avg_buy_price) * 100

        # 손절 조건 확인
        if profit_percent <= -stop_loss_percent:
            reason = f"손절 실행: {profit_percent:.2f}% 손실 (기준: -{stop_loss_percent}%)"
            self.logger.logger.warning(f"[{ticker}] {reason}")
            return "SELL", reason

        # 익절 조건 확인
        if profit_percent >= take_profit_percent:
            reason = f"익절 실행: {profit_percent:.2f}% 수익 (기준: +{take_profit_percent}%)"
            self.logger.logger.info(f"[{ticker}] {reason}")
            return "SELL", reason

        return "HOLD", f"현재 수익률: {profit_percent:.2f}% (손절: -{stop_loss_percent}%, 익절: +{take_profit_percent}%)"

    def enhanced_decide_action(self, ticker: str, holdings: float = 0,
                             avg_buy_price: float = 0, interval: str = None) -> Tuple[str, Dict[str, Any]]:
        """
        향상된 거래 결정 (손절/익절 포함)
        :param ticker: 코인 티커
        :param holdings: 보유 수량
        :param avg_buy_price: 평균 매수가
        :param interval: 캔들스틱 간격 (None이면 config에서 가져옴)
        """
        # 1. 시장 분석 (지정된 간격으로)
        analysis = self.analyze_market_data(ticker, interval)
        if analysis is None:
            return "HOLD", {"reason": "시장 데이터 분석 실패"}

        current_price = analysis['current_price']

        # 2. 손절/익절 우선 확인
        if holdings > 0 and avg_buy_price > 0:
            stop_action, stop_reason = self.check_stop_loss_take_profit(
                ticker, current_price, holdings, avg_buy_price
            )
            if stop_action == "SELL":
                return stop_action, {"reason": stop_reason, "analysis": analysis}

        # 3. 일반 전략 신호 확인
        signals = self.generate_signals(analysis)

        # 4. 최종 결정
        confidence_threshold = 0.6

        if signals['overall_signal'] >= 2 and signals['confidence'] >= confidence_threshold:
            action = "BUY"
            reason = f"매수 신호 감지 (신뢰도: {signals['confidence']:.2f}, RSI: {analysis['rsi']:.1f})"
        elif signals['overall_signal'] <= -2 and signals['confidence'] >= confidence_threshold:
            action = "SELL"
            reason = f"매도 신호 감지 (신뢰도: {signals['confidence']:.2f}, RSI: {analysis['rsi']:.1f})"
        else:
            action = "HOLD"
            reason = f"관망 (신호: {signals['overall_signal']}, 신뢰도: {signals['confidence']:.2f})"

        # 로깅
        self.logger.log_trade_decision(ticker, action, reason, analysis)

        return action, {'analysis': analysis, 'signals': signals, 'reason': reason}

def decide_action(ticker: str, short_window: int = None, long_window: int = None) -> str:
    """
    기존 인터페이스 유지를 위한 래퍼 함수
    """
    strategy = TradingStrategy()
    action, _ = strategy.decide_action(ticker)
    return action

if __name__ == "__main__":
    strategy = TradingStrategy()
    action, details = strategy.decide_action("BTC")
    print(f"최종 결정: {action}")
    if details:
        print(f"이유: {details['reason']}")
        print(f"분석 데이터: {details['analysis']}")
        print(f"신호: {details['signals']}")