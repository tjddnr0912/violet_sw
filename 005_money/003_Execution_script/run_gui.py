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

def check_dependencies():
    """필요한 패키지 확인"""
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

    if missing_packages:
        error_msg = f"다음 패키지들이 설치되지 않았습니다:\n" + "\n".join(f"• {pkg}" for pkg in missing_packages)
        error_msg += "\n\n해결 방법:\n"
        error_msg += "1. 터미널에서 다음 명령 실행:\n"
        error_msg += "   pip install " + " ".join(missing_packages) + "\n\n"
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

def show_startup_info():
    """시작 정보 창 표시"""
    info_window = tk.Tk()
    info_window.title("빗썸 자동매매 봇 GUI - 시작")
    info_window.geometry("600x500")
    info_window.resizable(False, False)

    # 중앙 정렬
    try:
        info_window.eval('tk::PlaceWindow . center')
    except:
        # 중앙 정렬이 실패하면 수동으로 중앙에 배치
        info_window.update_idletasks()
        x = (info_window.winfo_screenwidth() // 2) - (600 // 2)
        y = (info_window.winfo_screenheight() // 2) - (500 // 2)
        info_window.geometry(f"600x500+{x}+{y}")

    # 메인 프레임
    main_frame = tk.Frame(info_window, padx=20, pady=20)
    main_frame.pack(fill=tk.BOTH, expand=True)

    # 제목
    title_label = tk.Label(
        main_frame,
        text="🤖 빗썸 자동매매 봇 GUI",
        font=("Arial", 16, "bold"),
        fg="blue"
    )
    title_label.pack(pady=(0, 20))

    # 기능 설명
    features_text = """
🔥 주요 기능:

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
        print("🚀 실제 GUI 애플리케이션으로 전환합니다...")
        info_window.destroy()

        # 잠시 대기하여 창이 완전히 닫히도록 함
        info_window.update()
        time.sleep(0.1)

        launch_gui()

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

def launch_gui():
    """GUI 실행"""
    try:
        print("🔄 GUI 애플리케이션을 시작하고 있습니다...")

        # Add 001_python_code to Python path for imports
        python_code_dir = os.path.join(os.getcwd(), '001_python_code')
        if python_code_dir not in sys.path:
            sys.path.insert(0, python_code_dir)

        # 필요한 모듈들을 하나씩 임포트하여 오류 확인
        try:
            from gui_app import TradingBotGUI
            print("✅ GUI 모듈 임포트 성공")
        except ImportError as e:
            error_msg = f"GUI 모듈 임포트 실패: {e}\n\n" + \
                       "다음을 확인해주세요:\n" + \
                       "1. run.py 또는 ./gui를 먼저 실행해서 환경을 설정하세요\n" + \
                       "2. pip install -r requirements.txt 실행\n" + \
                       "3. 필요한 파일들이 모두 있는지 확인"
            messagebox.showerror("임포트 오류", error_msg)
            return

        # GUI 윈도우 생성
        root = tk.Tk()

        # 창 닫기 이벤트 처리
        def on_closing():
            if messagebox.askokcancel("종료", "GUI를 종료하시겠습니까?"):
                root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_closing)

        # GUI 애플리케이션 시작
        print("🚀 GUI 인터페이스를 생성하고 있습니다...")
        app = TradingBotGUI(root)

        print("✅ GUI가 성공적으로 시작되었습니다!")
        print("💡 GUI 창에서 봇을 제어할 수 있습니다.")

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

def main():
    """메인 실행 함수"""
    print("🔄 빗썸 자동매매 봇 GUI를 시작합니다...")
    print("📍 현재 디렉토리:", os.getcwd())

    # 파일 확인
    print("📂 필요한 파일들을 확인하고 있습니다...")
    if not check_files():
        print("❌ 필요한 파일이 누락되었습니다.")
        return
    print("✅ 모든 필요한 파일이 존재합니다.")

    # 의존성 확인 (GUI 모드에서는 경고만 표시)
    print("📦 의존성 패키지를 확인하고 있습니다...")
    if not check_dependencies():
        print("⚠️ 일부 패키지가 누락되었지만 GUI를 시작해봅니다.")
        print("💡 문제가 발생하면 ./gui 스크립트를 사용해보세요.")
    else:
        print("✅ 모든 의존성 패키지가 설치되어 있습니다.")

    # 시작 정보 표시
    print("🎮 GUI 시작 화면을 표시합니다...")
    print("💡 '🚀 GUI 시작' 버튼을 클릭하여 실제 거래 인터페이스로 이동하세요.")
    show_startup_info()

if __name__ == "__main__":
    # 명령행 인수 확인
    if len(sys.argv) > 1 and sys.argv[1] == "--direct":
        # 바로 GUI 실행 (시작 화면 건너뛰기)
        print("🚀 바로 GUI로 실행합니다...")

        if not check_files():
            sys.exit(1)

        try:
            launch_gui()
        except KeyboardInterrupt:
            print("\n⏹️ 사용자에 의해 중단되었습니다.")
        except Exception as e:
            print(f"❌ 직접 실행 중 오류: {e}")
            print("💡 대신 'python run_gui.py' (시작 화면 포함)를 시도해보세요.")
    else:
        main()