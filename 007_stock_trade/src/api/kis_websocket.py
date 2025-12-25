"""
한국투자증권 실시간 시세 WebSocket 클라이언트
- 주식 체결가 실시간 수신
- 주식 호가 실시간 수신
- 체결 통보 수신
"""

import json
import websocket
import threading
from typing import Callable, Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime

from .kis_auth import get_auth


@dataclass
class RealtimePrice:
    """실시간 체결가 정보"""
    code: str           # 종목코드
    time: str           # 체결시간 (HHMMSS)
    price: int          # 체결가
    change: int         # 전일대비
    change_rate: float  # 등락률
    volume: int         # 체결수량
    cum_volume: int     # 누적거래량


@dataclass
class RealtimeOrderbook:
    """실시간 호가 정보"""
    code: str           # 종목코드
    time: str           # 호가시간
    ask_prices: List[int]   # 매도호가 (1~10차)
    ask_volumes: List[int]  # 매도호가잔량
    bid_prices: List[int]   # 매수호가 (1~10차)
    bid_volumes: List[int]  # 매수호가잔량


class KISWebSocket:
    """한국투자증권 실시간 시세 WebSocket 클라이언트"""

    # WebSocket 도메인
    WS_DOMAIN_REAL = "ws://ops.koreainvestment.com:21000"  # 실전투자
    WS_DOMAIN_VIRTUAL = "ws://ops.koreainvestment.com:31000"  # 모의투자

    # TR ID
    TR_PRICE = "H0STCNT0"      # 실시간 체결가
    TR_ORDERBOOK = "H0STASP0"  # 실시간 호가
    TR_NOTICE_REAL = "H0STCNI0"   # 체결통보 (실전)
    TR_NOTICE_VIRTUAL = "H0STCNI9"  # 체결통보 (모의)

    def __init__(self, is_virtual: bool = True):
        """
        Args:
            is_virtual: True=모의투자, False=실전투자
        """
        self.is_virtual = is_virtual
        self.auth = get_auth(is_virtual)
        self.ws_url = self.WS_DOMAIN_VIRTUAL if is_virtual else self.WS_DOMAIN_REAL

        # WebSocket 객체
        self.ws: Optional[websocket.WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.is_connected = False

        # 콜백 함수
        self._on_price: Optional[Callable[[RealtimePrice], None]] = None
        self._on_orderbook: Optional[Callable[[RealtimeOrderbook], None]] = None
        self._on_notice: Optional[Callable[[dict], None]] = None
        self._on_error: Optional[Callable[[Exception], None]] = None

        # 구독 중인 종목
        self._subscribed_prices: set = set()
        self._subscribed_orderbooks: set = set()

        # 승인키 (WebSocket 인증용)
        self._approval_key: Optional[str] = None

    def _get_approval_key(self) -> str:
        """WebSocket 접속용 승인키 발급"""
        if self._approval_key:
            return self._approval_key

        import requests

        url = f"{self.auth.base_url}/oauth2/Approval"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.auth.app_key,
            "secretkey": self.auth.app_secret
        }

        response = requests.post(url, headers=headers, json=body)
        response.raise_for_status()

        data = response.json()
        self._approval_key = data.get("approval_key")
        return self._approval_key

    def connect(
        self,
        on_price: Optional[Callable[[RealtimePrice], None]] = None,
        on_orderbook: Optional[Callable[[RealtimeOrderbook], None]] = None,
        on_notice: Optional[Callable[[dict], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        """
        WebSocket 연결 시작

        Args:
            on_price: 체결가 수신 콜백
            on_orderbook: 호가 수신 콜백
            on_notice: 체결통보 수신 콜백
            on_error: 에러 발생 콜백
        """
        self._on_price = on_price
        self._on_orderbook = on_orderbook
        self._on_notice = on_notice
        self._on_error = on_error

        # 승인키 발급
        approval_key = self._get_approval_key()

        # WebSocket 연결
        self.ws = websocket.WebSocketApp(
            f"{self.ws_url}/tryitout/H0STCNT0",
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_ws_error,
            on_close=self._on_close
        )

        # 별도 스레드에서 실행
        self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.ws_thread.start()

    def disconnect(self):
        """WebSocket 연결 종료"""
        if self.ws:
            self.ws.close()
            self.is_connected = False

    def subscribe_price(self, stock_code: str):
        """
        실시간 체결가 구독

        Args:
            stock_code: 종목코드
        """
        if not self.is_connected:
            raise ConnectionError("WebSocket이 연결되지 않았습니다.")

        if stock_code in self._subscribed_prices:
            return

        self._send_subscribe(self.TR_PRICE, stock_code)
        self._subscribed_prices.add(stock_code)

    def unsubscribe_price(self, stock_code: str):
        """
        실시간 체결가 구독 해제

        Args:
            stock_code: 종목코드
        """
        if stock_code not in self._subscribed_prices:
            return

        self._send_unsubscribe(self.TR_PRICE, stock_code)
        self._subscribed_prices.discard(stock_code)

    def subscribe_orderbook(self, stock_code: str):
        """
        실시간 호가 구독

        Args:
            stock_code: 종목코드
        """
        if not self.is_connected:
            raise ConnectionError("WebSocket이 연결되지 않았습니다.")

        if stock_code in self._subscribed_orderbooks:
            return

        self._send_subscribe(self.TR_ORDERBOOK, stock_code)
        self._subscribed_orderbooks.add(stock_code)

    def unsubscribe_orderbook(self, stock_code: str):
        """
        실시간 호가 구독 해제

        Args:
            stock_code: 종목코드
        """
        if stock_code not in self._subscribed_orderbooks:
            return

        self._send_unsubscribe(self.TR_ORDERBOOK, stock_code)
        self._subscribed_orderbooks.discard(stock_code)

    def subscribe_notice(self):
        """체결통보 구독 (주문 체결 알림)"""
        if not self.is_connected:
            raise ConnectionError("WebSocket이 연결되지 않았습니다.")

        tr_id = self.TR_NOTICE_VIRTUAL if self.is_virtual else self.TR_NOTICE_REAL
        acct_no, _ = self.auth.get_account_info()
        self._send_subscribe(tr_id, acct_no)

    def _send_subscribe(self, tr_id: str, tr_key: str):
        """구독 요청 전송"""
        msg = {
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": "1",  # 1: 등록
                "content-type": "utf-8"
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": tr_key
                }
            }
        }
        self.ws.send(json.dumps(msg))

    def _send_unsubscribe(self, tr_id: str, tr_key: str):
        """구독 해제 요청 전송"""
        msg = {
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": "2",  # 2: 해제
                "content-type": "utf-8"
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": tr_key
                }
            }
        }
        self.ws.send(json.dumps(msg))

    def _on_open(self, ws):
        """WebSocket 연결 완료"""
        self.is_connected = True
        print(f"[KISWebSocket] 연결됨 ({datetime.now().strftime('%H:%M:%S')})")

    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket 연결 종료"""
        self.is_connected = False
        print(f"[KISWebSocket] 연결 종료 (code={close_status_code})")

    def _on_ws_error(self, ws, error):
        """WebSocket 에러 발생"""
        if self._on_error:
            self._on_error(error)
        else:
            print(f"[KISWebSocket] 에러: {error}")

    def _on_message(self, ws, message: str):
        """WebSocket 메시지 수신"""
        try:
            # 구분자로 분리된 데이터인 경우
            if message.startswith("0|") or message.startswith("1|"):
                self._parse_realtime_data(message)
            else:
                # JSON 형식 응답 (구독 확인 등)
                data = json.loads(message)
                header = data.get("header", {})
                if header.get("tr_id") == "PINGPONG":
                    # PING-PONG 응답
                    self.ws.send(message)
        except Exception as e:
            if self._on_error:
                self._on_error(e)

    def _parse_realtime_data(self, message: str):
        """실시간 데이터 파싱"""
        parts = message.split("|")
        if len(parts) < 4:
            return

        encrypt_flag = parts[0]  # 0: 평문, 1: 암호화
        tr_id = parts[1]
        data_cnt = parts[2]
        data = parts[3]

        if tr_id == self.TR_PRICE:
            self._parse_price(data)
        elif tr_id == self.TR_ORDERBOOK:
            self._parse_orderbook(data)
        elif tr_id in (self.TR_NOTICE_REAL, self.TR_NOTICE_VIRTUAL):
            self._parse_notice(data)

    def _parse_price(self, data: str):
        """체결가 데이터 파싱"""
        if not self._on_price:
            return

        fields = data.split("^")
        if len(fields) < 20:
            return

        try:
            price = RealtimePrice(
                code=fields[0],                    # 종목코드
                time=fields[1],                    # 체결시간
                price=int(fields[2]),              # 체결가
                change=int(fields[4]),             # 전일대비
                change_rate=float(fields[5]),      # 등락률
                volume=int(fields[12]),            # 체결수량
                cum_volume=int(fields[13])         # 누적거래량
            )
            self._on_price(price)
        except (ValueError, IndexError) as e:
            if self._on_error:
                self._on_error(e)

    def _parse_orderbook(self, data: str):
        """호가 데이터 파싱"""
        if not self._on_orderbook:
            return

        fields = data.split("^")
        if len(fields) < 50:
            return

        try:
            # 매도호가 1~10차
            ask_prices = [int(fields[3 + i * 4]) for i in range(10)]
            ask_volumes = [int(fields[4 + i * 4]) for i in range(10)]

            # 매수호가 1~10차
            bid_prices = [int(fields[5 + i * 4]) for i in range(10)]
            bid_volumes = [int(fields[6 + i * 4]) for i in range(10)]

            orderbook = RealtimeOrderbook(
                code=fields[0],
                time=fields[1],
                ask_prices=ask_prices,
                ask_volumes=ask_volumes,
                bid_prices=bid_prices,
                bid_volumes=bid_volumes
            )
            self._on_orderbook(orderbook)
        except (ValueError, IndexError) as e:
            if self._on_error:
                self._on_error(e)

    def _parse_notice(self, data: str):
        """체결통보 데이터 파싱"""
        if not self._on_notice:
            return

        fields = data.split("^")
        if len(fields) < 20:
            return

        try:
            notice = {
                "order_no": fields[1],         # 주문번호
                "code": fields[2],             # 종목코드
                "side": "매수" if fields[4] == "02" else "매도",
                "order_qty": int(fields[6]),   # 주문수량
                "order_price": int(fields[7]), # 주문가격
                "filled_qty": int(fields[8]),  # 체결수량
                "filled_price": int(fields[9]), # 체결가격
                "time": fields[10]             # 체결시간
            }
            self._on_notice(notice)
        except (ValueError, IndexError) as e:
            if self._on_error:
                self._on_error(e)
