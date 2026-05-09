#!/usr/bin/env python3
"""
统一入口脚本：输入股票/基金名称或代码，自动识别类型、获取数据、生成PDF报告

使用方式：
    python3 run_analysis.py 贵州茅台
    python3 run_analysis.py 600519
    python3 run_analysis.py 腾讯控股
    python3 run_analysis.py 00700.HK
    python3 run_analysis.py 沪深300ETF
    python3 run_analysis.py 510300
"""

import sys
import os
import json
from datetime import datetime

# 确保在项目目录下运行
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from config import ETF_INDEX_MAP
from providers import get_data_provider, get_search_provider


def _print_banner():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║          A股/港股/ETF 财报分析报告自动生成器                ║")
    print("║                                                            ║")
    print("║  支持输入：代码（600519）或名称（贵州茅台）                 ║")
    print("║  输出：专业 PDF 深度分析报告                               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


def _generate_output_filename(stock_name: str, code_type: str) -> str:
    """生成输出文件名"""
    type_label = {
        "etf": "ETF深度分析报告",
        "stock": "股票深度分析报告",
        "hk_stock": "港股深度分析报告",
    }
    label = type_label.get(code_type, "分析报告")
    date_str = datetime.now().strftime("%Y%m%d")
    return f"{stock_name}_{label}_{date_str}.pdf"


def run(user_input: str):
    """主流程：解析 → 识别 → 获取数据 → 生成报告"""
    _print_banner()

    # 初始化 providers
    data_provider = get_data_provider()
    search_provider = get_search_provider()

    # ── 步骤1：解析用户输入，获取 ts_code ──
    print("=" * 60)
    print(f"步骤 1/4：解析输入「{user_input}」")
    print("=" * 60)
    try:
        from identify_code_type import resolve_input
        ts_code = resolve_input(user_input)
    except ValueError as e:
        print(f"\n✗ 错误：{e}")
        sys.exit(1)
    print(f"  → 证券代码：{ts_code}")

    # ── 步骤2：识别证券类型 ──
    print()
    print("=" * 60)
    print(f"步骤 2/4：识别证券类型")
    print("=" * 60)
    try:
        code_type, meta = data_provider.identify_security(ts_code)
    except ValueError as e:
        print(f"\n✗ 错误：{e}")
        sys.exit(1)

    stock_name = meta.get("name", ts_code)
    type_label = {"etf": "ETF基金", "stock": "A股股票", "hk_stock": "港股"}
    print(f"  → 类型：{type_label.get(code_type, code_type)}")
    print(f"  → 名称：{stock_name}")
    print(f"  → 详情：{meta}")

    # ── 步骤3：获取数据 ──
    print()
    print("=" * 60)
    print(f"步骤 3/4：获取数据")
    print("=" * 60)

    data_file = os.path.join(PROJECT_DIR, f"temp_{ts_code.replace('.', '_')}_data.json")

    if code_type == "etf":
        code_prefix = ts_code.split(".")[0]
        index_code = ETF_INDEX_MAP.get(code_prefix, "000300.SH")
        print(f"  → 跟踪指数：{index_code}")
        result = data_provider.fetch_etf_data(ts_code, index_code)
    elif code_type == "stock":
        result = data_provider.fetch_stock_data(ts_code)
    elif code_type == "hk_stock":
        result = data_provider.fetch_hk_stock_data(ts_code)
    else:
        print(f"✗ 不支持的类型：{code_type}")
        sys.exit(1)

    if not result:
        print("\n✗ 数据获取失败，请检查网络连接或代码是否正确")
        sys.exit(1)

    # 步骤3.5：互联网研究（通过 SearchProvider）
    if code_type in ("stock", "hk_stock") and search_provider.is_available():
        print(f"\n  → 正在进行互联网研究（{search_provider.name}）...")
        try:
            market_label = "A股" if code_type == "stock" else "港股"
            research = search_provider.search_company(stock_name, ts_code, market_label)
            if research.get("status") == "success":
                result["web_research"] = research
                print(f"  ✓ 互联网研究完成")
            else:
                print(f"  ○ {research.get('summary', '跳过')}")
        except Exception as e:
            print(f"  ○ 互联网研究跳过: {e}")

    # 保存数据到临时文件
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  → 数据已保存：{os.path.basename(data_file)}")

    # ── 步骤4：生成PDF报告 ──
    print()
    print("=" * 60)
    print(f"步骤 4/4：生成PDF报告")
    print("=" * 60)

    output_filename = _generate_output_filename(stock_name, code_type)
    output_path = os.path.join(PROJECT_DIR, output_filename)

    if code_type == "etf":
        from step3_generate_pdf_report import create_etf_pdf
        create_etf_pdf(data_file, output_path)
    elif code_type == "stock":
        from step4_generate_stock_pdf import create_stock_pdf
        create_stock_pdf(data_file, output_path)
    elif code_type == "hk_stock":
        from step5_generate_hk_stock_pdf import create_hk_stock_pdf
        create_hk_stock_pdf(data_file, output_path)

    # ── 完成 ──
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  ✓ 报告生成完成！                                          ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  证券：{stock_name}（{ts_code}）")
    print(f"  类型：{type_label.get(code_type, code_type)}")
    print(f"  报告：{output_filename}")
    print(f"  路径：{output_path}")
    print()

    # 清理临时数据文件（可选保留）
    # os.remove(data_file)

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        _print_banner()
        print("用法：")
        print("  python3 run_analysis.py <股票名称或代码>")
        print()
        print("示例：")
        print("  python3 run_analysis.py 贵州茅台      # 按名称搜索A股")
        print("  python3 run_analysis.py 600519        # A股代码")
        print("  python3 run_analysis.py 腾讯控股      # 按名称搜索港股")
        print("  python3 run_analysis.py 00700.HK      # 港股代码")
        print("  python3 run_analysis.py 沪深300ETF    # ETF名称")
        print("  python3 run_analysis.py 510300        # ETF代码（6位以5开头）")
        print()
        sys.exit(0)

    # 支持多个词连在一起作为名称（如 "贵州 茅台"）
    user_input = " ".join(sys.argv[1:])
    run(user_input)
