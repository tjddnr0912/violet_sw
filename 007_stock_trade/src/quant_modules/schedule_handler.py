"""
스케줄 핸들러

퀀트 엔진의 일일 스케줄 관리 (장 전/장중/장마감 이벤트)
"""

import schedule
import logging
from datetime import datetime, timedelta

from .state_manager import EngineState, SchedulePhase
from ..utils import is_trading_day, get_trading_hours, get_market_open_time

logger = logging.getLogger(__name__)


class ScheduleHandler:
    """스케줄 이벤트 핸들러"""

    def __init__(self, engine):
        """
        Args:
            engine: QuantTradingEngine 인스턴스 참조
        """
        self.engine = engine

    def setup_schedule(self):
        """스케줄 설정"""
        e = self.engine

        # 장 전 스크리닝 (리밸런싱 일에만)
        schedule.every().day.at(e.config.screening_time).do(self.on_pre_market)
        schedule.every().day.at("09:30").do(self.on_pre_market)  # 10시 개장일 대비

        # 장 시작 - 주문 실행 (특수 개장일 대비 여러 시간 등록)
        schedule.every().day.at(e.config.market_open_time).do(self.on_market_open)
        schedule.every().day.at("10:00").do(self.on_market_open)  # 1/2 등 10시 개장

        # 장중 모니터링
        schedule.every(e.config.monitoring_interval).minutes.do(self.on_monitoring)

        # 장 마감 리포트
        schedule.every().day.at(e.config.market_close_time).do(self.on_market_close)

        # 주간 장부 점검 (토요일 10:00)
        schedule.every().saturday.at("10:00").do(e._on_weekly_reconciliation)

        logger.info("스케줄 설정 완료")
        logger.info(f"  - 스크리닝: {e.config.screening_time} (리밸런싱 일)")
        logger.info(f"  - 주문 실행: {e.config.market_open_time} (특수일: 10:00)")
        logger.info(f"  - 모니터링: {e.config.monitoring_interval}분 간격")
        logger.info(f"  - 리포트: {e.config.market_close_time}")
        logger.info(f"  - 주간 점검: 토요일 10:00")

    def check_initial_setup(self):
        """
        최초 실행 시 자동 스크리닝

        조건:
        1. 보유 포지션이 없음
        2. 이번 달 리밸런싱을 아직 하지 않음
        """
        e = self.engine
        current_month = datetime.now().strftime("%Y-%m")

        # 이미 이번 달 리밸런싱을 완료한 경우 스킵
        if e.last_rebalance_month == current_month:
            logger.info(f"이번 달({current_month}) 리밸런싱 완료됨 - 초기 스크리닝 스킵")
            return

        # 보유 포지션이 있으면 스킵
        if e.portfolio.positions:
            logger.info(f"보유 포지션 {len(e.portfolio.positions)}개 - 초기 스크리닝 스킵")
            return

        # 휴장일이면 스킵
        if not is_trading_day():
            logger.info("휴장일 - 초기 스크리닝 스킵 (다음 거래일에 자동 실행)")
            return

        logger.info("=" * 60)
        logger.info("최초 실행 감지 - 초기 스크리닝 시작")
        logger.info("=" * 60)

        e.notifier.send_message(
            "🚀 <b>최초 실행 감지</b>\n\n"
            "보유 포지션이 없어 초기 스크리닝을 시작합니다.\n"
            "스크리닝 완료 후 리밸런싱 주문이 생성됩니다."
        )

        try:
            # 스크리닝 실행
            screening_result = e.run_screening()
            if screening_result is None:
                logger.error("초기 스크리닝 실패")
                e.notifier.send_message(
                    "⚠️ <b>초기 스크리닝 실패</b>\n\n"
                    "수동으로 /run_screening 명령을 실행해주세요."
                )
                return

            # 리밸런싱 주문 생성
            orders = e.generate_rebalance_orders()

            if orders:
                now = datetime.now()
                e.last_rebalance_date = now
                e.last_rebalance_month = now.strftime("%Y-%m")
                e._save_state()

                logger.info(f"초기 설정 완료: {len(orders)}개 주문 생성")

                # 장 시간인 경우 즉시 실행
                if e._is_trading_time():
                    e.notifier.send_message(
                        f"✅ <b>초기 스크리닝 완료</b>\n\n"
                        f"• 생성된 주문: {len(orders)}개\n\n"
                        f"현재 장 시간입니다. 즉시 주문을 실행합니다."
                    )
                    logger.info("장중 초기 스크리닝 - 즉시 주문 실행")
                    e.execute_pending_orders()
                else:
                    e.notifier.send_message(
                        f"✅ <b>초기 스크리닝 완료</b>\n\n"
                        f"• 생성된 주문: {len(orders)}개\n\n"
                        f"다음 거래일 09:00 장 시작 시 자동 실행됩니다."
                    )
            else:
                logger.info("초기 설정 완료: 생성된 주문 없음")

        except Exception as ex:
            logger.error(f"초기 스크리닝 오류: {ex}", exc_info=True)
            from src.utils.error_formatter import format_user_error
            e.notifier.send_message(format_user_error(ex, "초기 스크리닝"))

    def on_pre_market(self):
        """장 전 이벤트"""
        e = self.engine
        if e.state != EngineState.RUNNING:
            return

        # 휴장일 제외
        if not is_trading_day():
            return

        # 이미 장 전 처리가 완료된 경우 스킵 (중복 실행 방지)
        if e.current_phase in [SchedulePhase.PRE_MARKET, SchedulePhase.MARKET_OPEN, SchedulePhase.MARKET_HOURS]:
            return

        # 실제 개장 시간 확인 (특수 개장일 대응)
        market_open_time = get_market_open_time()
        current_time = datetime.now().strftime("%H:%M")

        # 개장 30분 전부터 장 전 처리 가능
        open_dt = datetime.strptime(market_open_time, "%H:%M")
        pre_market_dt = open_dt - timedelta(minutes=30)
        pre_market_start = pre_market_dt.strftime("%H:%M")

        # 현재 시간이 장 전 처리 시간보다 이전이면 스킵
        if current_time < pre_market_start:
            logger.debug(f"장 전 처리 시간 전 ({current_time} < {pre_market_start}) - 스킵")
            return

        e.current_phase = SchedulePhase.PRE_MARKET
        logger.info("=" * 60)
        logger.info(f"장 전 처리 시작 (개장: {market_open_time})")
        e.notifier.send_message(
            f"🌅 <b>장 전 처리 시작</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"📅 개장: {market_open_time}"
        )

        # 포지션이 없으면 스크리닝 실행
        if not e.portfolio.positions:
            current_month = datetime.now().strftime("%Y-%m")
            if e.last_rebalance_month != current_month:
                # 이번 달 리밸런싱 전: 초기 스크리닝
                logger.info("포지션 없음 - 초기 스크리닝 실행")
                e.notifier.send_message(
                    "📋 <b>포지션 없음</b> - 초기 스크리닝을 실행합니다."
                )
                self.check_initial_setup()
                return
            else:
                # 이번 달 리밸런싱 완료 후 전량 청산 → 제로 포지션 복구 모드
                today_str = datetime.now().strftime("%Y-%m-%d")
                if e._last_zero_recovery_date == today_str:
                    logger.debug("제로 포지션 복구: 오늘 이미 시도함 - 스킵")
                    return
                e._last_zero_recovery_date = today_str
                logger.info("제로 포지션 복구 모드 - 리밸런싱 완료 후 전량 청산 감지")
                e.notifier.send_message(
                    "🔄 <b>제로 포지션 복구</b>\n\n"
                    "리밸런싱 완료 후 전량 청산이 감지되었습니다.\n"
                    "스크리닝 후 신규 매수를 시도합니다."
                )
                # _is_rebalance_day()가 제로 포지션이면 월간 잠금을 무시하므로
                # 아래 리밸런싱 체크로 넘어감

        # 리밸런싱 일인 경우 스크리닝 실행
        if e._is_rebalance_day():
            logger.info("리밸런싱 일 - 스크리닝 실행")
            e.notifier.send_message(
                "📆 <b>리밸런싱 일</b> - 스크리닝을 실행합니다."
            )

            # 스크리닝 실행 및 결과 체크
            screening_result = e.run_screening()
            if screening_result is None:
                logger.error("스크리닝 실패 - 리밸런싱 중단")
                e.notifier.send_message(
                    "⚠️ <b>스크리닝 실패</b>\n\n"
                    "리밸런싱 일이지만 스크리닝이 실패했습니다.\n"
                    "수동으로 /run_screening 명령을 실행하거나\n"
                    "로그를 확인해주세요."
                )
                return

            # 리밸런싱 주문 생성
            orders = e.generate_rebalance_orders()

            # 리밸런싱 날짜 기록 (중복 실행 방지)
            if orders:
                now = datetime.now()
                e.last_rebalance_date = now
                e.last_rebalance_month = now.strftime("%Y-%m")

                # 긴급 리밸런싱인 경우 별도 추적 (월 1회 제한)
                if e._urgent_rebalance_mode:
                    e.state_manager.last_urgent_rebalance_month = now.strftime("%Y-%m")
                    logger.info(f"긴급 리밸런싱 완료 기록: {e.state_manager.last_urgent_rebalance_month}")

                e._save_state()
                logger.info(f"리밸런싱 완료 기록: {e.last_rebalance_month}")
            else:
                logger.info("생성된 리밸런싱 주문 없음 (포트폴리오 유지)")
        else:
            logger.info("리밸런싱 일 아님 - 스크리닝 스킵")

    def on_market_open(self):
        """장 시작 이벤트"""
        e = self.engine
        if e.state != EngineState.RUNNING:
            return

        if not is_trading_day():
            return

        # 이미 장 시작 처리가 완료된 경우 스킵 (중복 실행 방지)
        if e.current_phase in [SchedulePhase.MARKET_OPEN, SchedulePhase.MARKET_HOURS]:
            return

        # 실제 개장 시간 확인 (특수 개장일 대응)
        market_open_time = get_market_open_time()
        current_time = datetime.now().strftime("%H:%M")

        # 현재 시간이 개장 시간보다 이전이면 스킵
        if current_time < market_open_time:
            logger.debug(f"개장 전 ({current_time} < {market_open_time}) - 스킵")
            return

        e.current_phase = SchedulePhase.MARKET_OPEN
        logger.info("=" * 60)
        logger.info(f"장 시작 ({market_open_time}) - 대기 주문 실행")

        pending_count = len(e.pending_orders)
        if pending_count > 0:
            e.notifier.send_message(
                f"🔔 <b>장 시작</b> ({market_open_time})\n"
                f"━━━━━━━━━━━━━━━\n"
                f"대기 주문 {pending_count}개 실행 중..."
            )
        else:
            e.notifier.send_message(
                f"🔔 <b>장 시작</b> ({market_open_time})\n"
                f"━━━━━━━━━━━━━━━\n"
                f"대기 주문 없음 - 모니터링 모드"
            )

        # 대기 주문 실행
        e.execute_pending_orders()

        e.current_phase = SchedulePhase.MARKET_HOURS

    def on_monitoring(self):
        """모니터링 이벤트"""
        e = self.engine
        if e.state != EngineState.RUNNING:
            return

        if not e._is_trading_time():
            return

        e.monitor_positions()

    def on_market_close(self):
        """장 마감 이벤트"""
        e = self.engine
        if e.state != EngineState.RUNNING:
            return

        if not is_trading_day():
            return

        e.current_phase = SchedulePhase.MARKET_CLOSE
        logger.info("=" * 60)
        logger.info("장 마감 - 일일 리포트 생성")
        e.notifier.send_message(
            f"🌙 <b>장 마감</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"일일 리포트를 생성합니다..."
        )

        # 일일 리포트
        e.generate_daily_report()

        # 리밸런싱 일이면 월간 리포트 발송
        if e._was_rebalance_today():
            logger.info("리밸런싱 일 - 월간 리포트 생성")
            e.generate_monthly_report(save_snapshot=True)

        # 상태 저장
        e._save_state()

        e.current_phase = SchedulePhase.AFTER_MARKET
