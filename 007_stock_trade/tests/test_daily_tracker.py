"""
DailyTracker 단위 테스트

daily_tracker.py의 핵심 기능을 검증:
1. DailySnapshot / TransactionRecord dataclass 직렬화/역직렬화
2. DailyTracker 저장/로드/조회
3. 거래 기록 (log_transaction)
4. 같은 날짜 업데이트
5. 오래된 데이터 정리
6. 빈 파일/손상 파일 처리
7. quant_engine에서 daily_pnl 계산 로직
"""

import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import unittest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_modules.daily_tracker import (
    DailySnapshot, TransactionRecord, DailyTracker, MAX_HISTORY_DAYS
)


class TestDailySnapshot(unittest.TestCase):
    """DailySnapshot dataclass 테스트"""

    def test_to_dict_from_dict_roundtrip(self):
        """직렬화 → 역직렬화 라운드트립"""
        snap = DailySnapshot(
            date="2026-02-09",
            total_assets=18_000_000,
            cash=5_000_000,
            invested=13_000_000,
            buy_amount=12_500_000,
            position_count=10,
            total_pnl=8_000_000,
            total_pnl_pct=80.0,
            daily_pnl=35_000,
            daily_pnl_pct=0.19,
            trades_today=3,
            positions=[{"code": "005930", "name": "삼성전자"}]
        )
        d = snap.to_dict()
        restored = DailySnapshot.from_dict(d)

        self.assertEqual(restored.date, "2026-02-09")
        self.assertEqual(restored.total_assets, 18_000_000)
        self.assertEqual(restored.cash, 5_000_000)
        self.assertEqual(restored.invested, 13_000_000)
        self.assertEqual(restored.buy_amount, 12_500_000)
        self.assertEqual(restored.position_count, 10)
        self.assertEqual(restored.total_pnl, 8_000_000)
        self.assertAlmostEqual(restored.total_pnl_pct, 80.0)
        self.assertEqual(restored.daily_pnl, 35_000)
        self.assertAlmostEqual(restored.daily_pnl_pct, 0.19)
        self.assertEqual(restored.trades_today, 3)
        self.assertEqual(len(restored.positions), 1)

    def test_from_dict_missing_optional_fields(self):
        """선택 필드 없는 dict에서 생성"""
        d = {
            "date": "2026-02-09",
            "total_assets": 10_000_000,
            "cash": 10_000_000,
            "invested": 0,
            "position_count": 0,
            "total_pnl": 0,
            "total_pnl_pct": 0,
        }
        snap = DailySnapshot.from_dict(d)
        self.assertEqual(snap.buy_amount, 0)
        self.assertEqual(snap.daily_pnl, 0)
        self.assertEqual(snap.daily_pnl_pct, 0)
        self.assertEqual(snap.trades_today, 0)
        self.assertEqual(snap.positions, [])

    def test_json_serializable(self):
        """JSON 직렬화 가능 여부"""
        snap = DailySnapshot(
            date="2026-02-09", total_assets=1, cash=1, invested=0,
            buy_amount=0, position_count=0, total_pnl=0, total_pnl_pct=0,
            daily_pnl=0, daily_pnl_pct=0, trades_today=0
        )
        result = json.dumps(snap.to_dict(), ensure_ascii=False)
        self.assertIn("2026-02-09", result)


class TestTransactionRecord(unittest.TestCase):
    """TransactionRecord dataclass 테스트"""

    def test_roundtrip(self):
        """직렬화 → 역직렬화 라운드트립"""
        rec = TransactionRecord(
            timestamp="2026-02-09T09:00:00",
            date="2026-02-09",
            type="BUY",
            code="005930",
            name="삼성전자",
            quantity=10,
            price=75_000,
            amount=750_000,
            order_no="ORD001",
            reason="리밸런싱 매수"
        )
        d = rec.to_dict()
        restored = TransactionRecord.from_dict(d)

        self.assertEqual(restored.type, "BUY")
        self.assertEqual(restored.code, "005930")
        self.assertEqual(restored.amount, 750_000)
        self.assertEqual(restored.pnl, 0)

    def test_sell_with_pnl(self):
        """매도 거래 (손익 포함)"""
        d = {
            "timestamp": "2026-02-09T11:30:00",
            "date": "2026-02-09",
            "type": "SELL",
            "code": "005930",
            "name": "삼성전자",
            "quantity": 10,
            "price": 80_000,
            "amount": 800_000,
            "pnl": 50_000,
            "pnl_pct": 6.67
        }
        rec = TransactionRecord.from_dict(d)
        self.assertEqual(rec.pnl, 50_000)
        self.assertAlmostEqual(rec.pnl_pct, 6.67)

    def test_from_dict_computed_amount(self):
        """amount 필드 없을 때 자동 계산"""
        d = {
            "timestamp": "2026-02-09T09:00:00",
            "date": "2026-02-09",
            "type": "BUY",
            "code": "005930",
            "name": "삼성전자",
            "quantity": 10,
            "price": 75_000,
            # amount 없음
        }
        rec = TransactionRecord.from_dict(d)
        self.assertEqual(rec.amount, 750_000)  # 10 * 75000


class TestDailyTracker(unittest.TestCase):
    """DailyTracker 클래스 테스트"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_tracker(self):
        return DailyTracker(data_dir=self.temp_dir)

    def test_init_empty(self):
        """빈 디렉토리에서 초기화"""
        tracker = self._make_tracker()
        self.assertEqual(len(tracker.snapshots), 0)
        self.assertEqual(len(tracker.transactions), 0)
        self.assertEqual(tracker.initial_capital, 0)

    def test_save_and_reload_snapshot(self):
        """스냅샷 저장 후 재로드"""
        tracker = self._make_tracker()
        tracker.initial_capital = 10_000_000
        snap = DailySnapshot(
            date="2026-02-09", total_assets=18_000_000, cash=5_000_000,
            invested=13_000_000, buy_amount=12_000_000, position_count=10,
            total_pnl=8_000_000, total_pnl_pct=80.0,
            daily_pnl=35_000, daily_pnl_pct=0.19, trades_today=3
        )
        tracker.save_daily_snapshot(snap)

        # 새 트래커로 재로드
        tracker2 = DailyTracker(data_dir=self.temp_dir)
        self.assertEqual(len(tracker2.snapshots), 1)
        self.assertEqual(tracker2.snapshots[0].date, "2026-02-09")
        self.assertEqual(tracker2.snapshots[0].total_assets, 18_000_000)
        self.assertEqual(tracker2.initial_capital, 10_000_000)

    def test_same_date_update(self):
        """같은 날짜 스냅샷 저장하면 업데이트"""
        tracker = self._make_tracker()

        snap1 = DailySnapshot(
            date="2026-02-09", total_assets=18_000_000, cash=5_000_000,
            invested=13_000_000, buy_amount=12_000_000, position_count=10,
            total_pnl=0, total_pnl_pct=0, daily_pnl=0, daily_pnl_pct=0,
            trades_today=0
        )
        tracker.save_daily_snapshot(snap1)
        self.assertEqual(len(tracker.snapshots), 1)

        snap2 = DailySnapshot(
            date="2026-02-09", total_assets=18_500_000, cash=4_500_000,
            invested=14_000_000, buy_amount=12_000_000, position_count=10,
            total_pnl=0, total_pnl_pct=0, daily_pnl=0, daily_pnl_pct=0,
            trades_today=2
        )
        tracker.save_daily_snapshot(snap2)
        self.assertEqual(len(tracker.snapshots), 1)  # 여전히 1개
        self.assertEqual(tracker.snapshots[0].total_assets, 18_500_000)  # 업데이트됨

    def test_log_transaction(self):
        """거래 즉시 기록"""
        tracker = self._make_tracker()

        trade_dict = {
            "type": "BUY",
            "code": "005930",
            "name": "삼성전자",
            "quantity": 10,
            "price": 75_000,
            "order_no": "ORD001",
            "reason": "리밸런싱 매수",
            "timestamp": "2026-02-09T09:00:00"
        }
        tracker.log_transaction(trade_dict)

        self.assertEqual(len(tracker.transactions), 1)
        self.assertEqual(tracker.transactions[0].code, "005930")
        self.assertEqual(tracker.transactions[0].amount, 750_000)
        self.assertEqual(tracker.transactions[0].date, "2026-02-09")

        # 파일 존재 확인
        self.assertTrue(tracker.transaction_file.exists())

        # 재로드 후 확인
        tracker2 = DailyTracker(data_dir=self.temp_dir)
        self.assertEqual(len(tracker2.transactions), 1)
        self.assertEqual(tracker2.transactions[0].name, "삼성전자")

    def test_log_sell_transaction_with_pnl(self):
        """매도 거래 기록 (손익 포함)"""
        tracker = self._make_tracker()

        trade_dict = {
            "type": "SELL",
            "code": "005930",
            "name": "삼성전자",
            "quantity": 10,
            "price": 80_000,
            "pnl": 50_000,
            "pnl_pct": 6.67,
            "order_no": "ORD002",
            "reason": "익절",
            "timestamp": "2026-02-09T14:00:00"
        }
        tracker.log_transaction(trade_dict)

        self.assertEqual(tracker.transactions[0].pnl, 50_000)
        self.assertAlmostEqual(tracker.transactions[0].pnl_pct, 6.67)

    def test_get_recent_snapshots(self):
        """최근 N일 스냅샷 조회"""
        tracker = self._make_tracker()

        # 10일치 스냅샷 추가
        for i in range(10):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            snap = DailySnapshot(
                date=date, total_assets=10_000_000 + i * 100_000,
                cash=5_000_000, invested=5_000_000 + i * 100_000,
                buy_amount=5_000_000, position_count=5,
                total_pnl=0, total_pnl_pct=0, daily_pnl=0,
                daily_pnl_pct=0, trades_today=0
            )
            tracker.save_daily_snapshot(snap)

        recent = tracker.get_recent_snapshots(days=3)
        self.assertLessEqual(len(recent), 4)  # 오늘 포함 ~3일

        # 최신순 정렬 확인
        for i in range(len(recent) - 1):
            self.assertGreaterEqual(recent[i].date, recent[i + 1].date)

    def test_get_recent_transactions(self):
        """최근 N일 거래 조회"""
        tracker = self._make_tracker()

        # 여러 날 거래 추가
        for i in range(10):
            date = (datetime.now() - timedelta(days=i))
            trade_dict = {
                "type": "BUY",
                "code": f"00{i:04d}",
                "name": f"종목{i}",
                "quantity": 10,
                "price": 10_000,
                "order_no": f"ORD{i:03d}",
                "reason": "테스트",
                "timestamp": date.isoformat()
            }
            tracker.log_transaction(trade_dict)

        recent = tracker.get_recent_transactions(days=3)
        self.assertLessEqual(len(recent), 4)

        # 최신순 정렬 확인
        for i in range(len(recent) - 1):
            self.assertGreaterEqual(recent[i].timestamp, recent[i + 1].timestamp)

    def test_get_latest_snapshot(self):
        """최신 스냅샷 조회"""
        tracker = self._make_tracker()
        self.assertIsNone(tracker.get_latest_snapshot())

        # 역순으로 추가해도 최신 날짜를 반환하는지
        for date in ["2026-02-07", "2026-02-09", "2026-02-08"]:
            snap = DailySnapshot(
                date=date, total_assets=10_000_000, cash=5_000_000,
                invested=5_000_000, buy_amount=5_000_000, position_count=5,
                total_pnl=0, total_pnl_pct=0, daily_pnl=0,
                daily_pnl_pct=0, trades_today=0
            )
            tracker.save_daily_snapshot(snap)

        latest = tracker.get_latest_snapshot()
        self.assertEqual(latest.date, "2026-02-09")

    def test_get_previous_snapshot(self):
        """직전 스냅샷 조회"""
        tracker = self._make_tracker()

        # 1개만 있으면 이전이 없음
        snap1 = DailySnapshot(
            date="2026-02-09", total_assets=10_000_000, cash=5_000_000,
            invested=5_000_000, buy_amount=5_000_000, position_count=5,
            total_pnl=0, total_pnl_pct=0, daily_pnl=0,
            daily_pnl_pct=0, trades_today=0
        )
        tracker.save_daily_snapshot(snap1)
        self.assertIsNone(tracker.get_previous_snapshot())

        # 2개면 이전 반환
        snap2 = DailySnapshot(
            date="2026-02-10", total_assets=10_100_000, cash=5_000_000,
            invested=5_100_000, buy_amount=5_000_000, position_count=5,
            total_pnl=0, total_pnl_pct=0, daily_pnl=0,
            daily_pnl_pct=0, trades_today=0
        )
        tracker.save_daily_snapshot(snap2)
        prev = tracker.get_previous_snapshot()
        self.assertIsNotNone(prev)
        self.assertEqual(prev.date, "2026-02-09")

    def test_corrupted_history_file(self):
        """손상된 히스토리 파일 처리"""
        # 손상된 파일 생성
        history_file = self.temp_dir / "daily_history.json"
        with open(history_file, 'w') as f:
            f.write("{invalid json content")

        tracker = self._make_tracker()
        self.assertEqual(len(tracker.snapshots), 0)

        # 백업 파일 생성 확인
        backups = list(self.temp_dir.glob("daily_history.backup.*.json"))
        self.assertEqual(len(backups), 1)

    def test_corrupted_transaction_file(self):
        """손상된 거래 일지 파일 처리"""
        tx_file = self.temp_dir / "transaction_journal.json"
        with open(tx_file, 'w') as f:
            f.write("not valid json")

        tracker = self._make_tracker()
        self.assertEqual(len(tracker.transactions), 0)

        backups = list(self.temp_dir.glob("transaction_journal.backup.*.json"))
        self.assertEqual(len(backups), 1)

    def test_cleanup_old_snapshots(self):
        """오래된 스냅샷 정리"""
        tracker = self._make_tracker()

        # MAX_HISTORY_DAYS + 10 개 추가
        for i in range(MAX_HISTORY_DAYS + 10):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            snap = DailySnapshot(
                date=date, total_assets=10_000_000, cash=5_000_000,
                invested=5_000_000, buy_amount=5_000_000, position_count=5,
                total_pnl=0, total_pnl_pct=0, daily_pnl=0,
                daily_pnl_pct=0, trades_today=0
            )
            tracker.snapshots.append(snap)

        # cleanup 트리거 (save시 자동)
        new_snap = DailySnapshot(
            date=datetime.now().strftime("%Y-%m-%d"),
            total_assets=10_000_000, cash=5_000_000,
            invested=5_000_000, buy_amount=5_000_000, position_count=5,
            total_pnl=0, total_pnl_pct=0, daily_pnl=0,
            daily_pnl_pct=0, trades_today=0
        )
        tracker.save_daily_snapshot(new_snap)
        self.assertLessEqual(len(tracker.snapshots), MAX_HISTORY_DAYS + 1)

    def test_get_first_snapshot_date(self):
        """최초 스냅샷 날짜"""
        tracker = self._make_tracker()
        self.assertIsNone(tracker.get_first_snapshot_date())

        for date in ["2026-02-09", "2026-01-15", "2026-02-01"]:
            snap = DailySnapshot(
                date=date, total_assets=10_000_000, cash=5_000_000,
                invested=5_000_000, buy_amount=5_000_000, position_count=5,
                total_pnl=0, total_pnl_pct=0, daily_pnl=0,
                daily_pnl_pct=0, trades_today=0
            )
            tracker.save_daily_snapshot(snap)

        self.assertEqual(tracker.get_first_snapshot_date(), "2026-01-15")

    def test_initial_capital_persistence(self):
        """initial_capital이 저장/로드 시 유지되는지"""
        tracker = self._make_tracker()
        tracker.initial_capital = 10_000_000
        tracker._save_history()

        tracker2 = DailyTracker(data_dir=self.temp_dir)
        self.assertEqual(tracker2.initial_capital, 10_000_000)

    def test_atomic_write_history(self):
        """히스토리 파일 atomic write (tmp → replace)"""
        tracker = self._make_tracker()
        snap = DailySnapshot(
            date="2026-02-09", total_assets=18_000_000, cash=5_000_000,
            invested=13_000_000, buy_amount=12_000_000, position_count=10,
            total_pnl=0, total_pnl_pct=0, daily_pnl=0,
            daily_pnl_pct=0, trades_today=0
        )
        tracker.save_daily_snapshot(snap)

        # tmp 파일이 남아있지 않은지
        tmp_files = list(self.temp_dir.glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0)

        # 원본 파일이 유효한 JSON인지
        with open(tracker.history_file, 'r') as f:
            data = json.load(f)
        self.assertIn("snapshots", data)
        self.assertIn("initial_capital", data)

    def test_atomic_write_transactions(self):
        """거래 일지 파일 atomic write"""
        tracker = self._make_tracker()
        tracker.log_transaction({
            "type": "BUY", "code": "005930", "name": "삼성전자",
            "quantity": 10, "price": 75_000, "order_no": "ORD001",
            "reason": "테스트", "timestamp": "2026-02-09T09:00:00"
        })

        tmp_files = list(self.temp_dir.glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0)

        with open(tracker.transaction_file, 'r') as f:
            data = json.load(f)
        self.assertIn("transactions", data)


class TestDailyPnlCalculation(unittest.TestCase):
    """quant_engine의 daily_pnl 계산 로직 검증 (수정된 get_previous_day_snapshot 사용)"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_daily_pnl_first_day(self):
        """첫날: 이전 스냅샷 없으므로 daily_pnl = 0"""
        tracker = DailyTracker(data_dir=self.temp_dir)
        today_str = datetime.now().strftime("%Y-%m-%d")
        prev = tracker.get_previous_day_snapshot(today_str)
        self.assertIsNone(prev)

        total_assets = 10_000_000
        daily_pnl = 0
        daily_pnl_pct = 0
        if prev:
            daily_pnl = total_assets - prev.total_assets
            daily_pnl_pct = (daily_pnl / prev.total_assets * 100) if prev.total_assets > 0 else 0

        self.assertEqual(daily_pnl, 0)
        self.assertEqual(daily_pnl_pct, 0)

    def test_daily_pnl_second_day(self):
        """둘째날: 전일 스냅샷 기준으로 계산"""
        tracker = DailyTracker(data_dir=self.temp_dir)

        snap1 = DailySnapshot(
            date="2026-02-08", total_assets=10_000_000, cash=5_000_000,
            invested=5_000_000, buy_amount=5_000_000, position_count=5,
            total_pnl=0, total_pnl_pct=0, daily_pnl=0,
            daily_pnl_pct=0, trades_today=0
        )
        tracker.save_daily_snapshot(snap1)

        total_assets = 10_100_000
        prev = tracker.get_previous_day_snapshot("2026-02-09")
        self.assertIsNotNone(prev)
        self.assertEqual(prev.date, "2026-02-08")

        daily_pnl = total_assets - prev.total_assets
        daily_pnl_pct = (daily_pnl / prev.total_assets * 100) if prev.total_assets > 0 else 0

        self.assertEqual(daily_pnl, 100_000)
        self.assertAlmostEqual(daily_pnl_pct, 1.0)

    def test_daily_pnl_same_day_update_fixed(self):
        """같은 날 재호출 시: get_previous_day_snapshot은 어제 것 반환 (수정됨)"""
        tracker = DailyTracker(data_dir=self.temp_dir)

        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # 어제 스냅샷
        snap_yesterday = DailySnapshot(
            date=yesterday, total_assets=10_000_000, cash=5_000_000,
            invested=5_000_000, buy_amount=5_000_000, position_count=5,
            total_pnl=0, total_pnl_pct=0, daily_pnl=0,
            daily_pnl_pct=0, trades_today=0
        )
        tracker.save_daily_snapshot(snap_yesterday)

        # 오늘 첫 스냅샷
        snap_today = DailySnapshot(
            date=today, total_assets=10_100_000, cash=5_000_000,
            invested=5_100_000, buy_amount=5_000_000, position_count=5,
            total_pnl=100_000, total_pnl_pct=1.0, daily_pnl=100_000,
            daily_pnl_pct=1.0, trades_today=2
        )
        tracker.save_daily_snapshot(snap_today)

        # 오늘 두번째 업데이트: get_previous_day_snapshot는 어제 것 반환
        prev = tracker.get_previous_day_snapshot(today)
        self.assertIsNotNone(prev)
        self.assertEqual(prev.date, yesterday)
        self.assertEqual(prev.total_assets, 10_000_000)

        # 올바른 계산: 10_200_000 - 10_000_000 = 200_000
        total_assets_updated = 10_200_000
        daily_pnl = total_assets_updated - prev.total_assets
        self.assertEqual(daily_pnl, 200_000)

    def test_get_previous_day_snapshot_no_data(self):
        """전일 스냅샷 없을 때 None 반환"""
        tracker = DailyTracker(data_dir=self.temp_dir)
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertIsNone(tracker.get_previous_day_snapshot(today))

    def test_get_previous_day_snapshot_only_today(self):
        """오늘 스냅샷만 있을 때 None 반환"""
        tracker = DailyTracker(data_dir=self.temp_dir)
        today = datetime.now().strftime("%Y-%m-%d")

        snap_today = DailySnapshot(
            date=today, total_assets=10_000_000, cash=5_000_000,
            invested=5_000_000, buy_amount=5_000_000, position_count=5,
            total_pnl=0, total_pnl_pct=0, daily_pnl=0,
            daily_pnl_pct=0, trades_today=0
        )
        tracker.save_daily_snapshot(snap_today)

        self.assertIsNone(tracker.get_previous_day_snapshot(today))

    def test_get_previous_day_snapshot_skips_gap(self):
        """며칠 간격 있을 때 가장 최근 이전 날짜 반환"""
        tracker = DailyTracker(data_dir=self.temp_dir)

        # 월요일(02/03), 금요일(02/07) 만 있고, 오늘은 월요일(02/10)
        for date in ["2026-02-03", "2026-02-07"]:
            snap = DailySnapshot(
                date=date, total_assets=10_000_000, cash=5_000_000,
                invested=5_000_000, buy_amount=5_000_000, position_count=5,
                total_pnl=0, total_pnl_pct=0, daily_pnl=0,
                daily_pnl_pct=0, trades_today=0
            )
            tracker.save_daily_snapshot(snap)

        prev = tracker.get_previous_day_snapshot("2026-02-10")
        self.assertIsNotNone(prev)
        self.assertEqual(prev.date, "2026-02-07")  # 주말 스킵, 금요일 반환


class TestLogTransactionEdgeCases(unittest.TestCase):
    """거래 기록 엣지 케이스"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_log_transaction_missing_fields(self):
        """필수 필드 누락 시에도 에러 없이 기록"""
        tracker = DailyTracker(data_dir=self.temp_dir)
        trade_dict = {
            "type": "BUY",
            "code": "005930",
            "name": "삼성전자",
            "quantity": 10,
            "price": 75_000,
            "timestamp": "2026-02-09T09:00:00"
            # order_no, reason 누락
        }
        tracker.log_transaction(trade_dict)
        self.assertEqual(len(tracker.transactions), 1)
        self.assertEqual(tracker.transactions[0].order_no, "")
        self.assertEqual(tracker.transactions[0].reason, "")

    def test_log_transaction_without_timestamp(self):
        """timestamp 누락 시 현재 시간 사용"""
        tracker = DailyTracker(data_dir=self.temp_dir)
        trade_dict = {
            "type": "BUY",
            "code": "005930",
            "name": "삼성전자",
            "quantity": 10,
            "price": 75_000,
            # timestamp 누락
        }
        tracker.log_transaction(trade_dict)
        self.assertEqual(len(tracker.transactions), 1)
        # 오늘 날짜가 기록되어야 함
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(tracker.transactions[0].date, today)

    def test_multiple_rapid_transactions(self):
        """빠르게 여러 건 기록 시 모두 저장"""
        tracker = DailyTracker(data_dir=self.temp_dir)
        for i in range(10):
            trade_dict = {
                "type": "BUY",
                "code": f"0059{i:02d}",
                "name": f"종목{i}",
                "quantity": 10,
                "price": 75_000,
                "order_no": f"ORD{i:03d}",
                "reason": "테스트",
                "timestamp": f"2026-02-09T09:{i:02d}:00"
            }
            tracker.log_transaction(trade_dict)

        self.assertEqual(len(tracker.transactions), 10)

        # 재로드 후 확인
        tracker2 = DailyTracker(data_dir=self.temp_dir)
        self.assertEqual(len(tracker2.transactions), 10)


if __name__ == "__main__":
    unittest.main()
