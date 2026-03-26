"""
Comprehensive Investment Report Generator
------------------------------------------
11개 섹터 분석을 종합하여 마스터급 투자 평가 보고서 생성
Claude CLI (claude -p)를 사용하여 종합 분석 수행
"""

import logging
import os
import subprocess
import tempfile
from datetime import datetime
from typing import Dict, List, Optional

from .config import SectorConfig, SECTORS, Sector
from .writer import SectorWriter

logger = logging.getLogger(__name__)

# Claude CLI 타임아웃 (15분)
CLAUDE_TIMEOUT = 900

# 최소 필요 섹터 수 (11개 중 최소 8개 이상 있어야 보고서 생성)
MIN_SECTORS_REQUIRED = 8


class ComprehensiveReportGenerator:
    """11개 섹터 종합 투자 평가 보고서 생성"""

    def __init__(self):
        self.writer = SectorWriter()

        # preflight: 스킬 파일 존재 여부 확인 (6시간 후 실패 방지)
        skill_path = os.path.expanduser("~/.claude/skills/sector-comprehensive/SKILL.md")
        if not os.path.exists(skill_path):
            logger.warning(f"Sector comprehensive skill file not found: {skill_path}")

        logger.info("ComprehensiveReportGenerator initialized")

    def collect_sector_files(self, date: datetime = None) -> Dict:
        """
        오늘 날짜의 섹터 분석 마크다운 파일 수집

        Returns:
            {'success': bool, 'sectors': {id: content}, 'missing': [ids], 'date_dir': str}
        """
        if date is None:
            date = datetime.now()

        date_dir = self.writer.get_date_dir(date)
        logger.info(f"Collecting sector files from: {date_dir}")

        sectors = {}
        missing = []

        for sector in SECTORS:
            filepath = self.writer.get_filepath(sector, date)
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                if content.strip():
                    sectors[sector.id] = content
                    logger.info(f"Loaded sector {sector.id}: {sector.name} ({len(content)} chars)")
                else:
                    missing.append(sector.id)
            else:
                missing.append(sector.id)

        total_chars = sum(len(c) for c in sectors.values())
        logger.info(f"Collected {len(sectors)}/{len(SECTORS)} sectors, total {total_chars} chars")

        if missing:
            missing_names = [SectorConfig.get_sector_by_id(sid).name for sid in missing]
            logger.warning(f"Missing sectors: {missing_names}")

        return {
            'success': len(sectors) >= MIN_SECTORS_REQUIRED,
            'sectors': sectors,
            'missing': missing,
            'date_dir': date_dir,
            'total_chars': total_chars,
            'error': f"Only {len(sectors)} sectors available (minimum {MIN_SECTORS_REQUIRED})" if len(sectors) < MIN_SECTORS_REQUIRED else None,
        }

    def generate_report(self, date: datetime = None) -> Dict:
        """
        종합 투자 평가 보고서 생성

        Returns:
            {'success': bool, 'content': str, 'filepath': str, 'error': str}
        """
        if date is None:
            date = datetime.now()

        # 1. 섹터 파일 수집
        collected = self.collect_sector_files(date)
        if not collected['success']:
            return {'success': False, 'error': collected['error']}

        # 2. Claude 프롬프트 구성
        prompt = self._build_comprehensive_prompt(collected['sectors'], collected['missing'], date)
        logger.info(f"Comprehensive prompt: {len(prompt)} chars")

        # 3. Claude CLI 호출
        try:
            analysis = self._call_claude(prompt)
        except Exception as e:
            return {'success': False, 'error': str(e)}

        # 4. 마크다운 보고서 저장
        report_content = self._build_report_markdown(analysis, date)
        filepath = os.path.join(collected['date_dir'], 'comprehensive_report.md')

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)

        logger.info(f"Comprehensive report saved: {filepath} ({len(report_content)} chars)")

        return {
            'success': True,
            'content': report_content,
            'filepath': filepath,
        }

    def generate_title(self, date: datetime = None) -> str:
        """보고서 제목 생성"""
        if date is None:
            date = datetime.now()

        week_number = (date.day - 1) // 7 + 1
        return f"{date.strftime('%Y-%m-%d')} {week_number}주차 종합 투자 평가 보고서"

    @staticmethod
    def _load_skill() -> str:
        """섹터 종합 스킬 파일 로드 (YAML frontmatter 제거)"""
        import re
        skill_path = os.path.expanduser("~/.claude/skills/sector-comprehensive/SKILL.md")

        if not os.path.exists(skill_path):
            raise FileNotFoundError(f"Sector comprehensive skill not found: {skill_path}")

        with open(skill_path, 'r', encoding='utf-8') as f:
            content = f.read()

        content = re.sub(r'^---\s*\n.*?\n---\s*\n?', '', content, count=1, flags=re.DOTALL)
        logger.info(f"Loaded sector-comprehensive skill: {len(content)} chars")
        return content.strip()

    def _build_comprehensive_prompt(
        self,
        sectors: Dict[int, str],
        missing: List[int],
        date: datetime,
    ) -> str:
        """종합 분석을 위한 Claude 프롬프트 구성 — SKILL.md 파일 참조"""

        week_number = (date.day - 1) // 7 + 1
        date_str = date.strftime('%Y년 %m월 %d일')

        # 섹터 데이터 결합
        sector_data = ""
        for sector_id in sorted(sectors.keys()):
            sector = SectorConfig.get_sector_by_id(sector_id)
            sector_data += f"\n{'='*60}\n"
            sector_data += f"=== SECTOR {sector_id}: {sector.name} ===\n"
            sector_data += f"{'='*60}\n\n"
            sector_data += sectors[sector_id]
            sector_data += "\n\n"

        missing_note = ""
        if missing:
            missing_names = [SectorConfig.get_sector_by_id(sid).name for sid in missing]
            missing_note = f"참고: 이번 주 다음 섹터는 분석 데이터가 없습니다: {', '.join(missing_names)}"

        skill_content = self._load_skill()

        prompt = f"""{skill_content}

# 보고서 기준 정보

- **보고서 기준일**: {date_str} ({week_number}주차)
{missing_note}

# 섹터 분석 데이터

{sector_data}
"""
        return prompt

    def _call_claude(self, prompt: str) -> str:
        """Claude CLI를 호출하여 종합 분석 생성"""
        logger.info(f"Calling Claude CLI for comprehensive analysis ({len(prompt)} chars)...")

        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False, encoding='utf-8'
            ) as f:
                f.write(prompt)
                temp_file = f.name

            with open(temp_file, 'r', encoding='utf-8') as f:
                result = subprocess.run(
                    ['claude', '-p', '--dangerously-skip-permissions', '-'],
                    stdin=f,
                    capture_output=True,
                    text=True,
                    timeout=CLAUDE_TIMEOUT,
                )

            os.unlink(temp_file)

        except subprocess.TimeoutExpired:
            if 'temp_file' in locals():
                os.unlink(temp_file)
            raise RuntimeError(f"Claude CLI timed out after {CLAUDE_TIMEOUT}s")
        except FileNotFoundError:
            if 'temp_file' in locals():
                os.unlink(temp_file)
            raise RuntimeError("Claude CLI not found. Is it installed and in PATH?")

        if result.returncode != 0:
            error_msg = result.stderr or "Unknown error"
            raise RuntimeError(f"Claude CLI failed (code {result.returncode}): {error_msg[:500]}")

        output = result.stdout.strip()
        if not output:
            raise RuntimeError("Claude CLI returned empty response")

        if len(output) < 3000:
            logger.warning(f"Claude response shorter than expected: {len(output)} chars")

        logger.info(f"Claude CLI analysis complete: {len(output)} chars")
        return output

    def _build_report_markdown(self, analysis: str, date: datetime) -> str:
        """종합 보고서 마크다운 구성"""
        week_number = (date.day - 1) // 7 + 1
        title = self.generate_title(date)

        return f"""# {title}

> 작성일: {date.strftime('%Y년 %m월 %d일')} ({week_number}주차)
> 유형: 11개 섹터 종합 투자 평가

---

{analysis}

---

*본 보고서는 정보 제공 목적이며, 투자 판단과 그에 따른 결과는 투자자 본인의 책임입니다.*
"""
