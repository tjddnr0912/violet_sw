"""
State Manager - 상태 저장/복구
-------------------------------
재시작 기능을 위한 진행 상태 관리
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from .config import SectorConfig, SECTORS

logger = logging.getLogger(__name__)


class StateManager:
    """섹터봇 진행 상태 관리"""

    def __init__(self, state_file: str = None):
        """
        Initialize state manager

        Args:
            state_file: 상태 파일 경로 (기본: SectorConfig.STATE_FILE)
        """
        self.state_file = state_file or SectorConfig.STATE_FILE

        # 절대 경로로 변환
        if not os.path.isabs(self.state_file):
            self.state_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                self.state_file
            )

        # 디렉토리 생성
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

        logger.info(f"StateManager initialized: {self.state_file}")

    def _get_week_key(self, date: datetime = None) -> str:
        """현재 주차 키 생성 (YYYY-WW 형식)"""
        if date is None:
            date = datetime.now()
        return date.strftime('%Y-%W')

    def load_state(self) -> Dict:
        """상태 파일 로드"""
        if not os.path.exists(self.state_file):
            return self._create_empty_state()

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                logger.info(f"Loaded state: week={state.get('week_key')}")
                return state
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return self._create_empty_state()

    def save_state(self, state: Dict) -> bool:
        """상태 파일 저장"""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved state: week={state.get('week_key')}")
            return True
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return False

    def _create_empty_state(self) -> Dict:
        """빈 상태 생성"""
        return {
            'week_key': self._get_week_key(),
            'start_time': datetime.now().isoformat(),
            'completed_sectors': [],
            'failed_sectors': [],
            'last_sector_id': 0,
            'blog_urls': {}
        }

    def is_same_week(self, state: Dict) -> bool:
        """현재 상태가 같은 주인지 확인"""
        current_week = self._get_week_key()
        state_week = state.get('week_key', '')
        return current_week == state_week

    def get_resume_sector_id(self) -> Optional[int]:
        """
        재개할 섹터 ID 반환

        Returns:
            재개할 섹터 ID (없으면 None)
        """
        state = self.load_state()

        # 같은 주가 아니면 처음부터
        if not self.is_same_week(state):
            logger.info("Different week, starting from sector 1")
            return None

        completed = set(state.get('completed_sectors', []))
        failed = set(state.get('failed_sectors', []))

        # 완료되지 않은 첫 번째 섹터 찾기
        for sector in SECTORS:
            if sector.id not in completed and sector.id not in failed:
                logger.info(f"Resume from sector {sector.id}: {sector.name}")
                return sector.id

        # 모두 완료/실패
        if len(completed) == len(SECTORS):
            logger.info("All sectors completed")
            return None

        # 실패한 섹터 재시도
        if failed:
            retry_id = min(failed)
            logger.info(f"Retrying failed sector {retry_id}")
            return retry_id

        return None

    def mark_sector_completed(
        self,
        sector_id: int,
        blog_url: str = None
    ) -> None:
        """섹터 완료 표시"""
        state = self.load_state()

        # 새 주라면 초기화
        if not self.is_same_week(state):
            state = self._create_empty_state()

        completed = set(state.get('completed_sectors', []))
        failed = set(state.get('failed_sectors', []))

        completed.add(sector_id)
        failed.discard(sector_id)  # 실패 목록에서 제거

        state['completed_sectors'] = sorted(list(completed))
        state['failed_sectors'] = sorted(list(failed))
        state['last_sector_id'] = sector_id
        state['last_update'] = datetime.now().isoformat()

        if blog_url:
            state['blog_urls'][str(sector_id)] = blog_url

        self.save_state(state)

    def mark_sector_failed(self, sector_id: int, error: str = None) -> None:
        """섹터 실패 표시"""
        state = self.load_state()

        if not self.is_same_week(state):
            state = self._create_empty_state()

        failed = set(state.get('failed_sectors', []))
        failed.add(sector_id)

        state['failed_sectors'] = sorted(list(failed))
        state['last_sector_id'] = sector_id
        state['last_update'] = datetime.now().isoformat()
        state['last_error'] = error

        self.save_state(state)

    def get_progress(self) -> Dict:
        """현재 진행 상황 반환"""
        state = self.load_state()

        if not self.is_same_week(state):
            return {
                'total': len(SECTORS),
                'completed': 0,
                'failed': 0,
                'remaining': len(SECTORS),
                'percent': 0
            }

        completed = len(state.get('completed_sectors', []))
        failed = len(state.get('failed_sectors', []))
        remaining = len(SECTORS) - completed - failed

        return {
            'total': len(SECTORS),
            'completed': completed,
            'failed': failed,
            'remaining': remaining,
            'percent': int(completed / len(SECTORS) * 100)
        }

    def reset_state(self) -> None:
        """상태 초기화"""
        state = self._create_empty_state()
        self.save_state(state)
        logger.info("State reset")

    def get_summary(self) -> str:
        """상태 요약 문자열 반환"""
        state = self.load_state()
        progress = self.get_progress()

        summary = f"""=== Sector Bot State ===
Week: {state.get('week_key', 'N/A')}
Progress: {progress['completed']}/{progress['total']} ({progress['percent']}%)
Completed: {state.get('completed_sectors', [])}
Failed: {state.get('failed_sectors', [])}
Last Update: {state.get('last_update', 'N/A')}
"""
        return summary


# CLI for testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    manager = StateManager()

    print(manager.get_summary())

    # 테스트
    print("\n=== Testing state management ===")

    # 섹터 1 완료
    manager.mark_sector_completed(1, "https://example.com/post1")
    print(f"After completing sector 1: {manager.get_progress()}")

    # 섹터 2 실패
    manager.mark_sector_failed(2, "Test error")
    print(f"After failing sector 2: {manager.get_progress()}")

    # 재개 포인트 확인
    resume_id = manager.get_resume_sector_id()
    print(f"Resume sector ID: {resume_id}")

    print("\n" + manager.get_summary())

    # 초기화
    # manager.reset_state()
    # print("\nAfter reset:")
    # print(manager.get_summary())
