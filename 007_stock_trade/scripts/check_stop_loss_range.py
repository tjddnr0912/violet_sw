"""Item #16: StopLossManager 변동성 기반 손절 3~15% 범위 검증"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.quant import StopLossManager as S


def main():
    entry = 50000

    # 변동성 0 → fallback (7%)
    stop = S.calculate_dynamic_stop(entry, 0.0)
    assert abs(stop - 46500) < 1, f"fallback 7% 실패: {stop}"

    # 매우 낮은 변동성 → MIN 3% (= 48500)
    stop = S.calculate_dynamic_stop(entry, 1.0)
    pct = (entry - stop) / entry
    assert pct >= S.MIN_STOP_PCT - 1e-6, f"MIN 미준수 pct={pct:.4f}"

    # 매우 높은 변동성 → MAX 15% (= 42500)
    stop = S.calculate_dynamic_stop(entry, 200.0)
    pct = (entry - stop) / entry
    assert pct <= S.MAX_STOP_PCT + 1e-6, f"MAX 초과 pct={pct:.4f}"

    # 정상 범위: 25% 변동성
    stop = S.calculate_dynamic_stop(entry, 25.0)
    pct = (entry - stop) / entry
    assert S.MIN_STOP_PCT <= pct <= S.MAX_STOP_PCT, f"범위 이탈 pct={pct:.4f}"

    print(f"PASS: 변동성 기반 손절 3~15% 범위 검증 (vol=25 → {pct*100:.2f}%)")


if __name__ == "__main__":
    main()
