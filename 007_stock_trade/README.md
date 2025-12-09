# Kiwoom Auto Trading System

키움증권 Open API를 이용한 주식 자동매매 시스템 프로토타입입니다.

## 1. 환경 설정 (Prerequisites)
이 시스템은 **Windows OS** 및 **32-bit Python** 환경에서만 동작합니다. (키움증권 API 제약사항)

### 필수 설치 항목
1.  **Python 3.x (32-bit)**: [Python 다운로드](https://www.python.org/downloads/windows/) (반드시 32-bit installer 선택)
2.  **키움증권 Open API+**: [키움증권 홈페이지](https://www1.kiwoom.com/h/customer/download/VOpenApiInfoView)에서 다운로드 및 설치.
3.  **KOA Studio**: API 테스트 및 모의투자용 (Open API 설치 시 포함됨).

## 2. 설치 (Installation)

프로젝트 의존성 패키지를 설치합니다.

```bash
pip install -r requirements.txt
```

## 3. 설정 (Configuration)

1.  프로젝트 루트의 `.env.example` 파일을 복사하여 `.env` 파일을 생성합니다.
2.  `.env` 파일을 열어 모의투자 계좌번호를 입력합니다.

```ini
# .env
TRADING_MODE=MOCK
ACCOUNT_NO=81xxxxxxxxx  # 본인의 모의투자 계좌번호 (숫자만 입력)
```

> **주의**: 키움증권 Open API는 코드 내에서 아이디/비밀번호 로그인을 지원하지 않습니다. 프로그램 실행 시 뜨는 로그인 창에서 직접 로그인하거나, 트레이 아이콘 설정에서 '계좌비밀번호 저장' 및 '자동로그인'을 설정해야 합니다.

## 4. 실행 (Execution)

`002_code` 디렉토리의 `main_gui.py`를 실행합니다.

```bash
python 002_code/main_gui.py
```

## 5. 사용 방법 (Usage)
1.  프로그램이 실행되면 키움증권 로그인 창이 뜹니다. (자동로그인 설정 시 자동 진행)
2.  로그인이 완료되면 메인 윈도우가 나타납니다.
3.  **Get Account Info** 버튼을 눌러 계좌 정보가 로그창에 출력되는지 확인합니다.
4.  **Start Strategy** 버튼을 누르면:
    *   HTS에 저장된 첫 번째 조건검색식을 불러옵니다.
    *   실시간으로 조건에 맞는 종목이 포착되면 자동으로 매수 주문(시장가 1주)을 전송합니다. (모의투자 환경에서만 테스트하세요!)

## 6. 문제 해결 (Troubleshooting)
*   **`ImportError: DLL load failed`**: Python이 64-bit인지 확인하세요. 32-bit여야 합니다.
*   **로그인 창이 안 뜰 때**: `Open API+`가 제대로 설치되었는지 확인하고, 관리자 권한으로 실행해 보세요.
