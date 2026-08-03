"""Weekly Markdown status brief for bloasis (paper trading + mention tracker).

Reads:
- Alpaca paper account (ALPACA_PAPER_API_KEY / ALPACA_PAPER_API_SECRET from env)
- Local SQLite bloasis.db (paper_orders, mention_predictions, social_post_mentions)
- Recent cron log tail (logs/mentions-track.log)

Emits Markdown on stdout. Pushed to Telegram by scripts/weekly-report.sh.

Design mirrors bstalk3r/scripts/measure_paper.py but scoped to bloasis's two
current tracks:
  1. edgar-rolling2 paper session — Alpaca-side equity + FIFO realized + open
  2. mention forward-tracker — DB-side prediction counts + realized excess so far

Pure stdlib + alpaca-py + sqlalchemy. No I/O side effects beyond stdout.
"""

from __future__ import annotations

import os
import statistics
import sys
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest, GetPortfolioHistoryRequest
from sqlalchemy import create_engine, text

REPO = Path(__file__).resolve().parents[1]
DB_PATH = REPO / "bloasis.db"
CRON_LOG = REPO / "logs" / "mentions-track.log"
BACKTEST_REF = "edgar-rolling2 backtest: sharpe 1.334 · α +4.09%/yr · maxDD 0.80 (PR20)"
PR56_EDGE = "PR56 retrospective neg+OOT: +1.32% pooled (n=129, corrected +0.50% n=52 after tz fix)"


def _alpaca() -> TradingClient:
    key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY", "")
    sec = os.environ.get("ALPACA_PAPER_API_SECRET") or os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not sec:
        raise SystemExit("ALPACA_PAPER_API_KEY / ALPACA_PAPER_API_SECRET not set")
    return TradingClient(key, sec, paper=True)


def _paper_section(out: list[str]) -> None:
    """edgar-rolling2 paper trading via Alpaca API."""
    c = _alpaca()
    out.append("\n\n*━━━ Paper (edgar-rolling2) ━━━*")

    # equity curve
    ph = c.get_portfolio_history(GetPortfolioHistoryRequest(period="3M", timeframe="1D"))
    eq = [e for e in (ph.equity or []) if e]
    if len(eq) >= 2:
        rets = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq)) if eq[i - 1]]
        std = statistics.pstdev(rets) if len(rets) > 1 else 0.0
        sharpe = (statistics.mean(rets) / std) * (252**0.5) if std else 0.0
        peak = eq[0]
        mdd = 0.0
        for x in eq:
            peak = max(peak, x)
            mdd = min(mdd, x / peak - 1)
        out.append(
            f"*Equity* {len(eq)}d: ${eq[0]:,.0f} → ${eq[-1]:,.0f} "
            f"({(eq[-1] / eq[0] - 1) * 100:+.2f}%)"
        )
        out.append(
            f"vol {std * (252**0.5) * 100:.1f}% · Sharpe {sharpe:+.2f} · maxDD {mdd * 100:+.1f}%"
        )
        if len(eq) < 60:
            out.append(f"⚠️ {len(eq)}d small sample — expect regression toward backtest")

    # FIFO round-trips
    all_orders = c.get_orders(GetOrdersRequest(status=QueryOrderStatus.ALL, limit=500))
    orders = [o for o in all_orders if str(o.status.value) == "filled" and o.filled_avg_price]
    lots: dict[str, deque] = defaultdict(deque)
    realized: list[float] = []
    for o in sorted(orders, key=lambda x: x.submitted_at):
        qty = float(o.filled_qty)
        px = float(o.filled_avg_price)
        if o.side.value == "buy":
            lots[o.symbol].append([qty, px])
        else:
            remain = qty
            while remain > 1e-9 and lots[o.symbol]:
                lot = lots[o.symbol][0]
                take = min(remain, lot[0])
                realized.append((px - lot[1]) / lot[1])
                lot[0] -= take
                remain -= take
                if lot[0] <= 1e-9:
                    lots[o.symbol].popleft()
    out.append(f"\n*Fills* {len(orders)} filled / {len(all_orders)} total")
    if realized:
        wins = sum(1 for r in realized if r > 0) / len(realized) * 100
        out.append(
            f"*Round-trips* {len(realized)}: avg {statistics.mean(realized) * 100:+.2f}% · "
            f"win {wins:.0f}%"
        )
    else:
        out.append("*Round-trips* 0 — nothing exited yet (open lots below)")

    # open positions
    a = c.get_account()
    pos = c.get_all_positions()
    upl = sum(float(p.unrealized_pl) for p in pos)
    out.append(
        f"\n*Open* {len(pos)} · equity ${float(a.equity):,.0f} · "
        f"cash ${float(a.cash):,.0f} · uPnL ${upl:+,.0f}"
    )
    for p in sorted(pos, key=lambda p: -float(p.unrealized_plpc)):
        avg = float(p.avg_entry_price)
        now = float(p.current_price)
        plpc = float(p.unrealized_plpc) * 100
        out.append(f"  {p.symbol} avg ${avg:,.2f} → ${now:,.2f} ({plpc:+.1f}%)")
    out.append(f"_{BACKTEST_REF}_")


def _mention_section(out: list[str]) -> None:
    """Mention forward-tracker via local SQLite."""
    out.append("\n\n*━━━ Mention tracker ━━━*")
    if not DB_PATH.exists():
        out.append("_bloasis.db not found — skipping_")
        return
    # Cron started writing tracker rows on this date — anything older is
    # backfilled retrospective (PR57), not real forward data.
    CRON_START = "2026-06-05"
    q_versions = (
        "SELECT extractor_version, COUNT(*) FROM social_post_mentions GROUP BY extractor_version"
    )
    q_fwd_total = f"SELECT COUNT(*) FROM mention_predictions WHERE created_at >= '{CRON_START}'"
    q_fwd_settled = (
        f"SELECT COUNT(*) FROM mention_predictions "
        f"WHERE created_at >= '{CRON_START}' AND settled_at IS NOT NULL"
    )
    q_pending = "SELECT COUNT(*) FROM mention_predictions WHERE settled_at IS NULL"
    q_avg_realized = (
        f"SELECT AVG(realized_excess) FROM mention_predictions "
        f"WHERE created_at >= '{CRON_START}' AND realized_excess IS NOT NULL"
    )
    q_avg_predicted = (
        f"SELECT AVG(predicted_excess) FROM mention_predictions WHERE created_at >= '{CRON_START}'"
    )

    e = create_engine(f"sqlite:///{DB_PATH}")
    with e.connect() as c:
        vers = c.execute(text(q_versions)).fetchall()
        out.append("*Extraction*: " + " · ".join(f"v{v}={n}" for v, n in vers))

        fwd_total = c.execute(text(q_fwd_total)).scalar()
        fwd_settled = c.execute(text(q_fwd_settled)).scalar()
        pending = c.execute(text(q_pending)).scalar()
        out.append(
            f"*Forward preds* since 6/5: {fwd_total} written · "
            f"{fwd_settled} settled · {pending} pending"
        )

        if fwd_settled and fwd_settled > 0:
            avg_ex = c.execute(text(q_avg_realized)).scalar()
            avg_pred = c.execute(text(q_avg_predicted)).scalar()
            out.append(
                f"*Realized* excess: {avg_ex * 100:+.2f}% vs predicted {avg_pred * 100:+.2f}%"
            )
        else:
            out.append(f"*Realized* excess: — (0 forward settled yet; ref [[{PR56_EDGE}]])")

    # last 7 cron runs summary
    if CRON_LOG.exists():
        try:
            lines = CRON_LOG.read_text(errors="replace").splitlines()
            starts = [i for i, ln in enumerate(lines) if "mentions-track START" in ln]
            recent = starts[-7:]
            out.append(f"\n*Cron* last {len(recent)} runs:")
            for si in recent:
                ts = lines[si].split(" mentions-track")[0].replace("=====", "").strip()
                nearby = "\n".join(lines[si : si + 12])
                ex = "?"
                pr = "0"
                se = "0"
                for ln in nearby.splitlines():
                    if "extracted " in ln and " posts," in ln:
                        ex = ln.split("extracted ")[-1].split(" posts")[0]
                    if "predicted " in ln and " new" in ln:
                        pr = ln.split("predicted ")[-1].split(" new")[0]
                    if "settled " in ln and " ripe" in ln:
                        se = ln.split("settled ")[-1].split(" ripe")[0]
                out.append(f"  {ts[:16]}  ex={ex} pred={pr} settle={se}")
        except Exception as exc:  # noqa: BLE001
            out.append(f"_cron log parse failed: {exc}_")


def main() -> None:
    out: list[str] = []
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out.append(f"🧪 *Bloasis weekly* — {now}")
    errors: list[str] = []
    try:
        _paper_section(out)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"paper: {exc}")
    try:
        _mention_section(out)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"mention: {exc}")
    if errors:
        out.append("\n\n⚠️ *Errors*:")
        for e in errors:
            out.append(f"  {e}")
    print("\n".join(out))
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
