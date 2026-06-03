#!/usr/bin/env python3
"""주간 서울 아파트 시장 흐름 다이제스트 봇.

  python weekly_realestate_bot.py --once [--test]   # 즉시 1회 (test=업로드 스킵)
  python weekly_realestate_bot.py --backfill 36     # 25구 × N개월 초기 적재
  python weekly_realestate_bot.py                   # 스케줄 (토 08:00)
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

from realestate_bot import config, fetcher, indicators, commentary, digest, mcp_client
from realestate_bot.store import RealEstateStore
from realestate_bot.detector import classify
from shared.blogger_uploader import BloggerUploader
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


def _convert_html(md: str) -> str:
    """h2 청크 분할 후 Claude HTML 변환 (buffett 패턴)."""
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
    parts = []
    for i, c in enumerate(chunks, 1):
        try:
            html, _ = convert_md_to_html_via_claude(c)
            parts.append(html if len(html) >= len(c) * 0.3 else c)
        except Exception as e:  # noqa: BLE001
            logger.warning("html chunk %s failed: %s", i, e)
            parts.append(c)
    return "\n\n".join(parts).strip()


class RealEstateBot:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.store = RealEstateStore()
        self.blogger = None if test_mode else BloggerUploader(
            blog_id=config.REALESTATE_BLOGGER_BLOG_ID,
            credentials_path=os.getenv("BLOGGER_CREDENTIALS_PATH", "./credentials/blogger_credentials.json"),
            token_path=os.getenv("BLOGGER_TOKEN_PATH", "./credentials/blogger_token.pkl"))
        self.telegram = (TelegramNotifier(os.getenv("TELEGRAM_BOT_TOKEN", ""),
                                          os.getenv("TELEGRAM_CHAT_ID", ""))
                         if TELEGRAM_ENABLED else None)
        logger.info("RealEstateBot init (test_mode=%s)", test_mode)

    def run(self) -> dict:
        result = {"success": False, "blog_url": None, "error": None}
        try:
            months = _recent_months(2)
            # 데이터 수집은 직접 MCP 경로(Claude 한도 無). 세션 1개로 25구×2개월.
            # 시황 해석(Gemini)·HTML 변환(Claude)만 AI를 쓴다.
            with mcp_client.MCPClient() as client:
                report = build_report(self.store, config.SEOUL_GU, months,
                                      as_of=date.today().isoformat(),
                                      fetch_region=client.fetch_region)
            comment = commentary.make_commentary(
                {"seoul": report["seoul"],
                 "top": dict(list(indicators.rank_regions(report["per_gu"]))[:5])})
            md = digest.build_digest(report)
            if comment:
                md += "\n\n## 시황 해석\n\n" + comment

            if report["seoul"]["new_total"] == 0:
                if self.telegram:
                    self.telegram.send_message("🏠 이번 주 서울 신규 신고 없음", parse_mode="HTML")
                result["success"] = True
                return result

            title = f"{date.today():%Y-%m-%d} 서울 아파트 시장 흐름"
            if not self.test_mode:
                html = _convert_html(md)
                up = self.blogger.upload_post(title=title, content=html,
                                              labels=["부동산", "서울", "주간"],
                                              is_draft=False, is_markdown=False)
                if not up["success"]:
                    raise RuntimeError(f"upload failed: {up.get('message')}")
                result["blog_url"] = up.get("url")
            result["success"] = True

            if self.telegram:
                s = report["seoul"]
                link = f"<a href='{result['blog_url']}'>블로그</a>" if result["blog_url"] else "테스트"
                self.telegram.send_message(
                    f"🏠 <b>{title}</b>\n신규 {s['new_total']} · 신고가 {s['high_total']}"
                    f"({s['high_pct']:.0f}%)\n{link}", parse_mode="HTML")
        except Exception as e:  # noqa: BLE001
            logger.error("realestate bot error: %s", e)
            result["error"] = str(e)
            if self.telegram:
                try:
                    self.telegram.send_message(f"❌ 부동산 봇 실패: {e}", parse_mode="HTML")
                except Exception:
                    pass
        return result

    def backfill(self, months: int, skip_existing: bool = True,
                 max_consecutive_fails: int = None, fetch_region=None):
        max_fails = (max_consecutive_fails if max_consecutive_fails is not None
                     else config.BACKFILL_MAX_CONSECUTIVE_FAILS)
        # 현재월은 신고지연으로 미확정 + 데이터 거의 없음 → 백필 제외(주간 라이브 런이 담당).
        # 게다가 0건이라 has_records_for_month로 캐시되지 않아 재개 때마다 헛호출됨.
        # 가장 최근 '완료된' months개월만 적재한다.
        all_months = _recent_months(months + 1)[1:]
        if fetch_region is not None:  # 테스트 주입
            self._backfill_loop(all_months, skip_existing, max_fails, fetch_region)
            return
        # 기본: MCP 서버 직접 호출(Claude 우회 → 한도 0). 세션 1개로 전체 백필.
        with mcp_client.MCPClient() as client:
            self._backfill_loop(all_months, skip_existing, max_fails, client.fetch_region)

    def _backfill_loop(self, all_months, skip_existing, max_fails, fetch_region):
        consecutive_fails = 0
        for gu, code in config.SEOUL_GU.items():
            for ym in all_months:
                if skip_existing and self.store.has_records_for_month(code, ym):
                    logger.info("backfill cached %s %s (already loaded, skip fetch)", gu, ym)
                    continue
                try:
                    recs = fetch_region(code, ym)
                    n = len(self.store.insert_new(recs))
                    logger.info("backfill %s %s: +%s", gu, ym, n)
                    consecutive_fails = 0
                except Exception as e:  # noqa: BLE001
                    consecutive_fails += 1
                    logger.warning("backfill skip %s %s: %s", gu, ym, e)
                    if consecutive_fails >= max_fails:
                        logger.error(
                            "backfill ABORTED: %s consecutive failures (한도/API 오류 추정). "
                            "적재분은 보존됨 — 회복 후 같은 명령으로 재개.",
                            consecutive_fails)
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
    p.add_argument("--backfill", type=int, metavar="MONTHS")
    args = p.parse_args()

    boot = RealEstateBot(test_mode=args.test)
    if args.backfill:
        boot.backfill(args.backfill)
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
