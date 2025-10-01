"""
포트폴리오 관리 및 계정 정보 분석 모듈

이 모듈은 빗썸 API를 통해 얻은 계정 정보를 분석하고,
포트폴리오 현황, 수익률, 평균 매수가 등을 계산합니다.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from bithumb_api import BithumbAPI, get_ticker
import config

@dataclass
class CoinHolding:
    """코인 보유 정보"""
    ticker: str
    balance: float
    available: float
    in_use: float
    average_buy_price: float
    current_price: float
    total_invested: float
    current_value: float
    profit_loss: float
    profit_rate: float

@dataclass
class AccountSummary:
    """계정 종합 정보"""
    krw_balance: float
    krw_available: float
    krw_in_use: float
    total_coin_value: float
    total_portfolio_value: float
    total_invested: float
    total_profit_loss: float
    total_profit_rate: float
    coin_holdings: List[CoinHolding]
    last_updated: datetime

class PortfolioManager:
    """포트폴리오 관리 클래스"""

    def __init__(self, api: BithumbAPI, transaction_history=None):
        self.api = api
        self.transaction_history = transaction_history
        self.config = config.get_config()
        self.account_cache = {}
        self.cache_expiry = 60  # 60초 캐시

    def get_all_balances(self) -> Optional[Dict]:
        """모든 코인의 잔고 조회"""
        try:
            if self.config['safety']['dry_run']:
                # 모의 거래 모드에서는 가상 잔고 반환
                return self._get_mock_balances()

            # 실제 거래 모드: 실제 API 호출
            balance_response = self.api.get_balance("ALL")
            if balance_response and balance_response.get('status') == '0000':
                return balance_response.get('data', {})

            # API 호출 실패 시 None 반환
            print("API 잔고 조회 실패")
            return None

        except Exception as e:
            print(f"잔고 조회 오류: {e}")
            return None

    def _get_mock_balances(self) -> Dict:
        """모의 거래 모드용 가상 잔고 (거래 내역 기반 계산)"""
        mock_data = {
            'total_krw': '1000000',
            'available_krw': '800000',
            'in_use_krw': '200000',
        }

        # 거래 내역에서 실제 보유량 계산 (매수 - 매도)
        if self.transaction_history:
            holdings = {}

            for transaction in self.transaction_history.transactions:
                if transaction['success'] and transaction['ticker'] != 'KRW':
                    ticker = transaction['ticker'].lower()

                    if ticker not in holdings:
                        holdings[ticker] = 0.0

                    if transaction['action'] == 'BUY':
                        holdings[ticker] += transaction['amount']
                    elif transaction['action'] == 'SELL':
                        holdings[ticker] -= transaction['amount']

            # 실제 보유량이 있는 경우만 추가 (0보다 큰 경우)
            for ticker, amount in holdings.items():
                if amount > 0:
                    mock_data[f'total_{ticker}'] = str(amount)
                    mock_data[f'available_{ticker}'] = str(amount)
                    mock_data[f'in_use_{ticker}'] = '0'

        return mock_data

    def calculate_average_buy_price(self, ticker: str) -> float:
        """특정 코인의 평균 매수가 계산"""
        if not self.transaction_history:
            return 0.0

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

    def get_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """여러 코인의 현재가 조회"""
        prices = {}

        for ticker in tickers:
            try:
                if self.config['safety']['dry_run']:
                    # 모의 거래 모드에서는 가상 가격
                    prices[ticker] = 50000000.0 if ticker == 'BTC' else 3000000.0
                else:
                    ticker_data = get_ticker(ticker)
                    if ticker_data:
                        prices[ticker] = float(ticker_data.get('closing_price', 0))
                    else:
                        prices[ticker] = 0.0
            except Exception as e:
                print(f"{ticker} 가격 조회 오류: {e}")
                prices[ticker] = 0.0

        return prices

    def analyze_coin_holding(self, ticker: str, balance_data: Dict, current_price: float) -> Optional[CoinHolding]:
        """개별 코인 보유 현황 분석"""
        try:
            ticker_lower = ticker.lower()
            total_balance = float(balance_data.get(f'total_{ticker_lower}', 0))
            available_balance = float(balance_data.get(f'available_{ticker_lower}', 0))
            in_use_balance = float(balance_data.get(f'in_use_{ticker_lower}', 0))

            if total_balance <= 0:
                return None

            # 평균 매수가 계산
            avg_buy_price = self.calculate_average_buy_price(ticker)

            # 투자 금액 및 현재 가치 계산
            total_invested = total_balance * avg_buy_price if avg_buy_price > 0 else 0
            current_value = total_balance * current_price

            # 손익 계산
            profit_loss = current_value - total_invested if total_invested > 0 else 0
            profit_rate = (profit_loss / total_invested * 100) if total_invested > 0 else 0

            return CoinHolding(
                ticker=ticker,
                balance=total_balance,
                available=available_balance,
                in_use=in_use_balance,
                average_buy_price=avg_buy_price,
                current_price=current_price,
                total_invested=total_invested,
                current_value=current_value,
                profit_loss=profit_loss,
                profit_rate=profit_rate
            )

        except Exception as e:
            print(f"{ticker} 보유 현황 분석 오류: {e}")
            return None

    def get_account_summary(self, force_refresh: bool = False) -> Optional[AccountSummary]:
        """계정 종합 정보 조회"""
        try:
            # 캐시 확인
            now = datetime.now()
            cache_key = 'account_summary'

            if not force_refresh and cache_key in self.account_cache:
                cached_data, cached_time = self.account_cache[cache_key]
                if (now - cached_time).total_seconds() < self.cache_expiry:
                    return cached_data

            # 전체 잔고 조회
            balance_data = self.get_all_balances()
            if not balance_data:
                return None

            # KRW 잔고 정보
            krw_total = float(balance_data.get('total_krw', 0))
            krw_available = float(balance_data.get('available_krw', 0))
            krw_in_use = float(balance_data.get('in_use_krw', 0))

            # 보유 코인 목록 추출
            coin_tickers = []
            for key in balance_data.keys():
                if key.startswith('total_') and not key.endswith('_krw'):
                    ticker = key.replace('total_', '').upper()
                    if float(balance_data[key]) > 0:
                        coin_tickers.append(ticker)

            # 현재가 조회
            current_prices = self.get_current_prices(coin_tickers)

            # 각 코인 보유 현황 분석
            coin_holdings = []
            total_coin_value = 0.0
            total_invested = 0.0

            for ticker in coin_tickers:
                holding = self.analyze_coin_holding(ticker, balance_data, current_prices.get(ticker, 0))
                if holding:
                    coin_holdings.append(holding)
                    total_coin_value += holding.current_value
                    total_invested += holding.total_invested

            # 전체 포트폴리오 계산
            total_portfolio_value = krw_total + total_coin_value
            total_profit_loss = total_coin_value - total_invested if total_invested > 0 else 0
            total_profit_rate = (total_profit_loss / total_invested * 100) if total_invested > 0 else 0

            account_summary = AccountSummary(
                krw_balance=krw_total,
                krw_available=krw_available,
                krw_in_use=krw_in_use,
                total_coin_value=total_coin_value,
                total_portfolio_value=total_portfolio_value,
                total_invested=total_invested,
                total_profit_loss=total_profit_loss,
                total_profit_rate=total_profit_rate,
                coin_holdings=coin_holdings,
                last_updated=now
            )

            # 캐시 저장
            self.account_cache[cache_key] = (account_summary, now)

            return account_summary

        except Exception as e:
            print(f"계정 정보 조회 오류: {e}")
            return None

    def get_portfolio_status_text(self) -> str:
        """포트폴리오 현황을 텍스트로 반환"""
        summary = self.get_account_summary()
        if not summary:
            return "❌ 계정 정보를 가져올 수 없습니다."

        status_text = f"""
🏦 === 계정 종합 현황 ===
💰 KRW 잔고: {summary.krw_balance:,.0f}원 (사용가능: {summary.krw_available:,.0f}원)
💎 코인 자산: {summary.total_coin_value:,.0f}원
💼 총 포트폴리오: {summary.total_portfolio_value:,.0f}원

📊 === 투자 수익률 ===
💵 총 투자금: {summary.total_invested:,.0f}원
{"📈" if summary.total_profit_loss >= 0 else "📉"} 총 손익: {summary.total_profit_loss:+,.0f}원 ({summary.total_profit_rate:+.2f}%)

🪙 === 보유 코인 현황 ==="""

        for holding in summary.coin_holdings:
            profit_emoji = "📈" if holding.profit_loss >= 0 else "📉"
            status_text += f"""
{holding.ticker}: {holding.balance:.6f}개
  ├─ 평균매수가: {holding.average_buy_price:,.0f}원
  ├─ 현재가: {holding.current_price:,.0f}원
  ├─ 현재가치: {holding.current_value:,.0f}원
  └─ {profit_emoji} 손익: {holding.profit_loss:+,.0f}원 ({holding.profit_rate:+.2f}%)"""

        status_text += f"\n\n⏰ 마지막 업데이트: {summary.last_updated.strftime('%Y-%m-%d %H:%M:%S')}"

        return status_text

    def get_trading_summary(self, days: int = 1) -> Dict[str, Any]:
        """거래 요약 정보"""
        if not self.transaction_history:
            return {}

        cutoff_date = datetime.now() - timedelta(days=days)
        recent_transactions = [
            t for t in self.transaction_history.transactions
            if datetime.fromisoformat(t['timestamp']) >= cutoff_date
        ]

        summary = {
            'total_transactions': len(recent_transactions),
            'successful_transactions': len([t for t in recent_transactions if t['success']]),
            'buy_count': len([t for t in recent_transactions if t['action'] == 'BUY' and t['success']]),
            'sell_count': len([t for t in recent_transactions if t['action'] == 'SELL' and t['success']]),
            'total_fees': sum(t.get('fee', 0) for t in recent_transactions if t['success']),
            'coins_traded': list(set(t['ticker'] for t in recent_transactions if t['success']))
        }

        return summary

    def export_portfolio_data(self) -> Dict[str, Any]:
        """포트폴리오 데이터를 JSON 형태로 내보내기"""
        summary = self.get_account_summary()
        if not summary:
            return {}

        return {
            'timestamp': summary.last_updated.isoformat(),
            'krw_balance': summary.krw_balance,
            'total_portfolio_value': summary.total_portfolio_value,
            'total_profit_loss': summary.total_profit_loss,
            'total_profit_rate': summary.total_profit_rate,
            'holdings': [
                {
                    'ticker': h.ticker,
                    'balance': h.balance,
                    'average_buy_price': h.average_buy_price,
                    'current_price': h.current_price,
                    'current_value': h.current_value,
                    'profit_loss': h.profit_loss,
                    'profit_rate': h.profit_rate
                }
                for h in summary.coin_holdings
            ]
        }