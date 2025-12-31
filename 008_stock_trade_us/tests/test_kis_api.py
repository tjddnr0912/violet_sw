"""
한국투자증권 API 테스트 모듈
- 각 기능을 개별적으로 테스트
- 실제 API 호출 없이 구조만 검증 (Mock 사용)
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.kis_auth import KISAuth, get_auth
from src.api.kis_client import KISClient, StockPrice, OrderResult, StockBalance


class TestKISAuth:
    """KISAuth 클래스 테스트"""

    def test_init_virtual(self):
        """모의투자 환경 초기화 테스트"""
        with patch.dict('os.environ', {
            'KIS_APP_KEY': 'test_key',
            'KIS_APP_SECRET': 'test_secret',
            'KIS_ACCOUNT_NO': '12345678-01'
        }):
            auth = KISAuth(is_virtual=True)
            assert auth.is_virtual is True
            assert auth.base_url == KISAuth.DOMAIN_VIRTUAL

    def test_init_real(self):
        """실전투자 환경 초기화 테스트"""
        with patch.dict('os.environ', {
            'KIS_APP_KEY': 'test_key',
            'KIS_APP_SECRET': 'test_secret',
            'KIS_ACCOUNT_NO': '12345678-01'
        }):
            auth = KISAuth(is_virtual=False)
            assert auth.is_virtual is False
            assert auth.base_url == KISAuth.DOMAIN_REAL

    def test_validate_credentials_missing_key(self):
        """API 키 누락 검증 테스트"""
        with patch.dict('os.environ', {}, clear=True):
            auth = KISAuth(is_virtual=True)
            assert auth.validate_credentials() is False

    def test_get_account_info(self):
        """계좌정보 파싱 테스트"""
        with patch.dict('os.environ', {
            'KIS_APP_KEY': 'test_key',
            'KIS_APP_SECRET': 'test_secret',
            'KIS_ACCOUNT_NO': '12345678-01'
        }):
            auth = KISAuth(is_virtual=True)
            acct_no, suffix = auth.get_account_info()
            assert acct_no == '12345678'
            assert suffix == '01'

    def test_get_headers(self):
        """API 헤더 생성 테스트"""
        with patch.dict('os.environ', {
            'KIS_APP_KEY': 'test_key',
            'KIS_APP_SECRET': 'test_secret',
            'KIS_ACCOUNT_NO': '12345678-01'
        }):
            auth = KISAuth(is_virtual=True)
            # Mock token to avoid API call
            auth.access_token = "test_token"
            auth.token_expires_at = datetime.now() + timedelta(hours=23)

            headers = auth.get_headers("FHKST01010100")

            assert headers["appkey"] == "test_key"
            assert headers["appsecret"] == "test_secret"
            assert headers["tr_id"] == "FHKST01010100"
            assert "Bearer test_token" in headers["authorization"]


class TestKISClient:
    """KISClient 클래스 테스트"""

    @pytest.fixture
    def mock_client(self):
        """테스트용 Mock 클라이언트 생성"""
        with patch.dict('os.environ', {
            'KIS_APP_KEY': 'test_key',
            'KIS_APP_SECRET': 'test_secret',
            'KIS_ACCOUNT_NO': '12345678-01'
        }):
            # 싱글톤 초기화
            import src.api.kis_auth as auth_module
            auth_module._auth_instance = None

            client = KISClient(is_virtual=True)
            # Mock token to avoid API call
            client.auth.access_token = "test_token"
            client.auth.token_expires_at = datetime.now() + timedelta(hours=23)
            return client

    def test_client_init(self, mock_client):
        """클라이언트 초기화 테스트"""
        assert mock_client.is_virtual is True
        assert mock_client.auth is not None

    @patch('src.api.kis_client.requests.get')
    def test_get_stock_price(self, mock_get, mock_client):
        """현재가 조회 테스트"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "output": {
                "hts_kor_isnm": "삼성전자",
                "stck_prpr": "71000",
                "prdy_vrss": "1000",
                "prdy_ctrt": "1.43",
                "acml_vol": "10000000",
                "stck_hgpr": "72000",
                "stck_lwpr": "70000",
                "stck_oprc": "70500"
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = mock_client.get_stock_price("005930")

        assert isinstance(result, StockPrice)
        assert result.code == "005930"
        assert result.name == "삼성전자"
        assert result.price == 71000

    @patch('src.api.kis_client.requests.post')
    def test_buy_stock(self, mock_post, mock_client):
        """매수 주문 테스트"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "msg1": "정상처리",
            "output": {
                "ODNO": "0000123456"
            }
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = mock_client.buy_stock("005930", qty=10, price=70000)

        assert isinstance(result, OrderResult)
        assert result.success is True
        assert result.order_no == "0000123456"

    @patch('src.api.kis_client.requests.post')
    def test_sell_stock(self, mock_post, mock_client):
        """매도 주문 테스트"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "rt_cd": "0",
            "msg1": "정상처리",
            "output": {
                "ODNO": "0000123457"
            }
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = mock_client.sell_stock("005930", qty=10, price=72000)

        assert isinstance(result, OrderResult)
        assert result.success is True

    @patch('src.api.kis_client.requests.get')
    def test_get_balance(self, mock_get, mock_client):
        """잔고 조회 테스트"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "output1": [
                {
                    "pdno": "005930",
                    "prdt_name": "삼성전자",
                    "hldg_qty": "100",
                    "pchs_avg_pric": "70000",
                    "prpr": "71000",
                    "evlu_pfls_amt": "100000",
                    "evlu_pfls_rt": "1.43"
                }
            ],
            "output2": [
                {
                    "tot_evlu_amt": "7100000",
                    "evlu_pfls_smtl_amt": "100000",
                    "dnca_tot_amt": "1000000",
                    "pchs_amt_smtl_amt": "7000000"
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = mock_client.get_balance()

        assert "stocks" in result
        assert len(result["stocks"]) == 1
        assert result["stocks"][0].code == "005930"
        assert result["total_eval"] == 7100000


class TestDataClasses:
    """데이터 클래스 테스트"""

    def test_stock_price(self):
        """StockPrice 데이터클래스 테스트"""
        price = StockPrice(
            code="005930",
            name="삼성전자",
            price=71000,
            change=1000,
            change_rate=1.43,
            volume=10000000,
            high=72000,
            low=70000,
            open=70500
        )
        assert price.code == "005930"
        assert price.price == 71000

    def test_order_result(self):
        """OrderResult 데이터클래스 테스트"""
        result = OrderResult(
            success=True,
            order_no="0000123456",
            message="정상처리"
        )
        assert result.success is True
        assert result.order_no == "0000123456"

    def test_stock_balance(self):
        """StockBalance 데이터클래스 테스트"""
        balance = StockBalance(
            code="005930",
            name="삼성전자",
            qty=100,
            avg_price=70000,
            current_price=71000,
            profit=100000,
            profit_rate=1.43
        )
        assert balance.qty == 100
        assert balance.profit == 100000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
