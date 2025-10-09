#!/usr/bin/env python3
"""
빗썸 자동매매 봇 GUI 실행기
"""

import sys
import os
import subprocess
import time
import tkinter as tk
from tkinter import messagebox

def check_dependencies(version="ver1"):
    """필요한 패키지 확인

    Args:
        version: 실행할 버전 (ver1, ver2 등)
    """
    missing_packages = []

    try:
        import pandas
        print("✅ pandas 패키지 확인됨")
    except ImportError:
        missing_packages.append("pandas")

    try:
        import requests
        print("✅ requests 패키지 확인됨")
    except ImportError:
        missing_packages.append("requests")

    try:
        import schedule
        print("✅ schedule 패키지 확인됨")
    except ImportError:
        missing_packages.append("schedule")

    try:
        import numpy
        print("✅ numpy 패키지 확인됨")
    except ImportError:
        missing_packages.append("numpy")

    # v2 and v3에서는 backtrader가 필수
    if version in ["ver2", "ver3"]:
        try:
            import backtrader
            print(f"✅ backtrader 패키지 확인됨 ({version} 필수)")
        except ImportError:
            missing_packages.append(f"backtrader ({version} 전용)")

    if missing_packages:
        error_msg = f"다음 패키지들이 설치되지 않았습니다:\n" + "\n".join(f"• {pkg}" for pkg in missing_packages)
        error_msg += "\n\n해결 방법:\n"
        error_msg += "1. 터미널에서 다음 명령 실행:\n"
        error_msg += "   cd /Users/seongwookjang/project/git/violet_sw/005_money\n"
        error_msg += "   source .venv/bin/activate  # if using venv\n"
        error_msg += "   pip install -r requirements.txt\n\n"
        error_msg += "2. 또는 ./gui 스크립트 사용 (자동 설치):\n"
        error_msg += "   ./gui\n\n"
        error_msg += "3. 또는 전체 설정 실행:\n"
        error_msg += "   python run.py --setup-only"

        messagebox.showerror("패키지 누락", error_msg)
        return False

    return True

def check_files():
    """필요한 파일 확인 (NEW structure)"""
    required_files = [
        # Core GUI files
        '001_python_code/gui_app.py',
        '001_python_code/config.py',  # Compatibility layer

        # Version 1 files
        '001_python_code/ver1/gui_trading_bot_v1.py',
        '001_python_code/ver1/trading_bot_v1.py',
        '001_python_code/ver1/strategy_v1.py',
        '001_python_code/ver1/config_v1.py',

        # Library core files
        '001_python_code/lib/core/logger.py',
        '001_python_code/lib/core/config_manager.py',
        '001_python_code/lib/core/version_loader.py',
        '001_python_code/lib/core/arg_parser.py',

        # Library API files
        '001_python_code/lib/api/bithumb_api.py',

        # Library GUI components
        '001_python_code/lib/gui/components/chart_widget.py',
        '001_python_code/lib/gui/components/signal_history_widget.py',
        '001_python_code/lib/gui/components/multi_chart_tab.py'
    ]

    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)

    if missing_files:
        messagebox.showerror(
            "파일 누락",
            f"다음 파일들이 누락되었습니다:\n" + "\n".join(missing_files) + "\n\n"
            "005_money 디렉토리에서 실행해주세요.\n\n"
            "또는 ver1 버전 파일이 누락되었을 수 있습니다."
        )
        return False

    return True

def show_startup_info(version="ver1"):
    """시작 정보 창 표시

    Args:
        version: 실행할 버전 (ver1, ver2, ver3 등)
    """
    info_window = tk.Tk()
    info_window.title(f"빗썸 자동매매 봇 GUI - 시작 ({version})")
    info_window.geometry("600x650")
    info_window.resizable(False, False)

    # 중앙 정렬
    try:
        info_window.eval('tk::PlaceWindow . center')
    except:
        # 중앙 정렬이 실패하면 수동으로 중앙에 배치
        info_window.update_idletasks()
        x = (info_window.winfo_screenwidth() // 2) - (600 // 2)
        y = (info_window.winfo_screenheight() // 2) - (550 // 2)
        info_window.geometry(f"600x550+{x}+{y}")

    # 메인 프레임
    main_frame = tk.Frame(info_window, padx=20, pady=20)
    main_frame.pack(fill=tk.BOTH, expand=True)

    # 제목
    version_display_map = {
        "ver1": "v1 - Elite 8-Indicator",
        "ver2": "v2 - 다중 시간대 전략",
        "ver3": "v3 - 포트폴리오 멀티코인"
    }
    version_display = version_display_map.get(version, version)
    title_label = tk.Label(
        main_frame,
        text=f"🤖 빗썸 자동매매 봇 GUI\n{version_display}",
        font=("Arial", 16, "bold"),
        fg="blue"
    )
    title_label.pack(pady=(0, 20))

    # 버전별 기능 설명
    if version == "ver3":
        features_text = """
🔥 주요 기능 (v3):

📊 포트폴리오 멀티코인 전략
  • 2-3개 코인 동시 모니터링 (BTC, ETH, XRP 등)
  • 최대 2개 포지션 동시 보유
  • 진입 점수 기반 우선순위 (높은 점수 우선)
  • 병렬 분석으로 빠른 의사결정

💼 포트폴리오 관리
  • 포트폴리오 레벨 리스크 관리
  • 개별 코인 Ver2 전략 적용
  • 스레드 안전 동시 실행
  • 6% 총 포트폴리오 리스크 제한

⚙️ 코인 선택
  • 동적 코인 선택 (체크박스)
  • 최소 1개, 최대 4개 코인
  • 실시간 코인 변경 가능
  • 코인별 상태 추적

🎮 실시간 모니터링
  • 포트폴리오 오버뷰 테이블
  • 코인별 진입 점수 (0-4)
  • 전체 P&L 및 포지션 현황
  • 15분 주기 자동 분석
"""
    elif version == "ver2":
        features_text = """
🔥 주요 기능 (v2):

📊 다중 시간대 전략
  • 일봉: EMA 50/200 골든크로스 체제 필터
  • 4시간봉: 점수 기반 진입 시스템 (3점 이상)
  • BB 하단 터치 +1, RSI 과매도 +1, 스토캐스틱 교차 +2

💼 포지션 관리
  • 50% 분할 진입/청산
  • 샹들리에 엑시트 (ATR 3배 추적 손절)
  • 본전 손절 자동 전환

⚙️ 위험 관리
  • 연속 손실 5회 제한
  • 일일 손실 5% 한도
  • 하루 최대 2회 거래

🎮 실시간 모니터링
  • 시장 체제 상태 (강세/약세/중립)
  • 진입 점수 실시간 계산 (0/4)
  • 회로차단기 상태
  • 포지션 단계 추적
"""
    else:
        features_text = """
🔥 주요 기능 (v1):

📊 실시간 모니터링
  • 현재 거래 코인 및 가격 표시
  • 체결 대기 주문 현황
  • 실시간 로그 스트림

💰 수익 현황 대시보드
  • 일별/총 수익 표시
  • 거래 횟수 및 성공률
  • 최근 거래 내역

⚙️ 실시간 설정 변경
  • 드롭다운으로 코인 선택
  • 체크 간격 변경 (10s ~ 4h)
  • 거래 금액 조정

🎮 간편한 제어
  • 원클릭 봇 시작/정지
  • 안전한 모의 거래 모드
  • 직관적인 GUI 인터페이스
"""

    features_label = tk.Label(
        main_frame,
        text=features_text,
        font=("Arial", 10),
        justify=tk.LEFT,
        anchor="w"
    )
    features_label.pack(fill=tk.BOTH, expand=True)

    # 주의사항
    warning_text = "⚠️  주의: 기본적으로 모의 거래 모드로 실행됩니다."
    warning_label = tk.Label(
        main_frame,
        text=warning_text,
        font=("Arial", 10, "bold"),
        fg="red"
    )
    warning_label.pack(pady=(10, 0))

    # 버튼 프레임
    button_frame = tk.Frame(main_frame)
    button_frame.pack(pady=(20, 0))

    # GUI 시작 버튼
    def start_gui():
        print(f"🚀 {version} GUI 애플리케이션으로 전환합니다...")
        info_window.destroy()

        # 잠시 대기하여 창이 완전히 닫히도록 함
        info_window.update()
        time.sleep(0.1)

        launch_gui(version)

    start_button = tk.Button(
        button_frame,
        text="🚀 GUI 시작",
        font=("Arial", 12, "bold"),
        bg="lightgreen",
        command=start_gui,
        width=15
    )
    start_button.pack(side=tk.LEFT, padx=(0, 10))

    # 종료 버튼
    exit_button = tk.Button(
        button_frame,
        text="❌ 종료",
        font=("Arial", 12),
        bg="lightcoral",
        command=info_window.destroy,
        width=15
    )
    exit_button.pack(side=tk.LEFT)

    info_window.mainloop()

def launch_gui(version="ver1"):
    """GUI 실행

    Args:
        version: 실행할 버전 (ver1, ver2, ver3 등)
    """
    try:
        print(f"🔄 GUI 애플리케이션을 시작하고 있습니다... (버전: {version})")

        # Add 001_python_code to Python path for imports
        python_code_dir = os.path.join(os.getcwd(), '001_python_code')
        if python_code_dir not in sys.path:
            sys.path.insert(0, python_code_dir)

        # 버전별로 다른 GUI 모듈 임포트
        try:
            if version == "ver3":
                # v3 GUI 실행 (Portfolio Multi-Coin)
                ver3_dir = os.path.join(python_code_dir, 'ver3')
                if ver3_dir not in sys.path:
                    sys.path.insert(0, ver3_dir)

                from ver3.gui_app_v3 import TradingBotGUIV3
                print("✅ v3 GUI 모듈 임포트 성공")
                gui_class = TradingBotGUIV3
            elif version == "ver2":
                # v2 GUI 실행
                ver2_dir = os.path.join(python_code_dir, 'ver2')
                if ver2_dir not in sys.path:
                    sys.path.insert(0, ver2_dir)

                from ver2.gui_app_v2 import TradingBotGUIV2
                print("✅ v2 GUI 모듈 임포트 성공")
                gui_class = TradingBotGUIV2
            else:
                # v1 GUI 실행 (기본)
                from gui_app import TradingBotGUI
                print("✅ v1 GUI 모듈 임포트 성공")
                gui_class = TradingBotGUI

        except ImportError as e:
            error_msg = f"GUI 모듈 임포트 실패: {e}\n\n" + \
                       "다음을 확인해주세요:\n"

            # v2/v3 특화 에러 메시지
            if version in ["ver2", "ver3"] and "backtrader" in str(e):
                error_msg += f"⚠️ {version}는 Backtrader 라이브러리가 필요합니다!\n\n" + \
                            "해결 방법:\n" + \
                            "1. 터미널에서 다음 명령 실행:\n" + \
                            "   cd /Users/seongwookjang/project/git/violet_sw/005_money\n" + \
                            "   source .venv/bin/activate  # if using venv\n" + \
                            "   pip install -r requirements.txt\n\n" + \
                            "2. 또는 개별 설치:\n" + \
                            "   pip install backtrader python-binance\n\n" + \
                            "3. 또는 v1 버전 사용:\n" + \
                            "   ./gui --version ver1"
            else:
                error_msg += "1. run.py 또는 ./gui를 먼저 실행해서 환경을 설정하세요\n" + \
                            "2. pip install -r requirements.txt 실행\n" + \
                            "3. 필요한 파일들이 모두 있는지 확인"

            messagebox.showerror("임포트 오류", error_msg)
            return

        # GUI 윈도우 생성
        root = tk.Tk()

        # 창 닫기 이벤트 처리
        def on_closing():
            if messagebox.askokcancel("종료", f"{version} GUI를 종료하시겠습니까?"):
                root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_closing)

        # GUI 애플리케이션 시작
        print(f"🚀 {version} GUI 인터페이스를 생성하고 있습니다...")
        app = gui_class(root)

        print(f"✅ {version} GUI가 성공적으로 시작되었습니다!")
        if version == "ver3":
            print("💡 v3 전략: Portfolio Multi-Coin Strategy (2-3 coins, max 2 positions)")
        elif version == "ver2":
            print("💡 v2 전략: 다중 시간대 분석 (일봉 체제 + 4시간 진입)")
        else:
            print("💡 v1 전략: Elite 8-Indicator Strategy")

        # 메인 루프 시작
        root.mainloop()

    except KeyboardInterrupt:
        print("\n⏹️ 사용자에 의해 GUI가 중단되었습니다.")
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"❌ GUI 실행 중 오류 발생: {e}")
        print(f"상세 오류:\n{error_detail}")

        messagebox.showerror(
            "GUI 실행 오류",
            f"GUI 실행 중 오류가 발생했습니다:\n{e}\n\n" +
            "해결 방법:\n" +
            "1. ./gui 스크립트를 대신 사용해보세요\n" +
            "2. run.py를 먼저 실행하여 환경을 설정하세요\n" +
            "3. 오류가 계속되면 RUN_SCRIPTS_SUMMARY.md를 참고하세요"
        )

def main(version="ver1"):
    """메인 실행 함수

    Args:
        version: 실행할 버전 (ver1, ver2, ver3 등)
    """
    print(f"🔄 빗썸 자동매매 봇 GUI를 시작합니다... (버전: {version})")
    print("📍 현재 디렉토리:", os.getcwd())

    # 파일 확인
    print("📂 필요한 파일들을 확인하고 있습니다...")
    if not check_files():
        print("❌ 필요한 파일이 누락되었습니다.")
        return
    print("✅ 모든 필요한 파일이 존재합니다.")

    # 의존성 확인 (GUI 모드에서는 경고만 표시)
    print("📦 의존성 패키지를 확인하고 있습니다...")
    if not check_dependencies(version):
        print("⚠️ 일부 패키지가 누락되었지만 GUI를 시작해봅니다.")
        print("💡 문제가 발생하면 ./gui 스크립트를 사용해보세요.")
    else:
        print("✅ 모든 의존성 패키지가 설치되어 있습니다.")

    # 시작 정보 표시
    print("🎮 GUI 시작 화면을 표시합니다...")
    print("💡 '🚀 GUI 시작' 버튼을 클릭하여 실제 거래 인터페이스로 이동하세요.")
    show_startup_info(version)

if __name__ == "__main__":
    # 명령행 인수 파싱
    version = "ver1"  # 기본값
    direct_mode = False

    # 간단한 인수 파싱
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] in ["--version", "-v"]:
            if i + 1 < len(sys.argv):
                version = sys.argv[i + 1]
                # Validate version
                if version not in ["ver1", "ver2", "ver3"]:
                    print(f"❌ 잘못된 버전: {version}")
                    print("사용 가능한 버전: ver1, ver2, ver3")
                    sys.exit(1)
                i += 2
            else:
                print("❌ --version 옵션에 값이 필요합니다 (예: --version ver2)")
                sys.exit(1)
        elif sys.argv[i] == "--direct":
            direct_mode = True
            i += 1
        else:
            print(f"❌ 알 수 없는 옵션: {sys.argv[i]}")
            print("사용법: python run_gui.py [--version ver1|ver2|ver3] [--direct]")
            sys.exit(1)

    if direct_mode:
        # 바로 GUI 실행 (시작 화면 건너뛰기)
        print(f"🚀 바로 {version} GUI로 실행합니다...")

        if not check_files():
            sys.exit(1)

        try:
            launch_gui(version)
        except KeyboardInterrupt:
            print("\n⏹️ 사용자에 의해 중단되었습니다.")
        except Exception as e:
            print(f"❌ 직접 실행 중 오류: {e}")
            print("💡 대신 'python run_gui.py' (시작 화면 포함)를 시도해보세요.")
    else:
        main(version)