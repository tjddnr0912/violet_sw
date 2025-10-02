#!/usr/bin/env python3
"""
동적 설정 관리자
명령행 인수, 대화형 메뉴, 런타임 설정 변경 지원
"""

import argparse
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime
import config

class ConfigManager:
    def __init__(self):
        self.config = config.get_config()
        self.original_config = config.get_config().copy()

    def parse_arguments(self) -> argparse.Namespace:
        """명령행 인수 파싱"""
        parser = argparse.ArgumentParser(
            description="빗썸 자동매매 봇",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
사용 예시:
  python main.py --interval 30s              # 30초마다 체크
  python main.py --interval 5m               # 5분마다 체크
  python main.py --amount 50000              # 거래금액 5만원
  python main.py --coin ETH --dry-run        # 이더리움 모의거래
  python main.py --interactive               # 대화형 설정
  python main.py --config custom_config.json # 커스텀 설정 파일
            """
        )

        # 거래 설정
        trading_group = parser.add_argument_group('거래 설정')
        trading_group.add_argument('--coin', '--ticker',
                                 default=self.config['trading']['target_ticker'],
                                 help='거래할 코인 (기본값: BTC)')
        trading_group.add_argument('--amount', type=int,
                                 default=self.config['trading']['trade_amount_krw'],
                                 help='거래 금액 (원, 기본값: 10000)')
        trading_group.add_argument('--max-trades', type=int,
                                 default=self.config['safety']['max_daily_trades'],
                                 help='일일 최대 거래 횟수 (기본값: 10)')

        # 시간 설정
        time_group = parser.add_argument_group('시간 설정')
        time_group.add_argument('--interval',
                              default=f"{self.config['schedule']['check_interval_minutes']}m",
                              help='체크 간격 (예: 30s, 5m, 1h, 기본값: 30m)')
        time_group.add_argument('--daily-time',
                              default=self.config['schedule']['daily_check_time'],
                              help='일일 체크 시간 (HH:MM 형식, 기본값: 09:05)')

        # 전략 설정
        strategy_group = parser.add_argument_group('전략 설정')
        strategy_group.add_argument('--candle-interval',
                                  default=self.config['strategy'].get('candlestick_interval', '24h'),
                                  choices=['1h', '6h', '12h', '24h'],
                                  help='캔들스틱 간격 (기본값: 24h)')
        strategy_group.add_argument('--short-ma', type=int,
                                  default=self.config['strategy']['short_ma_window'],
                                  help='단기 이동평균 기간 (기본값: 5)')
        strategy_group.add_argument('--long-ma', type=int,
                                  default=self.config['strategy']['long_ma_window'],
                                  help='장기 이동평균 기간 (기본값: 20)')
        strategy_group.add_argument('--rsi-period', type=int,
                                  default=self.config['strategy']['rsi_period'],
                                  help='RSI 기간 (기본값: 14)')

        # 모드 설정
        mode_group = parser.add_argument_group('실행 모드')
        mode_group.add_argument('--dry-run', action='store_true',
                              default=self.config['safety']['dry_run'],
                              help='모의 거래 모드')
        mode_group.add_argument('--live', action='store_true',
                              help='실제 거래 모드 (주의!)')
        mode_group.add_argument('--test-mode', action='store_true',
                              default=self.config['safety']['test_mode'],
                              help='테스트 모드 (거래 내역 기록 안함)')
        mode_group.add_argument('--emergency-stop', action='store_true',
                              help='긴급 정지 모드')

        # 기타
        other_group = parser.add_argument_group('기타')
        other_group.add_argument('--interactive', '-i', action='store_true',
                               help='대화형 설정 모드')
        other_group.add_argument('--config-file',
                               help='커스텀 설정 파일 경로')
        other_group.add_argument('--save-config',
                               help='현재 설정을 파일로 저장')
        other_group.add_argument('--show-config', action='store_true',
                               help='현재 설정 표시')
        other_group.add_argument('--reset-config', action='store_true',
                               help='설정을 기본값으로 리셋')
        other_group.add_argument('--show-portfolio', action='store_true',
                               help='포트폴리오 현황 표시')
        other_group.add_argument('--show-account', action='store_true',
                               help='계정 정보 상세 표시')
        other_group.add_argument('--export-portfolio',
                               help='포트폴리오 데이터를 JSON 파일로 내보내기')

        return parser.parse_args()

    def parse_interval(self, interval_str: str) -> Dict[str, Any]:
        """간격 문자열 파싱 (예: 30s, 5m, 1h)"""
        interval_str = interval_str.lower().strip()

        if interval_str.endswith('s'):
            seconds = int(interval_str[:-1])
            return {'type': 'seconds', 'value': seconds}
        elif interval_str.endswith('m'):
            minutes = int(interval_str[:-1])
            return {'type': 'minutes', 'value': minutes}
        elif interval_str.endswith('h'):
            hours = int(interval_str[:-1])
            return {'type': 'hours', 'value': hours}
        else:
            # 숫자만 있는 경우 분으로 간주
            minutes = int(interval_str)
            return {'type': 'minutes', 'value': minutes}

    def apply_arguments(self, args: argparse.Namespace) -> None:
        """명령행 인수를 설정에 적용"""
        # 거래 설정
        self.config['trading']['target_ticker'] = args.coin.upper()
        self.config['trading']['trade_amount_krw'] = args.amount
        self.config['safety']['max_daily_trades'] = args.max_trades

        # 시간 설정
        interval_info = self.parse_interval(args.interval)
        if interval_info['type'] == 'seconds':
            # 초 단위는 분으로 변환 (최소 1분)
            self.config['schedule']['check_interval_minutes'] = max(1, interval_info['value'] // 60)
            self.config['schedule']['check_interval_seconds'] = interval_info['value']
        elif interval_info['type'] == 'minutes':
            self.config['schedule']['check_interval_minutes'] = interval_info['value']
            self.config['schedule']['check_interval_seconds'] = interval_info['value'] * 60
        elif interval_info['type'] == 'hours':
            self.config['schedule']['check_interval_minutes'] = interval_info['value'] * 60
            self.config['schedule']['check_interval_seconds'] = interval_info['value'] * 3600

        self.config['schedule']['daily_check_time'] = args.daily_time

        # 전략 설정
        self.config['strategy']['candlestick_interval'] = args.candle_interval

        # 캔들 간격에 따라 권장 지표 설정 자동 적용
        if args.candle_interval in self.config['strategy'].get('interval_presets', {}):
            preset = self.config['strategy']['interval_presets'][args.candle_interval]
            # 명령줄에서 명시적으로 지정하지 않은 경우에만 프리셋 적용
            if args.short_ma == self.original_config['strategy']['short_ma_window']:
                self.config['strategy']['short_ma_window'] = preset['short_ma_window']
            else:
                self.config['strategy']['short_ma_window'] = args.short_ma

            if args.long_ma == self.original_config['strategy']['long_ma_window']:
                self.config['strategy']['long_ma_window'] = preset['long_ma_window']
            else:
                self.config['strategy']['long_ma_window'] = args.long_ma

            if args.rsi_period == self.original_config['strategy']['rsi_period']:
                self.config['strategy']['rsi_period'] = preset['rsi_period']
            else:
                self.config['strategy']['rsi_period'] = args.rsi_period
        else:
            # 프리셋이 없으면 명령줄 값 사용
            self.config['strategy']['short_ma_window'] = args.short_ma
            self.config['strategy']['long_ma_window'] = args.long_ma
            self.config['strategy']['rsi_period'] = args.rsi_period

        # 모드 설정
        if args.live:
            self.config['safety']['dry_run'] = False
        elif args.dry_run:
            self.config['safety']['dry_run'] = True

        if args.test_mode:
            self.config['safety']['test_mode'] = True

        if args.emergency_stop:
            self.config['safety']['emergency_stop'] = True

    def interactive_config(self) -> None:
        """대화형 설정 메뉴"""
        print("\n" + "="*50)
        print("🔧 대화형 설정 메뉴")
        print("="*50)

        while True:
            print("\n📋 현재 설정:")
            self.show_current_config()

            print("\n🛠️ 변경할 항목을 선택하세요:")
            print("1. 거래 코인")
            print("2. 거래 금액")
            print("3. 체크 간격")
            print("4. 거래 모드 (모의/실제)")
            print("5. 전략 설정")
            print("6. 설정 저장")
            print("7. 설정 완료")
            print("0. 취소")

            choice = input("\n선택 (0-7): ").strip()

            if choice == '1':
                self._configure_coin()
            elif choice == '2':
                self._configure_amount()
            elif choice == '3':
                self._configure_interval()
            elif choice == '4':
                self._configure_mode()
            elif choice == '5':
                self._configure_strategy()
            elif choice == '6':
                self._save_config_interactive()
            elif choice == '7':
                print("✅ 설정이 완료되었습니다.")
                break
            elif choice == '0':
                print("❌ 설정을 취소합니다.")
                self.config = self.original_config.copy()
                break
            else:
                print("❌ 잘못된 선택입니다.")

    def _configure_coin(self):
        """코인 설정"""
        current = self.config['trading']['target_ticker']
        print(f"\n현재 코인: {current}")
        print("사용 가능한 코인: BTC, ETH, XRP, ADA, DOT, LINK, ...")

        new_coin = input("새 코인 (Enter=유지): ").strip().upper()
        if new_coin:
            self.config['trading']['target_ticker'] = new_coin
            print(f"✅ 코인이 {new_coin}로 변경되었습니다.")

    def _configure_amount(self):
        """거래 금액 설정"""
        current = self.config['trading']['trade_amount_krw']
        print(f"\n현재 거래 금액: {current:,}원")

        try:
            new_amount = input("새 거래 금액 (원, Enter=유지): ").strip()
            if new_amount:
                amount = int(new_amount)
                if amount >= 5000:
                    self.config['trading']['trade_amount_krw'] = amount
                    print(f"✅ 거래 금액이 {amount:,}원으로 변경되었습니다.")
                else:
                    print("❌ 최소 거래 금액은 5,000원입니다.")
        except ValueError:
            print("❌ 숫자를 입력해주세요.")

    def _configure_interval(self):
        """체크 간격 설정"""
        current = self.config['schedule']['check_interval_minutes']
        print(f"\n현재 체크 간격: {current}분")
        print("형식: 30s (30초), 5m (5분), 1h (1시간)")

        new_interval = input("새 체크 간격 (Enter=유지): ").strip()
        if new_interval:
            try:
                interval_info = self.parse_interval(new_interval)
                if interval_info['type'] == 'seconds' and interval_info['value'] < 10:
                    print("❌ 최소 간격은 10초입니다.")
                    return

                # 설정 적용
                if interval_info['type'] == 'seconds':
                    self.config['schedule']['check_interval_seconds'] = interval_info['value']
                    self.config['schedule']['check_interval_minutes'] = max(1, interval_info['value'] // 60)
                elif interval_info['type'] == 'minutes':
                    self.config['schedule']['check_interval_minutes'] = interval_info['value']
                    self.config['schedule']['check_interval_seconds'] = interval_info['value'] * 60
                elif interval_info['type'] == 'hours':
                    self.config['schedule']['check_interval_minutes'] = interval_info['value'] * 60
                    self.config['schedule']['check_interval_seconds'] = interval_info['value'] * 3600

                print(f"✅ 체크 간격이 {new_interval}로 변경되었습니다.")
            except:
                print("❌ 잘못된 형식입니다. (예: 30s, 5m, 1h)")

    def _configure_mode(self):
        """거래 모드 설정"""
        current = "모의 거래" if self.config['safety']['dry_run'] else "실제 거래"
        print(f"\n현재 모드: {current}")
        print("1. 모의 거래 (안전)")
        print("2. 실제 거래 (주의!)")

        choice = input("선택 (1-2, Enter=유지): ").strip()
        if choice == '1':
            self.config['safety']['dry_run'] = True
            print("✅ 모의 거래 모드로 설정되었습니다.")
        elif choice == '2':
            confirm = input("⚠️ 실제 거래 모드는 자금 손실 위험이 있습니다. 계속하시겠습니까? (y/N): ")
            if confirm.lower() in ['y', 'yes']:
                self.config['safety']['dry_run'] = False
                print("✅ 실제 거래 모드로 설정되었습니다.")

    def _configure_strategy(self):
        """전략 설정"""
        print("\n📊 전략 설정")
        print(f"현재 단기 MA: {self.config['strategy']['short_ma_window']}")
        print(f"현재 장기 MA: {self.config['strategy']['long_ma_window']}")
        print(f"현재 RSI 기간: {self.config['strategy']['rsi_period']}")

        try:
            short_ma = input("단기 MA (Enter=유지): ").strip()
            if short_ma:
                self.config['strategy']['short_ma_window'] = int(short_ma)

            long_ma = input("장기 MA (Enter=유지): ").strip()
            if long_ma:
                self.config['strategy']['long_ma_window'] = int(long_ma)

            rsi_period = input("RSI 기간 (Enter=유지): ").strip()
            if rsi_period:
                self.config['strategy']['rsi_period'] = int(rsi_period)

            print("✅ 전략 설정이 변경되었습니다.")
        except ValueError:
            print("❌ 숫자를 입력해주세요.")

    def _save_config_interactive(self):
        """대화형 설정 저장"""
        filename = input("저장할 파일명 (Enter=기본값): ").strip()
        if not filename:
            filename = f"config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        self.save_config_to_file(filename)

    def show_current_config(self) -> None:
        """현재 설정 표시"""
        print(f"💰 거래 코인: {self.config['trading']['target_ticker']}")
        print(f"💵 거래 금액: {self.config['trading']['trade_amount_krw']:,}원")

        if 'check_interval_seconds' in self.config['schedule']:
            seconds = self.config['schedule']['check_interval_seconds']
            if seconds < 60:
                print(f"⏰ 체크 간격: {seconds}초")
            elif seconds < 3600:
                print(f"⏰ 체크 간격: {seconds//60}분")
            else:
                print(f"⏰ 체크 간격: {seconds//3600}시간")
        else:
            print(f"⏰ 체크 간격: {self.config['schedule']['check_interval_minutes']}분")

        print(f"🤖 거래 모드: {'모의 거래' if self.config['safety']['dry_run'] else '실제 거래'}")
        print(f"📊 MA 설정: 단기 {self.config['strategy']['short_ma_window']}, 장기 {self.config['strategy']['long_ma_window']}")

    def load_config_from_file(self, filepath: str) -> bool:
        """파일에서 설정 로드"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                file_config = json.load(f)

            # 기존 설정과 병합
            self._merge_config(self.config, file_config)
            print(f"✅ {filepath}에서 설정을 로드했습니다.")
            return True
        except Exception as e:
            print(f"❌ 설정 파일 로드 실패: {e}")
            return False

    def save_config_to_file(self, filepath: str) -> bool:
        """현재 설정을 파일로 저장"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            print(f"✅ 설정이 {filepath}에 저장되었습니다.")
            return True
        except Exception as e:
            print(f"❌ 설정 저장 실패: {e}")
            return False

    def _merge_config(self, base_config: Dict, new_config: Dict) -> None:
        """설정 병합"""
        for key, value in new_config.items():
            if key in base_config and isinstance(base_config[key], dict) and isinstance(value, dict):
                self._merge_config(base_config[key], value)
            else:
                base_config[key] = value

    def get_config(self) -> Dict[str, Any]:
        """현재 설정 반환"""
        return self.config

    def reset_config(self) -> None:
        """설정을 기본값으로 리셋"""
        self.config = self.original_config.copy()
        print("✅ 설정이 기본값으로 리셋되었습니다.")

    def update_signal_weights(self, weights: Dict[str, float]) -> bool:
        """신호 가중치 업데이트

        Args:
            weights: 지표별 가중치 딕셔너리 {'macd': 0.35, 'ma': 0.25, ...}

        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            # 가중치 합이 1.0인지 검증
            total_weight = sum(weights.values())
            if not (0.99 <= total_weight <= 1.01):  # 부동소수점 오차 허용
                print(f"⚠️ 경고: 가중치 합이 1.0이 아닙니다 (현재: {total_weight:.3f})")
                return False

            # 각 가중치가 0~1 범위인지 검증
            for key, value in weights.items():
                if not (0.0 <= value <= 1.0):
                    print(f"❌ 오류: '{key}' 가중치가 범위를 벗어났습니다 ({value:.3f})")
                    return False

            # 설정 업데이트
            self.config['strategy']['signal_weights'] = weights.copy()
            print(f"✅ 신호 가중치가 업데이트되었습니다: {weights}")
            return True

        except Exception as e:
            print(f"❌ 가중치 업데이트 실패: {e}")
            return False

    def update_thresholds(self, signal_threshold: float = None,
                         confidence_threshold: float = None) -> bool:
        """거래 임계값 업데이트

        Args:
            signal_threshold: 신호 임계값 (-1.0 ~ 1.0)
            confidence_threshold: 신뢰도 임계값 (0.0 ~ 1.0)

        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            updated = []

            if signal_threshold is not None:
                # 신호 임계값 검증
                if not (-1.0 <= signal_threshold <= 1.0):
                    print(f"❌ 오류: 신호 임계값이 범위를 벗어났습니다 ({signal_threshold:.3f})")
                    return False

                self.config['strategy']['signal_threshold'] = signal_threshold
                updated.append(f"신호 임계값: {signal_threshold:.2f}")

            if confidence_threshold is not None:
                # 신뢰도 임계값 검증
                if not (0.0 <= confidence_threshold <= 1.0):
                    print(f"❌ 오류: 신뢰도 임계값이 범위를 벗어났습니다 ({confidence_threshold:.3f})")
                    return False

                self.config['strategy']['confidence_threshold'] = confidence_threshold
                updated.append(f"신뢰도 임계값: {confidence_threshold:.2f}")

            if updated:
                print(f"✅ 임계값이 업데이트되었습니다: {', '.join(updated)}")
                return True
            else:
                print("⚠️ 경고: 업데이트할 임계값이 없습니다")
                return False

        except Exception as e:
            print(f"❌ 임계값 업데이트 실패: {e}")
            return False

    def normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """가중치 정규화 (합이 1.0이 되도록 조정)

        Args:
            weights: 정규화할 가중치 딕셔너리

        Returns:
            정규화된 가중치 딕셔너리
        """
        try:
            total = sum(weights.values())
            if total == 0:
                # 모든 가중치가 0인 경우 균등 분배
                num_weights = len(weights)
                return {key: 1.0 / num_weights for key in weights.keys()}

            # 비율 유지하면서 합이 1.0이 되도록 조정
            normalized = {key: value / total for key, value in weights.items()}
            return normalized

        except Exception as e:
            print(f"❌ 가중치 정규화 실패: {e}")
            return weights