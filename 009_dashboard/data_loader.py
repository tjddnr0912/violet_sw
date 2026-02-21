"""
Trading Data Loader - 007/005 데이터 통합 로더
"""
import json
import os
import time
from datetime import datetime, date
from typing import Dict, List, Any, Optional
from pathlib import Path


class TradingDataLoader:
    """007/005 트레이딩 데이터 통합 로더"""

    def __init__(self, base_path: Optional[str] = None):
        if base_path is None:
            # 기본 경로: 009_dashboard의 상위 디렉토리
            base_path = Path(__file__).parent.parent
        self.base_path = Path(base_path)

        self.data_paths = {
            'stock_engine': self.base_path / '007_stock_trade/data/quant/engine_state.json',
            'stock_metrics': self.base_path / '007_stock_trade/data/strategy_monitor.json',
            'crypto_factors': self.base_path / '005_money/logs/dynamic_factors_v3.json',
            'crypto_history': self.base_path / '005_money/logs/performance_history_v3.json',
            'stock_system': self.base_path / '007_stock_trade/data/quant/system_state.json',
            'stock_daily': self.base_path / '007_stock_trade/data/quant/daily_history.json',
            'stock_transactions': self.base_path / '007_stock_trade/data/quant/transaction_journal.json',
        }

    def _load_json(self, key: str) -> Optional[Dict | List]:
        """JSON 파일 로드"""
        path = self.data_paths.get(key)
        if not path or not path.exists():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    # === 주식 데이터 ===

    def get_stock_positions(self) -> List[Dict[str, Any]]:
        """주식 포지션 조회"""
        data = self._load_json('stock_engine')
        if not data:
            return []

        positions = data.get('positions', [])
        for pos in positions:
            # 손익률 계산
            if pos.get('entry_price') and pos.get('current_price'):
                pos['profit_pct'] = ((pos['current_price'] - pos['entry_price'])
                                     / pos['entry_price'] * 100)
                pos['profit_krw'] = ((pos['current_price'] - pos['entry_price'])
                                     * pos.get('quantity', 0))
            # 손절/익절 상태
            if pos.get('current_price') and pos.get('stop_loss'):
                pos['stop_loss_pct'] = ((pos['stop_loss'] - pos['entry_price'])
                                        / pos['entry_price'] * 100)
            if pos.get('current_price') and pos.get('take_profit_1'):
                pos['take_profit_1_pct'] = ((pos['take_profit_1'] - pos['entry_price'])
                                            / pos['entry_price'] * 100)
        return positions

    def get_stock_state(self) -> Dict[str, Any]:
        """주식 시스템 상태 조회"""
        data = self._load_json('stock_engine')
        if not data:
            return {}
        return {
            'last_rebalance_month': data.get('last_rebalance_month'),
            'last_urgent_rebalance_month': data.get('last_urgent_rebalance_month'),
            'updated_at': data.get('updated_at'),
            'position_count': len(data.get('positions', [])),
        }

    def get_stock_daily_history(self, days: int = 30) -> Dict[str, Any]:
        """주식 일일 자산 히스토리"""
        data = self._load_json('stock_daily')
        if not data:
            return {'initial_capital': 0, 'snapshots': []}
        snapshots = data.get('snapshots', [])
        return {
            'initial_capital': data.get('initial_capital', 0),
            'snapshots': snapshots[-days:],
        }

    def get_stock_transactions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """주식 거래 내역"""
        data = self._load_json('stock_transactions')
        if not data:
            return []
        txns = data.get('transactions', [])
        sorted_txns = sorted(txns, key=lambda x: x.get('timestamp', ''), reverse=True)
        return sorted_txns[:limit]

    # === 암호화폐 데이터 ===

    def get_crypto_regime(self) -> Dict[str, Any]:
        """암호화폐 시장 레짐 조회"""
        data = self._load_json('crypto_factors')
        if not data:
            return {}
        return {
            'market_regime': data.get('market_regime', 'unknown'),
            'volatility_level': data.get('volatility_level', 'unknown'),
            'entry_mode': data.get('entry_mode', 'unknown'),
            'entry_threshold_modifier': data.get('entry_threshold_modifier', 1.0),
            'stop_loss_modifier': data.get('stop_loss_modifier', 1.0),
            'current_atr_pct': data.get('current_atr_pct'),
            'take_profit_target': data.get('take_profit_target'),
            'last_update': data.get('last_realtime_update'),
        }

    def get_crypto_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """암호화폐 거래 내역 조회"""
        data = self._load_json('crypto_history')
        if not data:
            return []
        # 최신순 정렬
        sorted_data = sorted(data, key=lambda x: x.get('exit_time', ''), reverse=True)
        return sorted_data[:limit]

    def get_crypto_performance(self) -> Dict[str, Any]:
        """암호화폐 성과 통계"""
        history = self._load_json('crypto_history')
        if not history:
            return {'total_trades': 0, 'win_rate': 0, 'total_profit_pct': 0}

        closed_trades = [t for t in history if t.get('status') == 'closed']
        if not closed_trades:
            return {'total_trades': 0, 'win_rate': 0, 'total_profit_pct': 0}

        wins = sum(1 for t in closed_trades if t.get('profit_pct', 0) > 0)
        total_profit_pct = sum(t.get('profit_pct', 0) for t in closed_trades)

        return {
            'total_trades': len(closed_trades),
            'win_rate': wins / len(closed_trades) * 100 if closed_trades else 0,
            'total_profit_pct': total_profit_pct,
            'avg_profit_pct': total_profit_pct / len(closed_trades) if closed_trades else 0,
        }

    # === 암호화폐 코인별 데이터 ===

    def get_crypto_coin_summary(self) -> List[Dict[str, Any]]:
        """코인별 성과 집계"""
        history = self._load_json('crypto_history')
        if not history:
            return []

        coin_stats: Dict[str, Dict[str, Any]] = {}
        for t in history:
            if t.get('status') != 'closed':
                continue
            coin = t.get('coin', 'UNKNOWN')
            if coin not in coin_stats:
                coin_stats[coin] = {
                    'coin': coin, 'trades': 0, 'wins': 0,
                    'total_profit_pct': 0, 'total_profit_krw': 0,
                    'last_trade': '',
                }
            s = coin_stats[coin]
            s['trades'] += 1
            if t.get('profit_pct', 0) > 0:
                s['wins'] += 1
            s['total_profit_pct'] += t.get('profit_pct', 0)
            s['total_profit_krw'] += t.get('profit_krw', 0)
            exit_time = t.get('exit_time', '')
            if exit_time > s['last_trade']:
                s['last_trade'] = exit_time

        result = []
        for coin, s in coin_stats.items():
            s['win_rate'] = (s['wins'] / s['trades'] * 100) if s['trades'] > 0 else 0
            s['avg_profit_pct'] = s['total_profit_pct'] / s['trades'] if s['trades'] > 0 else 0
            result.append(s)

        result.sort(key=lambda x: x['trades'], reverse=True)
        return result

    def get_coin_price(self, coin: str) -> Dict[str, Any]:
        """Bithumb 공개 API로 실시간 시세 조회"""
        import requests
        try:
            resp = requests.get(
                f'https://api.bithumb.com/public/ticker/{coin.upper()}_KRW',
                timeout=5,
            )
            data = resp.json()
            if data.get('status') != '0000':
                return {'error': 'API error', 'coin': coin}
            d = data['data']
            closing = float(d.get('closing_price', 0))
            prev_closing = float(d.get('prev_closing_price', 0))
            change_pct = ((closing - prev_closing) / prev_closing * 100) if prev_closing else 0
            return {
                'coin': coin.upper(),
                'closing_price': closing,
                'opening_price': float(d.get('opening_price', 0)),
                'high_price': float(d.get('max_price', 0)),
                'low_price': float(d.get('min_price', 0)),
                'volume': float(d.get('units_traded_24H', 0)),
                'change_pct': round(change_pct, 2),
                'timestamp': d.get('date'),
            }
        except Exception as e:
            return {'error': str(e), 'coin': coin}

    def get_coin_chart(self, coin: str, interval: str = '1h') -> List[Dict[str, Any]]:
        """Bithumb 공개 API로 캔들스틱 차트 데이터 조회"""
        import requests
        interval_map = {
            '5m': '5m', '30m': '30m', '1h': '1h', '6h': '6h', '1d': '24h',
        }
        bithumb_interval = interval_map.get(interval, '1h')
        try:
            resp = requests.get(
                f'https://api.bithumb.com/public/candlestick/{coin.upper()}_KRW/{bithumb_interval}',
                timeout=5,
            )
            data = resp.json()
            if data.get('status') != '0000':
                return []
            candles = data.get('data', [])[-100:]
            result = []
            for c in candles:
                result.append({
                    'timestamp': c[0],
                    'open': float(c[1]),
                    'close': float(c[2]),
                    'high': float(c[3]),
                    'low': float(c[4]),
                    'volume': float(c[5]),
                })
            return result
        except Exception:
            return []

    def get_crypto_coin_trades(self, coin: str, limit: int = 20) -> List[Dict[str, Any]]:
        """특정 코인 거래 내역 필터"""
        history = self._load_json('crypto_history')
        if not history:
            return []
        filtered = [t for t in history if t.get('coin', '').upper() == coin.upper()]
        sorted_data = sorted(filtered, key=lambda x: x.get('exit_time', ''), reverse=True)
        return sorted_data[:limit]

    # === 시스템 상태 ===

    # 2026년 한국 공휴일
    KR_HOLIDAYS_2026 = {
        date(2026, 1, 1),   # 신정
        date(2026, 2, 16),  # 설 연휴
        date(2026, 2, 17),  # 설날
        date(2026, 2, 18),  # 설 연휴
        date(2026, 3, 1),   # 삼일절
        date(2026, 5, 5),   # 어린이날
        date(2026, 5, 24),  # 부처님오신날
        date(2026, 6, 6),   # 현충일
        date(2026, 8, 15),  # 광복절
        date(2026, 9, 24),  # 추석 연휴
        date(2026, 9, 25),  # 추석
        date(2026, 9, 26),  # 추석 연휴
        date(2026, 10, 3),  # 개천절
        date(2026, 10, 9),  # 한글날
        date(2026, 12, 25), # 성탄절
    }

    def _get_market_status(self) -> tuple:
        """한국 주식시장 상태 판별. Returns (market_status, market_status_text)"""
        now = datetime.now()
        today = now.date()
        weekday = today.weekday()  # 0=Mon, 6=Sun

        if weekday >= 5:
            return ('weekend', '주말 휴장')
        if today in self.KR_HOLIDAYS_2026:
            return ('holiday', '공휴일 휴장')

        hour_min = now.hour * 100 + now.minute
        if hour_min < 900:
            return ('pre_market', '장 시작 전')
        elif hour_min <= 1530:
            return ('trading', '장 운영 중')
        else:
            return ('after_hours', '장 마감')

    def _get_daemon_running(self) -> bool:
        """system_state.json에서 데몬 실행 상태 확인"""
        data = self._load_json('stock_system')
        if not data:
            return False
        return data.get('state') == 'running'

    def get_system_status(self) -> Dict[str, Any]:
        """봇 상태 확인 (장 시간 + 데몬 상태 기반)"""
        statuses = {}

        # 암호화폐 봇 (24시간 운영 - 파일 freshness 기반)
        crypto_path = self.data_paths.get('crypto_factors')
        if crypto_path and crypto_path.exists():
            mtime = crypto_path.stat().st_mtime
            age_minutes = (time.time() - mtime) / 60
            statuses['crypto_bot'] = {
                'running': age_minutes < 30,
                'last_update': datetime.fromtimestamp(mtime).isoformat(),
                'age_minutes': round(age_minutes, 1),
            }
        else:
            statuses['crypto_bot'] = {
                'running': False,
                'last_update': None,
                'age_minutes': None,
            }

        # 주식 봇 (장 시간 인식)
        market_status, market_status_text = self._get_market_status()
        daemon_running = self._get_daemon_running()

        stock_path = self.data_paths.get('stock_engine')
        if stock_path and stock_path.exists():
            mtime = stock_path.stat().st_mtime
            age_minutes = (time.time() - mtime) / 60

            if market_status == 'trading':
                running = age_minutes < 30
            else:
                running = daemon_running
        else:
            age_minutes = None
            mtime = None
            running = daemon_running

        statuses['stock_bot'] = {
            'running': running,
            'last_update': datetime.fromtimestamp(mtime).isoformat() if mtime else None,
            'age_minutes': round(age_minutes, 1) if age_minutes is not None else None,
            'daemon_running': daemon_running,
            'market_status': market_status,
            'market_status_text': market_status_text,
        }

        return statuses

    # === 종합 ===

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """전체 포트폴리오 요약"""
        stock_positions = self.get_stock_positions()
        stock_state = self.get_stock_state()
        crypto_regime = self.get_crypto_regime()
        crypto_perf = self.get_crypto_performance()
        system_status = self.get_system_status()

        # 주식 총 평가액 및 손익
        stock_total_value = sum(
            pos.get('current_price', 0) * pos.get('quantity', 0)
            for pos in stock_positions
        )
        stock_total_profit = sum(
            pos.get('profit_krw', 0) for pos in stock_positions
        )

        # 일일 P&L (daily_history에서 최신 snapshot)
        daily_data = self.get_stock_daily_history(days=1)
        latest_snapshot = daily_data['snapshots'][-1] if daily_data['snapshots'] else {}

        return {
            'stock': {
                'position_count': len(stock_positions),
                'total_value': stock_total_value,
                'total_profit': stock_total_profit,
                'total_assets': latest_snapshot.get('total_assets', 0),
                'daily_pnl': latest_snapshot.get('daily_pnl', 0),
                'daily_pnl_pct': latest_snapshot.get('daily_pnl_pct', 0),
                'total_pnl_pct': latest_snapshot.get('total_pnl_pct', 0),
                'updated_at': stock_state.get('updated_at'),
            },
            'crypto': {
                'market_regime': crypto_regime.get('market_regime'),
                'volatility_level': crypto_regime.get('volatility_level'),
                'total_trades': crypto_perf.get('total_trades'),
                'win_rate': crypto_perf.get('win_rate'),
                'total_profit_pct': crypto_perf.get('total_profit_pct'),
                'avg_profit_pct': crypto_perf.get('avg_profit_pct'),
                'updated_at': crypto_regime.get('last_update'),
            },
            'system_status': system_status,
            'generated_at': datetime.now().isoformat(),
        }

    def get_recent_trades(self, limit: int = 10) -> List[Dict[str, Any]]:
        """최근 거래 내역 (암호화폐)"""
        return self.get_crypto_history(limit)


# 테스트용
if __name__ == '__main__':
    loader = TradingDataLoader()
    print("=== Portfolio Summary ===")
    print(json.dumps(loader.get_portfolio_summary(), indent=2, ensure_ascii=False))
    print("\n=== Stock Positions ===")
    print(json.dumps(loader.get_stock_positions(), indent=2, ensure_ascii=False))
    print("\n=== Crypto Regime ===")
    print(json.dumps(loader.get_crypto_regime(), indent=2, ensure_ascii=False))
