"""
시스템 원격 제어 모듈
- 텔레그램을 통한 시스템 제어
- 상태 관리 및 명령 처리
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from enum import Enum
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


class SystemState(Enum):
    """시스템 상태"""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    EMERGENCY_STOP = "emergency_stop"


@dataclass
class SystemConfig:
    """시스템 설정"""
    dry_run: bool = True
    is_virtual: bool = True
    target_count: int = 15
    universe_size: int = 200
    stop_loss_pct: float = 7.0
    take_profit_pct: float = 10.0
    max_daily_trades: int = 10

    # 신호 가중치 (모니터링/최적화용, system_config.json에 저장)
    # 주의: 엔진 스크리너의 V/M/Q 팩터 가중치는 optimal_weights.json에서 관리
    momentum_weight: float = 0.20
    short_mom_weight: float = 0.10
    volatility_weight: float = 0.50
    volume_weight: float = 0.00


class SystemController:
    """시스템 원격 제어기 (Thread-safe Singleton)"""

    STATE_FILE = "data/quant/system_state.json"
    CONFIG_FILE = "config/system_config.json"

    _instance = None
    _lock = threading.Lock()
    _init_lock = threading.Lock()  # __init__ 보호용 별도 락

    def __new__(cls):
        """싱글톤 패턴 (Double-checked locking)"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        # 빠른 체크 (락 없이)
        if getattr(self, '_initialized', False):
            return

        # 스레드 안전한 초기화
        with self._init_lock:
            # 이중 체크 (락 획득 후)
            if self._initialized:
                return

            self._initialized = True
            self.state = SystemState.STOPPED
            self.config = SystemConfig()
            self.engine = None
            self.callbacks: Dict[str, Callable] = {}
            self.last_action = None
            self.last_action_time = None
            self._state_lock = threading.Lock()  # 상태 변경 보호용 락

            # 디렉토리 생성
            Path("data/quant").mkdir(parents=True, exist_ok=True)
            Path("config").mkdir(parents=True, exist_ok=True)

            # 저장된 상태/설정 로드
            self._load_state()
            self._load_config()

            logger.info("SystemController 초기화 완료")

    def _load_state(self):
        """상태 로드"""
        state_path = Path(self.STATE_FILE)
        if state_path.exists():
            try:
                with open(state_path, 'r') as f:
                    data = json.load(f)
                    self.state = SystemState(data.get('state', 'stopped'))
                    self.last_action = data.get('last_action')
                    self.last_action_time = data.get('last_action_time')
            except Exception as e:
                logger.error(f"상태 로드 실패: {e}")

    def _save_state(self):
        """상태 저장 (atomic write)"""
        try:
            data = {
                'state': self.state.value,
                'last_action': self.last_action,
                'last_action_time': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            # Atomic write: 임시 파일에 쓰고 이름 변경
            temp_file = f"{self.STATE_FILE}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            import os
            os.replace(temp_file, self.STATE_FILE)  # atomic on POSIX
        except Exception as e:
            logger.error(f"상태 저장 실패: {e}")

    def _load_config(self):
        """설정 로드"""
        config_path = Path(self.CONFIG_FILE)
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                    self.config = SystemConfig(**data)
            except Exception as e:
                logger.error(f"설정 로드 실패: {e}")

    def save_config(self):
        """설정 저장"""
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(asdict(self.config), f, indent=2, ensure_ascii=False)
            logger.info("설정 저장 완료")
        except Exception as e:
            logger.error(f"설정 저장 실패: {e}")

    def register_callback(self, name: str, callback: Callable):
        """콜백 등록"""
        self.callbacks[name] = callback
        logger.info(f"콜백 등록: {name}")

    def _trigger_callback(self, name: str, *args, **kwargs):
        """콜백 실행"""
        if name in self.callbacks:
            try:
                return self.callbacks[name](*args, **kwargs)
            except Exception as e:
                logger.error(f"콜백 실행 오류 ({name}): {e}")
        return None

    # ==================== 시스템 제어 ====================

    def start_trading(self) -> Dict[str, Any]:
        """자동매매 시작"""
        with self._state_lock:
            if self.state == SystemState.EMERGENCY_STOP:
                return {"success": False, "message": "긴급 정지 상태입니다. 먼저 해제하세요."}

            if self.state == SystemState.RUNNING:
                return {"success": False, "message": "이미 실행 중입니다."}

            self.state = SystemState.RUNNING
            self.last_action = "start_trading"
            self._save_state()

        # 엔진 시작 콜백 (락 외부에서 실행 - 데드락 방지)
        self._trigger_callback('on_start')

        logger.info("자동매매 시작됨")
        return {
            "success": True,
            "message": "자동매매가 시작되었습니다.",
            "state": self.state.value,
            "config": {
                "dry_run": self.config.dry_run,
                "target_count": self.config.target_count
            }
        }

    def stop_trading(self) -> Dict[str, Any]:
        """자동매매 중지"""
        with self._state_lock:
            if self.state == SystemState.STOPPED:
                return {"success": False, "message": "이미 중지 상태입니다."}

            prev_state = self.state
            self.state = SystemState.STOPPED
            self.last_action = "stop_trading"
            self._save_state()

        # 엔진 중지 콜백
        self._trigger_callback('on_stop')

        logger.info("자동매매 중지됨")
        return {
            "success": True,
            "message": "자동매매가 중지되었습니다.",
            "previous_state": prev_state.value,
            "state": self.state.value
        }

    def pause_trading(self) -> Dict[str, Any]:
        """자동매매 일시정지"""
        with self._state_lock:
            if self.state != SystemState.RUNNING:
                return {"success": False, "message": "실행 중 상태에서만 일시정지할 수 있습니다."}

            self.state = SystemState.PAUSED
            self.last_action = "pause_trading"
            self._save_state()

        self._trigger_callback('on_pause')

        logger.info("자동매매 일시정지됨")
        return {
            "success": True,
            "message": "자동매매가 일시정지되었습니다.\n/resume 명령으로 재개할 수 있습니다.",
            "state": self.state.value
        }

    def resume_trading(self) -> Dict[str, Any]:
        """자동매매 재개"""
        with self._state_lock:
            if self.state != SystemState.PAUSED:
                return {"success": False, "message": "일시정지 상태에서만 재개할 수 있습니다."}

            self.state = SystemState.RUNNING
            self.last_action = "resume_trading"
            self._save_state()

        self._trigger_callback('on_resume')

        logger.info("자동매매 재개됨")
        return {
            "success": True,
            "message": "자동매매가 재개되었습니다.",
            "state": self.state.value
        }

    def emergency_stop(self) -> Dict[str, Any]:
        """긴급 정지 - 모든 거래 즉시 중단"""
        with self._state_lock:
            prev_state = self.state
            self.state = SystemState.EMERGENCY_STOP
            self.last_action = "emergency_stop"
            self._save_state()

        # 긴급 정지 콜백 (포지션 정리 등)
        self._trigger_callback('on_emergency_stop')

        logger.warning("긴급 정지 실행됨!")
        return {
            "success": True,
            "message": "🚨 긴급 정지가 실행되었습니다.\n모든 거래가 중단됩니다.\n/clear_emergency 명령으로 해제할 수 있습니다.",
            "previous_state": prev_state.value,
            "state": self.state.value
        }

    def clear_emergency(self) -> Dict[str, Any]:
        """긴급 정지 해제"""
        with self._state_lock:
            if self.state != SystemState.EMERGENCY_STOP:
                return {"success": False, "message": "긴급 정지 상태가 아닙니다."}

            self.state = SystemState.STOPPED
            self.last_action = "clear_emergency"
            self._save_state()

        logger.info("긴급 정지 해제됨")
        return {
            "success": True,
            "message": "긴급 정지가 해제되었습니다.\n/start_trading 명령으로 거래를 재개할 수 있습니다.",
            "state": self.state.value
        }

    # ==================== 수동 실행 ====================

    def run_screening(self) -> Dict[str, Any]:
        """스크리닝 수동 실행"""
        if self.state == SystemState.EMERGENCY_STOP:
            return {"success": False, "message": "긴급 정지 상태에서는 실행할 수 없습니다."}

        # 콜백 등록 여부 확인
        if 'on_screening' not in self.callbacks:
            return {"success": False, "message": "스크리닝 콜백이 등록되지 않았습니다. 데몬이 실행 중인지 확인하세요."}

        result = self._trigger_callback('on_screening')

        if result:
            return {
                "success": True,
                "message": "스크리닝이 실행되었습니다.",
                "result": result
            }
        return {
            "success": True,
            "message": "스크리닝 요청이 전송되었습니다."
        }

    def run_rebalance(self) -> Dict[str, Any]:
        """리밸런싱 수동 실행"""
        if self.state == SystemState.EMERGENCY_STOP:
            return {"success": False, "message": "긴급 정지 상태에서는 실행할 수 없습니다."}

        if self.state != SystemState.RUNNING and self.state != SystemState.PAUSED:
            return {"success": False, "message": "거래 시스템이 활성화되어 있지 않습니다."}

        # 콜백 등록 여부 확인
        if 'on_rebalance' not in self.callbacks:
            return {"success": False, "message": "리밸런싱 콜백이 등록되지 않았습니다. 데몬이 실행 중인지 확인하세요."}

        result = self._trigger_callback('on_rebalance')

        # 콜백 결과가 dict면 그대로 반환
        if isinstance(result, dict):
            return result

        return {
            "success": True,
            "message": "리밸런싱 요청이 전송되었습니다.",
            "result": result
        }

    def run_optimize(self) -> Dict[str, Any]:
        """최적화 수동 실행"""
        # 콜백 등록 여부 확인
        if 'on_optimize' not in self.callbacks:
            return {"success": False, "message": "최적화 콜백이 등록되지 않았습니다. 데몬이 실행 중인지 확인하세요."}

        result = self._trigger_callback('on_optimize')

        return {
            "success": True,
            "message": "최적화가 시작되었습니다. 완료되면 알림이 전송됩니다.",
            "result": result
        }

    def run_monthly_report(self) -> Dict[str, Any]:
        """월간 리포트 수동 실행"""
        # 콜백 등록 여부 확인
        if 'on_monthly_report' not in self.callbacks:
            return {"success": False, "message": "월간 리포트 콜백이 등록되지 않았습니다. 데몬이 실행 중인지 확인하세요."}

        try:
            self._trigger_callback('on_monthly_report')
            return {
                "success": True,
                "message": "월간 리포트가 생성되었습니다."
            }
        except Exception as e:
            logger.error(f"월간 리포트 생성 실패: {e}")
            return {
                "success": False,
                "message": f"리포트 생성 중 오류: {str(e)[:100]}"
            }

    def run_urgent_rebalance(self, force: bool = False) -> Dict[str, Any]:
        """
        긴급 리밸런싱 실행 (부분 매수)

        Args:
            force: True면 보유 비율 관계없이 강제 실행

        Returns:
            실행 결과 딕셔너리
        """
        if self.state == SystemState.EMERGENCY_STOP:
            return {"success": False, "message": "긴급 정지 상태에서는 실행할 수 없습니다."}

        if self.state != SystemState.RUNNING and self.state != SystemState.PAUSED:
            return {"success": False, "message": "거래 시스템이 활성화되어 있지 않습니다."}

        # 콜백 등록 여부 확인
        if 'on_urgent_rebalance' not in self.callbacks:
            return {"success": False, "message": "긴급 리밸런싱 콜백이 등록되지 않았습니다. 데몬이 실행 중인지 확인하세요."}

        result = self._trigger_callback('on_urgent_rebalance', force)

        # 콜백 결과가 dict면 그대로 반환
        if isinstance(result, dict):
            return result

        return {
            "success": True,
            "message": "긴급 리밸런싱 요청이 전송되었습니다.",
            "result": result
        }

    # ==================== 설정 변경 ====================

    def set_dry_run(self, enabled: bool) -> Dict[str, Any]:
        """Dry-run 모드 설정"""
        prev_value = self.config.dry_run
        self.config.dry_run = enabled
        self.save_config()

        mode = "활성화" if enabled else "비활성화"
        warning = "\n⚠️ 실제 주문이 실행됩니다!" if not enabled else ""

        return {
            "success": True,
            "message": f"Dry-run 모드가 {mode}되었습니다.{warning}",
            "previous": prev_value,
            "current": enabled
        }

    def set_target_count(self, count: int) -> Dict[str, Any]:
        """목표 종목 수 설정"""
        if count < 1 or count > 50:
            return {"success": False, "message": "목표 종목 수는 1~50 사이여야 합니다."}

        prev_value = self.config.target_count
        self.config.target_count = count
        self.save_config()

        return {
            "success": True,
            "message": f"목표 종목 수가 {count}개로 변경되었습니다.",
            "previous": prev_value,
            "current": count
        }

    def set_stop_loss(self, pct: float) -> Dict[str, Any]:
        """손절 비율 설정"""
        if pct < 1.0 or pct > 30.0:
            return {"success": False, "message": "손절 비율은 1~30% 사이여야 합니다."}

        prev_value = self.config.stop_loss_pct
        self.config.stop_loss_pct = pct
        self.save_config()

        return {
            "success": True,
            "message": f"손절 비율이 {pct}%로 변경되었습니다.",
            "previous": prev_value,
            "current": pct
        }

    def set_weights(self, momentum: float = None, short_mom: float = None,
                   volatility: float = None, volume: float = None) -> Dict[str, Any]:
        """팩터 가중치 설정"""
        # 입력값 검증
        weights_to_set = {
            "momentum": momentum,
            "short_mom": short_mom,
            "volatility": volatility,
            "volume": volume
        }

        errors = []
        for name, value in weights_to_set.items():
            if value is not None:
                if not isinstance(value, (int, float)):
                    errors.append(f"{name}은(는) 숫자여야 합니다: {value}")
                elif not (0.0 <= value <= 1.0):
                    errors.append(f"{name}은(는) 0.0~1.0 사이여야 합니다: {value:.2f}")

        if errors:
            return {
                "success": False,
                "message": "가중치 검증 실패:\n" + "\n".join(f"  - {e}" for e in errors)
            }

        # 새 가중치 적용 후 합계 검증
        new_momentum = momentum if momentum is not None else self.config.momentum_weight
        new_short_mom = short_mom if short_mom is not None else self.config.short_mom_weight
        new_volatility = volatility if volatility is not None else self.config.volatility_weight
        new_volume = volume if volume is not None else self.config.volume_weight

        weight_sum = new_momentum + new_short_mom + new_volatility + new_volume
        if not (0.99 <= weight_sum <= 1.01):
            return {
                "success": False,
                "message": f"가중치 합계는 1.0이어야 합니다 (현재: {weight_sum:.2f})\n"
                          f"  모멘텀: {new_momentum:.2f}, 단기모멘텀: {new_short_mom:.2f}, "
                          f"변동성: {new_volatility:.2f}, 거래량: {new_volume:.2f}"
            }

        changes = []

        if momentum is not None:
            self.config.momentum_weight = momentum
            changes.append(f"모멘텀: {momentum:.2f}")

        if short_mom is not None:
            self.config.short_mom_weight = short_mom
            changes.append(f"단기모멘텀: {short_mom:.2f}")

        if volatility is not None:
            self.config.volatility_weight = volatility
            changes.append(f"변동성: {volatility:.2f}")

        if volume is not None:
            self.config.volume_weight = volume
            changes.append(f"거래량: {volume:.2f}")

        if changes:
            self.save_config()
            return {
                "success": True,
                "message": f"가중치가 변경되었습니다.\n" + "\n".join(changes),
                "weights": {
                    "momentum": self.config.momentum_weight,
                    "short_mom": self.config.short_mom_weight,
                    "volatility": self.config.volatility_weight,
                    "volume": self.config.volume_weight
                }
            }

        return {"success": False, "message": "변경할 가중치를 지정하세요."}

    # ==================== 상태 조회 ====================

    def get_status(self) -> Dict[str, Any]:
        """시스템 상태 조회"""
        return {
            "state": self.state.value,
            "last_action": self.last_action,
            "last_action_time": self.last_action_time,
            "config": asdict(self.config)
        }

    def get_positions(self) -> Dict[str, Any]:
        """포지션 조회"""
        result = self._trigger_callback('get_positions')

        if result:
            return {"success": True, "positions": result}

        # engine_state.json에서 포지션 로드
        state_file = Path("data/quant/engine_state.json")
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                positions = data.get("positions", [])
                # 포지션 데이터 변환 (손익률 계산 추가)
                formatted_positions = []
                for pos in positions:
                    entry_price = pos.get("entry_price", 0)
                    current_price = pos.get("current_price", entry_price)
                    quantity = pos.get("quantity", 0)

                    pnl = (current_price - entry_price) * quantity
                    pnl_pct = ((current_price / entry_price) - 1) * 100 if entry_price > 0 else 0

                    formatted_positions.append({
                        "code": pos.get("code"),
                        "name": pos.get("name"),
                        "quantity": quantity,
                        "entry_price": entry_price,
                        "current_price": current_price,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "stop_loss": pos.get("stop_loss", 0),
                        "take_profit_1": pos.get("take_profit_1", 0)
                    })

                return {"success": True, "positions": formatted_positions}
            except Exception as e:
                logger.error(f"포지션 로드 실패: {e}")
                return {"success": False, "positions": [], "message": f"로드 오류: {e}"}

        return {"success": True, "positions": [], "message": "보유 포지션 없음"}

    def close_position(self, stock_code: str) -> Dict[str, Any]:
        """특정 포지션 청산"""
        if self.state == SystemState.EMERGENCY_STOP:
            return {"success": False, "message": "긴급 정지 상태입니다."}

        result = self._trigger_callback('close_position', stock_code)

        # 콜백 결과가 dict면 그대로 반환
        if isinstance(result, dict):
            return result

        if result:
            return {
                "success": True,
                "message": f"{stock_code} 청산 요청이 전송되었습니다.",
                "result": result
            }

        return {"success": False, "message": "청산 콜백이 등록되지 않았습니다. 데몬이 실행 중인지 확인하세요."}

    def close_all_positions(self) -> Dict[str, Any]:
        """전체 포지션 청산"""
        if self.state == SystemState.EMERGENCY_STOP:
            return {"success": False, "message": "긴급 정지 상태입니다."}

        result = self._trigger_callback('close_all_positions')

        # 콜백 결과가 dict면 그대로 반환
        if isinstance(result, dict):
            return result

        if result:
            return {
                "success": True,
                "message": "전체 청산 요청이 전송되었습니다.",
                "result": result
            }

        return {"success": False, "message": "청산 콜백이 등록되지 않았습니다. 데몬이 실행 중인지 확인하세요."}

    def get_logs(self, lines: int = 20) -> Dict[str, Any]:
        """최근 로그 조회"""
        log_dir = Path("logs")
        today = datetime.now().strftime("%Y%m%d")
        log_file = log_dir / f"daemon_{today}.log"

        if not log_file.exists():
            # 다른 로그 파일 찾기
            log_files = sorted(log_dir.glob("daemon_*.log"), reverse=True)
            if log_files:
                log_file = log_files[0]
            else:
                return {"success": False, "message": "로그 파일이 없습니다."}

        try:
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                recent_lines = all_lines[-lines:]

            return {
                "success": True,
                "file": log_file.name,
                "lines": [line.strip() for line in recent_lines]
            }
        except Exception as e:
            return {"success": False, "message": f"로그 읽기 오류: {e}"}


# 싱글톤 인스턴스 접근
def get_controller() -> SystemController:
    """시스템 컨트롤러 인스턴스 반환"""
    return SystemController()
