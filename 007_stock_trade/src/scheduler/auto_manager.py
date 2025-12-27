"""
자동화된 전략 관리 스케줄러
- 월간 모니터링 자동 실행
- 반기 재최적화 자동 실행
- 가중치 자동 업데이트
- 텔레그램 알림 연동
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import schedule
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
import threading

# 프로젝트 루트의 .env 파일 명시적 로드
from dotenv import load_dotenv
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path, override=True)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/auto_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class WeightConfig:
    """가중치 설정 관리"""

    CONFIG_FILE = "config/optimal_weights.json"

    DEFAULT_WEIGHTS = {
        "momentum_weight": 0.20,
        "short_mom_weight": 0.10,
        "volatility_weight": 0.50,
        "volume_weight": 0.00,
        "target_count": 15,
        "optimized_date": "2025-12-27",
        "baseline_sharpe": 2.39,
        "baseline_return": 8.99,
        "baseline_mdd": -2.14,
        "auto_update": True
    }

    @classmethod
    def load(cls) -> dict:
        """가중치 설정 로드"""
        config_path = Path(cls.CONFIG_FILE)
        if config_path.exists():
            with open(config_path, 'r') as f:
                return json.load(f)
        return cls.DEFAULT_WEIGHTS.copy()

    @classmethod
    def save(cls, weights: dict):
        """가중치 설정 저장"""
        config_path = Path(cls.CONFIG_FILE)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        weights['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(config_path, 'w') as f:
            json.dump(weights, f, indent=2, ensure_ascii=False)

        logger.info(f"가중치 설정 저장됨: {config_path}")

    @classmethod
    def update_from_optimization(cls, optimization_result: dict) -> dict:
        """최적화 결과로 가중치 업데이트"""
        current = cls.load()

        # 최적화 결과가 더 좋으면 업데이트
        if optimization_result.get('sharpe_ratio', 0) > current.get('baseline_sharpe', 0) * 0.8:
            new_weights = {
                "momentum_weight": optimization_result['momentum_weight'],
                "short_mom_weight": optimization_result['short_mom_weight'],
                "volatility_weight": optimization_result['volatility_weight'],
                "volume_weight": optimization_result['volume_weight'],
                "target_count": int(optimization_result['target_count']),
                "optimized_date": datetime.now().strftime("%Y-%m-%d"),
                "baseline_sharpe": optimization_result['sharpe_ratio'],
                "baseline_return": optimization_result['total_return'],
                "baseline_mdd": optimization_result['max_drawdown'],
                "auto_update": True,
                "previous_weights": current
            }
            cls.save(new_weights)
            return new_weights

        return current


class TelegramReporter:
    """텔레그램 리포트 전송"""

    def __init__(self):
        from src.telegram import get_notifier
        self.notifier = get_notifier()

    def send_monitoring_report(self, metrics: dict, alerts: list):
        """모니터링 결과 전송"""
        status = "🔴 경고" if alerts else "🟢 정상"

        message = f"""
📊 <b>전략 모니터링 리포트</b>
━━━━━━━━━━━━━━━━━━━━

상태: {status}
검증기간: {metrics.get('start_date', 'N/A')} ~ {metrics.get('end_date', 'N/A')}

<b>📈 성과 지표</b>
• 총 수익률: {metrics.get('total_return', 0):+.2f}%
• 샤프비율: {metrics.get('sharpe_ratio', 0):.2f}
• 소르티노: {metrics.get('sortino_ratio', 0):.2f}
• MDD: {metrics.get('max_drawdown', 0):.2f}%
• 승률: {metrics.get('win_rate', 0):.1f}%
• 수익팩터: {metrics.get('profit_factor', 0):.2f}
"""

        if alerts:
            message += "\n<b>⚠️ 경고</b>\n"
            for alert in alerts:
                icon = "🔴" if alert['level'] == 'CRITICAL' else "🟡"
                message += f"{icon} {alert['message']}\n"
                message += f"   → {alert['action']}\n"

        message += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        self.notifier.send_message(message.strip())

    def send_optimization_report(self, result: dict, updated: bool):
        """최적화 결과 전송"""
        update_status = "✅ 자동 업데이트됨" if updated else "ℹ️ 기존 유지"

        message = f"""
🔧 <b>팩터 가중치 최적화 완료</b>
━━━━━━━━━━━━━━━━━━━━

{update_status}

<b>📊 최적 가중치</b>
• 모멘텀: {result.get('momentum_weight', 0):.2f}
• 단기모멘텀: {result.get('short_mom_weight', 0):.2f}
• 변동성: {result.get('volatility_weight', 0):.2f}
• 거래량: {result.get('volume_weight', 0):.2f}
• 종목수: {int(result.get('target_count', 15))}개

<b>📈 예상 성과</b>
• 샤프비율: {result.get('sharpe_ratio', 0):.2f}
• 수익률: {result.get('total_return', 0):+.2f}%
• MDD: {result.get('max_drawdown', 0):.2f}%

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
        self.notifier.send_message(message.strip())

    def send_alert(self, title: str, message: str, level: str = "INFO"):
        """일반 알림 전송"""
        icons = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "CRITICAL": "🚨",
            "SUCCESS": "✅"
        }
        icon = icons.get(level, "📢")

        full_message = f"""
{icon} <b>{title}</b>
━━━━━━━━━━━━━━━━━━━━

{message}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
        self.notifier.send_message(full_message.strip())

    def send_daily_summary(self, portfolio_value: float, daily_pnl: float, daily_pnl_pct: float):
        """일간 요약 전송"""
        pnl_icon = "📈" if daily_pnl >= 0 else "📉"

        message = f"""
{pnl_icon} <b>일간 포트폴리오 요약</b>
━━━━━━━━━━━━━━━━━━━━

💰 총 자산: ₩{portfolio_value:,.0f}
{pnl_icon} 오늘 손익: {daily_pnl:+,.0f}원 ({daily_pnl_pct:+.2f}%)

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
        self.notifier.send_message(message.strip())


class AutoStrategyManager:
    """자동 전략 관리자"""

    def __init__(self):
        self.reporter = TelegramReporter()
        self.weights = WeightConfig.load()
        self.running = False

        # 로그 디렉토리 생성
        Path("logs").mkdir(exist_ok=True)
        Path("data/quant").mkdir(parents=True, exist_ok=True)

    def run_monitoring(self) -> dict:
        """모니터링 실행"""
        logger.info("월간 모니터링 시작...")

        try:
            from scripts.monitor_strategy import run_validation, check_alerts, CURRENT_WEIGHTS

            # 현재 가중치로 업데이트
            import scripts.monitor_strategy as monitor_module
            monitor_module.CURRENT_WEIGHTS = self.weights

            # 검증 실행
            metrics = run_validation(months=3)

            if "error" in metrics:
                self.reporter.send_alert(
                    "모니터링 실패",
                    f"오류: {metrics['error']}",
                    "WARNING"
                )
                return metrics

            # 경고 체크
            alerts = check_alerts(metrics)

            # 텔레그램 리포트 전송
            self.reporter.send_monitoring_report(metrics, alerts)

            # 심각한 경고가 있으면 자동 재최적화 트리거
            critical_alerts = [a for a in alerts if a['level'] == 'CRITICAL']
            if critical_alerts and self.weights.get('auto_update', True):
                logger.warning("심각한 경고 감지, 자동 재최적화 시작...")
                self.run_optimization(auto_trigger=True)

            logger.info(f"모니터링 완료: 샤프비율={metrics.get('sharpe_ratio', 0):.2f}")
            return metrics

        except Exception as e:
            logger.error(f"모니터링 오류: {e}")
            self.reporter.send_alert("모니터링 오류", str(e), "CRITICAL")
            return {"error": str(e)}

    def run_optimization(self, auto_trigger: bool = False) -> dict:
        """최적화 실행"""
        trigger_reason = "자동 경고 감지" if auto_trigger else "정기 반기 최적화"
        logger.info(f"최적화 시작 ({trigger_reason})...")

        try:
            from scripts.optimize_weights import WeightOptimizer, get_price_data
            from pykrx import stock
            from datetime import datetime, timedelta

            # 데이터 수집
            end_date = datetime.now() - timedelta(days=2)
            start_date = end_date - timedelta(days=180)

            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")

            # KOSPI200 종목 조회
            for i in range(7):
                check_date = (end_date - timedelta(days=i)).strftime("%Y%m%d")
                tickers = stock.get_index_portfolio_deposit_file("1028", check_date)
                if tickers is not None and len(tickers) > 0:
                    break

            tickers = list(tickers)[:50]

            # 가격 데이터 수집
            price_data = {}
            for ticker in tickers:
                df = get_price_data(ticker, start_str, end_str)
                if df is not None and len(df) >= 60:
                    price_data[ticker] = df

            if len(price_data) < 10:
                raise ValueError("데이터 부족")

            # 최적화 실행
            optimizer = WeightOptimizer(price_data, start_date, end_date)
            results_df = optimizer.grid_search(verbose=False)

            if results_df.empty:
                raise ValueError("최적화 결과 없음")

            # 최적 결과
            best = results_df.iloc[0].to_dict()

            # 가중치 자동 업데이트
            updated = False
            if self.weights.get('auto_update', True):
                new_weights = WeightConfig.update_from_optimization(best)
                if new_weights != self.weights:
                    self.weights = new_weights
                    updated = True

            # 텔레그램 리포트 전송
            self.reporter.send_optimization_report(best, updated)

            logger.info(f"최적화 완료: 샤프비율={best.get('sharpe_ratio', 0):.2f}, 업데이트={updated}")
            return best

        except Exception as e:
            logger.error(f"최적화 오류: {e}")
            self.reporter.send_alert("최적화 오류", str(e), "CRITICAL")
            return {"error": str(e)}

    def schedule_jobs(self):
        """스케줄 작업 등록"""
        # 매월 1일 09:00 모니터링
        schedule.every().day.at("09:00").do(self._check_monthly_monitoring)

        # 매일 18:00 일간 요약 (선택적)
        # schedule.every().day.at("18:00").do(self._send_daily_summary)

        # 매일 체크 - 반기 최적화 (1월, 7월 첫째주)
        schedule.every().day.at("08:00").do(self._check_semiannual_optimization)

        logger.info("스케줄 작업 등록 완료")
        logger.info("  - 월간 모니터링: 매월 1일 09:00")
        logger.info("  - 반기 최적화: 1월/7월 첫째주")

    def _check_monthly_monitoring(self):
        """월간 모니터링 체크"""
        today = datetime.now()
        if today.day <= 3:  # 매월 1~3일
            # 이번 달 이미 실행했는지 체크
            last_run_file = Path("data/quant/last_monitoring.txt")
            if last_run_file.exists():
                last_run = last_run_file.read_text().strip()
                if last_run == today.strftime("%Y-%m"):
                    return  # 이미 실행됨

            self.run_monitoring()

            # 실행 기록
            last_run_file.parent.mkdir(parents=True, exist_ok=True)
            last_run_file.write_text(today.strftime("%Y-%m"))

    def _check_semiannual_optimization(self):
        """반기 최적화 체크"""
        today = datetime.now()

        # 1월 또는 7월 첫째주
        if today.month in [1, 7] and today.day <= 7:
            last_run_file = Path("data/quant/last_optimization.txt")
            if last_run_file.exists():
                last_run = last_run_file.read_text().strip()
                if last_run == today.strftime("%Y-%m"):
                    return  # 이미 실행됨

            self.run_optimization()

            # 실행 기록
            last_run_file.parent.mkdir(parents=True, exist_ok=True)
            last_run_file.write_text(today.strftime("%Y-%m"))

    def start(self):
        """스케줄러 시작"""
        self.running = True
        self.schedule_jobs()

        self.reporter.send_alert(
            "자동 관리 시작",
            "전략 자동 관리 스케줄러가 시작되었습니다.\n"
            "• 월간 모니터링: 매월 1일\n"
            "• 반기 최적화: 1월/7월",
            "SUCCESS"
        )

        logger.info("자동 관리 스케줄러 시작")

        while self.running:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 체크

    def stop(self):
        """스케줄러 중지"""
        self.running = False
        logger.info("자동 관리 스케줄러 중지")


def main():
    """메인 실행"""
    import argparse

    parser = argparse.ArgumentParser(description='자동 전략 관리')
    parser.add_argument('--daemon', action='store_true', help='데몬 모드로 실행')
    parser.add_argument('--monitor-now', action='store_true', help='즉시 모니터링 실행')
    parser.add_argument('--optimize-now', action='store_true', help='즉시 최적화 실행')
    parser.add_argument('--test-telegram', action='store_true', help='텔레그램 연동 테스트')

    args = parser.parse_args()

    manager = AutoStrategyManager()

    if args.test_telegram:
        manager.reporter.send_alert(
            "연동 테스트",
            "텔레그램 알림이 정상적으로 작동합니다!",
            "SUCCESS"
        )
        print("텔레그램 테스트 메시지 전송 완료")

    elif args.monitor_now:
        result = manager.run_monitoring()
        print(f"모니터링 완료: {result}")

    elif args.optimize_now:
        result = manager.run_optimization()
        print(f"최적화 완료: {result}")

    elif args.daemon:
        manager.start()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
