"""
성과 분석 및 시각화 모듈
- 포트폴리오 성과 지표 계산
- 시각화 차트 생성
- 리포트 생성
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """성과 지표"""
    # 수익률 지표
    total_return: float = 0.0           # 총 수익률 (%)
    annualized_return: float = 0.0      # 연환산 수익률 (%)
    cagr: float = 0.0                   # 연복리수익률 (%)

    # 리스크 지표
    volatility: float = 0.0             # 변동성 (연환산, %)
    downside_volatility: float = 0.0    # 하방 변동성 (%)
    max_drawdown: float = 0.0           # 최대 낙폭 (%)
    avg_drawdown: float = 0.0           # 평균 낙폭 (%)
    max_drawdown_duration: int = 0      # 최대 낙폭 기간 (일)

    # 위험조정 수익률
    sharpe_ratio: float = 0.0           # 샤프비율
    sortino_ratio: float = 0.0          # 소르티노비율
    calmar_ratio: float = 0.0           # 칼마비율
    information_ratio: float = 0.0      # 정보비율

    # 승률 지표
    win_rate: float = 0.0               # 승률 (%)
    profit_factor: float = 0.0          # 손익비
    avg_win: float = 0.0                # 평균 수익
    avg_loss: float = 0.0               # 평균 손실
    win_loss_ratio: float = 0.0         # 평균수익/평균손실

    # 거래 통계
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_holding_period: float = 0.0     # 평균 보유기간 (일)

    # 기간별 성과
    best_month: float = 0.0
    worst_month: float = 0.0
    positive_months: int = 0
    negative_months: int = 0


@dataclass
class BenchmarkComparison:
    """벤치마크 대비 성과"""
    portfolio_return: float = 0.0
    benchmark_return: float = 0.0
    alpha: float = 0.0                  # 알파 (초과수익)
    beta: float = 0.0                   # 베타 (시장 민감도)
    tracking_error: float = 0.0         # 추적오차
    information_ratio: float = 0.0      # 정보비율
    correlation: float = 0.0            # 상관계수


class PerformanceAnalyzer:
    """성과 분석기"""

    def __init__(self, risk_free_rate: float = 0.03):
        """
        Args:
            risk_free_rate: 무위험이자율 (연 단위, 기본 3%)
        """
        self.risk_free_rate = risk_free_rate

    def analyze(
        self,
        daily_values: List[float],
        dates: List[datetime] = None,
        trades: List[Dict] = None
    ) -> PerformanceMetrics:
        """
        성과 분석

        Args:
            daily_values: 일별 포트폴리오 가치
            dates: 날짜 리스트
            trades: 거래 내역

        Returns:
            PerformanceMetrics
        """
        if len(daily_values) < 2:
            return PerformanceMetrics()

        metrics = PerformanceMetrics()

        # 일별 수익률 계산
        returns = []
        for i in range(1, len(daily_values)):
            if daily_values[i - 1] > 0:
                r = (daily_values[i] / daily_values[i - 1]) - 1
                returns.append(r)

        if not returns:
            return metrics

        returns = np.array(returns)

        # 총 수익률
        metrics.total_return = (daily_values[-1] / daily_values[0] - 1) * 100

        # 연환산 수익률
        days = len(daily_values)
        years = days / 252  # 거래일 기준
        if years > 0:
            metrics.annualized_return = ((1 + metrics.total_return / 100) ** (1 / years) - 1) * 100
            metrics.cagr = metrics.annualized_return

        # 변동성 (연환산)
        metrics.volatility = np.std(returns) * np.sqrt(252) * 100

        # 하방 변동성
        negative_returns = returns[returns < 0]
        if len(negative_returns) > 0:
            metrics.downside_volatility = np.std(negative_returns) * np.sqrt(252) * 100

        # 최대 낙폭 계산
        peak = daily_values[0]
        max_dd = 0
        current_dd_start = 0
        max_dd_duration = 0
        current_dd_duration = 0
        drawdowns = []

        for i, value in enumerate(daily_values):
            if value > peak:
                peak = value
                if current_dd_duration > max_dd_duration:
                    max_dd_duration = current_dd_duration
                current_dd_duration = 0
            else:
                dd = (value / peak - 1) * 100
                drawdowns.append(dd)
                if dd < max_dd:
                    max_dd = dd
                current_dd_duration += 1

        metrics.max_drawdown = max_dd
        metrics.max_drawdown_duration = max_dd_duration
        if drawdowns:
            metrics.avg_drawdown = np.mean(drawdowns)

        # 샤프비율
        daily_rf = self.risk_free_rate / 252
        excess_returns = returns - daily_rf
        if np.std(excess_returns) > 0:
            metrics.sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)

        # 소르티노비율
        if metrics.downside_volatility > 0:
            metrics.sortino_ratio = (metrics.annualized_return - self.risk_free_rate * 100) / metrics.downside_volatility

        # 칼마비율
        if metrics.max_drawdown != 0:
            metrics.calmar_ratio = metrics.annualized_return / abs(metrics.max_drawdown)

        # 거래 통계
        if trades:
            sell_trades = [t for t in trades if t.get('side') == 'SELL' or t.get('type') == 'SELL']

            if sell_trades:
                metrics.total_trades = len(sell_trades)

                wins = [t for t in sell_trades if t.get('pnl', 0) > 0]
                losses = [t for t in sell_trades if t.get('pnl', 0) < 0]

                metrics.winning_trades = len(wins)
                metrics.losing_trades = len(losses)

                if metrics.total_trades > 0:
                    metrics.win_rate = metrics.winning_trades / metrics.total_trades * 100

                if wins:
                    metrics.avg_win = np.mean([t.get('pnl', 0) for t in wins])
                if losses:
                    metrics.avg_loss = abs(np.mean([t.get('pnl', 0) for t in losses]))

                if metrics.avg_loss > 0:
                    metrics.win_loss_ratio = metrics.avg_win / metrics.avg_loss

                total_wins = sum(t.get('pnl', 0) for t in wins)
                total_losses = abs(sum(t.get('pnl', 0) for t in losses))
                if total_losses > 0:
                    metrics.profit_factor = total_wins / total_losses

        # 월별 성과 (dates가 제공된 경우)
        if dates and len(dates) == len(daily_values):
            monthly_returns = self._calculate_monthly_returns(dates, daily_values)
            if monthly_returns:
                metrics.best_month = max(monthly_returns.values())
                metrics.worst_month = min(monthly_returns.values())
                metrics.positive_months = sum(1 for r in monthly_returns.values() if r > 0)
                metrics.negative_months = sum(1 for r in monthly_returns.values() if r < 0)

        return metrics

    def compare_benchmark(
        self,
        portfolio_values: List[float],
        benchmark_values: List[float]
    ) -> BenchmarkComparison:
        """
        벤치마크 대비 성과 비교

        Args:
            portfolio_values: 포트폴리오 일별 가치
            benchmark_values: 벤치마크 일별 가치

        Returns:
            BenchmarkComparison
        """
        comparison = BenchmarkComparison()

        if len(portfolio_values) < 2 or len(benchmark_values) < 2:
            return comparison

        # 길이 맞추기
        min_len = min(len(portfolio_values), len(benchmark_values))
        portfolio_values = portfolio_values[:min_len]
        benchmark_values = benchmark_values[:min_len]

        # 수익률 계산
        port_returns = []
        bench_returns = []

        for i in range(1, min_len):
            if portfolio_values[i - 1] > 0 and benchmark_values[i - 1] > 0:
                port_returns.append(portfolio_values[i] / portfolio_values[i - 1] - 1)
                bench_returns.append(benchmark_values[i] / benchmark_values[i - 1] - 1)

        if not port_returns:
            return comparison

        port_returns = np.array(port_returns)
        bench_returns = np.array(bench_returns)

        # 총 수익률
        comparison.portfolio_return = (portfolio_values[-1] / portfolio_values[0] - 1) * 100
        comparison.benchmark_return = (benchmark_values[-1] / benchmark_values[0] - 1) * 100

        # 베타 계산
        if np.var(bench_returns) > 0:
            comparison.beta = np.cov(port_returns, bench_returns)[0, 1] / np.var(bench_returns)

        # 알파 계산 (CAPM 기반)
        expected_return = self.risk_free_rate + comparison.beta * (np.mean(bench_returns) * 252 - self.risk_free_rate)
        comparison.alpha = (np.mean(port_returns) * 252 - expected_return) * 100

        # 추적오차
        tracking_diff = port_returns - bench_returns
        comparison.tracking_error = np.std(tracking_diff) * np.sqrt(252) * 100

        # 정보비율
        if comparison.tracking_error > 0:
            comparison.information_ratio = (comparison.portfolio_return - comparison.benchmark_return) / comparison.tracking_error

        # 상관계수
        comparison.correlation = np.corrcoef(port_returns, bench_returns)[0, 1]

        return comparison

    def _calculate_monthly_returns(
        self,
        dates: List[datetime],
        values: List[float]
    ) -> Dict[str, float]:
        """월별 수익률 계산"""
        monthly_returns = {}
        current_month = None
        month_start_value = None

        for date, value in zip(dates, values):
            month_key = date.strftime("%Y-%m")

            if current_month != month_key:
                if current_month and month_start_value:
                    monthly_returns[current_month] = (prev_value / month_start_value - 1) * 100
                current_month = month_key
                month_start_value = value

            prev_value = value

        # 마지막 월
        if current_month and month_start_value:
            monthly_returns[current_month] = (values[-1] / month_start_value - 1) * 100

        return monthly_returns

    def generate_report(
        self,
        metrics: PerformanceMetrics,
        benchmark: BenchmarkComparison = None
    ) -> str:
        """
        텍스트 리포트 생성

        Args:
            metrics: 성과 지표
            benchmark: 벤치마크 비교 (선택)

        Returns:
            리포트 문자열
        """
        lines = [
            "=" * 50,
            "        포트폴리오 성과 분석 리포트",
            "=" * 50,
            "",
            "[ 수익률 지표 ]",
            f"  총 수익률:        {metrics.total_return:+.2f}%",
            f"  연환산 수익률:    {metrics.annualized_return:+.2f}%",
            f"  CAGR:            {metrics.cagr:+.2f}%",
            "",
            "[ 리스크 지표 ]",
            f"  변동성 (연환산): {metrics.volatility:.2f}%",
            f"  하방 변동성:     {metrics.downside_volatility:.2f}%",
            f"  최대 낙폭:       {metrics.max_drawdown:.2f}%",
            f"  평균 낙폭:       {metrics.avg_drawdown:.2f}%",
            f"  최대 낙폭 기간:  {metrics.max_drawdown_duration}일",
            "",
            "[ 위험조정 수익률 ]",
            f"  샤프비율:        {metrics.sharpe_ratio:.2f}",
            f"  소르티노비율:    {metrics.sortino_ratio:.2f}",
            f"  칼마비율:        {metrics.calmar_ratio:.2f}",
            "",
            "[ 거래 통계 ]",
            f"  총 거래:         {metrics.total_trades}회",
            f"  승리 거래:       {metrics.winning_trades}회",
            f"  패배 거래:       {metrics.losing_trades}회",
            f"  승률:            {metrics.win_rate:.1f}%",
            f"  손익비:          {metrics.profit_factor:.2f}",
            f"  평균 수익:       {metrics.avg_win:+,.0f}원",
            f"  평균 손실:       {metrics.avg_loss:,.0f}원",
            "",
            "[ 월별 성과 ]",
            f"  최고 월:         {metrics.best_month:+.2f}%",
            f"  최저 월:         {metrics.worst_month:+.2f}%",
            f"  수익 월:         {metrics.positive_months}개월",
            f"  손실 월:         {metrics.negative_months}개월",
        ]

        if benchmark:
            lines.extend([
                "",
                "[ 벤치마크 대비 ]",
                f"  포트폴리오:      {benchmark.portfolio_return:+.2f}%",
                f"  벤치마크:        {benchmark.benchmark_return:+.2f}%",
                f"  알파:            {benchmark.alpha:+.2f}%",
                f"  베타:            {benchmark.beta:.2f}",
                f"  추적오차:        {benchmark.tracking_error:.2f}%",
                f"  정보비율:        {benchmark.information_ratio:.2f}",
                f"  상관계수:        {benchmark.correlation:.2f}",
            ])

        lines.append("")
        lines.append("=" * 50)

        return "\n".join(lines)


class ChartGenerator:
    """차트 생성기"""

    def __init__(self):
        self._check_matplotlib()

    def _check_matplotlib(self):
        """matplotlib 사용 가능 여부 확인"""
        try:
            import matplotlib
            matplotlib.use('Agg')  # 비대화형 백엔드
            import matplotlib.pyplot as plt
            self.plt = plt
            self.available = True
        except ImportError:
            self.available = False
            logger.warning("matplotlib이 설치되지 않아 차트 생성이 불가능합니다.")

    def plot_equity_curve(
        self,
        dates: List[datetime],
        values: List[float],
        benchmark_values: List[float] = None,
        title: str = "포트폴리오 수익률",
        filepath: str = None
    ) -> Optional[str]:
        """
        수익률 곡선 차트

        Args:
            dates: 날짜 리스트
            values: 포트폴리오 가치
            benchmark_values: 벤치마크 가치 (선택)
            title: 차트 제목
            filepath: 저장 경로 (None이면 자동 생성)

        Returns:
            저장된 파일 경로
        """
        if not self.available:
            return None

        fig, ax = self.plt.subplots(figsize=(12, 6))

        # 수익률로 변환
        portfolio_returns = [(v / values[0] - 1) * 100 for v in values]
        ax.plot(dates, portfolio_returns, label='포트폴리오', linewidth=2)

        if benchmark_values:
            benchmark_returns = [(v / benchmark_values[0] - 1) * 100 for v in benchmark_values]
            ax.plot(dates, benchmark_returns, label='벤치마크', linewidth=1.5, alpha=0.7)

        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('날짜')
        ax.set_ylabel('수익률 (%)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='black', linewidth=0.5)

        self.plt.tight_layout()

        if filepath is None:
            filepath = f"equity_curve_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        self.plt.savefig(filepath, dpi=150, bbox_inches='tight')
        self.plt.close()

        return filepath

    def plot_drawdown(
        self,
        dates: List[datetime],
        values: List[float],
        title: str = "낙폭 (Drawdown)",
        filepath: str = None
    ) -> Optional[str]:
        """
        낙폭 차트

        Args:
            dates: 날짜 리스트
            values: 포트폴리오 가치
            title: 차트 제목
            filepath: 저장 경로

        Returns:
            저장된 파일 경로
        """
        if not self.available:
            return None

        # 낙폭 계산
        peak = values[0]
        drawdowns = []

        for value in values:
            if value > peak:
                peak = value
            dd = (value / peak - 1) * 100
            drawdowns.append(dd)

        fig, ax = self.plt.subplots(figsize=(12, 4))

        ax.fill_between(dates, 0, drawdowns, alpha=0.3, color='red')
        ax.plot(dates, drawdowns, color='red', linewidth=1)

        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('날짜')
        ax.set_ylabel('낙폭 (%)')
        ax.grid(True, alpha=0.3)

        self.plt.tight_layout()

        if filepath is None:
            filepath = f"drawdown_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        self.plt.savefig(filepath, dpi=150, bbox_inches='tight')
        self.plt.close()

        return filepath

    def plot_monthly_returns(
        self,
        monthly_returns: Dict[str, float],
        title: str = "월별 수익률",
        filepath: str = None
    ) -> Optional[str]:
        """
        월별 수익률 차트

        Args:
            monthly_returns: 월별 수익률 딕셔너리
            title: 차트 제목
            filepath: 저장 경로

        Returns:
            저장된 파일 경로
        """
        if not self.available:
            return None

        months = list(monthly_returns.keys())
        returns = list(monthly_returns.values())

        colors = ['green' if r >= 0 else 'red' for r in returns]

        fig, ax = self.plt.subplots(figsize=(14, 5))

        bars = ax.bar(months, returns, color=colors, alpha=0.7)

        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('월')
        ax.set_ylabel('수익률 (%)')
        ax.axhline(y=0, color='black', linewidth=0.5)
        ax.grid(True, alpha=0.3, axis='y')

        # x축 레이블 회전
        self.plt.xticks(rotation=45, ha='right')

        self.plt.tight_layout()

        if filepath is None:
            filepath = f"monthly_returns_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        self.plt.savefig(filepath, dpi=150, bbox_inches='tight')
        self.plt.close()

        return filepath

    def plot_position_distribution(
        self,
        positions: List[Dict],
        title: str = "포지션 분포",
        filepath: str = None
    ) -> Optional[str]:
        """
        포지션 분포 차트 (파이 차트)

        Args:
            positions: 포지션 리스트 [{name, value, weight}, ...]
            title: 차트 제목
            filepath: 저장 경로

        Returns:
            저장된 파일 경로
        """
        if not self.available or not positions:
            return None

        names = [p['name'][:8] for p in positions]
        weights = [p.get('weight', p.get('value', 0)) for p in positions]

        fig, ax = self.plt.subplots(figsize=(10, 8))

        wedges, texts, autotexts = ax.pie(
            weights,
            labels=names,
            autopct='%1.1f%%',
            pctdistance=0.85
        )

        ax.set_title(title, fontsize=14, fontweight='bold')

        self.plt.tight_layout()

        if filepath is None:
            filepath = f"position_dist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        self.plt.savefig(filepath, dpi=150, bbox_inches='tight')
        self.plt.close()

        return filepath
