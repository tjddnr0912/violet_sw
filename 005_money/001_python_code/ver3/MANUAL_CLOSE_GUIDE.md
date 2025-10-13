# Manual Close Position 사용 가이드

## 📋 개요

`manual_close_position.py`는 Ver3 포지션을 수동으로 청산하는 스크립트입니다.

## ✅ 업데이트 내용 (2025-10-13)

- ✅ Transaction History (JSON + Markdown) 자동 기록
- ✅ P&L 계산 및 기록
- ✅ 프로그램 동작 중에도 안전하게 사용 가능 (단, 주의사항 참조)

## 🚀 사용 방법

**⚠️ 중요**: 반드시 프로젝트 루트 디렉토리에서 실행하세요!

### 방법 A: 래퍼 스크립트 사용 (권장 ⭐)

```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money

# 인터랙티브 모드
./close_positions.sh

# 특정 코인 청산
./close_positions.sh SOL

# 전체 청산
./close_positions.sh --all
```

### 방법 B: 가상환경 직접 활성화

```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money
source .venv/bin/activate
python 001_python_code/ver3/manual_close_position.py
```

---

### 1. 인터랙티브 모드 (추천)

```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money
./close_positions.sh
```

**화면 표시**:
```
================================================================================
CURRENT POSITIONS
================================================================================

BTC
  Entry Price:     169,522,000 KRW
  Current Price:   172,000,000 KRW
  Size:           0.00010000 BTC
  Position:                100%
  Entry Count:                1 times
  P&L:                    +1.46%

================================================================================

Select action:
  1. Close specific coin
  2. Close all positions
  3. Exit
```

### 2. 특정 코인만 청산

```bash
./close_positions.sh SOL
```

**예시**:
```bash
# SOL 포지션만 청산
./close_positions.sh SOL

# BTC 포지션만 청산
./close_positions.sh BTC

# ETH 포지션만 청산
./close_positions.sh ETH
```

### 3. 전체 포지션 청산 (계좌 전체 청산)

```bash
./close_positions.sh --all
```

**확인 프롬프트**:
```
⚠️  About to close ALL 3 positions:
   - BTC
   - ETH
   - SOL
   Mode: DRY-RUN

Confirm close all positions? (yes/no):
```

## ⚙️ DRY-RUN vs LIVE 모드

**모드 확인**:
```bash
# config_v3.py 또는 user_preferences_v3.json에서 설정됨
EXECUTION_CONFIG['dry_run'] = True   # DRY-RUN (안전)
EXECUTION_CONFIG['dry_run'] = False  # LIVE (실제 거래)
```

**DRY-RUN 모드**:
- ✅ 실제 거래 없음
- ✅ 로그에만 기록
- ✅ positions_v3.json 업데이트
- ✅ Transaction history 기록 (시뮬레이션)

**LIVE 모드**:
- 🔴 실제 Bithumb API 호출
- 🔴 실제 매도 주문 체결
- ✅ 모든 기록 업데이트

## 📊 Transaction History 기록

수동 청산 시 다음 정보가 자동으로 기록됩니다:

### JSON 기록 (`logs/transaction_history.json`):
```json
{
  "timestamp": "2025-10-13T12:34:56",
  "ticker": "BTC",
  "action": "SELL",
  "amount": 0.0001,
  "price": 172000000,
  "total_value": 17200,
  "fee": 8.6,
  "order_id": "MANUAL_2025-10-13_12:34:56",
  "success": true,
  "pnl": 1478.0
}
```

### Markdown 기록 (`logs/trading_history.md`):
```markdown
| 2025-10-13 | 12:34:56 | BTC | 🔴 매도 | 0.0001 | 172,000,000원 | 17,200원 | 9원 | +1,478원 | +9.40% | ✅ 성공 (Manual close) |
```

## ⚠️ 프로그램 동작 중 실행 시 주의사항

### 안전한 경우 ✅

**DRY-RUN 모드**:
- 프로그램과 독립적으로 작동
- positions_v3.json 파일 기반으로 동작
- 파일 잠금 없음 (read-only 접근)

**LIVE 모드 - 권장하지 않지만 가능**:
- 프로그램이 **대기 상태**(15분 사이클 중간)일 때는 안전
- 파일은 즉시 업데이트되어 다음 사이클에 반영됨

### 위험한 경우 ❌

**LIVE 모드 + 프로그램이 활발히 거래 중**:
- 프로그램이 동시에 같은 코인 거래 시도 가능
- Race condition 발생 가능
- **권장: 봇 중지 후 실행**

### 권장 사용 시나리오

#### 시나리오 1: 긴급 청산 (프로그램 실행 중)
```bash
# 1. 특정 코인만 긴급 청산 (예: 뉴스로 인한 급락)
cd /Users/seongwookjang/project/git/violet_sw/005_money
./close_positions.sh SOL

# 2. 프로그램은 다음 사이클(최대 15분 후)에 자동으로 동기화됨
```

#### 시나리오 2: 전체 청산 (안전)
```bash
# 1. GUI에서 봇 중지 (Stop 버튼)
# 2. 수동 청산 실행
cd /Users/seongwookjang/project/git/violet_sw/005_money
./close_positions.sh --all

# 3. 청산 완료 확인 후 봇 재시작
```

#### 시나리오 3: 코인 목록 변경 전 청산
```bash
# 1. 봇 중지
# 2. 기존 포지션 모두 청산
cd /Users/seongwookjang/project/git/violet_sw/005_money
./close_positions.sh --all

# 3. GUI에서 코인 선택 변경 (BTC, ETH, SOL → ADA, DOT, LINK)
# 4. 봇 재시작
```

## 🔒 파일 동기화

수동 청산 시 다음 파일이 업데이트됩니다:

1. **positions_v3.json** - 포지션 제거
2. **transaction_history.json** - 거래 기록 추가
3. **trading_history.md** - 거래 내역 추가 (append)

프로그램 재시작 시 자동으로 모든 파일 동기화됨.

## 📝 예제

### 예제 1: SOL 수동 청산

```bash
$ cd /Users/seongwookjang/project/git/violet_sw/005_money
$ ./close_positions.sh SOL

================================================================================
CURRENT POSITIONS
================================================================================

SOL
  Entry Price:         279,100 KRW
  Current Price:       285,000 KRW
  Size:           0.17914726 SOL
  Position:                100%
  Entry Count:                1 times
  P&L:                    +2.11%

================================================================================

⚠️  About to close position:
   Coin: SOL
   Size: 0.17914726
   Entry: 279,100 KRW
   Current: 285,000 KRW
   P&L: +2.11%
   Mode: DRY-RUN

Confirm close SOL? (yes/no): yes

✅ Successfully closed SOL position
```

### 예제 2: 전체 잔액 청산

```bash
$ cd /Users/seongwookjang/project/git/violet_sw/005_money
$ ./close_positions.sh --all

⚠️  About to close ALL 3 positions:
   - BTC
   - ETH
   - SOL
   Mode: LIVE

Confirm close all positions? (yes/no): yes

Closing BTC...
✅ Successfully closed BTC position

Closing ETH...
✅ Successfully closed ETH position

Closing SOL...
✅ Successfully closed SOL position

✅ Closed 3/3 positions
```

## 🆘 문제 해결

### 문제 1: "ModuleNotFoundError: No module named 'requests'"
**원인**: 가상환경이 활성화되지 않음
**해결**:
```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money
./close_positions.sh  # 래퍼 스크립트 사용 (자동으로 가상환경 활성화)
```

### 문제 2: "No position found"
**원인**: positions_v3.json에 포지션 없음
**해결**: GUI에서 실제 포지션 확인

### 문제 3: 프로그램과 불일치
**원인**: 프로그램 실행 중 수동 청산으로 동기화 안됨
**해결**: 봇 재시작 또는 다음 사이클(15분) 대기

### 문제 4: "Could not fetch current price"
**원인**: API 연결 문제
**해결**: 인터넷 연결 확인 후 재시도

## 💡 팁

1. **긴급 상황**: 특정 코인만 빠르게 청산 후 프로그램이 자동 동기화
2. **안전 우선**: 전체 청산 시 봇 중지 후 실행
3. **확인**: Transaction History 탭에서 청산 기록 확인
4. **P&L 확인**: 청산 전 화면에 표시되는 P&L 확인

## 📞 지원

문제 발생 시:
1. `logs/trading_YYYYMMDD.log` 확인
2. `logs/transaction_history.json` 확인
3. GUI Transaction History 탭 확인
