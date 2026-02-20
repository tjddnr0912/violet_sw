"""
분석 명령어 Mixin

cmd_screening, cmd_signal, cmd_price
"""

import time
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from ._base import with_error_handling
from ..validators import InputValidator

logger = logging.getLogger(__name__)


class AnalysisCommandsMixin:
    """분석 명령어 모음"""

    @with_error_handling("스크리닝")
    async def cmd_screening(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """스크리닝 명령어"""
        await update.message.reply_text("🔍 스크리닝 실행 중... 잠시만 기다려주세요.")

        from src.api.kis_quant import KISQuantClient
        from src.strategy.quant import CompositeScoreCalculator, TechnicalAnalyzer

        client = KISQuantClient()
        score_calc = CompositeScoreCalculator()
        analyzer = TechnicalAnalyzer()

        rankings = client.get_market_cap_ranking(count=20)

        scores = []
        for r in rankings:
            if r.code.endswith("5"):
                continue

            try:
                ratio = client.get_financial_ratio_ext(r.code)
                momentum = client.calculate_momentum(r.code)

                score = score_calc.calculate(
                    code=r.code,
                    name=r.name,
                    per=ratio.per,
                    pbr=ratio.pbr,
                    roe=ratio.roe,
                    return_1m=momentum.return_1m,
                    return_3m=momentum.return_3m,
                    return_6m=momentum.return_6m,
                    return_12m=momentum.return_12m,
                    distance_from_high=momentum.distance_from_high,
                    volatility=momentum.volatility_20d,
                    market_cap=r.market_cap
                )

                if score.passed_filter:
                    prices = client.get_daily_prices(r.code, count=60)
                    closes = [p.close for p in prices]
                    tech = analyzer.analyze(closes)

                    scores.append({
                        "code": r.code,
                        "name": r.name,
                        "composite_score": score.composite_score,
                        "return_12m": momentum.return_12m,
                        "per": ratio.per,
                        "tech_score": tech.score,
                        "tech_signal": tech.signal_type.value,
                        "price": prices[0].close
                    })

                time.sleep(0.05)

            except Exception:
                continue

        scores.sort(key=lambda x: x["composite_score"], reverse=True)

        lines = [
            "🔍 <b>[스크리닝 결과]</b>",
            "━━━━━━━━━━━━━━━",
            f"• 분석: {len(rankings)}개 → 통과: {len(scores)}개",
            "━━━━━━━━━━━━━━━",
            ""
        ]

        for i, s in enumerate(scores[:8], 1):
            signal_emoji = {
                "STRONG_BUY": "🟢",
                "BUY": "🔵",
                "HOLD": "⚪",
                "SELL": "🟠",
                "STRONG_SELL": "🔴"
            }.get(s["tech_signal"], "⚪")

            lines.append(
                f"<b>{i}. {s['name']}</b> ({s['code']})\n"
                f"   복합: {s['composite_score']:.1f} | 기술: {signal_emoji} {s['tech_score']:.0f}\n"
                f"   PER: {s['per']:.1f} | 12M: {s['return_12m']:+.1f}%\n"
                f"   현재가: {s['price']:,}원"
            )

        lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await update.message.reply_text("\n".join(lines), parse_mode='HTML')

    @with_error_handling("기술적 분석")
    async def cmd_signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """기술적 분석 신호 명령어"""
        if not context.args:
            await update.message.reply_text("사용법: /signal [종목코드]\n예: /signal 005930")
            return

        stock_code = context.args[0]

        is_valid, error_msg = InputValidator.validate_stock_code(stock_code)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_msg}")
            return

        from src.api.kis_quant import KISQuantClient
        from src.strategy.quant import TechnicalAnalyzer

        client = KISQuantClient()
        analyzer = TechnicalAnalyzer()

        prices_data = client.get_daily_prices(stock_code, count=100)
        ratio = client.get_financial_ratio_ext(stock_code)

        closes = [p.close for p in prices_data]
        current_price = closes[0]

        signal = analyzer.analyze(closes)

        ma5 = analyzer.calculate_ma(closes, 5)
        ma20 = analyzer.calculate_ma(closes, 20)
        ma60 = analyzer.calculate_ma(closes, 60)

        if current_price > ma20 > ma60:
            trend = "상승 ↑"
        elif current_price < ma20 < ma60:
            trend = "하락 ↓"
        else:
            trend = "횡보 →"

        signal_emoji = {
            "STRONG_BUY": "🟢 강력매수",
            "BUY": "🔵 매수",
            "HOLD": "⚪ 관망",
            "SELL": "🟠 매도",
            "STRONG_SELL": "🔴 강력매도"
        }.get(signal.signal_type.value, "⚪")

        from src.core import get_controller
        controller = get_controller()
        stop_loss_pct = controller.config.stop_loss_pct
        take_profit_pct = controller.config.take_profit_pct

        stop_loss = int(current_price * (1 - stop_loss_pct / 100))
        take_profit = int(current_price * (1 + take_profit_pct / 100))

        message = (
            f"📊 <b>[기술적 분석] {ratio.name}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"• 현재가: <code>{current_price:,}원</code>\n"
            f"• 추세: <code>{trend}</code>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"• 신호: {signal_emoji}\n"
            f"• 점수: <code>{signal.score:.0f}/100</code>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"• RSI: <code>{signal.rsi:.1f}</code>\n"
            f"• MACD: <code>{signal.macd_signal}</code>\n"
            f"• MA: <code>{signal.ma_signal}</code>\n"
            f"• BB: <code>{signal.bb_signal}</code>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"• MA5: {ma5:,.0f} | MA20: {ma20:,.0f}\n"
            f"• 손절가: <code>{stop_loss:,}원</code> (-{stop_loss_pct:.0f}%)\n"
            f"• 익절가: <code>{take_profit:,}원</code> (+{take_profit_pct:.0f}%)"
        )

        await update.message.reply_text(message, parse_mode='HTML')

    @with_error_handling("시세 조회")
    async def cmd_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """시세 조회 명령어"""
        if not self.kis_client:
            await update.message.reply_text("❌ API 클라이언트가 연결되지 않았습니다.")
            return

        if not context.args:
            await update.message.reply_text("사용법: /price [종목코드]\n예: /price 005930")
            return

        stock_code = context.args[0]

        is_valid, error_msg = InputValidator.validate_stock_code(stock_code)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_msg}")
            return

        price = self.kis_client.get_stock_price(stock_code)

        change_emoji = "🔺" if price.change > 0 else ("🔻" if price.change < 0 else "➖")

        message = (
            f"📊 <b>{price.name}</b> ({price.code})\n"
            f"━━━━━━━━━━━━━━━\n"
            f"현재가: <code>{price.price:,}원</code>\n"
            f"전일비: {change_emoji} <code>{price.change:+,}원</code> ({price.change_rate:+.2f}%)\n"
            f"━━━━━━━━━━━━━━━\n"
            f"시가: {price.open:,}원\n"
            f"고가: {price.high:,}원\n"
            f"저가: {price.low:,}원\n"
            f"거래량: {price.volume:,}주"
        )

        await update.message.reply_text(message, parse_mode='HTML')
