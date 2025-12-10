# 📱 텔레그램 알림 기능 구현 가이드

트레이딩 봇의 매수/매도 시도 및 결과를 텔레그램으로 실시간으로 받아볼 수 있는 기능 구현 가이드입니다.

---

## 📋 목차

1. [준비사항](#준비사항)
2. [텔레그램 봇 생성](#텔레그램-봇-생성)
3. [필요한 라이브러리](#필요한-라이브러리)
4. [코드 구현](#코드-구현)
5. [Trading Bot 통합](#trading-bot-통합)
6. [사용 예시](#사용-예시)
7. [문제 해결](#문제-해결)

---

## 준비사항

### 1. 필요한 정보
- **Telegram Bot Token**: BotFather로부터 발급
- **Chat ID**: 메시지를 받을 사용자/그룹의 ID
- **Python 라이브러리**: `python-telegram-bot` 또는 `requests`

### 2. 환경 변수 설정
`.env` 파일에 추가:
```bash
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_NOTIFICATIONS_ENABLED=True
```

---

## 텔레그램 봇 생성

### Step 1: BotFather와 대화 시작

1. 텔레그램에서 [@BotFather](https://t.me/botfather) 검색
2. 대화 시작

### Step 2: 새 봇 생성

```
사용자: /newbot
BotFather: Alright, a new bot. How are we going to call it? Please choose a name for your bot.

사용자: My Trading Bot
BotFather: Good. Now let's choose a username for your bot. It must end in `bot`.

사용자: mytradingbot_123_bot
BotFather: Done! Congratulations on your new bot. You will find it at t.me/mytradingbot_123_bot

Use this token to access the HTTP API:
1234567890:ABCdefGHIjklMNOpqrsTUVwxyz1234567890

Keep your token secure and store it safely, it can be used by anyone to control your bot.
```

**중요**: 발급받은 토큰을 안전하게 보관하세요!

### Step 3: Chat ID 획득

#### 방법 1: 봇과 대화 후 API로 확인

1. 생성한 봇에게 아무 메시지나 전송 (예: `/start`)
2. 브라우저에서 다음 URL 접속:
```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```

3. 응답에서 `chat.id` 확인:
```json
{
  "ok": true,
  "result": [
    {
      "update_id": 123456789,
      "message": {
        "message_id": 1,
        "from": {
          "id": 987654321,
          "is_bot": false,
          "first_name": "Your Name"
        },
        "chat": {
          "id": 987654321,  // <-- 이것이 Chat ID
          "first_name": "Your Name",
          "type": "private"
        }
      }
    }
  ]
}
```

#### 방법 2: 그룹 Chat ID 획득

1. 봇을 그룹에 추가
2. 그룹에서 봇에게 메시지 전송
3. 위의 API로 확인 (그룹 ID는 음수로 표시됨: `-1234567890`)

---

## 필요한 라이브러리

### 옵션 1: python-telegram-bot (권장)

**장점**: 
- 완전한 기능
- 비동기 지원
- 풍부한 문서

**설치**:
```bash
pip install python-telegram-bot==20.7
```

### 옵션 2: requests (간단한 알림만 필요한 경우)

**장점**:
- 가볍고 단순
- 추가 의존성 없음

**설치**:
```bash
pip install requests  # 이미 설치되어 있을 가능성 높음
```

---

## 코드 구현

### 1. 텔레그램 노티파이어 클래스 (Simple Version)

`001_python_code/lib/core/telegram_notifier.py`:

```python
"""
Telegram Notifier - Simple implementation using requests
"""

import os
import requests
from typing import Optional
from datetime import datetime


class TelegramNotifier:
    """
    Simple Telegram notification sender using requests library.
    
    Environment Variables Required:
        TELEGRAM_BOT_TOKEN: Bot token from BotFather
        TELEGRAM_CHAT_ID: Chat ID to send messages to
        TELEGRAM_NOTIFICATIONS_ENABLED: Enable/disable notifications (default: True)
    """
    
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED", "True").lower() == "true"
        
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        # Validate configuration
        if self.enabled and (not self.bot_token or not self.chat_id):
            print("⚠️  Telegram notifications enabled but credentials not found!")
            print("   Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env file")
            self.enabled = False
    
    def send_message(self, message: str, parse_mode: str = "Markdown") -> bool:
        """
        Send a message to Telegram.
        
        Args:
            message: Message text (supports Markdown or HTML)
            parse_mode: "Markdown" or "HTML" (default: Markdown)
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to send Telegram notification: {e}")
            return False
    
    def send_trade_alert(
        self,
        action: str,
        ticker: str,
        amount: float,
        price: float,
        success: bool,
        reason: str = "",
        order_id: str = ""
    ):
        """
        Send trading alert notification.
        
        Args:
            action: "BUY" or "SELL"
            ticker: Coin ticker (e.g., "BTC")
            amount: Trade amount
            price: Trade price
            success: Whether trade was successful
            reason: Additional reason/message
            order_id: Order ID if available
        """
        if not self.enabled:
            return
        
        # Emoji based on action and success
        if success:
            emoji = "🟢" if action == "BUY" else "🔴"
            status = "성공"
        else:
            emoji = "❌"
            status = "실패"
        
        # Format message
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        message = f"""
{emoji} *{action} {status}*

📊 코인: `{ticker}`
💰 수량: `{amount:.6f}`
💵 가격: `{price:,.0f} KRW`
💸 총액: `{amount * price:,.0f} KRW`

⏰ 시각: {timestamp}
"""
        
        if reason:
            message += f"📝 사유: {reason}\n"
        
        if order_id:
            message += f"🔖 주문ID: `{order_id}`\n"
        
        self.send_message(message)
    
    def send_error_alert(self, error_type: str, error_message: str, details: str = ""):
        """
        Send error alert notification.
        
        Args:
            error_type: Type of error
            error_message: Error message
            details: Additional details
        """
        if not self.enabled:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        message = f"""
⚠️ *에러 발생*

🔴 유형: {error_type}
📝 메시지: `{error_message}`

⏰ 시각: {timestamp}
"""
        
        if details:
            message += f"\n📋 상세:\n```\n{details}\n```"
        
        self.send_message(message)
    
    def send_bot_status(
        self,
        status: str,
        positions: int,
        max_positions: int,
        total_pnl: float = 0,
        coins: list = None
    ):
        """
        Send bot status notification.
        
        Args:
            status: Bot status (e.g., "STARTED", "STOPPED", "RUNNING")
            positions: Current number of positions
            max_positions: Maximum allowed positions
            total_pnl: Total profit/loss
            coins: List of monitored coins
        """
        if not self.enabled:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        status_emoji = {
            "STARTED": "🚀",
            "STOPPED": "🛑",
            "RUNNING": "✅",
            "ERROR": "❌"
        }.get(status, "ℹ️")
        
        message = f"""
{status_emoji} *봇 상태: {status}*

📊 포지션: {positions}/{max_positions}
💰 총 손익: `{total_pnl:+,.0f} KRW`

⏰ 시각: {timestamp}
"""
        
        if coins:
            message += f"🪙 모니터링 코인: {', '.join(coins)}\n"
        
        self.send_message(message)
    
    def send_daily_summary(self, summary_data: dict):
        """
        Send daily trading summary.
        
        Args:
            summary_data: Dictionary with summary information
        """
        if not self.enabled:
            return
        
        message = f"""
📈 *일일 거래 요약*

📅 날짜: {summary_data.get('date', 'N/A')}

🔵 매수 횟수: {summary_data.get('buy_count', 0)}
🔴 매도 횟수: {summary_data.get('sell_count', 0)}
💰 총 거래액: {summary_data.get('total_volume', 0):,.0f} KRW
💸 수수료: {summary_data.get('total_fees', 0):,.0f} KRW
📊 순손익: `{summary_data.get('net_pnl', 0):+,.0f} KRW`

✅ 성공: {summary_data.get('success_count', 0)}
❌ 실패: {summary_data.get('fail_count', 0)}
"""
        
        self.send_message(message)


# Singleton instance
_notifier_instance = None

def get_telegram_notifier() -> TelegramNotifier:
    """Get singleton instance of TelegramNotifier."""
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = TelegramNotifier()
    return _notifier_instance
```

---

### 2. 텔레그램 노티파이어 클래스 (Advanced Version)

비동기 처리가 필요한 경우 `python-telegram-bot` 사용:

`001_python_code/lib/core/telegram_notifier_async.py`:

```python
"""
Telegram Notifier - Advanced async implementation
"""

import os
import asyncio
from typing import Optional
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError


class TelegramNotifierAsync:
    """
    Asynchronous Telegram notification sender.
    
    Requires: python-telegram-bot>=20.0
    """
    
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED", "True").lower() == "true"
        
        if self.enabled and self.bot_token:
            self.bot = Bot(token=self.bot_token)
        else:
            self.bot = None
            if self.enabled:
                print("⚠️  Telegram bot token not configured")
    
    async def send_message_async(self, message: str, parse_mode: str = "Markdown") -> bool:
        """Send message asynchronously."""
        if not self.enabled or not self.bot:
            return False
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
            return True
        except TelegramError as e:
            print(f"❌ Telegram error: {e}")
            return False
    
    def send_message(self, message: str, parse_mode: str = "Markdown") -> bool:
        """Send message synchronously (creates new event loop)."""
        if not self.enabled or not self.bot:
            return False
        
        try:
            # Create new event loop for sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.send_message_async(message, parse_mode)
            )
            loop.close()
            return result
        except Exception as e:
            print(f"❌ Failed to send message: {e}")
            return False
    
    # Same trade_alert, error_alert methods as simple version...
```

---

## Trading Bot 통합

### 1. LiveExecutorV3에 통합

`001_python_code/ver3/live_executor_v3.py` 수정:

```python
from lib.core.telegram_notifier import get_telegram_notifier

class LiveExecutorV3:
    def __init__(self, ...):
        # ... existing code ...
        
        # Initialize Telegram notifier
        self.telegram = get_telegram_notifier()
        
        # Send bot started notification
        if self.telegram.enabled:
            self.telegram.send_bot_status(
                status="STARTED",
                positions=len(self.positions),
                max_positions=self.max_positions,
                coins=list(self.positions.keys())
            )
    
    def execute_trade(self, ticker: str, action: str, ...):
        """Execute trade with Telegram notifications."""
        
        try:
            # ... existing trade execution code ...
            
            # Send notification
            self.telegram.send_trade_alert(
                action=action,
                ticker=ticker,
                amount=rounded_units,
                price=price,
                success=True,
                reason=f"Score: {analysis.get('entry_score', 'N/A')}/4",
                order_id=response.get('order_id', 'DRY_RUN')
            )
            
        except Exception as e:
            # Send error notification
            self.telegram.send_error_alert(
                error_type="Trade Execution Error",
                error_message=str(e),
                details=f"Ticker: {ticker}, Action: {action}"
            )
            raise
```

### 2. TradingBotV3에 통합

`001_python_code/ver3/trading_bot_v3.py` 수정:

```python
from lib.core.telegram_notifier import get_telegram_notifier

class TradingBotV3:
    def __init__(self, config, log_prefix='ver3_cli'):
        # ... existing code ...
        
        # Initialize Telegram
        self.telegram = get_telegram_notifier()
    
    def run(self):
        """Run with startup notification."""
        
        # Send startup notification
        if self.telegram.enabled:
            self.telegram.send_bot_status(
                status="STARTED",
                positions=0,
                max_positions=self.portfolio_config.get('max_positions', 3),
                coins=self.coins
            )
        
        try:
            # ... existing run code ...
            
        except KeyboardInterrupt:
            # Send shutdown notification
            if self.telegram.enabled:
                self.telegram.send_bot_status(
                    status="STOPPED",
                    positions=len(self.portfolio_manager.executor.positions),
                    max_positions=self.portfolio_config.get('max_positions', 3)
                )
```

### 3. 에러 핸들러에 통합

`001_python_code/lib/core/logger.py` 수정:

```python
from lib.core.telegram_notifier import get_telegram_notifier

class TradingLogger:
    def __init__(self, log_dir="logs", log_prefix="trading"):
        # ... existing code ...
        
        self.telegram = get_telegram_notifier()
    
    def log_error(self, error_message: str, exception: Exception = None):
        """Log error with Telegram notification."""
        
        # Existing logging
        if exception:
            self.logger.error(f"[ERROR] {error_message}: {str(exception)}")
        else:
            self.logger.error(f"[ERROR] {error_message}")
        
        # Send Telegram notification for critical errors
        if self.telegram.enabled:
            self.telegram.send_error_alert(
                error_type="Trading Bot Error",
                error_message=error_message,
                details=str(exception) if exception else ""
            )
```

---

## 사용 예시

### 환경 변수 설정

`.env` 파일:
```bash
# Bithumb API
BITHUMB_CONNECT_KEY=your_key
BITHUMB_SECRET_KEY=your_secret

# Telegram Notifications
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321
TELEGRAM_NOTIFICATIONS_ENABLED=True
```

### 테스트 스크립트

`test_telegram.py`:
```python
#!/usr/bin/env python3
"""
Test Telegram notification
"""

import os
import sys
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent / "001_python_code"))

from lib.core.telegram_notifier import get_telegram_notifier

def test_notifications():
    """Test various notification types."""
    
    telegram = get_telegram_notifier()
    
    if not telegram.enabled:
        print("❌ Telegram notifications not enabled")
        print("   Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        return
    
    print("📱 Testing Telegram notifications...")
    
    # Test 1: Simple message
    print("\n1. Sending simple message...")
    telegram.send_message("🤖 Trading Bot Test Message")
    
    # Test 2: Trade alert
    print("2. Sending trade alert...")
    telegram.send_trade_alert(
        action="BUY",
        ticker="BTC",
        amount=0.001,
        price=50000000,
        success=True,
        reason="Test trade - Score: 4/4",
        order_id="TEST_12345"
    )
    
    # Test 3: Error alert
    print("3. Sending error alert...")
    telegram.send_error_alert(
        error_type="Connection Error",
        error_message="Failed to connect to API",
        details="This is a test error"
    )
    
    # Test 4: Bot status
    print("4. Sending bot status...")
    telegram.send_bot_status(
        status="RUNNING",
        positions=2,
        max_positions=3,
        total_pnl=50000,
        coins=["BTC", "ETH", "SOL"]
    )
    
    # Test 5: Daily summary
    print("5. Sending daily summary...")
    telegram.send_daily_summary({
        'date': '2025-12-09',
        'buy_count': 5,
        'sell_count': 3,
        'total_volume': 500000,
        'total_fees': 1250,
        'net_pnl': 25000,
        'success_count': 7,
        'fail_count': 1
    })
    
    print("\n✅ All test notifications sent!")
    print("   Check your Telegram app")

if __name__ == "__main__":
    test_notifications()
```

실행:
```bash
python test_telegram.py
```

---

## 문제 해결

### Q1: "Unauthorized" 에러

**원인**: Bot token이 잘못됨

**해결**:
1. BotFather에서 토큰 재확인
2. `.env` 파일의 `TELEGRAM_BOT_TOKEN` 확인
3. 공백이나 특수문자 확인

### Q2: "Chat not found" 에러

**원인**: Chat ID가 잘못되었거나 봇이 차단됨

**해결**:
1. 봇에게 `/start` 메시지 전송
2. `getUpdates` API로 Chat ID 재확인
3. 봇이 그룹에 추가되어 있는지 확인

### Q3: 메시지가 오지 않음

**체크리스트**:
- [ ] `.env` 파일이 프로젝트 루트에 있는가?
- [ ] `TELEGRAM_NOTIFICATIONS_ENABLED=True`로 설정되어 있는가?
- [ ] 봇이 차단되지 않았는가?
- [ ] 방화벽/네트워크 문제는 없는가?

**디버깅**:
```python
telegram = get_telegram_notifier()
print(f"Enabled: {telegram.enabled}")
print(f"Token: {telegram.bot_token[:10]}..." if telegram.bot_token else "None")
print(f"Chat ID: {telegram.chat_id}")
```

### Q4: Rate Limit 에러

**원인**: 너무 많은 메시지를 빠르게 전송

**해결**:
- 중요한 알림만 전송하도록 필터링
- 메시지 통합 (여러 이벤트를 하나의 메시지로)
- 알림 간격 조절

---

## 요약

### 설치 단계
1. ✅ BotFather에서 봇 생성 및 토큰 발급
2. ✅ Chat ID 획득
3. ✅ `.env` 파일에 설정 추가
4. ✅ `telegram_notifier.py` 파일 생성
5. ✅ Trading bot 코드에 통합
6. ✅ 테스트 실행

### 알림 종류
- 🟢 매수 성공/실패
- 🔴 매도 성공/실패  
- ⚠️ 에러 발생
- ✅ 봇 시작/중지
- 📊 일일 거래 요약

### 다음 단계
1. `requirements.txt`에 `requests` 추가 (또는 `python-telegram-bot`)
2. `.env.example` 업데이트
3. 실제 봇에 통합
4. 프로덕션 테스트

**Happy Trading! 🚀**
