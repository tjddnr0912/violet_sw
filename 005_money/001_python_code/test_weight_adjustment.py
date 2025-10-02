#!/usr/bin/env python3
"""
가중치 조정 기능 테스트 스크립트
ConfigManager의 가중치 업데이트 기능을 테스트합니다.
"""

from config_manager import ConfigManager
import json

def test_weight_adjustment():
    """가중치 조정 기능 테스트"""
    print("="*60)
    print("가중치 조정 기능 테스트")
    print("="*60)

    # ConfigManager 초기화
    manager = ConfigManager()
    config = manager.get_config()

    # 1. 현재 가중치 확인
    print("\n[1] 현재 가중치 설정:")
    current_weights = config['strategy']['signal_weights']
    for key, value in current_weights.items():
        print(f"  {key:10s}: {value:.2f} ({value*100:.0f}%)")
    print(f"  합계: {sum(current_weights.values()):.2f}")

    # 2. 가중치 업데이트 테스트 (정상 케이스)
    print("\n[2] 가중치 업데이트 테스트 (정상):")
    new_weights = {
        'macd': 0.40,
        'ma': 0.30,
        'rsi': 0.15,
        'bb': 0.10,
        'volume': 0.05
    }
    print(f"  새로운 가중치: {new_weights}")
    success = manager.update_signal_weights(new_weights)
    print(f"  결과: {'✅ 성공' if success else '❌ 실패'}")

    # 3. 업데이트된 가중치 확인
    print("\n[3] 업데이트된 가중치 확인:")
    updated_config = manager.get_config()
    updated_weights = updated_config['strategy']['signal_weights']
    for key, value in updated_weights.items():
        print(f"  {key:10s}: {value:.2f} ({value*100:.0f}%)")
    print(f"  합계: {sum(updated_weights.values()):.2f}")

    # 4. 잘못된 가중치 테스트 (합계 != 1.0)
    print("\n[4] 잘못된 가중치 테스트 (합계 != 1.0):")
    invalid_weights = {
        'macd': 0.50,
        'ma': 0.30,
        'rsi': 0.20,
        'bb': 0.10,
        'volume': 0.10
    }
    print(f"  잘못된 가중치 (합계 {sum(invalid_weights.values()):.2f}): {invalid_weights}")
    success = manager.update_signal_weights(invalid_weights)
    print(f"  결과: {'✅ 성공' if success else '❌ 실패 (예상된 동작)'}")

    # 5. 가중치 정규화 테스트
    print("\n[5] 가중치 정규화 테스트:")
    print(f"  정규화 전: {invalid_weights}")
    print(f"  합계: {sum(invalid_weights.values()):.2f}")
    normalized = manager.normalize_weights(invalid_weights)
    print(f"  정규화 후: {normalized}")
    print(f"  합계: {sum(normalized.values()):.2f}")
    for key, value in normalized.items():
        print(f"    {key:10s}: {value:.3f} ({value*100:.1f}%)")

    # 6. 임계값 업데이트 테스트
    print("\n[6] 임계값 업데이트 테스트:")
    current_signal_threshold = config['strategy'].get('signal_threshold', 0.5)
    current_confidence_threshold = config['strategy'].get('confidence_threshold', 0.6)
    print(f"  현재 신호 임계값: {current_signal_threshold:.2f}")
    print(f"  현재 신뢰도 임계값: {current_confidence_threshold:.2f}")

    success = manager.update_thresholds(
        signal_threshold=0.3,
        confidence_threshold=0.7
    )
    print(f"  업데이트 결과: {'✅ 성공' if success else '❌ 실패'}")

    updated_config = manager.get_config()
    print(f"  새 신호 임계값: {updated_config['strategy']['signal_threshold']:.2f}")
    print(f"  새 신뢰도 임계값: {updated_config['strategy']['confidence_threshold']:.2f}")

    # 7. 범위 벗어난 임계값 테스트
    print("\n[7] 범위 벗어난 임계값 테스트:")
    success = manager.update_thresholds(signal_threshold=1.5)  # 범위: -1.0 ~ 1.0
    print(f"  신호 임계값 1.5 (범위 초과): {'✅ 성공' if success else '❌ 실패 (예상된 동작)'}")

    success = manager.update_thresholds(confidence_threshold=-0.1)  # 범위: 0.0 ~ 1.0
    print(f"  신뢰도 임계값 -0.1 (범위 미달): {'✅ 성공' if success else '❌ 실패 (예상된 동작)'}")

    # 8. 최종 설정 확인
    print("\n[8] 최종 설정 확인:")
    final_config = manager.get_config()
    print(f"  신호 가중치:")
    for key, value in final_config['strategy']['signal_weights'].items():
        print(f"    {key:10s}: {value:.3f}")
    print(f"  신호 임계값: {final_config['strategy']['signal_threshold']:.2f}")
    print(f"  신뢰도 임계값: {final_config['strategy']['confidence_threshold']:.2f}")

    print("\n" + "="*60)
    print("테스트 완료!")
    print("="*60)


if __name__ == "__main__":
    test_weight_adjustment()
