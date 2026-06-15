#!/usr/bin/env python3
"""주간 전국 아파트 시장 흐름 다이제스트 봇 (서울 상세 + 경기·광역시·세종 권역 요약).

  python weekly_realestate_bot.py --once [--test]   # 즉시 1회 (test=업로드 스킵)
  python weekly_realestate_bot.py --backfill 36     # 119시군구 × N개월 초기 적재
  python weekly_realestate_bot.py                   # 스케줄 (토 01:00)
"""
import os
import re
import sys
import time
import logging
import argparse
import subprocess
import schedule
from datetime import datetime, date

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from realestate_bot import config, fetcher, indicators, commentary, digest, mcp_client, publish_meta
from realestate_bot.regions_extra import group_of
from realestate_bot.store import RealEstateStore
from realestate_bot.detector import classify
from shared.wordpress_uploader import WordPressUploader, auto_draft_enabled
from shared.telegram_notifier import TelegramNotifier
from shared.claude_html_converter import convert_md_to_html_via_claude

load_dotenv(override=True)
os.makedirs("./logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(f"./logs/realestate_bot_{datetime.now():%Y%m%d}.log",
                                  encoding="utf-8")],
)
logger = logging.getLogger(__name__)

TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"


def _recent_months(n: int, ref: date = None) -> list:
    ref = ref or date.today()
    out = []
    y, m = ref.year, ref.month
    for _ in range(n):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def build_report(store: RealEstateStore, regions: dict, months: list, as_of: str,
                 fetch_region=None) -> dict:
    """fetch → diff → 지표 → report dict.

    fetch_region 미지정 시 claude-p 운반책(fetcher.fetch_region)을 쓰지만,
    프로덕션 주간 런은 MCPClient.fetch_region(직접 경로, 한도 無)을 주입한다.
    """
    fetch = fetch_region or fetcher.fetch_region
    cur_year = int(as_of[:4])
    per_gu = {}
    highlights = []
    seoul = {"new_total": 0, "high_total": 0, "low_total": 0}

    for gu, code in regions.items():
        # 1) baseline 스냅샷(삽입 전)
        baseline = store.baseline_snapshot(code, as_of=as_of)
        # 2) fetch + 적재(diff)
        fetched = []
        for ym in months:
            try:
                fetched.extend(fetch(code, ym))
            except Exception as e:  # noqa: BLE001
                logger.warning("skip %s %s: %s", gu, ym, e)
        new_records = store.insert_new(fetched)
        # 3) 판정
        verdicts = []
        for r in new_records:
            v = classify(r, baseline.get((r["apt_name"], r["area_band"])))
            verdicts.append(v)
            if v.kind in ("HIGH", "LOW"):
                highlights.append({"gu": gu, "apt_name": r["apt_name"],
                                   "area_band": r["area_band"], "price_10k": r["price_10k"],
                                   "pct": v.pct, "kind": v.kind,
                                   "ref_price": v.ref_price, "ref_date": v.ref_date})
        # 4) 지표
        b = indicators.breadth(verdicts)
        latest_ym = months[0]
        prev_ym = months[1] if len(months) > 1 else None
        cur_bm = store.band_medians(code, latest_ym)
        prev_bm = store.band_medians(code, prev_ym) if prev_ym else {}
        mix = indicators.mix_adjusted_change(
            {k: v["median"] for k, v in cur_bm.items()},
            {k: v["median"] for k, v in prev_bm.items()},
            {k: v["count"] for k, v in cur_bm.items()})
        seg = indicators.segment_flags(new_records, current_year=cur_year)
        per_gu[gu] = {"new_count": len(new_records), "breadth": b,
                      "mix_change": mix, "segment": seg}
        seoul["new_total"] += len(new_records)
        seoul["high_total"] += b["high"]
        seoul["low_total"] += b["low"]

    seoul["high_pct"] = (seoul["high_total"] / seoul["new_total"] * 100
                         if seoul["new_total"] else 0.0)
    highlights.sort(key=lambda h: abs(h["pct"] or 0), reverse=True)
    return {"week_label": f"{as_of} 기준 주간", "seoul": seoul,
            "per_gu": per_gu, "highlights": highlights[:15]}


def synthesize(store: RealEstateStore, regions: dict, year_month: str) -> dict:
    """매매·전세·오피스텔을 종합한 부가 지표(DB 기준, 해당 월).

    - jeonse: 구별 아파트 전세가율(%) (전세 보증금중앙 / 매매 중앙)
    - jeonse_seoul: 비어있지 않은 구들의 평균 전세가율
    - officetel: 구별 오피스텔 매매 건수
    - officetel_total: 서울 오피스텔 매매 총건수
    - officetel_rent: 구별 오피스텔 전월세 건수
    - officetel_rent_total/_jeonse/_wolse: 서울 오피스텔 전월세 총건수·전세·월세
    데이터(전세/오피스텔)가 아직 없으면 값은 None/0으로 degrade.
    """
    jeonse, officetel, officetel_rent = {}, {}, {}
    o_rent_jeonse = o_rent_wolse = 0
    for gu, code in regions.items():
        tb = store.band_medians(code, year_month, "apartment")
        rb = store.rent_band_medians(code, year_month, "apartment")
        jeonse[gu] = indicators.jeonse_ratio(
            {b: v["median"] for b, v in tb.items()},
            {b: v["median_deposit_10k"] for b, v in rb.items()},
            {b: v["count"] for b, v in rb.items()})
        ob = store.band_medians(code, year_month, "officetel")
        officetel[gu] = sum(v["count"] for v in ob.values())
        rv = store.rent_volume(code, year_month, "officetel")
        officetel_rent[gu] = rv["total"]
        o_rent_jeonse += rv["jeonse"]
        o_rent_wolse += rv["wolse"]
    ratios = [r for r in jeonse.values() if r is not None]
    return {
        "jeonse": jeonse,
        "jeonse_seoul": round(sum(ratios) / len(ratios), 1) if ratios else None,
        "officetel": officetel,
        "officetel_total": sum(officetel.values()),
        "officetel_rent": officetel_rent,
        "officetel_rent_total": o_rent_jeonse + o_rent_wolse,
        "officetel_rent_jeonse": o_rent_jeonse,
        "officetel_rent_wolse": o_rent_wolse,
    }


def _convert_html(md: str):
    """h2 청크 분할 후 Claude HTML 변환. 반환 (html, blog_title) — 첫 청크 헤드라인 보존."""
    sections = re.split(r"(?=^## )", md, flags=re.MULTILINE)
    chunks, cur = [], ""
    for s in sections:
        s = s.strip()
        if not s:
            continue
        if len(cur) + len(s) < 5000:
            cur = (cur + "\n\n" + s) if cur else s
        else:
            chunks.append(cur)
            cur = s
    if cur:
        chunks.append(cur)
    parts, headline = [], ""
    for i, c in enumerate(chunks, 1):
        try:
            html, title = convert_md_to_html_via_claude(
                c, editorial={"author": "realestate", "content_type": "realestate"}
            )
            if i == 1 and title:
                headline = title
            parts.append(html if len(html) >= len(c) * 0.3 else c)
        except Exception as e:  # noqa: BLE001
            logger.warning("html chunk %s failed: %s", i, e)
            parts.append(c)
    return "\n\n".join(parts).strip(), headline


class RealEstateBot:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.store = RealEstateStore()
        # WordPress(grace-moon.com) 발행 — 부동산봇 → '부동산'(8)
        self.blogger = None if test_mode else WordPressUploader(
            default_categories=[8],
            strip_ads_default=True,
            force_draft=auto_draft_enabled())
        self.telegram = (TelegramNotifier(os.getenv("TELEGRAM_BOT_TOKEN", ""),
                                          os.getenv("TELEGRAM_CHAT_ID", ""))
                         if TELEGRAM_ENABLED else None)
        logger.info("RealEstateBot init (test_mode=%s)", test_mode)

    def run(self) -> dict:
        result = {"success": False, "blog_url": None, "error": None}
        try:
            months = _recent_months(2)
            regions = config.ALL_REGIONS
            gu_to_group = {gu: group_of(code) for gu, code in regions.items()}
            with mcp_client.MCPClient() as client:
                report = build_report(self.store, regions, months,
                                      as_of=date.today().isoformat(),
                                      fetch_region=client.fetch_region)
                self._collect_extra(client, regions, months)
            syn = synthesize(self.store, regions, months[1])
            rollup = indicators.rollup_groups(
                report["per_gu"], syn["jeonse"], syn["officetel"],
                syn["officetel_rent"], gu_to_group)

            # 하이라이트를 권역별로 분류
            hbg = {}
            for h in report["highlights"]:
                hbg.setdefault(gu_to_group.get(h["gu"], "기타"), []).append(h)

            # 서울 상세 스코프 분리
            seoul_gu = {gu: g for gu, g in report["per_gu"].items()
                        if gu_to_group.get(gu) == "서울"}
            seoul_block = self._seoul_block(seoul_gu, hbg.get("서울", []), syn, rollup.get("서울"))

            national = {"new_total": report["seoul"]["new_total"],
                        "high_total": report["seoul"]["high_total"],
                        "high_pct": report["seoul"]["high_pct"],
                        "low_total": report["seoul"]["low_total"]}
            d = {"week_label": report["week_label"], "national": national,
                 "groups": rollup, "highlights_by_group": hbg, "seoul": seoul_block}

            comment = commentary.make_commentary({"national": national, "groups": {
                g: {"new_total": s["new_total"], "high_pct": s["high_pct"],
                    "avg_jeonse": s["avg_jeonse"]} for g, s in rollup.items()}})
            md = digest.build_digest(d)
            if comment:
                md += "\n\n## 시황 해석\n\n" + comment

            if national["new_total"] == 0:
                if self.telegram:
                    self.telegram.send_message("🏠 이번 주 전국 신규 신고 없음", parse_mode="HTML")
                result["success"] = True
                return result

            # 가장 뜨거운 구(전국 top mover) → 핫스팟 라벨
            hottest = None
            ranked = indicators.rank_regions(report["per_gu"])
            if ranked:
                hottest = ranked[0][0]
            if not self.test_mode:
                html, headline = _convert_html(md)
                title = publish_meta.build_title(date.today(), headline)
                labels = publish_meta.build_labels(rollup, hottest_gu=hottest)
                # 데이터 출처(국토부 실거래가)를 권위 있는 외부 링크로 첨부
                # (Rank Math outbound links + 데이터 투명성).
                up = self.blogger.upload_post(
                    title=title, content=html, labels=labels,
                    is_draft=False, is_markdown=False,
                    sources=[{
                        "title": "국토교통부 실거래가 공개시스템",
                        "url": "https://rt.molit.go.kr/",
                    }],
                )
                if not up["success"]:
                    raise RuntimeError(f"upload failed: {up.get('message')}")
                result["blog_url"] = up.get("url")
            result["success"] = True

            if self.telegram:
                link = f"<a href='{result['blog_url']}'>블로그</a>" if result["blog_url"] else "테스트"
                self.telegram.send_message(
                    f"🏠 <b>전국 아파트 시장 흐름</b>\n신규 {national['new_total']} · "
                    f"신고가 {national['high_total']}({national['high_pct']:.0f}%)\n{link}",
                    parse_mode="HTML")
        except Exception as e:  # noqa: BLE001
            logger.error("realestate bot error: %s", e)
            result["error"] = str(e)
            if self.telegram:
                try:
                    self.telegram.send_message(f"❌ 부동산 봇 실패: {e}", parse_mode="HTML")
                except Exception:
                    pass
        return result

    def _seoul_block(self, seoul_gu: dict, seoul_highlights: list, syn: dict,
                     seoul_rollup: dict) -> dict:
        """서울 상세 렌더용 입력. 전세가율·오피스텔은 서울 구만 필터."""
        from realestate_bot import config as _cfg
        seoul_names = set(_cfg.SEOUL_GU.keys())
        jeonse = {gu: r for gu, r in syn["jeonse"].items() if gu in seoul_names}
        rated = [r for r in jeonse.values() if r is not None]
        officetel = {gu: c for gu, c in syn["officetel"].items() if gu in seoul_names}
        officetel_rent = {gu: c for gu, c in syn["officetel_rent"].items() if gu in seoul_names}
        r = seoul_rollup or {"new_total": 0, "high_total": 0, "low_total": 0, "high_pct": 0.0}
        return {
            "per_gu": seoul_gu, "highlights": seoul_highlights,
            "jeonse": jeonse,
            "jeonse_seoul": round(sum(rated) / len(rated), 1) if rated else None,
            "officetel": officetel, "officetel_total": sum(officetel.values()),
            "officetel_rent": officetel_rent,
            "officetel_rent_total": sum(officetel_rent.values()),
            "officetel_rent_jeonse": syn.get("officetel_rent_jeonse", 0),
            "officetel_rent_wolse": syn.get("officetel_rent_wolse", 0),
            "new_total": r["new_total"], "high_total": r["high_total"],
            "low_total": r["low_total"], "high_pct": r["high_pct"],
        }

    def _collect_extra(self, client, regions: dict, months: list):
        """전세가율용 아파트 전월세는 전 지역, 오피스텔(매매+전월세)은 서울·경기·광역시만 적재.
        한 종류가 실패해도 나머지·본 디제스트는 진행(degrade)."""
        for gu, code in regions.items():
            grp = group_of(code)
            specs = [(client.fetch_rent, self.store.insert_new_rents, "apartment")]
            if grp != "세종":   # 세종 오피스텔은 표본 적어 제외(스펙 §5)
                specs += [(client.fetch_officetel_trades, self.store.insert_new, "officetel"),
                          (client.fetch_officetel_rent, self.store.insert_new_rents, "officetel")]
            for ym in months:
                for fetch, insert, ptype in specs:
                    try:
                        insert(fetch(code, ym), ptype)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("extra collect skip %s %s %s: %s", ptype, gu, ym, e)

    def backfill(self, months: int, skip_existing: bool = True,
                 max_consecutive_fails: int = None, fetch_region=None):
        """매매(transactions) 백필. 현재월은 미확정이라 제외하고 완료월만 적재."""
        max_fails = (max_consecutive_fails if max_consecutive_fails is not None
                     else config.BACKFILL_MAX_CONSECUTIVE_FAILS)
        all_months = _recent_months(months + 1)[1:]
        fetch = fetch_region                                  # 테스트 주입
        if fetch is not None:
            self._backfill_loop(all_months, skip_existing, max_fails, fetch,
                                self.store.insert_new, self.store.has_records_for_month)
            return
        with mcp_client.MCPClient() as client:                # 기본: 직접 MCP(한도 0)
            self._backfill_loop(all_months, skip_existing, max_fails, client.fetch_region,
                                self.store.insert_new, self.store.has_records_for_month)

    def backfill_rents(self, months: int, skip_existing: bool = True,
                       max_consecutive_fails: int = None, fetch_rent=None):
        """전월세(rents) 백필. 매매와 동일 구조, store 작업만 전월세용."""
        max_fails = (max_consecutive_fails if max_consecutive_fails is not None
                     else config.BACKFILL_MAX_CONSECUTIVE_FAILS)
        all_months = _recent_months(months + 1)[1:]
        if fetch_rent is not None:                            # 테스트 주입
            self._backfill_loop(all_months, skip_existing, max_fails, fetch_rent,
                                self.store.insert_new_rents,
                                self.store.has_rent_records_for_month, tag="[rent]")
            return
        with mcp_client.MCPClient() as client:
            self._backfill_loop(all_months, skip_existing, max_fails, client.fetch_rent,
                                self.store.insert_new_rents,
                                self.store.has_rent_records_for_month, tag="[rent]")

    def backfill_all(self, months: int, skip_existing: bool = True,
                     max_consecutive_fails: int = None):
        """아파트·오피스텔 × 매매·전월세 4종을 한 MCP 세션에서 전부 적재.
        각 종류는 독립 fail-fast 카운터 — 한 종류가 한도/미승인(403)으로 막혀도
        나머지는 진행되고 적재분은 보존된다(멱등 재개 가능)."""
        max_fails = (max_consecutive_fails if max_consecutive_fails is not None
                     else config.BACKFILL_MAX_CONSECUTIVE_FAILS)
        all_months = _recent_months(months + 1)[1:]
        s = self.store
        with mcp_client.MCPClient() as client:
            specs = [
                ("apartment", "[apt]", client.fetch_region,
                 s.insert_new, s.has_records_for_month),
                ("apartment", "[apt-rent]", client.fetch_rent,
                 s.insert_new_rents, s.has_rent_records_for_month),
                ("officetel", "[oftl]", client.fetch_officetel_trades,
                 s.insert_new, s.has_records_for_month),
                ("officetel", "[oftl-rent]", client.fetch_officetel_rent,
                 s.insert_new_rents, s.has_rent_records_for_month),
            ]
            for ptype, tag, fetch_fn, insert_m, has_m in specs:
                logger.info("=== backfill%s 시작 (property_type=%s) ===", tag, ptype)
                insert_fn = (lambda recs, m=insert_m, p=ptype: m(recs, p))
                has_fn = (lambda code, ym, m=has_m, p=ptype: m(code, ym, p))
                self._backfill_loop(all_months, skip_existing, max_fails,
                                    fetch_fn, insert_fn, has_fn, tag)

    def _backfill_loop(self, all_months, skip_existing, max_fails, fetch_fn,
                       insert_fn, has_fn, tag=""):
        consecutive_fails = 0
        for gu, code in config.ALL_REGIONS.items():  # 서울+경기+광역시+세종 전체
            for ym in all_months:
                if skip_existing and has_fn(code, ym):
                    logger.info("backfill%s cached %s %s (already loaded, skip fetch)", tag, gu, ym)
                    continue
                try:
                    recs = fetch_fn(code, ym)
                    n = len(insert_fn(recs))
                    logger.info("backfill%s %s %s: +%s", tag, gu, ym, n)
                    consecutive_fails = 0
                except Exception as e:  # noqa: BLE001
                    consecutive_fails += 1
                    logger.warning("backfill%s skip %s %s: %s", tag, gu, ym, e)
                    if consecutive_fails >= max_fails:
                        logger.error(
                            "backfill%s ABORTED: %s consecutive failures (한도/API 오류 추정). "
                            "적재분은 보존됨 — 회복 후 같은 명령으로 재개.",
                            tag, consecutive_fails)
                        return

    def run_scheduled(self):
        getattr(schedule.every(), config.SCHEDULE_DAY).at(config.SCHEDULE_TIME).do(self.run)
        logger.info("scheduled %s %s", config.SCHEDULE_DAY, config.SCHEDULE_TIME)
        while True:
            schedule.run_pending()
            time.sleep(60)


def main():
    p = argparse.ArgumentParser(description="Seoul weekly apartment market digest bot")
    p.add_argument("--once", action="store_true")
    p.add_argument("--test", action="store_true")
    p.add_argument("--backfill", type=int, metavar="MONTHS", help="아파트 매매")
    p.add_argument("--backfill-rents", type=int, metavar="MONTHS", dest="backfill_rents",
                   help="아파트 전월세")
    p.add_argument("--backfill-all", type=int, metavar="MONTHS", dest="backfill_all",
                   help="아파트·오피스텔 매매+전월세 4종 일괄")
    args = p.parse_args()

    boot = RealEstateBot(test_mode=args.test)
    if args.backfill_all:
        boot.backfill_all(args.backfill_all)
    elif args.backfill:
        boot.backfill(args.backfill)
    elif args.backfill_rents:
        boot.backfill_rents(args.backfill_rents)
    elif args.once:
        r = boot.run()
        print(f"Result: {'OK' if r['success'] else 'FAIL'} {r.get('blog_url') or r.get('error') or ''}")
    else:
        try:
            boot.run_scheduled()
        except KeyboardInterrupt:
            logger.info("stopped")


if __name__ == "__main__":
    main()
