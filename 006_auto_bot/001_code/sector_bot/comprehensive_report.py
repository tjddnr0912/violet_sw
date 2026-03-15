"""
Comprehensive Investment Report Generator
------------------------------------------
11개 섹터 분석을 종합하여 마스터급 투자 평가 보고서 생성
Claude CLI (claude -p)를 사용하여 종합 분석 수행
"""

import glob
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

    def _build_comprehensive_prompt(
        self,
        sectors: Dict[int, str],
        missing: List[int],
        date: datetime,
    ) -> str:
        """종합 분석을 위한 Claude 프롬프트 구성"""

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
            missing_note = f"\n참고: 이번 주 다음 섹터는 분석 데이터가 없습니다: {', '.join(missing_names)}\n"

        prompt = f"""# Role

당신은 월스트리트 경력 30년 이상의 마스터급 경제분석 및 시장 예측 애널리스트입니다.
Goldman Sachs, Morgan Stanley, JP Morgan 등 최상위 투자은행에서 Chief Strategist로 근무하며,
2000년 닷컴 버블, 2008년 금융위기, 2020년 팬데믹, 2022년 금리 인상 사이클 등
수많은 경제 위기와 호황을 직접 경험하고 고객 자산을 성공적으로 방어한 베테랑입니다.
거시경제 흐름, 섹터별 상관관계, 자금 흐름의 변곡점을 꿰뚫어 보는 탁월한 안목을 보유하고 있으며,
개인 투자자와 기관 투자자 모두에게 실질적으로 활용 가능한 리서치 리포트를 작성하는 데 전문성을 갖고 있습니다.

# Context

- **보고서 기준일**: {date_str} ({week_number}주차)
- **데이터 소스**: 아래에 첨부된 11개 섹터별 주간 투자 분석 보고서
- **섹터 구성**: AI/양자컴퓨터, 금융, 조선/항공/우주, 에너지, 바이오, IT/Cloud/DC, 주식시장, 반도체, 자동차/배터리/로봇, 리츠(REITs), 필수 소비재
- **각 섹터 보고서 내용**: 지난 한 주간의 섹터별 주요 뉴스, 가격 변동, 기업 동향, 정책 변화 등을 Gemini AI가 웹 검색 기반으로 수집·분석한 자료
- **독자**: 한국의 개인 투자자 (미국·글로벌 시장에 투자하는 투자자 포함)
- **발행 채널**: 투자정보 블로그 (매주 일요일 저녁 발행)
{missing_note}
# Task

주어진 11개 섹터 분석 보고서를 종합적으로 취합하여, **지난 한 주간의 글로벌 시장 전체를 아우르는 평가**와 함께 **투자자가 다음 한 주를 어떻게 준비하고 대응해야 할지**에 대한 종합 투자 평가 보고서를 작성하세요.

단순히 각 섹터를 나열·요약하는 것이 아니라, 다음의 관점에서 분석해야 합니다:
1. **연결**: 섹터 간에 어떤 인과관계와 파급 효과가 존재하는가?
2. **판단**: 현재 시장의 국면(risk-on/risk-off, 순환/방어)은 무엇이며, 그 근거는?
3. **행동**: 투자자가 다음 주에 구체적으로 무엇을 해야 하는가? (매수/매도/관망/리밸런싱)

# Output Format

마크다운 형식으로, 아래 8개 섹션을 순서대로 작성하세요.

## 1. Executive Summary (핵심 요약)
- 이번 주 시장의 3~5가지 핵심 테이크어웨이 (한 줄씩 간결하게)
- 가장 주목해야 할 변화와 그것이 투자에 미치는 실질적 의미
- 현재 시장 국면 판단 (Bull/Bear/Neutral, Risk-On/Risk-Off)

## 2. 크로스 섹터 상관관계 분석
- 이번 주 확인된 섹터 간 실제 연관성과 파급 효과
  (예: 금리 변동 → 리츠/금융/에너지, AI 수요 → 반도체 → 에너지/DC)
- 자금 흐름의 방향: 어디서 빠져나와 어디로 들어가고 있는가?
- 강세/약세 섹터 분류와 그 배경

## 3. 최우선 투자 기회 (Top Picks)
- 매력도 순위별 투자 기회 5~7개 선정
- 각 기회별: 섹터, 종목/ETF, 투자 근거 (데이터 인용), 예상 수익/리스크 비율
- 단기(1~2주) vs 중기(1~3개월) 구분
- 진입 타이밍 제안

## 4. 리스크 요인 및 헤지 전략
- 현재 시장의 주요 리스크 요인 3~5개
- 각 리스크별: 발생 확률(높음/중간/낮음), 예상 영향도, 영향받는 섹터
- 구체적 헤지 수단 (인버스 ETF, 섹터 로테이션, 현금 비중 조절 등)

## 5. 거시경제 전망
- 금리 환경: 각국 중앙은행 스탠스와 다음 액션 예상
- 인플레이션/경기 방향성: 최신 지표 기반 판단
- 글로벌 유동성 흐름과 달러 강약
- 지정학적 이슈의 시장 영향도 평가

## 6. 포트폴리오 배분 추천
리스크 프로파일별 자산 배분 추천 (섹터별 비중 % 제시):
- **보수형**: 원금 보존 우선, 안정적 배당 수익 추구
- **중립형**: 성장과 안정의 균형
- **공격형**: 고수익 추구, 변동성 감내 가능
각 프로파일별 추천 근거와 지난 주 대비 변경 사항 명시

## 7. 주목 종목 워치리스트
- 구체적인 종목/ETF 6~10개
- 각 종목별: 현재 상황, 주목 이유, 기술적 관점 (지지/저항), 매수/관망 판단
- 보유 추천 기간 (단기/중기)

## 8. 다음 주 전망 및 대응 전략
- 다음 주 핵심 경제 이벤트 캘린더 (날짜별)
- 실적 발표 예정 주요 기업
- 시나리오별 대응: 상승 시 / 하락 시 / 횡보 시 각각 어떻게 할 것인가
- 주간 핵심 모니터링 지표 (체크해야 할 수치/이벤트)

# Blogger 스타일 가이드

이 보고서는 Google Blogger에 게시되므로 블로그 콘텐츠에 적합한 스타일로 작성해야 합니다:

1. **이모지 활용**: 섹션 제목과 핵심 포인트에 이모지를 적극 사용하여 시각적 가독성 확보
   (예: 📊 Executive Summary, 🔗 크로스 섹터, 🎯 Top Picks, ⚠️ 리스크, 🌍 거시경제, 💼 포트폴리오, 📋 워치리스트, 🔮 전망)
2. **짧은 문단**: 3~4문장 이내로 문단을 구성. 긴 문단은 읽기 힘듦
3. **스캔 가능한 레이아웃**: 핵심 내용은 **굵게(bold)** 강조, 목록과 글머리 기호 적극 활용
4. **첫 문단 Hook**: 글의 첫 150자 내에 이번 주 시장의 핵심 메시지를 담아 독자의 관심을 끌 것
5. **표(Table) 활용**: 종목 비교, 섹터별 비중, 리스크 평가 등은 표로 정리하여 한눈에 파악 가능하게
6. **결론에서 핵심 재강조**: 보고서 말미에 "이번 주 핵심 액션 3가지" 등으로 핵심을 다시 요약

# SEO 최적화 (Search Engine Optimization)

검색 엔진에서 이 보고서가 잘 노출되도록 다음 사항을 반드시 준수:

1. **키워드 전략**
   - "주간 투자 전망", "섹터 분석", "포트폴리오 전략", "{date.strftime('%Y년 %m월')} 투자" 등 핵심 키워드를 제목과 첫 문단에 자연스럽게 포함
   - 각 섹터명(AI, 반도체, 에너지, 바이오 등), 주요 종목명(NVIDIA, Tesla, 삼성전자 등), 경제 키워드(금리, 인플레이션, S&P 500 등)를 본문 전체에 자연스럽게 분산 배치
   - 키워드 과다 사용(stuffing) 금지 — 자연스러운 문맥 유지

2. **제목 구조 (Heading Hierarchy)**
   - h1은 보고서 전체 제목 1개만 (메인 제목)
   - h2로 8개 섹션 구분, h3으로 세부 항목 구성
   - 소제목에 검색 의도를 반영하는 키워드 포함 (예: "## 📊 2026년 3월 3주차 시장 핵심 요약" 식으로)

3. **첫 문단 최적화**
   - 첫 150자가 Google 검색 결과의 메타 설명(snippet)으로 활용됨
   - "이번 주 글로벌 시장은 ___하였으며, 투자자들은 ___에 주목해야 합니다" 형태로 핵심을 압축

4. **관련 키워드 자연 배치**
   - 동의어와 관련어 활용: "주식시장" ↔ "증시", "투자전략" ↔ "포트폴리오 전략", "금리인상" ↔ "긴축"
   - 시의성 있는 키워드: 해당 주의 주요 이벤트명, 실적 발표 기업명 등

# Constraints

1. **언어**: 한글로 작성. 종목명·지수명·전문용어는 영문 병기 가능
2. **분량**: 최소 5000자 이상, 충분히 상세하게. 블로그 수익을 위해 양질의 긴 콘텐츠 필요
3. **객관성**: 모든 판단과 추천에는 섹터 보고서의 구체적 데이터(수치, 날짜, 기업명)를 인용하여 근거를 제시할 것
4. **정직성**: 섹터 보고서에 없는 데이터를 임의로 생성하지 말 것. 불확실한 부분은 불확실하다고 명시할 것
5. **실용성**: 추상적 조언이 아닌, 투자자가 즉시 행동할 수 있는 구체적 액션 제시
6. **균형**: 낙관론과 비관론을 균형 있게 제시. 일방적 강세/약세 편향 금지
7. **구조**: 단순 섹터별 나열이 아닌, 섹터 간 연관성과 전체 시장 맥락 속에서 통합적으로 서술
8. **면책**: 보고서 말미에 "본 보고서는 정보 제공 목적이며, 투자 판단과 그에 따른 결과는 투자자 본인의 책임입니다"를 반드시 포함
9. **AI 언급 금지**: "AI가 작성", "자동 생성", "Gemini", "Claude" 등 AI 관련 문구를 보고서 본문에 절대 포함하지 말 것

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
                    ['claude', '-p', '-'],
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
