#!/usr/bin/env python3
"""Optional free market-data fallbacks.

These helpers supplement the configured Tushare-compatible source with public
quote/history endpoints. They are deliberately fail-open: missing packages,
network errors, schema drift, or anti-bot failures return empty results instead
of interrupting report generation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import requests


def _code_body(ts_code: str) -> str:
    code = (ts_code or "").strip().upper()
    if code.startswith("HK"):
        code = code[2:]
    if "." in code:
        code = code.split(".")[0]
    return code


def _hk_symbol(ts_code: str) -> str:
    return _code_body(ts_code).zfill(5)


def _hk_yfinance_symbol(ts_code: str) -> str:
    return _code_body(ts_code).lstrip("0").zfill(4) + ".HK"


def _six_digit(ts_code: str) -> str:
    return _code_body(ts_code).zfill(6)


def _a_tencent_symbol(ts_code: str) -> str:
    code = _six_digit(ts_code)
    if code.startswith(("6", "5", "9")):
        return f"sh{code}"
    return f"sz{code}"


def _safe_float(value: Any):
    try:
        if value in (None, "", "-", "--"):
            return None
        out = float(value)
        if pd.isna(out):
            return None
        return out
    except Exception:
        return None


def _safe_int(value: Any):
    val = _safe_float(value)
    return int(val) if val is not None else None


def _as_trade_date(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if "-" in text:
        return text.replace("-", "")[:8]
    return text[:8]


def _window_dates(days: int = 520) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _pick(row: Any, *names: str):
    for name in names:
        if name in row:
            value = row.get(name)
            if value not in (None, "", "-", "--"):
                return value
    return None


def _records_to_payload(fields: list[str], rows: list[list[Any]], source: str | None = None) -> dict:
    payload = {"fields": fields, "items": rows}
    if source:
        payload["source"] = source
    return payload


def _quote_payload(ts_code: str, source: str, row: Any, market: str) -> dict:
    return {
        "ts_code": ts_code,
        "market": market,
        "source": source,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "name": str(_pick(row, "名称", "股票名称", "name") or ""),
        "price": _safe_float(_pick(row, "最新价", "最新", "price")),
        "change_pct": _safe_float(_pick(row, "涨跌幅", "pct_chg", "change_pct")),
        "change_amount": _safe_float(_pick(row, "涨跌额", "change", "change_amount")),
        "volume": _safe_int(_pick(row, "成交量", "volume")),
        "amount": _safe_float(_pick(row, "成交额", "amount")),
        "turnover_rate": _safe_float(_pick(row, "换手率", "turnover_rate")),
        "amplitude": _safe_float(_pick(row, "振幅", "amplitude")),
        "open": _safe_float(_pick(row, "开盘价", "开盘", "open")),
        "high": _safe_float(_pick(row, "最高价", "最高", "high")),
        "low": _safe_float(_pick(row, "最低价", "最低", "low")),
        "pre_close": _safe_float(_pick(row, "昨收", "昨收价", "pre_close")),
        "pe": _safe_float(_pick(row, "市盈率", "市盈率-动态", "pe", "pe_ratio")),
        "pb": _safe_float(_pick(row, "市净率", "pb", "pb_ratio")),
        "total_mv": _safe_float(_pick(row, "总市值", "total_mv")),
        "circ_mv": _safe_float(_pick(row, "流通市值", "circ_mv")),
    }


def fetch_hk_daily(ts_code: str) -> dict | None:
    """Fetch HK daily bars from AkShare Eastmoney history."""
    try:
        import akshare as ak
    except Exception:
        return fetch_hk_daily_yfinance(ts_code)

    start_date, end_date = _window_dates()
    try:
        df = ak.stock_hk_hist(
            symbol=_hk_symbol(ts_code),
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
    except Exception:
        return fetch_hk_daily_yfinance(ts_code)
    if df is None or df.empty:
        return fetch_hk_daily_yfinance(ts_code)

    df = df.copy().sort_values("日期")
    fields = [
        "ts_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "change",
        "pct_chg",
        "vol",
        "amount",
        "turnover_rate",
    ]
    rows = []
    closes = pd.to_numeric(df.get("收盘"), errors="coerce")
    for idx, row in df.iterrows():
        close = _safe_float(row.get("收盘"))
        pre_close = _safe_float(closes.shift(1).get(idx))
        rows.append([
            ts_code,
            _as_trade_date(row.get("日期")),
            _safe_float(row.get("开盘")),
            _safe_float(row.get("最高")),
            _safe_float(row.get("最低")),
            close,
            pre_close,
            _safe_float(row.get("涨跌额")),
            _safe_float(row.get("涨跌幅")),
            _safe_float(row.get("成交量")),
            _safe_float(row.get("成交额")),
            _safe_float(row.get("换手率")),
        ])
    return _records_to_payload(fields, rows[-250:], "akshare_stock_hk_hist")


def fetch_hk_daily_yfinance(ts_code: str) -> dict | None:
    """Fetch HK daily bars from Yahoo Finance as a third fallback."""
    try:
        import yfinance as yf
    except Exception:
        return None

    start_date, _ = _window_dates()
    try:
        df = yf.download(
            _hk_yfinance_symbol(ts_code),
            start=datetime.strptime(start_date, "%Y%m%d").strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False,
            threads=False,
        )
    except Exception:
        return None
    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    df = df.reset_index().copy()
    fields = [
        "ts_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "change",
        "pct_chg",
        "vol",
        "amount",
        "turnover_rate",
    ]
    rows = []
    close_series = pd.to_numeric(df.get("Close"), errors="coerce")
    for idx, row in df.iterrows():
        close = _safe_float(row.get("Close"))
        pre_close = _safe_float(close_series.shift(1).get(idx))
        change = close - pre_close if close is not None and pre_close not in (None, 0) else None
        pct_chg = (change / pre_close * 100) if change is not None and pre_close else None
        rows.append([
            ts_code,
            _as_trade_date(row.get("Date")),
            _safe_float(row.get("Open")),
            _safe_float(row.get("High")),
            _safe_float(row.get("Low")),
            close,
            pre_close,
            round(change, 4) if change is not None else None,
            round(pct_chg, 4) if pct_chg is not None else None,
            _safe_float(row.get("Volume")),
            None,
            None,
        ])
    rows = [r for r in rows if r[1] and r[5] is not None]
    return _records_to_payload(fields, rows[-250:], "yfinance_hk_daily") if rows else None


def fetch_hk_realtime(ts_code: str) -> dict | None:
    """Fetch HK realtime quote from AkShare Eastmoney, with Sina fallback."""
    try:
        import akshare as ak
    except Exception:
        return None

    code = _hk_symbol(ts_code)
    for source, getter in (("akshare_hk_spot_em", ak.stock_hk_spot_em), ("akshare_hk_spot", ak.stock_hk_spot)):
        try:
            df = getter()
        except Exception:
            continue
        if df is None or df.empty or "代码" not in df.columns:
            continue
        matches = df[df["代码"].astype(str).str.zfill(5) == code]
        if matches.empty:
            continue
        quote = _quote_payload(ts_code, source, matches.iloc[0], "HK")
        return quote if quote.get("price") else None
    return None


def fetch_etf_daily(ts_code: str) -> dict | None:
    """Fetch A-share ETF daily bars from AkShare Eastmoney history."""
    try:
        import akshare as ak
    except Exception:
        return None

    start_date, end_date = _window_dates()
    code = _six_digit(ts_code)
    try:
        df = ak.fund_etf_hist_em(
            symbol=code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
    except Exception:
        return None
    if df is None or df.empty:
        return None

    df = df.copy().sort_values("日期")
    fields = [
        "ts_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "change",
        "pct_chg",
        "vol",
        "amount",
    ]
    rows = []
    closes = pd.to_numeric(df.get("收盘"), errors="coerce")
    for idx, row in df.iterrows():
        rows.append([
            ts_code,
            _as_trade_date(row.get("日期")),
            _safe_float(row.get("开盘")),
            _safe_float(row.get("最高")),
            _safe_float(row.get("最低")),
            _safe_float(row.get("收盘")),
            _safe_float(closes.shift(1).get(idx)),
            _safe_float(row.get("涨跌额")),
            _safe_float(row.get("涨跌幅")),
            _safe_float(row.get("成交量")),
            _safe_float(row.get("成交额")),
        ])
    return _records_to_payload(fields, rows[-250:], "akshare_fund_etf_hist_em")


def fetch_etf_realtime(ts_code: str) -> dict | None:
    """Fetch A-share ETF realtime quote from efinance first, then AkShare."""
    code = _six_digit(ts_code)

    try:
        import efinance as ef
        df = ef.stock.get_realtime_quotes(["ETF"])
        if df is not None and not df.empty:
            code_col = "股票代码" if "股票代码" in df.columns else "code"
            matches = df[df[code_col].astype(str).str.zfill(6) == code]
            if not matches.empty:
                quote = _quote_payload(ts_code, "efinance_etf", matches.iloc[0], "CN_ETF")
                if quote.get("price"):
                    return quote
    except Exception:
        pass

    try:
        import akshare as ak
        df = ak.fund_etf_spot_em()
        if df is not None and not df.empty and "代码" in df.columns:
            matches = df[df["代码"].astype(str).str.zfill(6) == code]
            if not matches.empty:
                quote = _quote_payload(ts_code, "akshare_fund_etf_spot_em", matches.iloc[0], "CN_ETF")
                if quote.get("price"):
                    return quote
    except Exception:
        pass
    return None


def fetch_a_realtime(ts_code: str) -> dict | None:
    """Fetch A-share realtime quote from AkShare Eastmoney."""
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
    except Exception:
        return fetch_a_realtime_tencent(ts_code)
    if df is None or df.empty or "代码" not in df.columns:
        return fetch_a_realtime_tencent(ts_code)
    code = _six_digit(ts_code)
    matches = df[df["代码"].astype(str).str.zfill(6) == code]
    if matches.empty:
        return fetch_a_realtime_tencent(ts_code)
    quote = _quote_payload(ts_code, "akshare_stock_zh_a_spot_em", matches.iloc[0], "CN_A")
    return quote if quote.get("price") else fetch_a_realtime_tencent(ts_code)


def fetch_a_realtime_tencent(ts_code: str) -> dict | None:
    """Fetch a lightweight single A-share quote from Tencent Finance."""
    symbol = _a_tencent_symbol(ts_code)
    try:
        resp = requests.get(
            "http://qt.gtimg.cn/q=" + symbol,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception:
        return None

    text = resp.text.strip()
    if not text or "~" not in text:
        return None
    try:
        payload = text.split('"', 1)[1].rsplit('"', 1)[0]
    except Exception:
        return None
    fields = payload.split("~")
    if len(fields) < 40:
        return None

    row = {
        "名称": fields[1] if len(fields) > 1 else "",
        "最新价": fields[3] if len(fields) > 3 else None,
        "昨收": fields[4] if len(fields) > 4 else None,
        "开盘": fields[5] if len(fields) > 5 else None,
        "成交量": fields[6] if len(fields) > 6 else None,
        "涨跌额": fields[31] if len(fields) > 31 else None,
        "涨跌幅": fields[32] if len(fields) > 32 else None,
        "最高": fields[33] if len(fields) > 33 else None,
        "最低": fields[34] if len(fields) > 34 else None,
        "成交额": _safe_float(fields[37]) * 10000 if len(fields) > 37 and _safe_float(fields[37]) is not None else None,
        "换手率": fields[38] if len(fields) > 38 else None,
        "市盈率": fields[39] if len(fields) > 39 else None,
        "总市值": _safe_float(fields[45]) * 100000000 if len(fields) > 45 and _safe_float(fields[45]) is not None else None,
        "流通市值": _safe_float(fields[44]) * 100000000 if len(fields) > 44 and _safe_float(fields[44]) is not None else None,
    }
    quote = _quote_payload(ts_code, "tencent_a_quote", row, "CN_A")
    return quote if quote.get("price") else None


def has_items(payload: dict | None) -> bool:
    return bool(payload and payload.get("items"))


def record_source(data: dict, source: str, status: str, detail: str = "") -> None:
    data.setdefault("free_market_data", []).append({
        "source": source,
        "status": status,
        "detail": detail,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    })
