"""Item #34: factor_weights 정규화 후 합 = 1.0 검증"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.quant import CompositeScoreCalculator


def main():
    w = json.load(open("config/optimal_weights.json"))["factor_weights"]
    calc = CompositeScoreCalculator(
        value_weight=w["value_weight"],
        momentum_weight=w["momentum_weight"],
        quality_weight=w["quality_weight"],
        volume_weight=w["volume_weight"],
    )
    total = calc.value_weight + calc.momentum_weight + calc.quality_weight + calc.volume_weight
    assert abs(total - 1.0) < 0.01, f"정규화 후 합={total}"
    print(
        f"PASS: 정규화 V={calc.value_weight:.3f} M={calc.momentum_weight:.3f} "
        f"Q={calc.quality_weight:.3f} Vol={calc.volume_weight:.3f} 합={total:.3f}"
    )


if __name__ == "__main__":
    main()
