#!/usr/bin/env python3
"""
统一入口脚本：输入股票/基金名称或代码，自动识别类型、获取数据、生成PDF报告

使用方式（单只分析）：
    python3 run_analysis.py 贵州茅台
    python3 run_analysis.py 600519

使用方式（多只对比）：
    python3 run_analysis.py 贵州茅台 五粮液 泸州老窖
    python3 run_analysis.py 510300 510500 159915
"""

import sys
import os
import json
import re
from datetime import datetime

# 确保在项目目录下运行
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from config import ETF_INDEX_MAP, MAX_COMPARE_COUNT
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


def _is_single_name(args: list) -> bool:
    """判断多个参数是否构成一个名称（如 "贵州 茅台" → 真，"贵州茅台 五粮液" → 假）"""
    # 如果只有一个参数，肯定是单个输入
    if len(args) <= 1:
        return True
    # 如果每个参数都像代码（纯数字或含.HK/.SH/.SZ），则是多个独立输入
    code_pattern = re.compile(r"^\d{5,6}(\.(?:SH|SZ|HK))?$", re.IGNORECASE)
    if all(code_pattern.match(a) for a in args):
        return False
    # 如果任一参数含中文且单独能构成证券名称（≥2个中文字符），视为多个独立输入
    cn_args = [a for a in args if re.search(r"[\u4e00-\u9fff]{2,}", a)]
    if len(cn_args) >= 2:
        return False
    # 否则视为一个名称的多个词（如 "沪深 300 ETF"）
    return True


def run_comparison(inputs: list):
    """对比模式：多只标的横向对比"""
    _print_banner()
    print("  📊 对比分析模式（%d 只标的）" % len(inputs))
    print()

    if len(inputs) > MAX_COMPARE_COUNT:
        print(f"✗ 最多同时对比 {MAX_COMPARE_COUNT} 只，当前输入了 {len(inputs)} 只")
        sys.exit(1)

    # 初始化 providers
    data_provider = get_data_provider()
    search_provider = get_search_provider()
    from identify_code_type import resolve_input

    # 逐个解析、识别、获取数据
    all_results = []  # [{ts_code, code_type, name, meta, data, data_file}, ...]

    for i, user_input in enumerate(inputs, 1):
        print("=" * 60)
        print(f"  标的 {i}/{len(inputs)}：「{user_input}」")
        print("=" * 60)

        # 解析
        try:
            ts_code = resolve_input(user_input)
        except ValueError as e:
            print(f"  ✗ 解析失败：{e}，跳过")
            continue
        print(f"  → 代码：{ts_code}")

        # 识别
        try:
            code_type, meta = data_provider.identify_security(ts_code)
        except ValueError as e:
            print(f"  ✗ 识别失败：{e}，跳过")
            continue

        stock_name = meta.get("name", ts_code)
        print(f"  → 类型：{code_type}　名称：{stock_name}")

        # 获取数据
        print(f"  → 正在获取数据...")
        if code_type == "etf":
            code_prefix = ts_code.split(".")[0]
            index_code = ETF_INDEX_MAP.get(code_prefix, "000300.SH")
            result = data_provider.fetch_etf_data(ts_code, index_code)
        elif code_type == "stock":
            result = data_provider.fetch_stock_data(ts_code)
        elif code_type == "hk_stock":
            result = data_provider.fetch_hk_stock_data(ts_code)
        else:
            print(f"  ✗ 不支持的类型：{code_type}，跳过")
            continue

        if not result:
            print(f"  ✗ 数据获取失败，跳过")
            continue

        # 互联网研究
        if code_type in ("stock", "hk_stock") and search_provider.is_available():
            try:
                market_label = "A股" if code_type == "stock" else "港股"
                research = search_provider.search_company(stock_name, ts_code, market_label)
                if research.get("status") == "success":
                    result["web_research"] = research
            except Exception:
                pass

        # 保存临时文件
        data_file = os.path.join(PROJECT_DIR, f"temp_{ts_code.replace('.', '_')}_data.json")
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        all_results.append({
            "ts_code": ts_code,
            "code_type": code_type,
            "name": stock_name,
            "meta": meta,
            "data": result,
            "data_file": data_file,
        })
        print(f"  ✓ 完成")
        print()

    if len(all_results) < 2:
        print(f"\n✗ 成功获取数据的标的不足2只（{len(all_results)}只），无法生成对比报告")
        sys.exit(1)

    # 判断对比类型
    types = [r["code_type"] for r in all_results]
    if len(set(types)) == 1:
        compare_type = types[0]  # 纯 etf / stock / hk_stock
    else:
        compare_type = "mixed"   # 混合对比

    # 生成对比报告
    print("=" * 60)
    print(f"  生成对比分析报告（{len(all_results)}只标的）")
    print("=" * 60)

    names = [r["name"] for r in all_results]
    date_str = datetime.now().strftime("%Y%m%d")
    output_filename = "_vs_".join(names) + f"_对比分析报告_{date_str}.pdf"
    output_path = os.path.join(PROJECT_DIR, output_filename)

    from step6_generate_comparison_pdf import create_comparison_pdf
    create_comparison_pdf(all_results, compare_type, output_path)

    # 完成
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  ✓ 对比报告生成完成！                                      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  标的：{'、'.join(names)}")
    print(f"  报告：{output_filename}")
    print(f"  路径：{output_path}")
    print()

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        _print_banner()
        print("用法：")
        print("  python3 run_analysis.py <名称或代码>           # 单只分析")
        print("  python3 run_analysis.py <标的1> <标的2> ...    # 多只对比（最多5只）")
        print()
        print("示例（单只）：")
        print("  python3 run_analysis.py 贵州茅台      # A股")
        print("  python3 run_analysis.py 600519        # A股代码")
        print("  python3 run_analysis.py 腾讯控股      # 港股")
        print("  python3 run_analysis.py 510300        # ETF")
        print()
        print("示例（对比）：")
        print("  python3 run_analysis.py 贵州茅台 五粮液 泸州老窖    # A股对比")
        print("  python3 run_analysis.py 510300 510500 159915        # ETF对比")
        print("  python3 run_analysis.py 比亚迪 00175.HK             # 跨市场对比")
        print()
        sys.exit(0)

    args = sys.argv[1:]

    # 判断是单个输入还是多个对比
    if _is_single_name(args):
        # 单只分析模式
        user_input = " ".join(args)
        run(user_input)
    else:
        # 多只对比模式
        run_comparison(args)
