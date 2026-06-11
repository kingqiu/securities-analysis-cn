#!/usr/bin/env python3
"""
Local setup helper for securities-analysis-cn.

It installs Python dependencies, creates .env from .env.example when missing,
and runs the preflight checker. It does not ask for or print API keys.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
REQUIREMENTS = PROJECT_DIR / "requirements.txt"
ENV_EXAMPLE = PROJECT_DIR / ".env.example"
ENV_FILE = PROJECT_DIR / ".env"


def _run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}")
    sys.stdout.flush()
    return subprocess.call(cmd, cwd=PROJECT_DIR)


def _check_python() -> bool:
    version = sys.version_info
    ok = version >= (3, 9)
    current = f"{version.major}.{version.minor}.{version.micro}"
    if ok:
        print(f"[OK] Python {current}")
    else:
        print(f"[FAIL] Python {current}; please use Python 3.9 or newer")
    return ok


def _ensure_env() -> None:
    if ENV_FILE.exists():
        print("[OK] .env already exists")
        return
    if not ENV_EXAMPLE.exists():
        print("[WARN] .env.example is missing; cannot create .env automatically")
        return
    shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
    print("[OK] created .env from .env.example")
    print("     Next: open .env and fill TUSHARE_API_TOKEN, TUSHARE_API_URL, and optional LLM/Tavily keys.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install dependencies and initialize securities-analysis-cn.")
    parser.add_argument("--skip-install", action="store_true", help="Do not run pip install; only create .env and check setup.")
    args = parser.parse_args()

    print("securities-analysis-cn setup")
    print(f"Project: {PROJECT_DIR}")
    print()

    if not _check_python():
        return 1

    if not args.skip_install:
        if not REQUIREMENTS.exists():
            print(f"[FAIL] missing {REQUIREMENTS}")
            return 1
        code = _run([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)])
        if code != 0:
            print("[FAIL] dependency installation failed")
            return code
    else:
        print("[SKIP] dependency installation")

    _ensure_env()
    print()
    print("Running preflight check...")
    return _run([sys.executable, str(PROJECT_DIR / "scripts" / "check_env.py")])


if __name__ == "__main__":
    sys.exit(main())
