#!/usr/bin/env python3
"""
퀀트 시스템 통합 데몬
- 자동매매 엔진
- 전략 자동 관리 (모니터링, 최적화)
- 텔레그램 알림
"""

import sys
import os
import atexit

# 프로젝트 루트 경로 설정
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)

# 프로젝트 .env 파일 로드
from dotenv import load_dotenv
from pathlib import Path
env_path = Path(project_root) / ".env"
load_dotenv(env_path, override=True)

import logging
import signal
import threading
from datetime import datetime

# PID 파일 경로
PID_FILE = Path(project_root) / "data" / "daemon.pid"


def kill_existing_daemon() -> bool:
    """기존 데몬 프로세스 종료"""
    if not PID_FILE.exists():
        return False

    try:
        with open(PID_FILE, 'r') as f:
            old_pid = int(f.read().strip())

        # 프로세스 존재 여부 확인
        try:
            os.kill(old_pid, 0)  # 시그널 0은 프로세스 존재 확인용
        except OSError:
            # 프로세스가 없음 - PID 파일만 삭제
            PID_FILE.unlink()
            return False

        # 기존 프로세스 종료
        print(f"⚠️  기존 데몬 프로세스 발견 (PID: {old_pid})")
        print("   종료 중...")

        os.kill(old_pid, signal.SIGTERM)

        # 종료 대기 (최대 5초)
        import time
        for _ in range(10):
            time.sleep(0.5)
            try:
                os.kill(old_pid, 0)
            except OSError:
                print("   ✅ 기존 프로세스 종료됨")
                break
        else:
            # SIGTERM으로 안 되면 SIGKILL
            print("   강제 종료 시도...")
            try:
                os.kill(old_pid, signal.SIGKILL)
            except OSError:
                pass

        # Telegram 세션 정리 대기
        print("   텔레그램 세션 정리 대기 (3초)...")
        time.sleep(3)

        PID_FILE.unlink(missing_ok=True)
        return True

    except Exception as e:
        print(f"⚠️  기존 프로세스 확인 오류: {e}")
        PID_FILE.unlink(missing_ok=True)
        return False


def write_pid_file():
    """현재 프로세스 PID 파일 생성"""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


def cleanup_pid_file():
    """종료 시 PID 파일 삭제"""
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass

# 로그 디렉토리 생성
Path("logs").mkdir(exist_ok=True)

# LOG_LEVEL 환경변수에서 읽기 (기본값: INFO)
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/daemon_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)

# httpx 로거 레벨 올리기 (텔레그램 getUpdates 폴링 로그 숨김)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.info(f"로그 레벨: {log_level_str}")


class QuantDaemon:
    """퀀트 시스템 통합 데몬"""

    def __init__(self, dry_run: bool = True, is_virtual: bool = True):
        self.dry_run = dry_run
        self.is_virtual = is_virtual
        self.running = False
        self.threads = []
        self.engine = None  # QuantTradingEngine 인스턴스

    def start_trading_engine(self):
        """자동매매 엔진 시작"""
        from src.quant_engine import QuantTradingEngine, QuantEngineConfig
        from src.scheduler import WeightConfig
        from src.api import KISClient
        from src.core import get_controller

        # SystemController에서 저장된 설정 로드
        controller = get_controller()
        sys_config = controller.config

        # 팩터 가중치 로드 (optimal_weights.json)
        self.weights = WeightConfig.load()

        # SystemController 설정과 동기화
        # (텔레그램 명령으로 변경된 설정 반영)
        self.dry_run = sys_config.dry_run
        self.is_virtual = sys_config.is_virtual

        # 실제 계좌 잔고 조회 (조회 실패 시 1천만원 기본값 사용)
        self.total_capital = 10_000_000
        try:
            client = KISClient(is_virtual=self.is_virtual)
            balance = client.get_balance()
            if balance and 'cash' in balance:
                self.total_capital = balance['cash']
                logger.info(f"계좌 잔고 조회 성공: {self.total_capital:,}원")

                # market_calendar에 KIS 클라이언트 등록 (휴장일 자동 업데이트용)
                from src.utils.market_calendar import set_kis_client
                set_kis_client(client)
            else:
                logger.warning(f"계좌 잔고 조회 실패 - 기본값 사용: {self.total_capital:,}원")
        except Exception as e:
            logger.warning(f"계좌 잔고 조회 오류: {e} - 기본값 사용: {self.total_capital:,}원")

        # 목표 종목 수: SystemController 우선, 없으면 optimal_weights
        self.target_count = sys_config.target_count or self.weights.get('target_count', 15)

        config = QuantEngineConfig(
            universe_size=sys_config.universe_size,
            target_stock_count=self.target_count,
            total_capital=self.total_capital,
            dry_run=self.dry_run
        )

        logger.info(f"설정 로드: dry_run={self.dry_run}, target={self.target_count}, virtual={self.is_virtual}")

        self.engine = QuantTradingEngine(config=config, is_virtual=self.is_virtual)

        # SystemController에 콜백 등록 (텔레그램 명령어 연동)
        self._register_callbacks(controller)

        def run_engine():
            try:
                self.engine.start()
            except Exception as e:
                logger.error(f"트레이딩 엔진 오류: {e}")

        thread = threading.Thread(target=run_engine, name="TradingEngine", daemon=True)
        thread.start()
        self.threads.append(thread)
        logger.info("자동매매 엔진 시작됨")

        # SystemController 상태를 RUNNING으로 변경
        from src.core.system_controller import SystemState
        controller.state = SystemState.RUNNING
        controller._save_state()
        logger.info("시스템 상태: RUNNING")

    def _register_callbacks(self, controller):
        """SystemController에 엔진 콜백 등록"""
        if not self.engine:
            logger.warning("엔진이 없어 콜백 등록 스킵")
            return

        # 스크리닝 콜백
        controller.register_callback('on_screening', self.engine.run_screening)

        # 리밸런싱 콜백
        controller.register_callback('on_rebalance', self.engine.manual_rebalance)

        # 월간 리포트 콜백
        controller.register_callback('on_monthly_report', lambda: self.engine.generate_monthly_report(save_snapshot=False))

        # 엔진 제어 콜백
        controller.register_callback('on_stop', self.engine.stop)
        controller.register_callback('on_pause', self.engine.pause)
        controller.register_callback('on_resume', self.engine.resume)

        # 포지션 청산 콜백
        controller.register_callback('close_position', self._close_position)
        controller.register_callback('close_all_positions', self._close_all_positions)

        logger.info("SystemController 콜백 등록 완료")

    def _close_position(self, stock_code: str) -> dict:
        """특정 포지션 청산"""
        if not self.engine:
            return {"success": False, "message": "엔진이 실행 중이 아닙니다"}

        try:
            # 엔진의 포지션에서 해당 종목 찾기
            position = None
            for pos in self.engine.positions:
                if pos.code == stock_code:
                    position = pos
                    break

            if not position:
                return {"success": False, "message": f"포지션 없음: {stock_code}"}

            # 매도 주문 생성
            from src.quant_engine import PendingOrder
            order = PendingOrder(
                code=position.code,
                name=position.name,
                order_type="SELL",
                quantity=position.quantity,
                price=0,  # 시장가
                reason="수동 청산"
            )

            # 대기 주문에 추가
            self.engine.pending_orders.append(order)
            self.engine._save_state()

            logger.info(f"청산 주문 생성: {position.name} ({stock_code}) {position.quantity}주")
            return {"success": True, "message": f"{position.name} 청산 주문 생성됨"}

        except Exception as e:
            logger.error(f"청산 오류: {e}")
            return {"success": False, "message": str(e)}

    def _close_all_positions(self) -> dict:
        """전체 포지션 청산"""
        if not self.engine:
            return {"success": False, "message": "엔진이 실행 중이 아닙니다"}

        try:
            if not self.engine.positions:
                return {"success": False, "message": "보유 포지션 없음"}

            from src.quant_engine import PendingOrder
            count = 0

            for position in self.engine.positions:
                order = PendingOrder(
                    code=position.code,
                    name=position.name,
                    order_type="SELL",
                    quantity=position.quantity,
                    price=0,  # 시장가
                    reason="전체 청산"
                )
                self.engine.pending_orders.append(order)
                count += 1

            self.engine._save_state()
            logger.info(f"전체 청산 주문 생성: {count}개 종목")
            return {"success": True, "message": f"{count}개 종목 청산 주문 생성됨"}

        except Exception as e:
            logger.error(f"전체 청산 오류: {e}")
            return {"success": False, "message": str(e)}

    def start_auto_manager(self):
        """자동 관리 스케줄러 시작"""
        from src.scheduler import AutoStrategyManager

        manager = AutoStrategyManager()

        def run_manager():
            try:
                manager.start()
            except Exception as e:
                logger.error(f"자동 관리 오류: {e}")

        thread = threading.Thread(target=run_manager, name="AutoManager", daemon=True)
        thread.start()
        self.threads.append(thread)
        logger.info("자동 관리 스케줄러 시작됨")

    def start_telegram_bot(self):
        """텔레그램 봇 시작"""
        thread = self._create_telegram_thread()
        thread.start()
        self.threads.append(thread)
        logger.info("텔레그램 봇 시작됨")

    def _create_telegram_thread(self):
        """텔레그램 봇 스레드 생성"""
        from src.telegram.bot import TelegramBotHandler
        from src.api import KISClient

        # API 클라이언트 생성 (잔고/시세 조회용)
        try:
            kis_client = KISClient(is_virtual=self.is_virtual)
            logger.info("텔레그램 봇용 KIS 클라이언트 연결됨")
        except Exception as e:
            logger.warning(f"KIS 클라이언트 연결 실패: {e} - 캐시 데이터 사용")
            kis_client = None

        bot = TelegramBotHandler(kis_client=kis_client)
        self._telegram_bot = bot  # 재시작 시 참조용

        def run_bot():
            try:
                bot.start()
            except Exception as e:
                logger.error(f"텔레그램 봇 오류: {e}")

        return threading.Thread(target=run_bot, name="TelegramBot", daemon=True)

    def send_startup_notification(self):
        """시작 알림 전송 (재시도 포함)"""
        import time
        from src.telegram import get_notifier

        notifier = get_notifier()

        mode = "🧪 모의투자" if self.is_virtual else "💰 실전투자"
        dry_run = "✅ Dry-Run" if self.dry_run else "🔴 실제 주문"

        # 가중치 정보 (기본값 처리)
        weights = getattr(self, 'weights', {})
        total_capital = getattr(self, 'total_capital', 10_000_000)
        target_count = getattr(self, 'target_count', 15)

        mom_w = weights.get('momentum_weight', 0.2)
        short_mom_w = weights.get('short_mom_weight', 0.1)
        vol_w = weights.get('volatility_weight', 0.5)

        message = f"""
🚀 <b>퀀트 시스템 시작</b>
━━━━━━━━━━━━━━━━━━━━

{mode} | {dry_run}

<b>투자 설정:</b>
• 투자금: {total_capital:,}원
• 목표 종목: {target_count}개

<b>팩터 가중치:</b>
• 모멘텀: {mom_w:.0%} | 단기: {short_mom_w:.0%} | 변동성: {vol_w:.0%}

<b>자동 관리 일정:</b>
• 월간 모니터링: 매월 1일 09:00
• 반기 최적화: 1월/7월

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        # 재시도 로직 (최대 3회, 2초 간격)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if notifier.send_message(message.strip()):
                    logger.info("시작 알림 전송 성공")
                    return  # 성공
                else:
                    raise Exception("send_message returned False")
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"시작 알림 전송 실패 (시도 {attempt + 1}/{max_retries}): {e}")
                    time.sleep(2)  # 2초 대기 후 재시도
                else:
                    logger.error(f"시작 알림 전송 최종 실패: {e}")

    def start(self):
        """데몬 시작"""
        self.running = True

        print("\n" + "=" * 60)
        print("     퀀트 시스템 통합 데몬 시작")
        print("=" * 60)
        print(f"\n모드: {'모의투자' if self.is_virtual else '실전투자'}")
        print(f"Dry-Run: {self.dry_run}")
        print("\n시작 중...")

        try:
            # 각 서비스 시작
            self.start_trading_engine()
            self.start_auto_manager()
            self.start_telegram_bot()

            # 시작 알림
            self.send_startup_notification()

            print("\n✅ 모든 서비스 시작 완료")
            print("   Ctrl+C로 종료\n")
            print("=" * 60)

            # 시그널 핸들러 등록
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

            # 메인 루프 (스레드 모니터링 및 자동 재시작)
            import time
            restart_counts = {}  # 스레드별 재시작 횟수
            max_restarts = 5     # 최대 재시작 횟수

            while self.running:
                # 스레드 상태 체크 및 재시작
                for i, thread in enumerate(self.threads):
                    if not thread.is_alive():
                        thread_name = thread.name
                        restart_counts[thread_name] = restart_counts.get(thread_name, 0) + 1

                        if restart_counts[thread_name] <= max_restarts:
                            logger.warning(f"스레드 종료 감지: {thread_name} - 재시작 시도 ({restart_counts[thread_name]}/{max_restarts})")

                            # 텔레그램 봇 스레드 재시작
                            if thread_name == "TelegramBot":
                                time.sleep(5)  # 잠시 대기 후 재시작
                                new_thread = self._create_telegram_thread()
                                new_thread.start()
                                self.threads[i] = new_thread
                                logger.info(f"텔레그램 봇 스레드 재시작됨")
                            else:
                                logger.warning(f"{thread_name} 스레드는 자동 재시작 미지원")
                        else:
                            logger.error(f"스레드 {thread_name} 최대 재시작 횟수 초과 - 재시작 중단")

                time.sleep(10)

        except KeyboardInterrupt:
            self.stop()

    def _signal_handler(self, signum, frame):
        """시그널 핸들러"""
        logger.info(f"시그널 수신: {signum}")
        self.stop()

    def stop(self):
        """데몬 중지"""
        self.running = False

        # SystemController 상태를 STOPPED로 변경
        try:
            from src.core import get_controller
            from src.core.system_controller import SystemState
            controller = get_controller()
            controller.state = SystemState.STOPPED
            controller._save_state()
            logger.info("시스템 상태: STOPPED")
        except Exception as e:
            logger.debug(f"상태 저장 실패 (무시): {e}")

        # 종료 알림 (이벤트 루프 닫힘 오류 무시)
        try:
            from src.telegram import get_notifier
            notifier = get_notifier()
            notifier.send_message("🛑 퀀트 시스템이 종료되었습니다.")
        except Exception as e:
            logger.debug(f"종료 알림 전송 실패 (무시): {e}")

        logger.info("데몬 종료 중...")
        print("\n데몬 종료됨")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='퀀트 시스템 통합 데몬')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Dry-run 모드 (기본값)')
    parser.add_argument('--no-dry-run', action='store_true',
                        help='실제 주문 모드')
    parser.add_argument('--virtual', action='store_true', default=True,
                        help='모의투자 (기본값)')
    parser.add_argument('--real', action='store_true',
                        help='실전투자')
    parser.add_argument('--force', '-f', action='store_true',
                        help='기존 프로세스 강제 종료 후 시작')

    args = parser.parse_args()

    # ========== 중복 실행 방지 ==========
    # 기존 데몬이 실행 중이면 종료
    if kill_existing_daemon():
        print("")  # 줄바꿈

    # PID 파일 생성 및 종료 시 정리 등록
    write_pid_file()
    atexit.register(cleanup_pid_file)

    logger.info(f"데몬 시작 (PID: {os.getpid()})")

    # SystemController에서 저장된 설정 로드
    from src.core import get_controller
    controller = get_controller()

    # 명령줄 인자가 명시적으로 지정된 경우 SystemController에 저장
    if args.no_dry_run:
        controller.config.dry_run = False
        controller.save_config()
        logger.info("명령줄 인자로 dry_run=False 설정됨")

    if args.real:
        confirm = input("⚠️ 실전투자 모드입니다. 계속하시겠습니까? (yes/no): ")
        if confirm.lower() != 'yes':
            print("취소됨")
            cleanup_pid_file()
            return
        controller.config.is_virtual = False
        controller.save_config()
        logger.info("명령줄 인자로 is_virtual=False 설정됨")

    # SystemController의 설정 사용 (기본값 또는 이전에 저장된 값)
    dry_run = controller.config.dry_run
    is_virtual = controller.config.is_virtual

    daemon = QuantDaemon(dry_run=dry_run, is_virtual=is_virtual)
    daemon.start()


if __name__ == "__main__":
    main()
