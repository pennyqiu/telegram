#!/usr/bin/env python3
"""
KOL 雷达 · AI 分析（可选环节）

把 digest.py 产出的当日精简摘要（daily_digest_latest.md）自动推送给一个
OpenAI 兼容 / Anthropic 原生的大模型 API，生成结构化的当日分析，写成
Markdown + 简单 HTML 两份，方便直接在网站上浏览。

没配置 API Key 时不会报错中断 —— 会打印清晰的原因 + 手动方案（摘要文件本来就是
可以直接拖进任意 AI 对话框或用 @ 引用的格式），cron 照常继续跑完剩下步骤。

支持的供应商（通过 AI_API_BASE + AI_MODEL 切换，OpenAI 兼容协议即可，无需改代码）：
  OpenAI        AI_API_BASE=https://api.openai.com/v1        AI_MODEL=gpt-4o-mini
  DeepSeek      AI_API_BASE=https://api.deepseek.com/v1      AI_MODEL=deepseek-chat
  Moonshot/Kimi AI_API_BASE=https://api.moonshot.cn/v1       AI_MODEL=moonshot-v1-8k
  智谱GLM       AI_API_BASE=https://open.bigmodel.cn/api/paas/v4  AI_MODEL=glm-4-flash
  Claude(原生)  AI_API_STYLE=anthropic  AI_API_BASE=https://api.anthropic.com/v1  AI_MODEL=claude-3-5-haiku-20241022

用法：
  python3 ai_analyze.py                                              # 用默认路径 output/digest/daily_digest_latest.md
  python3 ai_analyze.py --input /var/www/kol-radar/digest/daily_digest_latest.md --out-dir /var/www/kol-radar/digest
"""

from __future__ import annotations

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SYSTEM_PROMPT = (
    "你是一名专注于 AI / 半导体 / 云计算 / 机器人产业的买方研究分析师，"
    "帮用户消化每天从多位行业 KOL 那里抓取的推文与 newsletter 原文。"
    "请用简体中文、Markdown 格式输出，包含以下几个部分：\n"
    "## 今日要点摘要（3-6条，每条一句话）\n"
    "## 值得关注的信号或观点分歧（不同博主之间有没有矛盾/呼应，是否有明显情绪或立场变化）\n"
    "## 提及的标的/公司及情绪方向（列出 cashtag 或公司名，标注偏多/偏空/中性，附一句依据）\n"
    "## 需要进一步跟踪的线索（有没有值得深挖的产品/数据/事件）\n"
    "只依据提供的原文内容分析，不要编造未提及的信息；如果某部分没有对应内容，写「暂无」。"
)


def _load_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _call_openai_style(base: str, key: str, model: str, content: str, timeout: int) -> str:
    url = base.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0.3,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read())
    return payload["choices"][0]["message"]["content"]


def _call_anthropic_style(base: str, key: str, model: str, content: str, timeout: int) -> str:
    url = base.rstrip("/") + "/messages"
    body = json.dumps({
        "model": model,
        "max_tokens": 4096,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": content}],
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read())
    return "".join(block.get("text", "") for block in payload.get("content", []))


def _simple_md_to_html(md: str) -> str:
    """极简 Markdown → HTML（够用即可：标题/粗体/换行），不引入额外依赖。"""
    import html as html_mod
    import re as re_mod
    lines = []
    for line in md.splitlines():
        esc = html_mod.escape(line)
        esc = re_mod.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        if esc.startswith("### "):
            lines.append(f"<h3>{esc[4:]}</h3>")
        elif esc.startswith("## "):
            lines.append(f"<h2>{esc[3:]}</h2>")
        elif esc.startswith("# "):
            lines.append(f"<h1>{esc[2:]}</h1>")
        elif esc.strip() == "":
            lines.append("<br>")
        else:
            lines.append(f"<p>{esc}</p>")
    body = "\n".join(lines)
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>KOL 雷达 · AI 每日分析</title>
<style>
body{{max-width:760px;margin:40px auto;padding:0 20px;font-family:-apple-system,"PingFang SC",sans-serif;
     line-height:1.7;color:#1a1a1a;background:#fafafa}}
h1,h2,h3{{color:#0f172a}}
h2{{border-bottom:2px solid #e2e8f0;padding-bottom:6px;margin-top:32px}}
strong{{color:#c2410c}}
p{{margin:6px 0}}
.meta{{color:#64748b;font-size:13px;margin-bottom:24px}}
</style></head><body>
<div class="meta">生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
{body}
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description="把当日摘要推送给大模型 API 生成分析（未配置 Key 则跳过并给出手动方案）")
    ap.add_argument("--input", default=str(ROOT / "output" / "digest" / "daily_digest_latest.md"),
                     help="输入的摘要 Markdown 文件")
    ap.add_argument("--out-dir", default="", help="分析结果输出目录（默认与输入文件同目录）")
    ap.add_argument("--timeout", type=int, default=90, help="API 请求超时秒数")
    args = ap.parse_args()

    _load_env()

    src = Path(args.input)
    if not src.exists():
        print(f"❌ 找不到摘要文件：{src}（先跑 digest.py --daily-json 生成）")
        sys.exit(1)
    content = src.read_text(encoding="utf-8")

    out_dir = Path(args.out_dir) if args.out_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    key = os.environ.get("AI_API_KEY", "").strip()
    base = os.environ.get("AI_API_BASE", "https://api.deepseek.com/v1").strip()
    model = os.environ.get("AI_MODEL", "deepseek-chat").strip()
    style = os.environ.get("AI_API_STYLE", "openai").strip().lower()

    if not key:
        print("⚠️  未配置 AI_API_KEY，跳过自动分析（不影响每日抓取本身）。")
        print(f"   手动方案：把这份摘要拖进任意 AI 对话框，或在 Cursor 里用 @ 引用直接问："
              f"\n   {src}")
        print("   想开启自动分析：在 kol_radar/.env 里配置 AI_API_KEY（+ 按需调整 AI_API_BASE/AI_MODEL），"
              "支持 DeepSeek / Moonshot / 智谱GLM / OpenAI 等任意 OpenAI 兼容接口，见 .env.example 注释。")
        return

    print(f"🤖 调用 {model}（{base}，{style} 协议）分析 {src.name}（{len(content)} 字符）...")
    try:
        if style == "anthropic":
            result = _call_anthropic_style(base, key, model, content, args.timeout)
        else:
            result = _call_openai_style(base, key, model, content, args.timeout)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:500] if hasattr(e, "read") else ""
        print(f"❌ AI API 调用失败：HTTP {e.code} {detail}")
        print(f"   摘要文件仍在：{src}，可以手动拖给 AI 分析。")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"❌ AI API 调用失败：{e}")
        print(f"   摘要文件仍在：{src}，可以手动拖给 AI 分析。")
        sys.exit(1)

    date_tag = datetime.now().strftime("%Y-%m-%d")
    md_path = out_dir / f"analysis_{date_tag}.md"
    md_path.write_text(result, encoding="utf-8")
    (out_dir / "analysis_latest.md").write_text(result, encoding="utf-8")

    html_str = _simple_md_to_html(result)
    (out_dir / f"analysis_{date_tag}.html").write_text(html_str, encoding="utf-8")
    (out_dir / "analysis_latest.html").write_text(html_str, encoding="utf-8")

    print(f"✅ 分析完成：{md_path}（固定入口：{out_dir / 'analysis_latest.html'}）")


if __name__ == "__main__":
    main()
