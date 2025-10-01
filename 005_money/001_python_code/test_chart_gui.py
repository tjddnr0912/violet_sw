#!/usr/bin/env python3
"""
차트 GUI 기능 테스트
"""

import tkinter as tk
import sys
import os

# 환경변수 설정 (테스트용)
os.environ['BITHUMB_CONNECT_KEY'] = os.getenv('BITHUMB_CONNECT_KEY', 'YOUR_CONNECT_KEY')
os.environ['BITHUMB_SECRET_KEY'] = os.getenv('BITHUMB_SECRET_KEY', 'YOUR_SECRET_KEY')

from gui_app import TradingBotGUI

def main():
    """GUI 테스트 실행"""
    print("=" * 80)
    print("차트 GUI 기능 테스트 시작")
    print("=" * 80)
    print()
    print("✅ 테스트 항목:")
    print("  1. GUI 초기화 및 모든 탭 표시")
    print("  2. 실시간 차트 탭 렌더링")
    print("  3. 캔들스틱 차트 그리기")
    print("  4. 기술적 지표 오버레이 (MA, RSI, 볼린저밴드)")
    print("  5. 매수/매도 시그널 배경색 표시")
    print("  6. 설정 변경 시 차트 자동 업데이트")
    print()
    print("📝 GUI 조작 방법:")
    print("  - '📊 실시간 차트' 탭을 클릭")
    print("  - 지표 체크박스를 클릭하여 표시 변경")
    print("  - '새로고침' 버튼으로 차트 갱신")
    print("  - '설정 적용' 버튼으로 코인/간격 변경")
    print()

    try:
        root = tk.Tk()
        app = TradingBotGUI(root)

        print("✅ GUI 초기화 성공!")
        print("💡 GUI 창에서 차트 탭을 확인하세요.")
        print()

        root.mainloop()

    except Exception as e:
        print(f"❌ GUI 실행 실패: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())