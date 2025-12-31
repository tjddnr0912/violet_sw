# 빗썸(Bithumb) API 레퍼런스

## 개요

빗썸 API는 암호화폐 거래 및 시장 데이터 조회를 위한 RESTful API를 제공합니다.
- 공식 문서: https://apidocs.bithumb.com/
- 지원 버전: v1.2.0, v2.1.0, v2.1.5

---

## 1. Public API (인증 불필요)

### 1.1 현재가 정보 조회 (Ticker)

```
GET https://api.bithumb.com/public/ticker/{order_currency}_{payment_currency}
```

**응답 필드:**
| 필드 | 타입 | 설명 |
|------|------|------|
| opening_price | String | 시가 (00시 기준) |
| closing_price | String | 종가 (현재가) |
| min_price | String | 저가 (00시 기준) |
| max_price | String | 고가 (00시 기준) |
| units_traded | String | 거래량 (00시 기준) |
| acc_trade_value | String | 거래금액 (00시 기준) |
| prev_closing_price | String | 전일종가 |
| units_traded_24H | String | 최근 24시간 거래량 |
| acc_trade_value_24H | String | 최근 24시간 거래금액 |
| fluctate_24H | String | 최근 24시간 변동가 |
| fluctate_rate_24H | String | 최근 24시간 변동률 |

**예시:**
```python
import requests
response = requests.get("https://api.bithumb.com/public/ticker/BTC_KRW")
data = response.json()
print(data['data']['closing_price'])  # 현재 비트코인 가격
```

---

### 1.2 호가 정보 조회 (Orderbook)

```
GET https://api.bithumb.com/public/orderbook/{order_currency}_{payment_currency}
```

**응답 필드:**
| 필드 | 타입 | 설명 |
|------|------|------|
| timestamp | Number | 호가 생성 시각 (Unix timestamp) |
| order_currency | String | 주문 통화 |
| payment_currency | String | 결제 통화 |
| bids | Array | 매수 호가 리스트 |
| asks | Array | 매도 호가 리스트 |
| total_ask_size | String | 매도 총 잔량 |
| total_bid_size | String | 매수 총 잔량 |

**호가 유닛 구조:**
```json
{
  "quantity": "0.5",      // 주문 수량
  "price": "50000000"     // 주문 가격
}
```

- 단일 마켓 조회 시 최대 30호가 제공
- 멀티 마켓 조회 시 15호가 제공

---

### 1.3 캔들스틱 조회 (Candlestick/OHLCV)

```
GET https://api.bithumb.com/public/candlestick/{order_currency}_{payment_currency}/{chart_intervals}
```

**chart_intervals 옵션:**
| 값 | 설명 |
|----|------|
| 1m | 1분봉 |
| 3m | 3분봉 |
| 5m | 5분봉 |
| 10m | 10분봉 |
| 30m | 30분봉 |
| 1h | 1시간봉 |
| 6h | 6시간봉 |
| 12h | 12시간봉 |
| 24h | 24시간봉 (일봉) |

**응답 데이터 구조:**
```json
[
  [
    1625097600000,    // timestamp (ms)
    "35000000",       // open (시가)
    "35500000",       // close (종가)
    "36000000",       // high (고가)
    "34500000",       // low (저가)
    "123.45"          // volume (거래량)
  ]
]
```

**예시:**
```python
import pandas as pd
import requests

url = "https://api.bithumb.com/public/candlestick/BTC_KRW/1h"
response = requests.get(url)
data = response.json()

df = pd.DataFrame(data['data'],
                  columns=['time', 'open', 'close', 'high', 'low', 'volume'])
df['time'] = pd.to_datetime(df['time'], unit='ms')
```

---

### 1.4 체결 내역 조회 (Transaction History)

```
GET https://api.bithumb.com/public/transaction_history/{order_currency}_{payment_currency}
```

**응답 필드:**
| 필드 | 타입 | 설명 |
|------|------|------|
| transaction_date | String | 거래 체결 시각 |
| type | String | 거래 유형 (bid: 매수, ask: 매도) |
| units_traded | String | 거래 수량 |
| price | String | 거래 가격 |
| total | String | 거래 금액 |

---

### 1.5 마켓 코드 조회

```
GET https://api.bithumb.com/public/assetsstatus/ALL
```

지원되는 모든 코인 목록과 상태를 조회합니다.

---

## 2. Private API (인증 필요)

### 인증 방식

Private API는 API Key와 Secret Key를 사용한 HMAC-SHA512 서명이 필요합니다.

**헤더 구성:**
```
Api-Key: {Connect Key}
Api-Sign: {Signature (Base64 encoded HMAC-SHA512)}
Api-Nonce: {Timestamp in milliseconds}
```

**서명 생성 방법:**
```python
import hmac
import hashlib
import base64
import time
import urllib.parse

endpoint = "/info/balance"
nonce = str(int(time.time() * 1000))
params = {"endpoint": endpoint, "currency": "BTC"}

query_string = urllib.parse.urlencode(params)
message = endpoint + chr(0) + query_string + chr(0) + nonce

signature = hmac.new(
    secret_key.encode('utf-8'),
    message.encode('utf-8'),
    hashlib.sha512
)
signature = base64.b64encode(signature.hexdigest().encode('utf-8'))
```

---

### 2.1 잔고 조회

```
POST https://api.bithumb.com/info/balance
```

**파라미터:**
| 필드 | 필수 | 설명 |
|------|------|------|
| currency | O | 통화 코드 (예: BTC, ALL) |

**응답:**
```json
{
  "status": "0000",
  "data": {
    "total_btc": "1.5",
    "available_btc": "1.0",
    "total_krw": "10000000",
    "available_krw": "8000000"
  }
}
```

---

### 2.2 시장가 매수

```
POST https://api.bithumb.com/trade/market_buy
```

**파라미터:**
| 필드 | 필수 | 설명 |
|------|------|------|
| order_currency | O | 주문 통화 (예: BTC) |
| payment_currency | O | 결제 통화 (예: KRW) |
| units | O | 매수 금액 (KRW 단위) |

---

### 2.3 시장가 매도

```
POST https://api.bithumb.com/trade/market_sell
```

**파라미터:**
| 필드 | 필수 | 설명 |
|------|------|------|
| order_currency | O | 주문 통화 (예: BTC) |
| payment_currency | O | 결제 통화 (예: KRW) |
| units | O | 매도 수량 (코인 수량) |

---

### 2.4 지정가 주문

```
POST https://api.bithumb.com/trade/place
```

**파라미터:**
| 필드 | 필수 | 설명 |
|------|------|------|
| order_currency | O | 주문 통화 |
| payment_currency | O | 결제 통화 |
| units | O | 주문 수량 |
| price | O | 주문 가격 |
| type | O | 주문 유형 (bid: 매수, ask: 매도) |

---

### 2.5 미체결 주문 조회

```
POST https://api.bithumb.com/info/orders
```

---

### 2.6 거래 내역 조회

```
POST https://api.bithumb.com/info/user_transactions
```

---

## 3. WebSocket API (실시간 데이터)

빗썸은 WebSocket을 통해 실시간 데이터를 제공합니다.

**연결 URL:** `wss://pubwss.bithumb.com/pub/ws`

**구독 가능 채널:**
| 채널 | 설명 |
|------|------|
| ticker | 실시간 현재가 |
| orderbook | 실시간 호가 |
| transaction | 실시간 체결 |

**구독 메시지 형식:**
```json
{
  "type": "ticker",
  "symbols": ["BTC_KRW", "ETH_KRW"],
  "tickTypes": ["30M", "1H", "12H", "24H", "MID"]
}
```

---

## 4. 퀀트 매매에 활용 가능한 데이터

### 4.1 기술적 분석 데이터
- **OHLCV 캔들스틱**: 다양한 시간대의 가격/거래량 데이터
- **호가 데이터**: 매수/매도 압력 분석, 유동성 측정
- **체결 내역**: 거래 추세, 대량 거래 감지

### 4.2 퀀트 지표 계산 가능
| 지표 | 필요 데이터 | API |
|------|-------------|-----|
| 이동평균 (MA) | 종가 | Candlestick |
| RSI | 종가 | Candlestick |
| MACD | 종가 | Candlestick |
| 볼린저 밴드 | 종가 | Candlestick |
| ATR | 고가/저가/종가 | Candlestick |
| 거래량 분석 | 거래량 | Candlestick |
| 호가 불균형 | 호가 | Orderbook |
| VWAP | 가격/거래량 | Transaction |

### 4.3 제약사항
- **온체인 데이터 미제공**: 블록체인 네트워크 데이터는 별도 소스 필요
- **펀딩비 미제공**: 선물 거래 관련 데이터 없음
- **API 호출 제한**: 초당 요청 수 제한 있음

---

## 5. 참고 자료

- [빗썸 공식 API 문서](https://apidocs.bithumb.com/)
- [pybithumb 라이브러리](https://github.com/sharebook-kr/pybithumb)
- [API 이용안내](https://apidocs.bithumb.com/docs/api-소개)
