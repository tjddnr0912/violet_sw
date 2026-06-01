"""계산된 지표를 받아 AI 해석 시황을 생성 (실패 시 빈 문자열로 degrade)."""
import json
import logging

logger = logging.getLogger(__name__)

_FRAME = (
    "다음은 서울 아파트 주간 실거래 지표(코드가 계산한 확정 숫자)다. "
    "숫자를 재계산하지 말고, 아래 순서로 2~3문단의 시황만 한국어로 써라: "
    "① 거래량(활동·선행) → ② 중앙가 방향 → ③ 신고가/신저점 비중(모멘텀) → "
    "④ 세그먼트·구간 확산. 단정 대신 정합성으로 해석하고, 최근 월은 미확정임을 감안하라. "
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
