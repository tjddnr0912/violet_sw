#!/usr/bin/env python3
"""
빗썸 자동매매 봇 실행 스크립트 (업데이트됨)
새로운 명령행 인수와 동적 설정 지원
"""

import os
import sys
import subprocess
import platform
import argparse

def show_usage_examples():
    """사용 예시 표시"""
    print("""
🚀 빗썸 자동매매 봇 사용 예시

📋 기본 실행:
  python run.py
  python run.py --help

⏰ 시간 간격 설정:
  python run.py --interval 30s          # 30초마다
  python run.py --interval 5m           # 5분마다
  python run.py --interval 1h           # 1시간마다

💰 거래 설정:
  python run.py --coin ETH              # 이더리움 거래
  python run.py --amount 50000          # 5만원씩 거래
  python run.py --coin ETH --amount 30000 --interval 1m

🛠️ 설정 관리:
  python run.py --show-config           # 현재 설정 확인
  python run.py --interactive           # 대화형 설정
  python run.py --save-config my.json   # 설정 저장

🔧 전략 조정:
  python run.py --short-ma 3 --long-ma 15
  python run.py --rsi-period 7

📁 파일 관리:
  python run.py --config-file my.json   # 저장된 설정 사용

⚠️  안전 모드:
  python run.py --dry-run               # 모의 거래 (기본값)
  python run.py --test-mode             # 테스트 모드 (내역 기록 안함)
  python run.py --live                  # 실제 거래 (주의!)

🔍 API 테스트:
  python run.py --test-api              # API 연결 테스트

상세한 사용법은 USAGE_EXAMPLES.md 파일을 참고하세요.
""")

def parse_run_arguments():
    """run.py 전용 인수 파싱"""
    parser = argparse.ArgumentParser(
        description="빗썸 자동매매 봇 실행 스크립트",
        add_help=False  # main.py의 help과 충돌 방지
    )

    parser.add_argument('--setup-only', action='store_true',
                      help='환경 설정만 하고 봇은 실행하지 않음')
    parser.add_argument('--skip-setup', action='store_true',
                      help='환경 설정을 건너뛰고 봇만 실행')
    parser.add_argument('--examples', action='store_true',
                      help='사용 예시 표시')
    parser.add_argument('--force-install', action='store_true',
                      help='패키지 강제 재설치')
    parser.add_argument('--test-api', action='store_true',
                      help='API 연결 테스트 실행')

    # 알려진 인수만 파싱 (나머지는 main.py로 전달)
    args, unknown = parser.parse_known_args()
    return args, unknown

def check_python_version():
    """Python 버전 확인"""
    if sys.version_info < (3, 7):
        print("❌ Python 3.7 이상이 필요합니다.")
        print(f"현재 버전: {sys.version}")
        return False
    print(f"✅ Python 버전 확인: {sys.version.split()[0]}")
    return True

def setup_virtual_environment():
    """가상환경 설정"""
    venv_path = ".venv"

    if not os.path.exists(venv_path):
        print("📦 가상환경을 생성하고 있습니다...")
        try:
            subprocess.run([sys.executable, "-m", "venv", venv_path], check=True)
            print("✅ 가상환경 생성 완료")
        except subprocess.CalledProcessError:
            print("❌ 가상환경 생성 실패")
            return False
    else:
        print("✅ 가상환경이 이미 존재합니다")

    return True

def get_pip_command():
    """운영체제에 맞는 pip 명령어 반환"""
    system = platform.system()
    if system == "Windows":
        return os.path.join(".venv", "Scripts", "pip")
    else:
        return os.path.join(".venv", "bin", "pip")

def get_python_command():
    """운영체제에 맞는 python 명령어 반환"""
    system = platform.system()
    if system == "Windows":
        return os.path.join(".venv", "Scripts", "python")
    else:
        return os.path.join(".venv", "bin", "python")

def install_dependencies(force_install=False):
    """의존성 패키지 설치"""
    print("📦 의존성 패키지를 확인하고 있습니다...")

    pip_cmd = get_pip_command()

    try:
        # pip 업그레이드
        if force_install:
            subprocess.run([pip_cmd, "install", "--upgrade", "pip"], check=True)

        # requirements.txt 설치
        if os.path.exists("requirements.txt"):
            install_cmd = [pip_cmd, "install", "-r", "requirements.txt"]
            if force_install:
                install_cmd.append("--force-reinstall")
            subprocess.run(install_cmd, check=True)
            print("✅ 의존성 패키지 설치 완료")
        else:
            # 필수 패키지 직접 설치
            packages = ["pandas", "requests", "schedule", "numpy"]
            for package in packages:
                install_cmd = [pip_cmd, "install", package]
                if force_install:
                    install_cmd.append("--force-reinstall")
                subprocess.run(install_cmd, check=True)
            print("✅ 필수 패키지 설치 완료")

        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 패키지 설치 실패: {e}")
        return False

def check_config(python_cmd):
    """설정 파일 확인"""
    print("🔧 설정을 확인하고 있습니다...")

    try:
        result = subprocess.run([
            python_cmd, "-c",
            "import sys; sys.path.insert(0, '001_python_code'); import config; print('✅ 설정 파일 로드 성공'); print('API Keys configured:', config.BITHUMB_CONNECT_KEY != 'YOUR_CONNECT_KEY')"
        ], capture_output=True, text=True, check=True)

        print(result.stdout.strip())

        if "False" in result.stdout:
            print("⚠️  API 키가 설정되지 않았습니다.")
            print("   환경변수 또는 config.py 파일에서 API 키를 설정해주세요.")
            print("   모의 거래 모드로 실행됩니다.")

        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 설정 확인 실패: {e}")
        return False

def display_startup_info(main_args):
    """시작 정보 표시"""
    print("\n" + "="*60)
    print("🤖 빗썸 자동매매 봇")
    print("="*60)

    # 전달될 인수가 있으면 표시
    if main_args:
        print("📋 설정된 옵션:")
        args_str = " ".join(main_args)

        # 주요 옵션 하이라이트
        if "--interval" in args_str:
            interval_idx = main_args.index("--interval")
            if interval_idx + 1 < len(main_args):
                print(f"  ⏰ 체크 간격: {main_args[interval_idx + 1]}")

        if "--coin" in args_str:
            coin_idx = main_args.index("--coin")
            if coin_idx + 1 < len(main_args):
                print(f"  💰 거래 코인: {main_args[coin_idx + 1]}")

        if "--amount" in args_str:
            amount_idx = main_args.index("--amount")
            if amount_idx + 1 < len(main_args):
                print(f"  💵 거래 금액: {main_args[amount_idx + 1]}원")

        if "--live" in args_str:
            print("  🔴 실제 거래 모드 (주의!)")
        elif "--dry-run" in args_str or "--dry-run" not in args_str:
            print("  ⚠️  모의 거래 모드")

        if "--interactive" in args_str:
            print("  🛠️ 대화형 설정 모드")

        print(f"  📝 전체 옵션: {args_str}")

    print("\n📈 주요 기능:")
    print("  • 빗썸 API 연동 (인증, 거래, 잔고조회)")
    print("  • 고도화된 거래 전략 (MA, RSI, 볼린저밴드)")
    print("  • 포괄적 로깅 시스템")
    print("  • 거래 내역 추적 및 리포트")
    print("  • 안전 장치 (모의거래, 거래한도)")
    print("  • 유연한 시간 간격 설정 (초/분/시간)")
    print()
    print("⚠️  주의사항:")
    print("  • 기본적으로 모의 거래 모드로 실행됩니다")
    print("  • 실제 거래 시 자금 손실 위험이 있습니다")
    print("  • 설정을 신중히 검토하세요")
    print("="*60)
    print()

def run_trading_bot(main_args):
    """거래 봇 실행"""
    print("🤖 거래 봇을 시작합니다...")

    python_cmd = get_python_command()

    try:
        # main.py에 인수 전달
        cmd = [python_cmd, "001_python_code/main.py"] + main_args
        print(f"실행 명령: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ 거래 봇 실행 실패: {e}")
        return False
    except KeyboardInterrupt:
        print("\n\n⏹️  사용자에 의해 중단되었습니다.")
        return True

    return True

def main():
    """메인 실행 함수"""
    print("🔄 빗썸 자동매매 봇 설정을 시작합니다...\n")

    # run.py 전용 인수 파싱
    run_args, main_args = parse_run_arguments()

    # 사용 예시 표시
    if run_args.examples:
        show_usage_examples()
        return

    # API 테스트 실행
    if run_args.test_api:
        print("🔍 API 연결 테스트를 실행합니다...\n")

        # 가상환경과 의존성만 확인
        if not check_python_version():
            return
        if not setup_virtual_environment():
            return
        if not install_dependencies():
            return

        # API 테스트 실행
        python_cmd = get_python_command()
        try:
            subprocess.run([python_cmd, "001_python_code/test_api_connection.py"], check=True)
        except subprocess.CalledProcessError:
            print("❌ API 테스트 실행 실패")
        return

    # 1. Python 버전 확인
    if not check_python_version():
        return

    # 2. 가상환경 설정 (건너뛰기 옵션 확인)
    if not run_args.skip_setup:
        if not setup_virtual_environment():
            return

    # 3. 의존성 설치 (건너뛰기 옵션 확인)
    if not run_args.skip_setup:
        if not install_dependencies(run_args.force_install):
            return

    # 4. 설정 확인
    python_cmd = get_python_command()
    if not check_config(python_cmd):
        return

    # 설정만 하고 종료하는 옵션
    if run_args.setup_only:
        print("✅ 환경 설정이 완료되었습니다.")
        print("봇을 실행하려면: python main.py")
        return

    # 5. 시작 정보 표시
    display_startup_info(main_args)

    # 6. 사용자 확인 (특정 조건에서만)
    need_confirmation = True

    # 자동 실행 조건들
    if (main_args and
        ("--help" in main_args or
         "--show-config" in main_args or
         "--save-config" in main_args or
         "--reset-config" in main_args or
         "--interactive" in main_args or
         "--gui" in main_args)):
        need_confirmation = False

    if need_confirmation:
        try:
            user_input = input("계속 진행하시겠습니까? [y/N]: ").strip().lower()
            if user_input not in ['y', 'yes']:
                print("프로그램을 종료합니다.")
                return
        except KeyboardInterrupt:
            print("\n프로그램을 종료합니다.")
            return

    # 7. 거래 봇 실행
    run_trading_bot(main_args)

if __name__ == "__main__":
    main()