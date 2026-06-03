"""SQLite 상태 저장소 — 적재·diff·baseline·집계."""
import os
import sqlite3
import statistics
from datetime import date as _date

from realestate_bot import config


def _record_key(r: dict) -> str:
    return "|".join([
        str(r["region_code"]), str(r["apt_name"]), str(r.get("dong", "")),
        f'{float(r["area_sqm"]):.4f}', str(r["floor"]),
        str(r["trade_date"]), str(r["price_10k"]),
    ])


def _rent_record_key(r: dict) -> str:
    return "|".join([
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
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS transactions (
              record_key TEXT PRIMARY KEY,
              region_code TEXT, apt_name TEXT, dong TEXT,
              area_sqm REAL, area_band INTEGER,
              floor INTEGER, price_10k INTEGER,
              trade_date TEXT, build_year INTEGER, deal_type TEXT,
              first_seen_date TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_group
              ON transactions(region_code, apt_name, area_band, trade_date);
            CREATE INDEX IF NOT EXISTS idx_vol
              ON transactions(region_code, trade_date);

            CREATE TABLE IF NOT EXISTS rents (
              record_key TEXT PRIMARY KEY,
              region_code TEXT, apt_name TEXT, dong TEXT,
              area_sqm REAL, area_band INTEGER, floor INTEGER,
              deposit_10k INTEGER, monthly_rent_10k INTEGER, contract_type TEXT,
              trade_date TEXT, build_year INTEGER, first_seen_date TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_rent_vol
              ON rents(region_code, trade_date);
            CREATE INDEX IF NOT EXISTS idx_rent_group
              ON rents(region_code, area_band, monthly_rent_10k, trade_date);
            """
        )
        self.conn.commit()

    def insert_new(self, records: list) -> list:
        """INSERT OR IGNORE 후 실제 삽입된(신규) 레코드만 반환."""
        today = _date.today().isoformat()
        new_records = []
        cur = self.conn.cursor()
        for r in records:
            key = _record_key(r)
            band = _area_band(r["area_sqm"])
            cur.execute(
                """INSERT OR IGNORE INTO transactions
                   (record_key, region_code, apt_name, dong, area_sqm, area_band,
                    floor, price_10k, trade_date, build_year, deal_type, first_seen_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, r["region_code"], r["apt_name"], r.get("dong", ""),
                 float(r["area_sqm"]), band, int(r["floor"]), int(r["price_10k"]),
                 r["trade_date"], r.get("build_year"), r.get("deal_type"), today),
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
        # 36개월 전 (대략: 연/월 빼기)
        y, m = ref.year, ref.month - config.BASELINE_MONTHS
        while m <= 0:
            m += 12
            y -= 1
        return f"{y:04d}-{m:02d}-01"

    def baseline_snapshot(self, region_code: str, as_of: str = "now") -> dict:
        cutoff = self._cutoff(as_of)
        rows = self.conn.execute(
            """SELECT apt_name, area_band,
                      MAX(price_10k) AS mx, MIN(price_10k) AS mn, COUNT(*) AS cnt
               FROM transactions
               WHERE region_code=? AND trade_date>=?
               GROUP BY apt_name, area_band""",
            (region_code, cutoff),
        ).fetchall()
        snap = {}
        for row in rows:
            key = (row["apt_name"], row["area_band"])
            mx_date = self.conn.execute(
                """SELECT trade_date FROM transactions
                   WHERE region_code=? AND apt_name=? AND area_band=? AND price_10k=?
                   ORDER BY trade_date DESC LIMIT 1""",
                (region_code, row["apt_name"], row["area_band"], row["mx"]),
            ).fetchone()["trade_date"]
            mn_date = self.conn.execute(
                """SELECT trade_date FROM transactions
                   WHERE region_code=? AND apt_name=? AND area_band=? AND price_10k=?
                   ORDER BY trade_date DESC LIMIT 1""",
                (region_code, row["apt_name"], row["area_band"], row["mn"]),
            ).fetchone()["trade_date"]
            snap[key] = {"max": row["mx"], "max_date": mx_date,
                         "min": row["mn"], "min_date": mn_date, "count": row["cnt"]}
        return snap

    def monthly_volume(self, region_code: str, months: int = 12) -> list:
        rows = self.conn.execute(
            """SELECT substr(replace(trade_date,'-',''),1,6) AS ym, COUNT(*) AS cnt
               FROM transactions WHERE region_code=?
               GROUP BY ym ORDER BY ym DESC LIMIT ?""",
            (region_code, months),
        ).fetchall()
        return [(row["ym"], row["cnt"]) for row in reversed(rows)]

    def band_medians(self, region_code: str, year_month: str) -> dict:
        like = f"{year_month[:4]}-{year_month[4:6]}-%"
        rows = self.conn.execute(
            """SELECT area_band, price_10k FROM transactions
               WHERE region_code=? AND trade_date LIKE ?""",
            (region_code, like),
        ).fetchall()
        by_band = {}
        for row in rows:
            by_band.setdefault(row["area_band"], []).append(row["price_10k"])
        return {b: {"median": int(statistics.median(p)), "count": len(p)}
                for b, p in by_band.items()}

    def has_records_for_month(self, region_code: str, year_month: str) -> bool:
        """해당 (구, 월)에 적재된 레코드가 1건이라도 있으면 True (백필 재개 시 skip 판정)."""
        like = f"{year_month[:4]}-{year_month[4:6]}-%"
        row = self.conn.execute(
            "SELECT 1 FROM transactions WHERE region_code=? AND trade_date LIKE ? LIMIT 1",
            (region_code, like),
        ).fetchone()
        return row is not None

    # ── 전월세(rents) ──────────────────────────────────────────────
    def insert_new_rents(self, records: list) -> list:
        """전월세 INSERT OR IGNORE 후 실제 삽입된(신규) 레코드만 반환."""
        today = _date.today().isoformat()
        new_records = []
        cur = self.conn.cursor()
        for r in records:
            key = _rent_record_key(r)
            band = _area_band(r["area_sqm"])
            cur.execute(
                """INSERT OR IGNORE INTO rents
                   (record_key, region_code, apt_name, dong, area_sqm, area_band,
                    floor, deposit_10k, monthly_rent_10k, contract_type,
                    trade_date, build_year, first_seen_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, r["region_code"], r.get("apt_name", ""), r.get("dong", ""),
                 float(r["area_sqm"]), band, int(r["floor"]),
                 int(r["deposit_10k"]), int(r.get("monthly_rent_10k", 0)),
                 r.get("contract_type"), r["trade_date"], r.get("build_year"), today),
            )
            if cur.rowcount == 1:
                out = dict(r)
                out["area_band"] = band
                new_records.append(out)
        self.conn.commit()
        return new_records

    def has_rent_records_for_month(self, region_code: str, year_month: str) -> bool:
        like = f"{year_month[:4]}-{year_month[4:6]}-%"
        row = self.conn.execute(
            "SELECT 1 FROM rents WHERE region_code=? AND trade_date LIKE ? LIMIT 1",
            (region_code, like),
        ).fetchone()
        return row is not None

    def rent_band_medians(self, region_code: str, year_month: str) -> dict:
        """평형 밴드별 전세(월세=0) 보증금 중앙값 → 전세가율 산출용.
        반환 {band: {median_deposit_10k, count}}."""
        like = f"{year_month[:4]}-{year_month[4:6]}-%"
        rows = self.conn.execute(
            """SELECT area_band, deposit_10k FROM rents
               WHERE region_code=? AND trade_date LIKE ? AND monthly_rent_10k=0""",
            (region_code, like),
        ).fetchall()
        by_band = {}
        for row in rows:
            by_band.setdefault(row["area_band"], []).append(row["deposit_10k"])
        return {b: {"median_deposit_10k": int(statistics.median(d)), "count": len(d)}
                for b, d in by_band.items()}
