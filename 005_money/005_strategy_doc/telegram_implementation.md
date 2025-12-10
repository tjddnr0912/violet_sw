# 🔧 텔레그램 알림 실제 구현 코드

Ver3 Trading Bot에 텔레그램 알림을 추가하는 실제 구현 코드입니다.

---

## 📁 파일 구조

```
005_money/
├── 001_python_code/
│   ├── lib/
│   │   └── core/
│   │       ├── telegram_notifier.py          # 새로 추가
│   │       ├── logger.py                      # 수정
│   │       └── ...
│   ├── ver3/
│   │   ├── live_executor_v3.py               # 수정
│   │   ├── trading_bot_v3.py                 # 수정
│   │   └── ...
│   └── test_telegram.py                      # 새로 추가 (테스트용)
├── .env                                       # 수정
└── requirements.txt                           # 수정
```

---

## 📝 Step-by-Step 구현

### Step 1: requirements.txt 업데이트

`requirements.txt`에 추가:
```txt
# Existing dependencies
pandas>=2.0.0
numpy>=1.24.0
requests>=2.31.0
schedule>=1.2.0
matplotlib>=3.7.0

# Telegram notifications (choose one)
# Option 1: Simple (권장 - 가벼움)
requests>=2.31.0  # 이미 있음

# Option 2: Advanced (비동기 처리 필요시)
# python-telegram-bot>=20.7
```

설치:
```bash
pip install -r requirements.txt
```

### Step 2: .env 파일 업데이트

`.env` 파일에 추가:
```bash
# ===================================
# Telegram Notification Settings
# ===================================
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_NOTIFICATIONS_ENABLED=False  # True로 변경하여 활성화
```

`.env.example` 파일에도 추가:
```bash
# Telegram Notifications
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_NOTIFICATIONS_ENABLED=True
```

### Step 3: telegram_notifier.py 생성

전체 코드는 `telegram_notification_guide.md` 참조

핵심 부분만 요약:
```python
# 001_python_code/lib/core/telegram_notifier.py

import os
import requests
from datetime import datetime

class TelegramNotifier:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED", "False").lower() == "true"
        
        if self.enabled and (not self.bot_token or not self.chat_id):
            print("⚠️  Telegram notifications enabled but credentials missing!")
            self.enabled = False
    
    def send_message(self, message: str, parse_mode: str = "Markdown") -> bool:
        if not self.enabled:
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"❌ Telegram error: {e}")
            return False
    
    def send_trade_alert(self, action, ticker, amount, price, success, reason="", order_id=""):
        # 구현 내용은 가이드 참조
        pass

# Singleton
_notifier = None
def get_telegram_notifier():
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier
```

### Step 4: live_executor_v3.py 수정

**위치**: `001_python_code/ver3/live_executor_v3.py`

#### 4-1. Import 추가

파일 상단에 추가:
```python
from lib.core.telegram_notifier import get_telegram_notifier
```

#### 4-2. __init__ 메서드 수정

```python
def __init__(self, coins, config, logger, api, transaction_history, markdown_logger):
    # ... 기존 코드 ...
    
    # Initialize Telegram notifier (추가)
    self.telegram = get_telegram_notifier()
    
    # Send startup notification
    if self.telegram.enabled:
        self.telegram.send_bot_status(
            status="STARTED",
            positions=len(self.positions),
            max_positions=self.max_positions,
            coins=coins
        )
```

#### 4-3. execute_trade 메서드 수정

매수/매도 성공 시 알림 추가:

```python
def execute_trade(self, ticker: str, action: str, analysis: Dict[str, Any]) -> bool:
    """Execute trade with Telegram notifications."""
    
    try:
        # ... 기존 거래 실행 코드 ...
        
        # 거래 성공 시
        if response and response.get('status') == '0000':
            order_id = response.get('order_id', 'N/A')
            
            # 기존 로깅 코드...
            
            # ===== 텔레그램 알림 추가 =====
            self.telegram.send_trade_alert(
                action=action,
                ticker=ticker,
                amount=rounded_units,
                price=price,
                success=True,
                reason=f"Score: {analysis.get('entry_score', 'N/A')}/4, Regime: {analysis.get('market_regime', 'N/A')}",
                order_id=order_id
            )
            # =============================
            
            return True
            
    except Exception as e:
        # 에러 발생 시 알림
        self.telegram.send_error_alert(
            error_type="Trade Execution Error",
            error_message=str(e),
            details=f"Ticker: {ticker}, Action: {action}"
        )
        
        self.logger.log_error(f"Trade execution failed for {ticker}", e)
        return False
```

#### 4-4. close_position 메서드 수정

포지션 종료 시 알림:

```python
def close_position(self, ticker: str, reason: str = "Manual close"):
    """Close position with notification."""
    
    try:
        # ... 기존 종료 코드 ...
        
        # 종료 성공 시 알림
        if success:
            self.telegram.send_trade_alert(
                action="CLOSE",
                ticker=ticker,
                amount=pos.size,
                price=current_price,
                success=True,
                reason=reason,
                order_id=response.get('order_id', 'CLOSED')
            )
            
    except Exception as e:
        self.telegram.send_error_alert(
            error_type="Position Close Error",
            error_message=str(e),
            details=f"Ticker: {ticker}, Reason: {reason}"
        )
```

### Step 5: trading_bot_v3.py 수정

**위치**: `001_python_code/ver3/trading_bot_v3.py`

#### 5-1. Import 추가

```python
from lib.core.telegram_notifier import get_telegram_notifier
```

#### 5-2. __init__ 메서드에 텔레그램 초기화

```python
def __init__(self, config: Dict[str, Any], log_prefix: str = 'ver3_cli'):
    # ... 기존 코드 ...
    
    # Initialize Telegram (추가)
    self.telegram = get_telegram_notifier()
```

#### 5-3. run 메서드에 시작 알림

```python
def run(self):
    """Main loop with startup notification."""
    
    self.running = True
    self.cycle_count = 0
    
    # Send startup notification
    if self.telegram.enabled:
        self.telegram.send_bot_status(
            status="STARTED",
            positions=0,
            max_positions=self.portfolio_config.get('max_positions', 3),
            coins=self.coins
        )
    
    self.logger.logger.info("=" * 60)
    self.logger.logger.info("Trading Bot V3 Started")
    # ... 나머지 코드 ...
```

#### 5-4. 종료 시 알림

```python
def run(self):
    try:
        while self.running:
            # ... 메인 루프 ...
            
    except KeyboardInterrupt:
        self.logger.logger.info("\nShutdown signal received")
        
        # Send shutdown notification
        if self.telegram.enabled:
            positions = len(self.portfolio_manager.executor.positions)
            self.telegram.send_bot_status(
                status="STOPPED",
                positions=positions,
                max_positions=self.portfolio_config.get('max_positions', 3),
                total_pnl=0  # 필요시 실제 P&L 계산
            )
```

### Step 6: 일일 요약 추가 (선택사항)

하루가 끝날 때 요약 전송:

```python
def send_daily_summary(self):
    """Send daily trading summary."""
    
    if not self.telegram.enabled:
        return
    
    # Get transaction history
    summary = self.transaction_history.get_summary(days=1)
    
    self.telegram.send_daily_summary({
        'date': datetime.now().strftime('%Y-%m-%d'),
        'buy_count': summary.get('buy_count', 0),
        'sell_count': summary.get('sell_count', 0),
        'total_volume': summary.get('total_volume', 0),
        'total_fees': summary.get('total_fees', 0),
        'net_pnl': 0,  # 계산 필요
        'success_count': summary.get('successful_transactions', 0),
        'fail_count': summary.get('total_transactions', 0) - summary.get('successful_transactions', 0)
    })
```

스케줄러에 추가:
```python
import schedule

# 매일 자정에 요약 전송
schedule.every().day.at("00:00").do(self.send_daily_summary)
```

---

## 🧪 테스트

### 테스트 스크립트 생성

`test_telegram.py`:
```python
#!/usr/bin/env python3
"""Test Telegram notifications"""

import os
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent / "001_python_code"))

from lib.core.telegram_notifier import get_telegram_notifier

def main():
    print("📱 Testing Telegram notifications...\n")
    
    telegram = get_telegram_notifier()
    
    if not telegram.enabled:
        print("❌ Telegram not enabled")
        print("   1. Set TELEGRAM_BOT_TOKEN in .env")
        print("   2. Set TELEGRAM_CHAT_ID in .env")
        print("   3. Set TELEGRAM_NOTIFICATIONS_ENABLED=True")
        return
    
    print("✅ Telegram configured")
    print(f"   Bot Token: {telegram.bot_token[:10]}...")
    print(f"   Chat ID: {telegram.chat_id}")
    print()
    
    # Test message
    print("Sending test message...")
    success = telegram.send_message("🤖 Ver3 Trading Bot Test")
    
    if success:
        print("✅ Message sent successfully!")
        print("   Check your Telegram app")
    else:
        print("❌ Failed to send message")
        print("   Check bot token and chat ID")

if __name__ == "__main__":
    main()
```

실행:
```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money
python test_telegram.py
```

---

## 📊 알림 예시

### 매수 성공 알림
```
🟢 BUY 성공

📊 코인: BTC
💰 수량: 0.001000
💵 가격: 50,000,000 KRW
💸 총액: 50,000 KRW

⏰ 시각: 2025-12-09 15:30:45
📝 사유: Score: 4/4, Regime: BULLISH
🔖 주문ID: 12345678
```

### 매도 성공 알림
```
🔴 SELL 성공

📊 코인: ETH
💰 수량: 0.050000
💵 가격: 4,200,000 KRW
💸 총액: 210,000 KRW

⏰ 시각: 2025-12-09 16:45:20
📝 사유: TP1 reached (+2.5%)
🔖 주문ID: 87654321
```

### 에러 알림
```
⚠️ 에러 발생

🔴 유형: Trade Execution Error
📝 메시지: Insufficient balance

⏰ 시각: 2025-12-09 17:10:33

📋 상세:
Ticker: SOL, Action: BUY
Available: 45,000 KRW
Required: 100,000 KRW
```

### 봇 상태 알림
```
🚀 봇 상태: STARTED

📊 포지션: 0/3
💰 총 손익: +0 KRW

⏰ 시각: 2025-12-09 09:00:00
🪙 모니터링 코인: BTC, ETH, SOL
```

---

## ⚙️ 고급 설정

### 알림 필터링

특정 조건에만 알림 전송:

```python
class TelegramNotifier:
    def __init__(self):
        # ... 기존 코드 ...
        
        # 알림 필터 설정
        self.notify_on_buy = os.getenv("TELEGRAM_NOTIFY_BUY", "True").lower() == "true"
        self.notify_on_sell = os.getenv("TELEGRAM_NOTIFY_SELL", "True").lower() == "true"
        self.notify_on_error = os.getenv("TELEGRAM_NOTIFY_ERROR", "True").lower() == "true"
        self.min_trade_amount = float(os.getenv("TELEGRAM_MIN_AMOUNT", "0"))
    
    def send_trade_alert(self, action, ticker, amount, price, success, reason="", order_id=""):
        if not self.enabled:
            return
        
        # 필터 적용
        if action == "BUY" and not self.notify_on_buy:
            return
        if action == "SELL" and not self.notify_on_sell:
            return
        
        total_amount = amount * price
        if total_amount < self.min_trade_amount:
            return  # 소액 거래는 알림 안 함
        
        # 나머지 코드...
```

`.env`에 추가:
```bash
# Telegram 알림 필터
TELEGRAM_NOTIFY_BUY=True
TELEGRAM_NOTIFY_SELL=True
TELEGRAM_NOTIFY_ERROR=True
TELEGRAM_MIN_AMOUNT=50000  # 5만원 이상만 알림
```

### Rate Limiting

너무 많은 알림 방지:

```python
from datetime import datetime, timedelta

class TelegramNotifier:
    def __init__(self):
        # ... 기존 코드 ...
        
        self.last_message_time = {}
        self.min_interval = 10  # 같은 종류 메시지 최소 10초 간격
    
    def _should_send(self, message_type: str) -> bool:
        """Check if enough time has passed since last message."""
        
        now = datetime.now()
        if message_type in self.last_message_time:
            elapsed = (now - self.last_message_time[message_type]).total_seconds()
            if elapsed < self.min_interval:
                return False
        
        self.last_message_time[message_type] = now
        return True
    
    def send_trade_alert(self, ...):
        if not self._should_send("trade"):
            return  # 너무 빠른 연속 알림 차단
        
        # 나머지 코드...
```

---

## 🔍 트러블슈팅

### 일반적인 문제들

1. **"Unauthorized" 에러**
   - Bot token 확인
   - `.env` 파일 위치 확인
   - 환경변수 로드 확인

2. **"Chat not found" 에러**
   - 봇에게 `/start` 전송
   - Chat ID 재확인
   - 그룹에서는 봇을 관리자로 추가

3. **메시지가 오지 않음**
   - `test_telegram.py` 실행하여 설정 확인
   - 로그에서 에러 메시지 확인
   - 방화벽 설정 확인

4. **Rate limit 에러**
   - 알림 빈도 줄이기
   - Rate limiting 구현
   - 중요한 알림만 활성화

---

## 📋 체크리스트

구현 전:
- [ ] BotFather에서 봇 생성
- [ ] Bot token 발급
- [ ] Chat ID 획득
- [ ] `.env` 파일 설정

코드 작성:
- [ ] `telegram_notifier.py` 생성
- [ ] `live_executor_v3.py` 수정
- [ ] `trading_bot_v3.py` 수정
- [ ] `requirements.txt` 업데이트

테스트:
- [ ] `test_telegram.py` 실행
- [ ] 테스트 메시지 수신 확인
- [ ] 봇 시작 알림 확인
- [ ] 거래 알림 테스트 (Dry run)

배포:
- [ ] 프로덕션 환경 `.env` 설정
- [ ] 알림 필터 설정
- [ ] Rate limiting 설정
- [ ] 모니터링 시작

**구현 완료! 🎉**
