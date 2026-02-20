"""
트래커 베이스 클래스

daily_tracker / monthly_tracker 공통 JSON 로드/세이브 패턴
"""

import json
import shutil
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class TrackerBase:
    """JSON 파일 기반 트래커 공통 기능"""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    def _load_json(self, filepath: Path, description: str):
        """
        JSON 파일 로드 (손상 시 백업 생성)

        Args:
            filepath: JSON 파일 경로
            description: 로그용 설명 (예: "일별 히스토리")

        Returns:
            dict or None (파일 없음/손상/오류 시)
        """
        if not filepath.exists():
            logger.info(f"{description} 파일 없음. 새로 시작합니다.")
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)

        except json.JSONDecodeError as e:
            backup_file = self.data_dir / f"{filepath.stem}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            shutil.copy2(filepath, backup_file)
            logger.error(f"{description} 파일 손상: {e}. 백업: {backup_file}")
            return None

        except Exception as e:
            logger.error(f"{description} 로드 실패: {e}", exc_info=True)
            return None

    def _save_json(self, filepath: Path, data: dict, description: str) -> bool:
        """
        JSON 파일 원자적 저장 (temp → rename)

        Args:
            filepath: JSON 파일 경로
            data: 저장할 데이터
            description: 로그용 설명

        Returns:
            True if successful
        """
        try:
            temp_file = filepath.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            temp_file.replace(filepath)
            return True

        except Exception as e:
            logger.error(f"{description} 저장 실패: {e}", exc_info=True)
            return False
