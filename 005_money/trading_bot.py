import time
import json
from datetime import datetime
from typing import Dict, Any, Optional
from bithumb_api import BithumbAPI
from strategy import TradingStrategy
from logger import TradingLogger, TransactionHistory, MarkdownTransactionLogger
from portfolio_manager import PortfolioManager
import config

class TradingBot:
    def __init__(self):
        self.config = config.get_config()
        self.logger = TradingLogger(self.config['logging']['log_dir'])
        self.transaction_history = TransactionHistory()
        self.markdown_logger = MarkdownTransactionLogger()

        # API 초기화
        api_config = self.config['api']
        self.api = BithumbAPI(
            connect_key=api_config['connect_key'],
            secret_key=api_config['secret_key']
        )

        # 전략 초기화
        self.strategy = TradingStrategy(self.logger)

        # 포트폴리오 관리자 초기화
        self.portfolio_manager = PortfolioManager(self.api, self.transaction_history)

        # 상태 추적
        self.is_authenticated = False
        self.current_balance = {}
        self.daily_trade_count = 0
        self.last_trade_time = None

    def authenticate(self) -> bool:
        """
        빗썸 API 인증 및 계정 정보 확인
        """
        try:
            if self.config['safety']['dry_run']:
                self.logger.logger.info("모의 거래 모드로 실행 중입니다.")
                self.is_authenticated = True
                return True

            # 잔고 조회 기능 비활성화 - 인증은 거래 시에만 확인
            self.current_balance = {}
            self.is_authenticated = True
            self.logger.logger.info("빗썸 API 인증 확인 (잔고 조회 비활성화)")
            return True

        except Exception as e:
            self.logger.log_error("인증 과정에서 오류 발생", e)
            return False

    def get_current_balance(self, currency: str = "KRW") -> float:
        """
        현재 잔고 조회
        """
        try:
            if self.config['safety']['dry_run']:
                # 모의 거래 모드에서는 가상 잔고 반환
                if currency == "KRW":
                    return 1000000.0  # 100만원 가상 잔고
                else:
                    return 0.1  # 0.1 코인 가상 잔고

            # 실제 거래 모드 - 빗썸 API로 실제 잔고 조회
            # 빗썸 API는 'ALL'을 파라미터로 사용하여 모든 잔고를 조회
            balance_response = self.api.get_balance("ALL")

            if balance_response and balance_response.get('status') == '0000':
                data = balance_response.get('data', {})

                if currency == "KRW":
                    # KRW 잔고: available_krw 필드 사용
                    available_balance = data.get('available_krw', '0')
                else:
                    # 코인 잔고: available_{currency} 필드 사용 (소문자)
                    available_balance = data.get(f'available_{currency.lower()}', '0')

                return float(available_balance)
            else:
                error_msg = balance_response.get('message', 'Unknown error') if balance_response else 'No response'
                self.logger.log_error(f"잔고 조회 실패: {currency} - {error_msg}")
                return 0.0

        except Exception as e:
            self.logger.log_error(f"잔고 조회 오류: {currency}", e)
            return 0.0

    def calculate_trade_amount(self, action: str, ticker: str, current_price: float) -> float:
        """
        거래할 수량 계산
        """
        try:
            if action == "BUY":
                available_krw = self.get_current_balance("KRW")
                trade_amount_krw = min(
                    self.config['trading']['trade_amount_krw'],
                    available_krw * 0.99  # 수수료 고려하여 99% 사용
                )

                if trade_amount_krw < self.config['trading']['min_trade_amount']:
                    return 0.0

                # KRW 금액을 코인 수량으로 변환
                coin_amount = trade_amount_krw / current_price
                return coin_amount

            elif action == "SELL":
                available_coin = self.get_current_balance(ticker)
                # 보유 코인의 일정 비율 매도 (기본 50%)
                sell_ratio = 0.5
                return available_coin * sell_ratio

            return 0.0

        except Exception as e:
            self.logger.log_error(f"거래 수량 계산 오류: {action} {ticker}", e)
            return 0.0

    def get_average_buy_price(self, ticker: str) -> float:
        """
        평균 매수가 계산
        """
        try:
            total_amount = 0.0
            total_cost = 0.0

            for transaction in self.transaction_history.transactions:
                if (transaction['ticker'] == ticker and
                    transaction['success'] and
                    transaction['action'] == 'BUY'):

                    amount = transaction['amount']
                    price = transaction['price']

                    total_amount += amount
                    total_cost += amount * price

            return total_cost / total_amount if total_amount > 0 else 0.0

        except Exception as e:
            self.logger.log_error(f"평균 매수가 계산 오류: {ticker}", e)
            return 0.0

    def execute_trade(self, ticker: str, action: str, amount: float, current_price: float) -> bool:
        """
        실제 거래 실행
        """
        try:
            if self.config['safety']['dry_run']:
                # 모의 거래 모드
                total_value = amount * current_price
                self.logger.log_trade_execution(
                    ticker, action, amount, current_price,
                    order_id="DRY_RUN_" + str(int(time.time())),
                    success=True
                )

                # 모의 거래 내역 기록 (테스트 모드가 아닌 경우에만)
                if not self.config['safety'].get('test_mode', False):
                    fee = total_value * self.config['trading']['trading_fee_rate']
                    order_id = "DRY_RUN_" + str(int(time.time()))

                    self.transaction_history.add_transaction(
                        ticker, action, amount, current_price,
                        order_id=order_id,
                        fee=fee,
                        success=True
                    )

                    # 마크다운 거래 로그 기록
                    self.markdown_logger.log_transaction(
                        ticker, action, amount, current_price,
                        order_id=order_id,
                        fee=fee,
                        success=True,
                        transaction_history=self.transaction_history
                    )
                else:
                    self.logger.logger.info(f"[TEST MODE] 거래 내역 기록 건너뜀: {action} {amount:.6f} {ticker}")
                return True

            # 실제 거래 실행 전 API 키 검증
            if not self._verify_api_credentials():
                self.logger.log_error("API 인증 실패로 거래를 중단합니다.")
                return False

            # 실제 거래 실행
            if action == "BUY":
                response = self.api.place_buy_order(ticker, units=amount)
            elif action == "SELL":
                response = self.api.place_sell_order(ticker, units=amount)
            else:
                return False

            if response and response.get('status') == '0000':
                order_id = response.get('order_id', 'N/A')
                total_value = amount * current_price

                self.logger.log_trade_execution(
                    ticker, action, amount, current_price, order_id, True
                )

                # 거래 내역 기록 (테스트 모드가 아닌 경우에만)
                if not self.config['safety'].get('test_mode', False):
                    fee = total_value * self.config['trading']['trading_fee_rate']

                    self.transaction_history.add_transaction(
                        ticker, action, amount, current_price,
                        order_id=order_id,
                        fee=fee,
                        success=True
                    )

                    # 마크다운 거래 로그 기록
                    self.markdown_logger.log_transaction(
                        ticker, action, amount, current_price,
                        order_id=order_id,
                        fee=fee,
                        success=True,
                        transaction_history=self.transaction_history
                    )
                else:
                    self.logger.logger.info(f"[TEST MODE] 실거래 내역 기록 건너뜀: {action} {amount:.6f} {ticker}")

                self.daily_trade_count += 1
                self.last_trade_time = datetime.now()
                return True
            else:
                error_msg = response.get('message', 'Unknown error') if response else 'No response'
                self.logger.log_trade_execution(
                    ticker, action, amount, current_price, success=False
                )
                self.logger.log_error(f"거래 실행 실패: {error_msg}")

                # 실패한 거래도 마크다운 로그에 기록 (테스트 모드가 아닌 경우에만)
                if not self.config['safety'].get('test_mode', False):
                    self.markdown_logger.log_transaction(
                        ticker, action, amount, current_price,
                        success=False,
                        transaction_history=self.transaction_history
                    )
                else:
                    self.logger.logger.info(f"[TEST MODE] 실패 거래 내역 기록 건너뜀: {action} {amount:.6f} {ticker}")
                return False

        except Exception as e:
            self.logger.log_error(f"거래 실행 중 오류 발생: {action} {ticker}", e)
            return False

    def check_safety_limits(self) -> bool:
        """
        안전 제한 사항 확인
        """
        # 긴급 정지 확인
        if self.config['safety']['emergency_stop']:
            self.logger.logger.warning("긴급 정지가 활성화되어 있습니다.")
            return False

        # 일일 거래 한도 확인
        if self.daily_trade_count >= self.config['safety']['max_daily_trades']:
            self.logger.logger.warning(f"일일 거래 한도 초과: {self.daily_trade_count}")
            return False

        return True

    def execute_trading_decision(self, ticker: str) -> bool:
        """
        거래 결정 실행
        """
        try:
            # 안전 제한 확인
            if not self.check_safety_limits():
                return False

            # 설정된 캔들 간격 가져오기
            interval = self.config['strategy'].get('candlestick_interval', '24h')

            # 보유 정보 가져오기 (손절/익절 확인용)
            holdings = self.get_current_balance(ticker) if not self.config['safety']['dry_run'] else 0
            avg_buy_price = self.get_average_buy_price(ticker)

            # 향상된 전략 분석 (손절/익절 포함, 캔들 간격 전달)
            if hasattr(self.strategy, 'enhanced_decide_action'):
                action, details = self.strategy.enhanced_decide_action(ticker, holdings, avg_buy_price, interval)
            else:
                action, details = self.strategy.decide_action(ticker)

            if action == "HOLD":
                return True

            # 현재 가격 정보 가져오기
            current_price = details['analysis']['current_price']

            # 거래 수량 계산
            trade_amount = self.calculate_trade_amount(action, ticker, current_price)

            if trade_amount <= 0:
                self.logger.logger.warning(f"거래 수량이 부족합니다: {action} {ticker}")
                return False

            # 최소 거래 금액 확인
            trade_value_krw = trade_amount * current_price
            if trade_value_krw < self.config['trading']['min_trade_amount']:
                self.logger.logger.warning(f"최소 거래 금액 미달: {trade_value_krw:,.0f} KRW")
                return False

            # 거래 실행
            success = self.execute_trade(ticker, action, trade_amount, current_price)

            if success:
                self.logger.logger.info(
                    f"거래 성공: {action} {trade_amount:.6f} {ticker} at {current_price:,.0f} KRW"
                )

            return success

        except Exception as e:
            self.logger.log_error(f"거래 결정 실행 중 오류: {ticker}", e)
            return False

    def run_trading_cycle(self) -> None:
        """
        한 번의 거래 사이클 실행
        """
        try:
            if not self.is_authenticated:
                if not self.authenticate():
                    self.logger.log_error("인증 실패로 거래를 중단합니다.")
                    return

            ticker = self.config['trading']['target_ticker']
            self.logger.logger.info(f"거래 사이클 시작: {ticker}")

            # 거래 실행
            self.execute_trading_decision(ticker)

            # 잔고 업데이트 (일정 간격으로)
            if (not self.last_trade_time or
                (datetime.now() - self.last_trade_time).total_seconds() >
                self.config['safety']['balance_check_interval'] * 60):

                current_balance = self.get_current_balance("KRW")
                coin_balance = self.get_current_balance(ticker)

                balance_info = {
                    'krw_balance': current_balance,
                    f'{ticker.lower()}_balance': coin_balance,
                    'timestamp': datetime.now().isoformat()
                }
                self.logger.log_balance_update(balance_info)

            # 포트폴리오 변화 로깅 (매 사이클마다)
            self.log_portfolio_change()

        except Exception as e:
            self.logger.log_error("거래 사이클 실행 중 오류 발생", e)

    def generate_daily_report(self) -> str:
        """
        일일 거래 리포트 생성
        """
        ticker = self.config['trading']['target_ticker']
        report = self.transaction_history.generate_report(ticker, days=1)

        # 현재 잔고 정보 추가
        krw_balance = self.get_current_balance("KRW")
        coin_balance = self.get_current_balance(ticker)

        report += f"""
=== 현재 잔고 정보 ===
KRW 잔고: {krw_balance:,.0f} 원
{ticker} 잔고: {coin_balance:.6f} 개
일일 거래 횟수: {self.daily_trade_count}회
"""

        return report

    def reset_daily_counters(self):
        """
        일일 카운터 리셋
        """
        self.daily_trade_count = 0
        self.logger.logger.info("일일 거래 카운터가 리셋되었습니다.")

    def get_account_summary(self, force_refresh: bool = False):
        """
        계정 종합 정보 조회
        """
        return self.portfolio_manager.get_account_summary(force_refresh)

    def get_portfolio_status_text(self) -> str:
        """
        포트폴리오 현황을 텍스트로 반환
        """
        return self.portfolio_manager.get_portfolio_status_text()

    def get_detailed_balance_info(self) -> Dict[str, Any]:
        """
        상세 잔고 정보 조회 (GUI용)
        """
        try:
            summary = self.portfolio_manager.get_account_summary()
            if not summary:
                return {
                    'error': True,
                    'message': '계정 정보를 가져올 수 없습니다.'
                }

            # GUI에 표시할 수 있는 형태로 데이터 구성
            detailed_info = {
                'error': False,
                'last_updated': summary.last_updated.strftime('%Y-%m-%d %H:%M:%S'),
                'krw_info': {
                    'total': summary.krw_balance,
                    'available': summary.krw_available,
                    'in_use': summary.krw_in_use,
                },
                'portfolio_summary': {
                    'total_value': summary.total_portfolio_value,
                    'coin_value': summary.total_coin_value,
                    'total_invested': summary.total_invested,
                    'profit_loss': summary.total_profit_loss,
                    'profit_rate': summary.total_profit_rate,
                },
                'holdings': []
            }

            # 각 코인 보유 현황
            for holding in summary.coin_holdings:
                detailed_info['holdings'].append({
                    'ticker': holding.ticker,
                    'balance': holding.balance,
                    'available': holding.available,
                    'in_use': holding.in_use,
                    'avg_buy_price': holding.average_buy_price,
                    'current_price': holding.current_price,
                    'current_value': holding.current_value,
                    'profit_loss': holding.profit_loss,
                    'profit_rate': holding.profit_rate,
                    'total_invested': holding.total_invested
                })

            return detailed_info

        except Exception as e:
            self.logger.log_error("상세 잔고 정보 조회 오류", e)
            return {
                'error': True,
                'message': f'오류 발생: {str(e)}'
            }

    def get_markdown_log_path(self) -> str:
        """
        마크다운 거래 로그 파일 경로 반환
        """
        return self.markdown_logger.get_markdown_file_path()

    def display_startup_account_info(self) -> str:
        """
        시작 시 표시할 계정 정보 요약
        """
        try:
            summary = self.portfolio_manager.get_account_summary()
            if not summary:
                return "❌ 계정 정보를 가져올 수 없습니다."

            startup_info = f"""
🏦 === 계정 현황 ===
💰 보유 현금: {summary.krw_available:,.0f}원 (총 {summary.krw_balance:,.0f}원)
💎 코인 자산: {summary.total_coin_value:,.0f}원 ({len(summary.coin_holdings)}개 코인)
💼 총 자산: {summary.total_portfolio_value:,.0f}원
{"📈" if summary.total_profit_loss >= 0 else "📉"} 총 수익률: {summary.total_profit_rate:+.2f}% ({summary.total_profit_loss:+,.0f}원)"""

            # 주요 보유 코인 (상위 3개)
            if summary.coin_holdings:
                sorted_holdings = sorted(summary.coin_holdings, key=lambda x: x.current_value, reverse=True)
                startup_info += "\n\n🪙 주요 보유 코인:"

                for holding in sorted_holdings[:3]:
                    profit_emoji = "📈" if holding.profit_loss >= 0 else "📉"
                    startup_info += f"\n  • {holding.ticker}: {holding.balance:.6f}개 ({holding.current_value:,.0f}원) {profit_emoji} {holding.profit_rate:+.2f}%"

            return startup_info

        except Exception as e:
            self.logger.log_error("시작 계정 정보 표시 오류", e)
            return f"⚠️ 계정 정보 조회 중 오류 발생: {str(e)}"

    def log_portfolio_change(self):
        """
        포트폴리오 변화를 로그에 기록
        """
        try:
            summary = self.portfolio_manager.get_account_summary()
            if summary:
                self.logger.logger.info(f"포트폴리오 현황 - 총자산: {summary.total_portfolio_value:,.0f}원, 수익률: {summary.total_profit_rate:+.2f}%")

                # 거래 통계
                trading_summary = self.portfolio_manager.get_trading_summary(days=1)
                if trading_summary:
                    self.logger.logger.info(
                        f"일일 거래 통계 - 총 {trading_summary['total_transactions']}회 "
                        f"(매수: {trading_summary['buy_count']}, 매도: {trading_summary['sell_count']})"
                    )

        except Exception as e:
            self.logger.log_error("포트폴리오 변화 로깅 오류", e)

    def generate_comprehensive_report(self) -> str:
        """
        포괄적인 거래 리포트 생성
        """
        try:
            # 기존 일일 리포트
            basic_report = self.generate_daily_report()

            # 포트폴리오 현황 추가
            portfolio_status = self.portfolio_manager.get_portfolio_status_text()

            # 거래 통계
            trading_summary = self.portfolio_manager.get_trading_summary(days=7)  # 7일간

            stats_text = f"""
📊 === 주간 거래 통계 (7일) ===
총 거래 횟수: {trading_summary.get('total_transactions', 0)}회
성공한 거래: {trading_summary.get('successful_transactions', 0)}회
매수: {trading_summary.get('buy_count', 0)}회 | 매도: {trading_summary.get('sell_count', 0)}회
총 수수료: {trading_summary.get('total_fees', 0):,.0f}원
거래한 코인: {', '.join(trading_summary.get('coins_traded', []))}
"""

            return f"{basic_report}\n{portfolio_status}\n{stats_text}"

        except Exception as e:
            self.logger.log_error("포괄적 리포트 생성 오류", e)
            return self.generate_daily_report()  # 기본 리포트라도 반환