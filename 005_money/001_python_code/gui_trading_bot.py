#!/usr/bin/env python3
"""
GUI용 거래 봇 래퍼
실시간 상태 업데이트를 위한 GUI 전용 봇 클래스
"""

import threading
import time
import queue
from datetime import datetime
from typing import Dict, Any, Optional, Callable

from trading_bot import TradingBot
from bithumb_api import get_ticker
from logger import TradingLogger, TransactionHistory
import config

class GUITradingBot(TradingBot):
    def __init__(self, status_callback: Callable = None):
        super().__init__()
        self.status_callback = status_callback
        self.current_status = {
            'coin': self.config['trading']['target_ticker'],
            'current_price': 0,
            'avg_buy_price': 0,
            'holdings': 0,
            'pending_orders': [],
            'last_action': 'HOLD',
            'last_update': datetime.now()
        }

        # 가격 모니터링 스레드
        self.price_monitor_thread = None
        self.monitoring = False

        # 미체결 주문 조회 비활성화 로그 플래그 (1회만 출력)
        self._pending_orders_log_shown = False

    def start_price_monitoring(self):
        """가격 모니터링 시작"""
        if not self.monitoring:
            self.monitoring = True
            self.price_monitor_thread = threading.Thread(target=self._price_monitor_loop, daemon=True)
            self.price_monitor_thread.start()

    def stop_price_monitoring(self):
        """가격 모니터링 중지"""
        self.monitoring = False

    def _price_monitor_loop(self):
        """가격 모니터링 루프"""
        while self.monitoring:
            try:
                self.update_current_price()
                self.update_holdings()
                self.update_pending_orders()

                if self.status_callback:
                    self.status_callback(self.current_status.copy())

                time.sleep(5)  # 5초마다 업데이트

            except Exception as e:
                self.logger.log_error(f"가격 모니터링 오류: {e}")
                time.sleep(30)  # 오류 시 30초 대기

    def update_current_price(self):
        """현재 가격 업데이트"""
        try:
            ticker_data = get_ticker(self.current_status['coin'])
            if ticker_data:
                self.current_status['current_price'] = float(ticker_data.get('closing_price', 0))
                self.current_status['last_update'] = datetime.now()
        except Exception as e:
            self.logger.log_error(f"가격 조회 오류: {e}")

    def update_holdings(self):
        """보유 수량 업데이트"""
        try:
            if not self.config['safety']['dry_run']:
                # 실제 거래 모드에서는 API로 잔고 조회
                coin_balance = self.get_current_balance(self.current_status['coin'])
                self.current_status['holdings'] = coin_balance
            else:
                # 모의 거래 모드에서는 거래 내역에서 계산
                self.current_status['holdings'] = self.calculate_holdings_from_history()

        except Exception as e:
            self.logger.log_error(f"보유량 조회 오류: {e}")

    def update_pending_orders(self):
        """미체결 주문 업데이트"""
        try:
            if not self.config['safety']['dry_run']:
                # 실제 거래 모드에서는 미체결 주문 조회 비활성화 (보안상 이유)
                # 처음 1회만 로그 출력
                if not self._pending_orders_log_shown:
                    self.logger.logger.info("미체결 주문 조회가 보안상의 이유로 비활성화되었습니다.")
                    self._pending_orders_log_shown = True
                self.current_status['pending_orders'] = []
                return

                # 기존 코드 (비활성화됨)
                # orders_response = self.api.get_orders(self.current_status['coin'])
                if orders_response and orders_response.get('status') == '0000':
                    self.current_status['pending_orders'] = orders_response.get('data', [])
                else:
                    self.current_status['pending_orders'] = []
            else:
                # 모의 거래에서는 미체결 주문이 없음
                self.current_status['pending_orders'] = []

        except Exception as e:
            self.logger.log_error(f"미체결 주문 조회 오류: {e}")
            self.current_status['pending_orders'] = []

    def calculate_holdings_from_history(self) -> float:
        """거래 내역에서 보유량 계산"""
        try:
            holdings = 0.0
            coin = self.current_status['coin']

            for transaction in self.transaction_history.transactions:
                if transaction['ticker'] == coin and transaction['success']:
                    if transaction['action'] == 'BUY':
                        holdings += transaction['amount']
                    elif transaction['action'] == 'SELL':
                        holdings -= transaction['amount']

            return max(0, holdings)  # 음수 방지

        except Exception as e:
            self.logger.log_error(f"보유량 계산 오류: {e}")
            return 0.0

    def calculate_avg_buy_price(self) -> float:
        """평균 매수가 계산"""
        try:
            total_amount = 0.0
            total_cost = 0.0
            coin = self.current_status['coin']

            for transaction in self.transaction_history.transactions:
                if (transaction['ticker'] == coin and
                    transaction['success'] and
                    transaction['action'] == 'BUY'):

                    amount = transaction['amount']
                    price = transaction['price']

                    total_amount += amount
                    total_cost += amount * price

            return total_cost / total_amount if total_amount > 0 else 0.0

        except Exception as e:
            self.logger.log_error(f"평균 매수가 계산 오류: {e}")
            return 0.0

    def run_trading_cycle(self) -> bool:
        """거래 사이클 실행 (GUI용 오버라이드)"""
        try:
            success = super().run_trading_cycle()

            # 거래 실행 후 상태 업데이트
            self.current_status['avg_buy_price'] = self.calculate_avg_buy_price()

            return success

        except Exception as e:
            self.logger.log_error(f"GUI 거래 사이클 오류: {e}")
            return False

    def execute_trading_decision(self, ticker: str) -> bool:
        """거래 결정 실행 (GUI용 오버라이드) - 엘리트 전략 사용"""
        try:
            # 시장 데이터 분석 (엘리트 지표 포함)
            interval = self.config.get('strategy', {}).get('candlestick_interval', '1h')
            analysis = self.strategy.analyze_market_data(ticker, interval)
            if not analysis:
                return False

            # 가중치 기반 신호 생성 (엘리트 전략)
            signals = self.strategy.generate_weighted_signals(analysis)

            # 신호 및 분석 결과를 상태에 추가 (GUI 업데이트용)
            self.current_status['signals'] = signals
            self.current_status['analysis'] = analysis

            # 최종 액션 결정
            final_action = signals.get('final_action', 'HOLD')
            self.current_status['last_action'] = final_action

            # 로깅
            log_analysis = analysis.copy()
            log_analysis.pop('price_data', None)  # DataFrame 제거
            self.logger.log_strategy_analysis(ticker, {
                'analysis': log_analysis,
                'signals': signals,
                'action': final_action,
                'reason': signals.get('reason', '')
            })

            if final_action == "HOLD":
                return True

            # 거래 실행 (실제 매수/매도)
            # NOTE: 이 부분은 기존 TradingBot의 로직을 사용
            # 실제로는 더 세밀한 주문 관리 필요
            if final_action == "BUY":
                success = self._execute_buy(ticker, analysis['current_price'])
            elif final_action == "SELL":
                success = self._execute_sell(ticker, analysis['current_price'])
            else:
                success = False

            # 거래 실행 후 상태 업데이트
            if success:
                self.current_status['avg_buy_price'] = self.calculate_avg_buy_price()
                self.update_holdings()

            return success

        except Exception as e:
            self.logger.log_error(f"GUI 거래 결정 실행 오류: {e}")
            return False

    def _execute_buy(self, ticker: str, current_price: float) -> bool:
        """매수 실행 (내부 메서드)"""
        try:
            trade_amount_krw = self.config['trading']['trade_amount_krw']

            if self.config['safety']['dry_run']:
                # 모의 거래
                amount = trade_amount_krw / current_price
                self.transaction_history.add_transaction(
                    ticker=ticker,
                    action='BUY',
                    amount=amount,
                    price=current_price,
                    total_value=trade_amount_krw,
                    fee=0,
                    success=True,
                    note='모의 거래'
                )
                self.logger.logger.info(f"[모의 거래] 매수: {ticker} {amount:.6f}개 @ {current_price:,.0f}원")
                return True
            else:
                # 실제 거래 (여기서는 간단하게 처리, 실제로는 더 복잡함)
                # TODO: 실제 빗썸 API 호출
                return False

        except Exception as e:
            self.logger.log_error(f"매수 실행 오류: {e}")
            return False

    def _execute_sell(self, ticker: str, current_price: float) -> bool:
        """매도 실행 (내부 메서드)"""
        try:
            holdings = self.calculate_holdings_from_history()

            if holdings <= 0:
                self.logger.logger.warning(f"매도 실패: 보유 수량 없음 ({ticker})")
                return False

            if self.config['safety']['dry_run']:
                # 모의 거래
                total_value = holdings * current_price
                self.transaction_history.add_transaction(
                    ticker=ticker,
                    action='SELL',
                    amount=holdings,
                    price=current_price,
                    total_value=total_value,
                    fee=0,
                    success=True,
                    note='모의 거래'
                )
                self.logger.logger.info(f"[모의 거래] 매도: {ticker} {holdings:.6f}개 @ {current_price:,.0f}원")
                return True
            else:
                # 실제 거래
                # TODO: 실제 빗썸 API 호출
                return False

        except Exception as e:
            self.logger.log_error(f"매도 실행 오류: {e}")
            return False

    def change_coin(self, new_coin: str):
        """거래 코인 변경"""
        try:
            self.current_status['coin'] = new_coin
            self.config['trading']['target_ticker'] = new_coin

            # 설정 업데이트
            config.TRADING_CONFIG['target_ticker'] = new_coin

            # 상태 초기화
            self.current_status['current_price'] = 0
            self.current_status['avg_buy_price'] = self.calculate_avg_buy_price()
            self.update_holdings()

            self.logger.logger.info(f"거래 코인이 {new_coin}로 변경되었습니다.")

        except Exception as e:
            self.logger.log_error(f"코인 변경 오류: {e}")

    def change_interval(self, new_interval: str):
        """체크 간격 변경"""
        try:
            from config_manager import ConfigManager
            config_manager = ConfigManager()

            # 간격 파싱
            interval_info = config_manager.parse_interval(new_interval)

            if interval_info['type'] == 'seconds':
                self.config['schedule']['check_interval_seconds'] = interval_info['value']
                self.config['schedule']['check_interval_minutes'] = max(1, interval_info['value'] // 60)
            elif interval_info['type'] == 'minutes':
                self.config['schedule']['check_interval_minutes'] = interval_info['value']
                self.config['schedule']['check_interval_seconds'] = interval_info['value'] * 60
            elif interval_info['type'] == 'hours':
                self.config['schedule']['check_interval_minutes'] = interval_info['value'] * 60
                self.config['schedule']['check_interval_seconds'] = interval_info['value'] * 3600

            # 전역 설정 업데이트
            config.SCHEDULE_CONFIG.update(self.config['schedule'])

            self.logger.logger.info(f"체크 간격이 {new_interval}로 변경되었습니다.")

        except Exception as e:
            self.logger.log_error(f"간격 변경 오류: {e}")

    def change_amount(self, new_amount: int):
        """거래 금액 변경"""
        try:
            self.config['trading']['trade_amount_krw'] = new_amount
            config.TRADING_CONFIG['trade_amount_krw'] = new_amount

            self.logger.logger.info(f"거래 금액이 {new_amount:,}원으로 변경되었습니다.")

        except Exception as e:
            self.logger.log_error(f"거래 금액 변경 오류: {e}")

    def get_status(self) -> Dict[str, Any]:
        """현재 상태 반환"""
        return self.current_status.copy()

    def get_profit_summary(self, days: int = 1) -> Dict[str, Any]:
        """수익 요약 반환"""
        try:
            coin = self.current_status['coin']
            summary = self.transaction_history.get_summary(coin, days)

            # 실현 수익 계산
            realized_profit = 0.0
            for transaction in self.transaction_history.transactions:
                if (transaction['ticker'] == coin and
                    transaction['success'] and
                    transaction['action'] == 'SELL'):

                    # 간단한 수익 계산 (실제로는 더 복잡한 FIFO/LIFO 계산 필요)
                    realized_profit += transaction['total_value']

            # 미실현 수익 계산
            current_holdings = self.current_status['holdings']
            avg_buy_price = self.current_status['avg_buy_price']
            current_price = self.current_status['current_price']

            unrealized_profit = 0.0
            if current_holdings > 0 and avg_buy_price > 0:
                unrealized_profit = current_holdings * (current_price - avg_buy_price)

            summary.update({
                'realized_profit': realized_profit,
                'unrealized_profit': unrealized_profit,
                'total_profit': realized_profit + unrealized_profit,
                'current_holdings': current_holdings,
                'avg_buy_price': avg_buy_price
            })

            return summary

        except Exception as e:
            self.logger.log_error(f"수익 요약 계산 오류: {e}")
            return {
                'realized_profit': 0.0,
                'unrealized_profit': 0.0,
                'total_profit': 0.0,
                'total_transactions': 0,
                'successful_transactions': 0
            }