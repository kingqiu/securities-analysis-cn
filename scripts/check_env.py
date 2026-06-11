#!/usr/bin/env python3
"""
Preflight checker for securities-analysis-cn.

It verifies local dependencies, .env configuration, output permissions, and
basic Chinese font availability without calling paid market-data APIs.
"""

from __future__ import annotations

import importlib
import os
import sys
import warnings
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_DIR / ".matplotlib-cache"))
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL.*")


REQUIRED_MODULES = [
    ("requests", "requests"),
    ("pandas", "pandas"),
    ("matplotlib", "matplotlib"),
    ("reportlab", "reportlab"),
    ("numpy", "numpy"),
    ("dotenv", "python-dotenv"),
    ("akshare", "akshare"),
]

OPTIONAL_MODULES = [
    ("efinance", "efinance", "ETF realtime quote first choice; AkShare fallback still works if unavailable"),
    ("yfinance", "yfinance", "HK daily price fallback after AkShare"),
]


FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",
    "/Library/Fonts/Arial Unicode MS.ttf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]


def _status(ok: bool, label: str, detail: str = "") -> bool:
    mark = "OK" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{mark}] {label}{suffix}")
    return ok


def _warn(label: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[WARN] {label}{suffix}")


def check_modules() -> bool:
    ok = True
    for module, package in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
            _status(True, f"Python package: {package}")
        except Exception as exc:
            ok = False
            _status(False, f"Python package: {package}", f"{type(exc).__name__}; install with: pip install -r {PROJECT_DIR / 'requirements.txt'}")

    for module, package, detail in OPTIONAL_MODULES:
        try:
            importlib.import_module(module)
            _status(True, f"Optional package: {package}")
        except Exception as exc:
            _warn(f"Optional package: {package}", f"{detail}; current issue: {type(exc).__name__}")
    return ok


def check_env_file() -> bool:
    env_path = PROJECT_DIR / ".env"
    example_path = PROJECT_DIR / ".env.example"
    if not env_path.exists():
        return _status(False, ".env file", f"copy from {example_path}")

    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        pass

    data_token = os.environ.get("TUSHARE_API_TOKEN", "").strip()
    llm_provider = os.environ.get("LLM_PROVIDER", "minimax").strip()
    search_provider = os.environ.get("SEARCH_PROVIDER", "auto").strip()
    tavily_key = (
        os.environ.get("TAVILY_API_KEY", "").strip()
        or os.environ.get("TAVILY_API_TOKEN", "").strip()
        or os.environ.get("TAVILY_TOKEN", "").strip()
        or os.environ.get("TAVILY_KEY", "").strip()
    )
    ok = True
    ok &= _status(bool(data_token), "TUSHARE_API_TOKEN", "required for market and financial data")

    if llm_provider == "minimax":
        key = os.environ.get("MINIMA_API_KEY", "").strip()
        _status(bool(key), "MINIMA_API_KEY", "optional; missing key falls back to rule-based advice")
    elif llm_provider == "openai":
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        _status(bool(key), "OPENAI_API_KEY", "optional; missing key falls back to rule-based advice")
    else:
        ok = False
        _status(False, "LLM_PROVIDER", "supported values: minimax, openai")

    if search_provider not in ("auto", "ai_summary", "tavily", "none"):
        ok = False
        _status(False, "SEARCH_PROVIDER", "supported values: auto, tavily, ai_summary, none")
    elif search_provider == "auto":
        has_tavily = bool(tavily_key)
        if has_tavily:
            _status(True, "TAVILY_API_KEY", "Tavily first; AI fallback if unavailable")
        else:
            _warn("TAVILY_API_KEY", "missing; SEARCH_PROVIDER=auto will use AI fallback")
    elif search_provider == "tavily":
        has_tavily = bool(tavily_key)
        if has_tavily:
            _status(True, "TAVILY_API_KEY", "Tavily first; AI fallback if unavailable")
        else:
            _warn("TAVILY_API_KEY", "missing; Tavily cannot run and AI fallback will be used")
    else:
        _status(True, "SEARCH_PROVIDER", search_provider)

    return bool(ok)


def check_fonts() -> bool:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return _status(True, "Chinese PDF font", path)
    return _status(False, "Chinese PDF font", "install a CJK font such as SimHei, STHeiti, or WenQuanYi Micro Hei")


def check_write_access() -> bool:
    probe = PROJECT_DIR / ".preflight_write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return _status(True, "Output directory writable", str(PROJECT_DIR))
    except OSError as exc:
        return _status(False, "Output directory writable", str(exc))


def main() -> int:
    print("securities-analysis-cn preflight check")
    print(f"Project: {PROJECT_DIR}")
    print()

    checks = [
        check_modules(),
        check_env_file(),
        check_fonts(),
        check_write_access(),
    ]

    print()
    if all(checks):
        print("All required checks passed. You can run: python3 run_analysis.py 贵州茅台")
        return 0

    print("Some checks failed. Fix the FAIL items above, then run this checker again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
