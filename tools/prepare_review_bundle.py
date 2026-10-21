"""给已测试的分发目录附上简明入口、原验证分析和可离线浏览的示例。"""

from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path


def prepare(args):
    root = Path(__file__).resolve().parents[1]
    bundle = args.bundle.resolve()
    platform_check = args.checks.resolve()
    for folder in ("docs",):
        shutil.copytree(root / folder, bundle / folder, dirs_exist_ok=True)
    for name in ("README.md", "NOTICE.md", "requirements-runtime.txt"):
        shutil.copy2(root / name, bundle / name)
    validation = bundle / "validation"
    validation.mkdir(exist_ok=False)
    suite = root / "evidence/validation_20261021_v1"
    for name in ("summary.json", "per_case.csv", "protocol.json"):
        shutil.copy2(suite / name, validation / name)
    shutil.copy2(root / "docs/validation_panels.png", validation / "validation_panels.png")
    diagnostic = root / "evidence/improvement_review_20261021/readonly_analysis_final"
    for name in ("summary.json", "low_response_per_case.csv", "protocol.json"):
        shutil.copy2(diagnostic / name, validation / ("diagnostic_" + name))
    summary = json.loads((suite / "summary.json").read_text())
    table = "<table><tr><th>维度</th><th>对象数</th><th>最终一阶条件通过</th><th>形状 NMSE 中位数</th><th>时延 MAE / day</th><th>稳定性 WARN</th></tr>"
    for group in summary["groups"]:
        table += (
            f"<tr><td>{group['dimension']}D</td><td>{group['completed']}</td><td>{group['numerical_pass']}</td>"
            f"<td>{group['shape_nmse_median']:.6f}</td><td>{group['lag_mae_days']:.6f}</td>"
            f"<td>{group['floating_default_warn']}</td></tr>"
        )
    body = (
        "<p>复用原 144 例合成数据与结果，未重新求解。每维 3 种形态 × 3 种噪声 × 2 种缺测 × 4 个驱动。"
        "1D 为 16 时延点；2D 为 9 × 16 网格。二维 64/72 的历史包含中间求解失败标志。</p>"
        + table
        + "</table><p>最终一阶条件与浮动默认图像的稳定性分别记录。当前没有真实 AGN 验证。</p>"
        '<img src="validation_panels.png" alt="全部对象的恢复误差与警告">'
        '<p><a href="per_case.csv">逐对象 CSV</a> · <a href="summary.json">原汇总</a> · '
        '<a href="protocol.json">原协议</a> · <a href="diagnostic_summary.json">低响应区诊断</a></p>'
    )
    page = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>144 例合成验证</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:30px auto;padding:0 20px;color:#17283e}"
        "img{max-width:100%}table{border-collapse:collapse;width:100%}th,td{text-align:left;border-bottom:1px solid #ccc;padding:10px}</style>"
        "<h1>144 例合成验证</h1>" + body + "</html>"
    )
    (validation / "report.html").write_text(page, encoding="utf-8")
    smoke = platform_check / ("smoke" if args.platform == "windows" else "cli-smoke")
    for dimension in (1, 2):
        example = bundle / f"examples/{dimension}D"
        example.mkdir(parents=True)
        case = f"case_{dimension - 1:04d}"
        data, result = smoke / f"data/{case}", smoke / f"results/{case}"
        report = platform_check / f"report_{dimension}D"
        # 示例的数据、解和报告始终取自同一次平台检查。
        if args.platform == "macos":
            gui = json.loads((platform_check / "gui-flow.json").read_text())
            artifacts = Path(gui["artifacts"]) / f"{dimension}D"
            report = next(artifacts.glob("report_*"))
            data, result = next(artifacts.glob("*D_data_*")), next(artifacts.glob("mem_*"))
        identity = json.loads((data / "dataset.json").read_text())["observation_id"]
        assert identity == json.loads((result / "result.json").read_text())["observation_id"]
        assert identity == json.loads((report / "check.json").read_text())["observation_id"]
        for source, name in ((data, "data"), (result, "result")):
            shutil.copytree(source, example / name)
        shutil.copytree(report, example / "report")
    checks = bundle / "CHECKS"
    checks.mkdir()
    for name in ("validation.json", "gui-flow.json"):
        shutil.copy2(platform_check / name, checks / name)
    shutil.copy2(root / "evidence/improvement_review_20261021/tests_final.xml", checks / "unit_tests.xml")
    shutil.copy2(diagnostic / "summary.json", checks / "old_144_readonly_check.json")
    entry = "BLRWorkbench.exe" if args.platform == "windows" else "BLR MEM Workbench.app"
    text = (
        f"BLR MEM Workbench 0.1.0.dev1\n\n"
        f"1. 完整解压，双击 {entry}。无需安装 Python。\n"
        "2. 初次检查可设噪声比例为 0.05，生成数据。默认 0 仍保留无噪声真值。\n"
        "3. MEM 页自动填入数据目录，运行 MEM。\n"
        "4. 检测与报告页查看中文摘要，生成并打开报告。\n\n"
        "先看现成报告：examples/1D/report/report.html、examples/2D/report/report.html\n"
        "144 例验证分析：validation/report.html\n"
        "详细使用说明：docs/USAGE_ZH.md；交付与检查范围：docs/DELIVERY_ZH.md\n\n"
        "无噪声拟合需显式填写 C、L 误差下限，它们是拟合权重，可能影响恢复结果。\n"
        "二维浮动默认图像稳定性仍有 WARN；程序运行成功不代表完整科学验收。\n"
        "Windows 版已经在 Wine 中通过两维完整流程，真实 Windows 10/11 尚待检查者验收。\n"
        "Mac 版为 Apple Silicon，使用临时签名，未做 Apple 公证。\n"
    )
    (bundle / "START_HERE.txt").write_text(text, encoding="utf-8-sig")
    (bundle / "START_HERE.html").write_text(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>从这里开始</title>'
        "<style>body{font:16px/1.8 system-ui;max-width:860px;margin:40px auto;padding:0 20px}pre{white-space:pre-wrap}</style>"
        "<h1>BLR MEM 工作台</h1><pre>" + html.escape(text) + "</pre>"
        '<p><a href="examples/1D/report/report.html">一维示例</a> · <a href="examples/2D/report/report.html">二维示例</a> · '
        '<a href="validation/report.html">144 例验证分析</a></p></html>',
        encoding="utf-8",
    )
    print(bundle)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--checks", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "macos"), required=True)
    prepare(parser.parse_args())
