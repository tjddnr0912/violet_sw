"""SQLite 상태 저장소 — 적재·diff·baseline·집계.

property_type('apartment'|'officetel')로 매물 유형을 구분한다. 기존 메서드는
기본값 'apartment'라 아파트 동작이 불변이고, 오피스텔은 property_type만 바꿔
같은 코드로 적재·집계한다. record_key는 아파트만 기존 포맷(prefix 無)을 유지해
기존 94만 행 마이그레이션·중복을 피하고, 그 외 유형만 prefix로 네임스페이스 분리.
"""
import os
import sqlite3
import statistics
from datetime import date as _date

from realestate_bot import config


def _key_prefix(property_type: str) -> str:
    return "" if property_type == "apartment" else f"{property_type}|"


def _record_key(r: dict, property_type: str = "apartment") -> str:
    return _key_prefix(property_type) + "|".join([
        str(r["region_code"]), str(r.get("apt_name", "")), str(r.get("dong", "")),
        f'{float(r["area_sqm"]):.4f}', str(r["floor"]),
        str(r["trade_date"]), str(r["price_10k"]),
    ])


def _rent_record_key(r: dict, property_type: str = "apartment") -> str:
    return _key_prefix(property_type) + "|".join([
        str(r["region_code"]), str(r.get("apt_name", "")), str(r.get("dong", "")),
        f'{float(r["area_sqm"]):.4f}', str(r["floor"]), str(r["trade_date"]),
        str(r["deposit_10k"]), str(r.get("monthly_rent_10k", 0)),
    ])


def _area_band(area_sqm) -> int:
    return int(round(float(area_sqm)))


class RealEstateStore:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        # 1) 테이블 생성(신규 DB는 property_type 포함)
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS transactions (
              record_key TEXT PRIMARY KEY,
              property_type TEXT DEFAULT 'apartment',
              region_code TEXT, apt_name TEXT, dong TEXT,
              area_sqm REAL, area_band INTEGER,
              floor INTEGER, price_10k INTEGER,
              trade_date TEXT, build_year INTEGER, deal_type TEXT,
              first_seen_date TEXT
            );
            CREATE TABLE IF NOT EXISTS rents (
              record_key TEXT PRIMARY KEY,
              property_type TEXT DEFAULT 'apartment',
              region_code TEXT, apt_name TEXT, dong TEXT,
              area_sqm REAL, area_band INTEGER, floor INTEGER,
              deposit_10k INTEGER, monthly_rent_10k INTEGER, contract_type TEXT,
              trade_date TEXT, build_year INTEGER, first_seen_date TEXT
            );
            """
        )
        # 2) 구 DB에 property_type 컬럼 추가 (인덱스가 이 컬럼을 참조하므로 인덱스 생성 전에)
        self._migrate_property_type()
        # 3) property_type 인덱스 (컬럼 존재 보장 후)
        self.conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_txn_grp
              ON transactions(region_code, property_type, apt_name, area_band, trade_date);
            CREATE INDEX IF NOT EXISTS idx_txn_vol
              ON transactions(region_code, property_type, trade_date);
            CREATE INDEX IF NOT EXISTS idx_rent_grp
              ON rents(region_code, property_type, area_band, monthly_rent_10k, trade_date);
            CREATE INDEX IF NOT EXISTS idx_rent_vol2
              ON rents(region_code, property_type, trade_date);
            """
        )
        self.conn.commit()

    def _migrate_property_type(self):
        """기존 DB(컬럼 없는 transactions/rents)에 property_type 추가(기존 행='apartment')."""
        for tbl in ("transactions", "rents"):
            cols = [row[1] for row in self.conn.execute(f"PRAGMA table_info({tbl})")]
            if cols and "property_type" not in cols:
                self.conn.execute(
                    f"ALTER TABLE {tbl} ADD COLUMN property_type TEXT DEFAULT 'apartment'")

    # ── 매매(transactions) ─────────────────────────────────────────
    def insert_new(self, records: list, property_type: str = "apartment") -> list:
        """INSERT OR IGNORE 후 실제 삽입된(신규) 레코드만 반환."""
        today = _date.today().isoformat()
        new_records = []
        cur = self.conn.cursor()
        for r in records:
            key = _record_key(r, property_type)
            band = _area_band(r["area_sqm"])
            cur.execute(
                """INSERT OR IGNORE INTO transactions
                   (record_key, property_type, region_code, apt_name, dong, area_sqm,
                    area_band, floor, price_10k, trade_date, build_year, deal_type,
                    first_seen_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, property_type, r["region_code"], r.get("apt_name", ""),
                 r.get("dong", ""), float(r["area_sqm"]), band, int(r["floor"]),
                 int(r["price_10k"]), r["trade_date"], r.get("build_year"),
                 r.get("deal_type"), today),
            )
            if cur.rowcount == 1:
                out = dict(r)
                out["area_band"] = band
                new_records.append(out)
        self.conn.commit()
        return new_records

    def _cutoff(self, as_of: str) -> str:
        if as_of == "now":
            ref = _date.today()
        else:
            ref = _date.fromisoformat(as_of)
        y, m = ref.year, ref.month - config.BASELINE_MONTHS
        while m <= 0:
            m += 12
            y -= 1
        return f"{y:04d}-{m:02d}-01"

    def baseline_snapshot(self, region_code: str, as_of: str = "now",
                          property_type: str = "apartment") -> dict:
        cutoff = self._cutoff(as_of)
        rows = self.conn.execute(
            """SELECT apt_name, area_band,
                      MAX(price_10k) AS mx, MIN(price_10k) AS mn, COUNT(*) AS cnt
               FROM transactions
               WHERE region_code=? AND property_type=? AND trade_date>=?
               GROUP BY apt_name, area_band""",
            (region_code, property_type, cutoff),
        ).fetchall()
        snap = {}
        for row in rows:
            key = (row["apt_name"], row["area_band"])
            mx_date = self.conn.execute(
                """SELECT trade_date FROM transactions
                   WHERE region_code=? AND property_type=? AND apt_name=? AND area_band=?
                         AND price_10k=?
                   ORDER BY trade_date DESC LIMIT 1""",
                (region_code, property_type, row["apt_name"], row["area_band"], row["mx"]),
            ).fetchone()["trade_date"]
            mn_date = self.conn.execute(
                """SELECT trade_date FROM transactions
                   WHERE region_code=? AND property_type=? AND apt_name=? AND area_band=?
                         AND price_10k=?
                   ORDER BY trade_date DESC LIMIT 1""",
                (region_code, property_type, row["apt_name"], row["area_band"], row["mn"]),
            ).fetchone()["trade_date"]
            snap[key] = {"max": row["mx"], "max_date": mx_date,
                         "min": row["mn"], "min_date": mn_date, "count": row["cnt"]}
        return snap

    def monthly_volume(self, region_code: str, months: int = 12,
                       property_type: str = "apartment") -> list:
        rows = self.conn.execute(
            """SELECT substr(replace(trade_date,'-',''),1,6) AS ym, COUNT(*) AS cnt
               FROM transactions WHERE region_code=? AND property_type=?
               GROUP BY ym ORDER BY ym DESC LIMIT ?""",
            (region_code, property_type, months),
        ).fetchall()
        return [(row["ym"], row["cnt"]) for row in reversed(rows)]

    def band_medians(self, region_code: str, year_month: str,
                     property_type: str = "apartment") -> dict:
        like = f"{year_month[:4]}-{year_month[4:6]}-%"
        rows = self.conn.execute(
            """SELECT area_band, price_10k FROM transactions
               WHERE region_code=? AND property_type=? AND trade_date LIKE ?""",
            (region_code, property_type, like),
        ).fetchall()
        by_band = {}
        for row in rows:
            by_band.setdefault(row["area_band"], []).append(row["price_10k"])
        return {b: {"median": int(statistics.median(p)), "count": len(p)}
                for b, p in by_band.items()}

    def has_records_for_month(self, region_code: str, year_month: str,
                              property_type: str = "apartment") -> bool:
        """해당 (구, 월, 유형)에 적재된 레코드가 1건이라도 있으면 True (백필 skip 판정)."""
        like = f"{year_month[:4]}-{year_month[4:6]}-%"
        row = self.conn.execute(
            """SELECT 1 FROM transactions
               WHERE region_code=? AND property_type=? AND trade_date LIKE ? LIMIT 1""",
            (region_code, property_type, like),
        ).fetchone()
        return row is not None

    # ── 전월세(rents) ──────────────────────────────────────────────
    def insert_new_rents(self, records: list, property_type: str = "apartment") -> list:
        today = _date.today().isoformat()
        new_records = []
        cur = self.conn.cursor()
        for r in records:
            key = _rent_record_key(r, property_type)
            band = _area_band(r["area_sqm"])
            cur.execute(
                """INSERT OR IGNORE INTO rents
                   (record_key, property_type, region_code, apt_name, dong, area_sqm,
                    area_band, floor, deposit_10k, monthly_rent_10k, contract_type,
                    trade_date, build_year, first_seen_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, property_type, r["region_code"], r.get("apt_name", ""),
                 r.get("dong", ""), float(r["area_sqm"]), band, int(r["floor"]),
                 int(r["deposit_10k"]), int(r.get("monthly_rent_10k", 0)),
                 r.get("contract_type"), r["trade_date"], r.get("build_year"), today),
            )
            if cur.rowcount == 1:
                out = dict(r)
                out["area_band"] = band
                new_records.append(out)
        self.conn.commit()
        return new_records

    def has_rent_records_for_month(self, region_code: str, year_month: str,
                                   property_type: str = "apartment") -> bool:
        like = f"{year_month[:4]}-{year_month[4:6]}-%"
        row = self.conn.execute(
            """SELECT 1 FROM rents
               WHERE region_code=? AND property_type=? AND trade_date LIKE ? LIMIT 1""",
            (region_code, property_type, like),
        ).fetchone()
        return row is not None

    def rent_band_medians(self, region_code: str, year_month: str,
                          property_type: str = "apartment") -> dict:
        """평형 밴드별 전세(월세=0) 보증금 중앙값 → 전세가율 산출용.
        반환 {band: {median_deposit_10k, count}}."""
        like = f"{year_month[:4]}-{year_month[4:6]}-%"
        rows = self.conn.execute(
            """SELECT area_band, deposit_10k FROM rents
               WHERE region_code=? AND property_type=? AND trade_date LIKE ?
                     AND monthly_rent_10k=0""",
            (region_code, property_type, like),
        ).fetchall()
        by_band = {}
        for row in rows:
            by_band.setdefault(row["area_band"], []).append(row["deposit_10k"])
        return {b: {"median_deposit_10k": int(statistics.median(d)), "count": len(d)}
                for b, d in by_band.items()}
