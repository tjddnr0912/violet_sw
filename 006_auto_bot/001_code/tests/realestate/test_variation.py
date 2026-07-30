"""헤더·섹션 순서 변주 — 결정성(재실행 동일) + 실제 변주(주마다 다름) 동시 검증."""
import re

from realestate_bot import digest, variation
from tests.realestate.test_digest import _input


def _weeks(n=12):
    return [f"2026-{(i // 4) + 1:02d}-{(i % 4) * 7 + 6:02d} 기준 주간" for i in range(n)]


def test_seed_and_pick_are_deterministic():
    a = variation.headers("2026-06-06 기준 주간")
    b = variation.headers("2026-06-06 기준 주간")
    assert a == b                                     # 같은 주 재실행 → 동일
    assert a != variation.headers("2026-06-13 기준 주간")


def test_rotate_preserves_items():
    items = ["a", "b", "c", "d"]
    out = variation.rotate(variation.seed("w1"), "slot", items)
    assert sorted(out) == sorted(items) and len(out) == len(items)
    assert items == ["a", "b", "c", "d"]              # 원본 불변


def test_rotate_degrades_on_short_lists():
    sd = variation.seed("w1")
    assert variation.rotate(sd, "s", []) == []
    assert variation.rotate(sd, "s", ["only"]) == ["only"]


def test_headers_actually_vary_across_weeks():
    """12주치 헤더가 한 값에 고정되지 않는다 (템플릿 신호 완화의 핵심)."""
    for slot in ("national", "seoul", "seoul_table", "seoul_jeonse", "metro"):
        seen = {variation.headers(w)[slot] for w in _weeks()}
        assert len(seen) >= 2, f"{slot} 헤더가 변주되지 않음: {seen}"


def test_section_order_varies_across_weeks():
    """서울 하위 블록·권역 블록의 등장 순서가 주마다 달라진다."""
    orders = set()
    for w in _weeks():
        d = _input()
        d["week_label"] = w
        md = digest.build_digest(d)
        # h2/h3 중 지표 키워드만 추출해 순서 시그니처 생성
        seq = []
        for line in md.splitlines():
            if not line.startswith("#"):
                continue
            for key in ("전세가율", "오피스텔", "경기", "광역시", "세종"):
                if key in line:
                    seq.append(key)
                    break
        orders.add(tuple(seq))
    assert len(orders) >= 3, f"순서 변주 부족: {orders}"


def test_all_blocks_survive_every_week():
    """순서가 어떻게 섞이든 블록 누락은 없어야 한다."""
    for w in _weeks():
        d = _input()
        d["week_label"] = w
        md = digest.build_digest(d)
        assert "| 구 | 신규 | 신고가 비중 | 중앙가 변화(믹스보정) | 비고 |" in md
        assert "전세가율" in md and "오피스텔" in md
        assert "은마" in md                            # 서울 하이라이트
        assert re.search(r"^## 경기", md, re.M)
        assert "광역시" in md and "부산" in md
        assert re.search(r"^## 세종", md, re.M)
        assert md.rstrip().endswith("믹스보정) 기준.")   # 데이터 출처 각주는 항상 끝
