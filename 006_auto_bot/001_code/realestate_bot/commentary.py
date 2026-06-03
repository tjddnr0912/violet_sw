"""계산된 지표를 받아 AI 해석 시황을 생성 (실패 시 빈 문자열로 degrade)."""
import json
import logging

logger = logging.getLogger(__name__)

_FRAME = (
    "다음은 전국 주간 아파트 실거래 지표(코드가 계산한 확정 숫자)다. "
    "숫자를 재계산하지 말고, 서울·경기·6대 광역시를 고르게 다루는 3~5문단 시황을 "
    "한국어로 써라: ① 전국 거래량·온도 → ② 수도권(서울·경기) 흐름 → "
    "③ 지방 광역시 대비 → ④ 신고가/신저점·전세가율 신호. "
    "권역 간 온도차를 단정 대신 비교로 해석하고, 최근 월은 신고 지연으로 미확정임을 감안하라. "
    "한자 학술 용어 헤더(기승전결 등) 금지, 표/숫자 나열 금지, 해석 문장만.\n\n지표:\n"
)


def _ask_gemini(prompt: str) -> str:
    from shared.gemini_cli import call_gemini_with_fallback
    resp = call_gemini_with_fallback(prompt, use_grounding=False)
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("empty gemini response")
    return text


def make_commentary(indicators_summary: dict) -> str:
    prompt = _FRAME + json.dumps(indicators_summary, ensure_ascii=False, indent=2)
    try:
        return _ask_gemini(prompt)
    except Exception as e:  # noqa: BLE001
        logger.warning("commentary degraded (no AI): %s", e)
        return ""
