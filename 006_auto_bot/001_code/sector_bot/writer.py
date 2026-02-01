"""
Sector Writer - 마크다운 파일 I/O
----------------------------------
섹터 분석 결과를 마크다운 파일로 저장
"""

import os
import logging
from datetime import datetime
from typing import Dict, Optional, List

from .config import SectorConfig, Sector

logger = logging.getLogger(__name__)


class SectorWriter:
    """섹터 분석 결과 마크다운 파일 관리"""

    def __init__(self, output_dir: str = None):
        """
        Initialize writer

        Args:
            output_dir: 출력 디렉토리 (기본: SectorConfig.OUTPUT_DIR)
        """
        self.base_dir = output_dir or SectorConfig.OUTPUT_DIR

        # 절대 경로로 변환
        if not os.path.isabs(self.base_dir):
            self.base_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                self.base_dir
            )

        os.makedirs(self.base_dir, exist_ok=True)
        logger.info(f"SectorWriter initialized: {self.base_dir}")

    def get_date_dir(self, date: datetime = None) -> str:
        """날짜별 디렉토리 경로 반환"""
        if date is None:
            date = datetime.now()

        date_str = date.strftime('%Y%m%d')
        date_dir = os.path.join(self.base_dir, date_str)
        os.makedirs(date_dir, exist_ok=True)
        return date_dir

    def get_filename(self, sector: Sector, date: datetime = None) -> str:
        """섹터별 파일명 생성"""
        return f"sector_{sector.id:02d}_{sector.name_en}.md"

    def get_filepath(self, sector: Sector, date: datetime = None) -> str:
        """섹터별 전체 파일 경로 반환"""
        date_dir = self.get_date_dir(date)
        filename = self.get_filename(sector, date)
        return os.path.join(date_dir, filename)

    def save_analysis(
        self,
        sector: Sector,
        analysis_result: Dict,
        title: str,
        date: datetime = None
    ) -> Dict:
        """
        분석 결과를 마크다운 파일로 저장

        Args:
            sector: 섹터 정보
            analysis_result: 분석 결과 딕셔너리
            title: 포스트 제목
            date: 날짜

        Returns:
            저장 결과 딕셔너리
        """
        try:
            if date is None:
                date = datetime.now()

            filepath = self.get_filepath(sector, date)

            # 마크다운 콘텐츠 구성
            content = self._build_markdown(
                sector=sector,
                analysis=analysis_result.get('analysis', ''),
                sources=analysis_result.get('sources', []),
                title=title,
                date=date
            )

            # 파일 저장
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"Saved: {filepath} ({len(content)} chars)")

            return {
                'success': True,
                'filepath': filepath,
                'content': content
            }

        except Exception as e:
            logger.error(f"Save error for {sector.name}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _build_markdown(
        self,
        sector: Sector,
        analysis: str,
        sources: List[str],
        title: str,
        date: datetime
    ) -> str:
        """마크다운 콘텐츠 구성"""

        # 주차 계산
        week_number = (date.day - 1) // 7 + 1

        md = f"""# {title}

> 작성일: {date.strftime('%Y년 %m월 %d일')} ({week_number}주차)
> 섹터: {sector.name}

---

{analysis}

---

## 출처

"""
        # 출처 추가
        if sources:
            for i, url in enumerate(sources[:15], 1):
                md += f"{i}. {url}\n"
        else:
            md += "- 출처 정보 없음\n"

        md += f"""
---

*이 보고서는 Gemini AI를 통해 자동 생성되었습니다.*
*투자 결정 시 추가적인 검증이 필요합니다.*
"""

        return md

    def read_analysis(self, sector: Sector, date: datetime = None) -> Optional[str]:
        """저장된 분석 파일 읽기"""
        filepath = self.get_filepath(sector, date)

        if not os.path.exists(filepath):
            return None

        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()

    def exists(self, sector: Sector, date: datetime = None) -> bool:
        """분석 파일 존재 여부 확인"""
        filepath = self.get_filepath(sector, date)
        return os.path.exists(filepath)

    def list_date_dirs(self) -> List[str]:
        """저장된 날짜 디렉토리 목록 반환"""
        if not os.path.exists(self.base_dir):
            return []

        dirs = []
        for name in os.listdir(self.base_dir):
            path = os.path.join(self.base_dir, name)
            if os.path.isdir(path) and name.isdigit() and len(name) == 8:
                dirs.append(name)

        return sorted(dirs, reverse=True)  # 최신 날짜 순

    def cleanup_old_data(self, keep_weeks: int = 8) -> int:
        """
        오래된 데이터 정리

        Args:
            keep_weeks: 유지할 주 수 (기본: 8주)

        Returns:
            삭제된 디렉토리 수
        """
        import shutil
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(weeks=keep_weeks)
        cutoff_str = cutoff_date.strftime('%Y%m%d')

        deleted_count = 0
        for date_str in self.list_date_dirs():
            if date_str < cutoff_str:
                dir_path = os.path.join(self.base_dir, date_str)
                try:
                    shutil.rmtree(dir_path)
                    logger.info(f"Deleted old data: {dir_path}")
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete {dir_path}: {e}")

        return deleted_count


# CLI for testing
if __name__ == "__main__":
    from dotenv import load_dotenv
    from .config import SECTORS

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    writer = SectorWriter()

    # 테스트 데이터 저장
    sector = SECTORS[0]
    test_result = {
        'analysis': '# 테스트 분석\n\n이것은 테스트 분석 내용입니다.',
        'sources': ['https://example.com/1', 'https://example.com/2']
    }

    result = writer.save_analysis(
        sector=sector,
        analysis_result=test_result,
        title=f"테스트 {sector.name} 투자정보"
    )

    if result['success']:
        print(f"Saved to: {result['filepath']}")
        print(f"Content:\n{result['content'][:500]}")
    else:
        print(f"Failed: {result.get('error')}")
