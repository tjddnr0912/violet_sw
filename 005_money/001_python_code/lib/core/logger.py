import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any
from collections import deque
import json

class TradingLogger:
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        self.setup_logger()

    def setup_logger(self):
        """로깅 설정"""
        log_filename = os.path.join(self.log_dir, f"trading_{datetime.now().strftime('%Y%m%d')}.log")

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )

        self.logger = logging.getLogger('TradingBot')

    def log_trade_decision(self, ticker: str, action: str, reason: str, price_data: Dict[str, Any] = None):
        """거래 결정 로그"""
        message = f"[DECISION] {ticker}: {action} - {reason}"
        if price_data:
            message += f" | Price: {price_data.get('closing_price', 'N/A')}"

        self.logger.info(message)

    def log_trade_execution(self, ticker: str, action: str, amount: float, price: float, order_id: str = None, success: bool = True):
        """거래 실행 로그"""
        status = "SUCCESS" if success else "FAILED"
        message = f"[EXECUTION] {status} - {ticker}: {action} {amount} at {price:,.0f} KRW"
        if order_id:
            message += f" | Order ID: {order_id}"

        if success:
            self.logger.info(message)
        else:
            self.logger.error(message)

    def log_balance_update(self, balance_data: Dict[str, Any]):
        """잔고 업데이트 로그"""
        message = f"[BALANCE] Updated balance: {json.dumps(balance_data, ensure_ascii=False)}"
        self.logger.info(message)

    def log_error(self, error_message: str, exception: Exception = None):
        """에러 로그"""
        if exception:
            self.logger.error(f"[ERROR] {error_message}: {str(exception)}")
        else:
            self.logger.error(f"[ERROR] {error_message}")

    def log_strategy_analysis(self, ticker: str, analysis_data: Dict[str, Any]):
        """전략 분석 로그"""
        message = f"[ANALYSIS] {ticker}: {json.dumps(analysis_data, ensure_ascii=False)}"
        self.logger.info(message)

class TransactionHistory:
    # Maximum number of transactions to keep in memory (about 3-6 months of active trading)
    MAX_TRANSACTIONS = 1000

    def __init__(self, history_file: str = "transaction_history.json"):
        self.history_file = history_file
        loaded_history = self.load_history()
        # Use deque with maxlen for automatic size limiting
        self.transactions = deque(loaded_history, maxlen=self.MAX_TRANSACTIONS)

    def load_history(self) -> list:
        """거래 내역 로드"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            print(f"Error loading transaction history: {e}")
            return []

    def save_history(self):
        """거래 내역 저장"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                # Convert deque to list for JSON serialization
                json.dump(list(self.transactions), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving transaction history: {e}")

    def add_transaction(self, ticker: str, action: str, amount: float, price: float,
                       order_id: str = None, fee: float = 0.0, success: bool = True, pnl: float = 0.0):
        """거래 기록 추가"""
        transaction = {
            'timestamp': datetime.now().isoformat(),
            'ticker': ticker,
            'action': action,
            'amount': amount,
            'price': price,
            'total_value': amount * price,
            'fee': fee,
            'order_id': order_id,
            'success': success,
            'pnl': pnl  # Profit/Loss amount (only for SELL transactions)
        }

        self.transactions.append(transaction)
        self.save_history()

    def get_summary(self, ticker: str = None, days: int = None) -> Dict[str, Any]:
        """거래 요약 정보"""
        filtered_transactions = self.transactions

        if ticker:
            filtered_transactions = [t for t in filtered_transactions if t['ticker'] == ticker]

        if days:
            cutoff_date = datetime.now() - timedelta(days=days)
            filtered_transactions = [
                t for t in filtered_transactions
                if datetime.fromisoformat(t['timestamp']) >= cutoff_date
            ]

        if not filtered_transactions:
            return {'total_transactions': 0, 'total_volume': 0, 'total_fees': 0}

        total_volume = sum(t['total_value'] for t in filtered_transactions if t['success'])
        total_fees = sum(t['fee'] for t in filtered_transactions if t['success'])
        buy_count = len([t for t in filtered_transactions if t['action'] == 'BUY' and t['success']])
        sell_count = len([t for t in filtered_transactions if t['action'] == 'SELL' and t['success']])

        return {
            'total_transactions': len(filtered_transactions),
            'successful_transactions': len([t for t in filtered_transactions if t['success']]),
            'buy_count': buy_count,
            'sell_count': sell_count,
            'total_volume': total_volume,
            'total_fees': total_fees
        }

    def generate_report(self, ticker: str = None, days: int = 30) -> str:
        """거래 리포트 생성"""
        summary = self.get_summary(ticker, days)

        report = f"""
=== 거래 내역 리포트 ===
조회 기간: {days}일
대상 코인: {ticker if ticker else '전체'}

총 거래 횟수: {summary['total_transactions']}회
성공한 거래: {summary['successful_transactions']}회
매수 횟수: {summary['buy_count']}회
매도 횟수: {summary['sell_count']}회
총 거래량: {summary['total_volume']:,.0f} KRW
총 수수료: {summary['total_fees']:,.0f} KRW
"""

        return report

class MarkdownTransactionLogger:
    """마크다운 테이블 형태로 거래 내역을 기록하는 로거"""

    def __init__(self, markdown_file: str = "logs/trading_history.md"):
        self.markdown_file = markdown_file
        self.log_dir = os.path.dirname(markdown_file)

        # 로그 디렉토리 생성
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        # 마크다운 파일 초기화 (헤더가 없는 경우에만)
        self.initialize_markdown_file()

    def initialize_markdown_file(self):
        """마크다운 파일 초기화 (헤더 생성)"""
        if not os.path.exists(self.markdown_file):
            header = """# 📊 자동매매 거래 내역

## 거래 기록

| 날짜 | 시간 | 코인 | 거래유형 | 수량 | 단가 | 총금액 | 수수료 | 수익금액 | 수익률 | 메모 |
|------|------|------|----------|------|------|--------|--------|----------|--------|------|

"""
            try:
                with open(self.markdown_file, 'w', encoding='utf-8') as f:
                    f.write(header)
            except Exception as e:
                print(f"마크다운 파일 초기화 오류: {e}")

    def calculate_sell_profit(self, ticker: str, sell_amount: float, sell_price: float,
                             transaction_history, sell_fee: float = 0.0,
                             position_entry_time: str = None, current_sell_time: str = None) -> tuple:
        """
        매도 시 수익 계산 (포지션 기반 FIFO, 수수료 포함, 부분 매도 지원)

        Args:
            ticker: 코인 심볼
            sell_amount: 매도 수량
            sell_price: 매도 단가
            transaction_history: 거래 내역 객체
            sell_fee: 매도 수수료
            position_entry_time: 현재 포지션의 진입 시각 (ISO format)
            current_sell_time: 현재 매도 시각 (자기 자신 제외용, ISO format)

        Returns:
            (profit_amount, profit_rate) 튜플
        """
        try:
            if not transaction_history:
                return 0.0, 0.0

            # 현재 포지션의 매수 거래만 필터링 (시간순 정렬)
            buy_transactions = []
            for t in transaction_history.transactions:
                if (t['ticker'] == ticker and
                    t['action'] == 'BUY' and
                    t['success']):
                    # 포지션 진입 시각이 주어진 경우 해당 포지션의 매수만 포함
                    if position_entry_time:
                        if t['timestamp'] >= position_entry_time:
                            buy_transactions.append(t)
                    else:
                        buy_transactions.append(t)

            buy_transactions.sort(key=lambda x: x['timestamp'])

            # 현재 포지션의 매도 거래 (이전 매도 수량 추적용, 현재 매도 제외)
            sell_transactions = []
            for t in transaction_history.transactions:
                if (t['ticker'] == ticker and
                    t['action'] == 'SELL' and
                    t['success']):
                    # 현재 매도 제외
                    if current_sell_time and t['timestamp'] >= current_sell_time:
                        continue
                    # 포지션 진입 시각이 주어진 경우 해당 포지션의 매도만 포함
                    if position_entry_time:
                        if t['timestamp'] >= position_entry_time:
                            sell_transactions.append(t)
                    else:
                        sell_transactions.append(t)

            sell_transactions.sort(key=lambda x: x['timestamp'])

            # 각 매수 거래에서 이미 매도된 수량 계산 (FIFO)
            buy_remaining = {i: buy_tx['amount'] for i, buy_tx in enumerate(buy_transactions)}

            for sell_tx in sell_transactions:
                remaining_to_deduct = sell_tx['amount']
                for i, buy_tx in enumerate(buy_transactions):
                    if remaining_to_deduct <= 0:
                        break
                    if buy_remaining[i] > 0:
                        deduct = min(remaining_to_deduct, buy_remaining[i])
                        buy_remaining[i] -= deduct
                        remaining_to_deduct -= deduct

            # 현재 매도에 대한 P&L 계산
            total_buy_cost = 0.0  # 매수 비용 (수수료 포함)
            remaining_sell_amount = sell_amount

            # FIFO 방식으로 매수 거래와 매칭 (남은 수량만 사용)
            for i, buy_tx in enumerate(buy_transactions):
                if remaining_sell_amount <= 0:
                    break

                available_amount = buy_remaining[i]
                if available_amount <= 0:
                    continue

                buy_amount = buy_tx['amount']
                buy_price = buy_tx['price']
                buy_fee = buy_tx.get('fee', 0.0)  # 매수 수수료

                # 이번 매수 거래에서 처리할 수량 (남은 수량 기준)
                matched_amount = min(remaining_sell_amount, available_amount)

                # 해당 수량에 대한 매수 비용 계산 (수수료 비례 배분)
                matched_cost = matched_amount * buy_price
                matched_fee = (matched_amount / buy_amount) * buy_fee if buy_amount > 0 else 0.0
                total_buy_cost += matched_cost + matched_fee

                remaining_sell_amount -= matched_amount

            # 매도 총액 (수수료 차감)
            sell_total = (sell_amount * sell_price) - sell_fee

            # 수익 계산 (실제 수령액 - 실제 투자액)
            profit_amount = sell_total - total_buy_cost
            profit_rate = (profit_amount / total_buy_cost * 100) if total_buy_cost > 0 else 0.0

            return profit_amount, profit_rate

        except Exception as e:
            print(f"수익 계산 오류: {e}")
            return 0.0, 0.0

    def log_transaction(self, ticker: str, action: str, amount: float, price: float,
                       order_id: str = None, fee: float = 0.0, success: bool = True,
                       transaction_history=None, position_entry_time: str = None):
        """거래 내역을 마크다운 테이블에 기록"""
        try:
            now = datetime.now()
            date_str = now.strftime('%Y-%m-%d')
            time_str = now.strftime('%H:%M:%S')

            # 총 거래금액
            total_amount = amount * price

            # 수익 정보 (매도인 경우에만)
            profit_amount = 0.0
            profit_rate = 0.0
            profit_str = "-"
            profit_rate_str = "-"

            if action == "SELL" and success and transaction_history:
                # 현재 시각을 ISO format으로 전달 (자기 자신 제외용)
                current_sell_time = now.isoformat()
                profit_amount, profit_rate = self.calculate_sell_profit(
                    ticker, amount, price, transaction_history,
                    sell_fee=fee,
                    position_entry_time=position_entry_time,
                    current_sell_time=current_sell_time
                )
                if profit_amount != 0:
                    profit_str = f"{profit_amount:+,.0f}원"
                    profit_rate_str = f"{profit_rate:+.2f}%"

            # 거래 유형 이모지
            action_emoji = "🔵 매수" if action == "BUY" else "🔴 매도"

            # 상태 표시
            status_memo = "✅ 성공" if success else "❌ 실패"
            if order_id and order_id.startswith("DRY_RUN"):
                status_memo += " (모의거래)"

            # 테이블 행 생성
            table_row = (
                f"| {date_str} | {time_str} | {ticker} | {action_emoji} | "
                f"{amount:.6f} | {price:,.0f}원 | {total_amount:,.0f}원 | "
                f"{fee:,.0f}원 | {profit_str} | {profit_rate_str} | {status_memo} |\n"
            )

            # 파일에 추가
            with open(self.markdown_file, 'a', encoding='utf-8') as f:
                f.write(table_row)

        except Exception as e:
            print(f"마크다운 로그 기록 오류: {e}")

    def add_summary_section(self, period_days: int = 30):
        """요약 섹션을 마크다운 파일에 추가"""
        try:
            summary_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            summary_section = f"""

## 📈 거래 요약 ({period_days}일) - {summary_date}

> 최근 {period_days}일간의 거래 활동 요약

### 주요 통계
- **총 거래 횟수**: 계산 필요
- **성공한 거래**: 계산 필요
- **총 거래량**: 계산 필요
- **총 수수료**: 계산 필요

---

"""

            with open(self.markdown_file, 'a', encoding='utf-8') as f:
                f.write(summary_section)

        except Exception as e:
            print(f"요약 섹션 추가 오류: {e}")

    def get_markdown_file_path(self) -> str:
        """마크다운 파일 경로 반환"""
        return os.path.abspath(self.markdown_file)