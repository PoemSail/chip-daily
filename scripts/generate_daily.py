#!/usr/bin/env python3
"""
芯片日报 - 每日内容自动生成脚本
每天北京时间12:00由 GitHub Actions 触发
收集过去24小时的全球芯片设计与半导体制造行业资讯
"""

import os
import re
import sys
import datetime
import feedparser
import anthropic
from pathlib import Path

# ──────────────────────────────────────────
# 配置
# ──────────────────────────────────────────

BEIJING_TZ = datetime.timezone(datetime.timedelta(hours=8))

# 半导体行业关键词，用于过滤无关新闻
KEYWORDS = [
    # 公司
    "TSMC", "台积电", "Intel", "英特尔", "Samsung", "三星", "NVIDIA", "英伟达",
    "AMD", "Qualcomm", "高通", "ASML", "Applied Materials", "Lam Research",
    "KLA", "Tokyo Electron", "TEL", "ASE", "日月光", "SK Hynix", "Micron",
    "美光", "Western Digital", "IMEC", "imec", "ARM", "安谋",
    "Broadcom", "博通", "MediaTek", "联发科", "SMIC", "中芯国际",
    "华虹", "长江存储", "长鑫存储", "华为海思", "紫光展锐",
    # 技术名词
    "chip", "semiconductor", "wafer", "fab", "foundry", "lithography",
    "EUV", "ArF", "immersion", "FinFET", "nanosheet", "GAA", "CFET",
    "process node", "nm process", "advanced packaging", "chiplet",
    "HBM", "DRAM", "NAND", "3D NAND", "LPDDR", "HBM3", "CoWoS",
    "SoIC", "FOPLP", "SiP", "2.5D", "3D IC", "TSV", "RDL",
    "EDA", "TCAD", "DFM", "OPC", "mask", "reticle", "photomask",
    "CMP", "CVD", "ALD", "PVD", "etching", "implantation",
    "transistor", "gate", "interconnect", "BEOL", "FEOL",
    # 产品类型
    "CPU", "GPU", "NPU", "APU", "SoC", "FPGA", "ASIC", "MCU",
    "AI chip", "AI accelerator", "memory", "storage chip",
    # 行业词汇（中文）
    "芯片", "半导体", "晶圆", "代工", "光刻", "制程", "封装", "先进制程",
    "集成电路", "存储器", "刻蚀", "沉积", "离子注入", "化学机械抛光",
    "良率", "产能", "扩产", "建厂", "出口管制", "芯片法案",
]

# RSS 新闻源配置
FEEDS = [
    {
        "name": "EE Times",
        "url": "https://www.eetimes.com/feed/",
        "lang": "en",
    },
    {
        "name": "Semiconductor Engineering",
        "url": "https://semiengineering.com/feed/",
        "lang": "en",
    },
    {
        "name": "IEEE Spectrum",
        "url": "https://spectrum.ieee.org/feeds/feed.rss",
        "lang": "en",
    },
    {
        "name": "Tom's Hardware",
        "url": "https://www.tomshardware.com/feeds/all",
        "lang": "en",
    },
    {
        "name": "The Register - Hardware",
        "url": "https://www.theregister.com/hardware/headlines.atom",
        "lang": "en",
    },
    {
        "name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "lang": "en",
    },
    {
        "name": "Electronic Design",
        "url": "https://www.electronicdesign.com/rss",
        "lang": "en",
    },
    {
        "name": "EE News",
        "url": "https://www.eenewseurope.com/rss/rss.xml",
        "lang": "en",
    },
    {
        "name": "EE Times China",
        "url": "https://www.eet-china.com/rss.xml",
        "lang": "zh",
    },
    {
        "name": "EEWORLD",
        "url": "https://www.eeworld.com.cn/rss/news.xml",
        "lang": "zh",
    },
]

# ──────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────

def is_related(title: str, summary: str = "") -> bool:
    """判断是否与芯片/半导体相关"""
    text = (title + " " + summary).lower()
    return any(kw.lower() in text for kw in KEYWORDS)

def parse_entry_time(entry) -> datetime.datetime:
    """解析 RSS 条目的发布时间，返回 UTC datetime"""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime.datetime(*val[:6], tzinfo=datetime.timezone.utc)
            except Exception:
                pass
    return datetime.datetime.now(datetime.timezone.utc)

def strip_html(text: str) -> str:
    """去除 HTML 标签"""
    return re.sub(r"<[^>]+>", "", text or "").strip()

def fetch_news(hours: int = 24) -> list[dict]:
    """
    从所有 RSS 源抓取过去 N 小时的相关新闻
    返回列表，每项含 title / url / summary / source / time
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    items = []

    for feed_cfg in FEEDS:
        try:
            print(f"  正在抓取 {feed_cfg['name']} ...", flush=True)
            feed = feedparser.parse(feed_cfg["url"])

            for entry in feed.entries:
                pub_time = parse_entry_time(entry)
                if pub_time < cutoff:
                    continue

                title = strip_html(entry.get("title", ""))
                raw_summary = entry.get("summary", entry.get("description", ""))
                summary = strip_html(raw_summary)[:600]
                url = entry.get("link", "")

                if not title or not url:
                    continue

                if is_related(title, summary):
                    items.append(
                        {
                            "title": title,
                            "url": url,
                            "summary": summary,
                            "source": feed_cfg["name"],
                            "lang": feed_cfg["lang"],
                            "time": pub_time.astimezone(BEIJING_TZ).strftime(
                                "%Y-%m-%d %H:%M"
                            ),
                        }
                    )
        except Exception as exc:
            print(f"  警告：{feed_cfg['name']} 抓取失败 — {exc}", file=sys.stderr)

    # 去重（按 URL）并按时间降序排列
    seen_urls: set[str] = set()
    deduped = []
    for item in sorted(items, key=lambda x: x["time"], reverse=True):
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            deduped.append(item)

    return deduped[:35]  # 最多 35 条原料，供 Claude 筛选


# ──────────────────────────────────────────
# 日报生成
# ──────────────────────────────────────────

REPORT_PROMPT = """你是「芯片日报」的资深主编，专注于全球芯片设计与半导体制造行业。
今天日期：{date_str}（北京时间）

以下是今天从各大行业媒体收集到的原始新闻（共 {count} 条）：

{news_context}

请将这些新闻整理成一份专业的中文日报。严格按照下面的 Hugo Markdown 格式输出，
不要输出任何额外解释，只输出 Markdown 本身：

---
title: "{date_str}"
date: {date_str}T12:00:00+08:00
tags: ["daily"]
draft: false
---

# 芯片日报 {date_str}

## 概览

### 要闻
（选出 2-4 条今天最重要的新闻，格式：- 新闻标题简短描述 [↗](完整URL) `#序号`）

### 芯片设计
（EDA工具、架构创新、新芯片发布、IP授权等，无则删除此节）

### 半导体制造
（工艺制程、光刻、刻蚀、封装、良率、产能、设备等，无则删除此节）

### 产业动态
（投融资、并购、合作、产能扩张、新厂建设等，无则删除此节）

### 技术前沿
（学术论文、技术突破、标准制定等，无则删除此节）

### 政策法规
（出口管制、补贴政策、监管动向等，无则删除此节）

---

（下面逐条展开，按重要性排列，最多 15 条，格式如下）

## [新闻标题](完整URL) `#1`
> **一句话摘要**（20字内，点明核心信息）

3-6 句话的中文详细说明。重要数字用**粗体**，关键技术术语用 `代码格式`。
内容要专业、准确，不是简单翻译，而是提炼核心信息并给出行业背景。

相关链接：
- <完整URL>

---

（重复上述格式直到展开所有选定条目）

---

**提示**：内容由 AI 辅助创作，请以原始来源为准。

要求：
1. 所有正文必须是中文，技术术语可保留英文
2. 严格按照 frontmatter 格式，title 和 date 不能错
3. 从原始新闻中挑选最重要、最具代表性的 10-15 条展开
4. 概览节的序号 #1, #2... 必须与下方展开条目序号对应
5. 不要虚构或夸大任何信息，如原文不详则如实说"细节待披露"
"""

EMPTY_REPORT_TEMPLATE = """\
---
title: "{date_str}"
date: {date_str}T12:00:00+08:00
tags: ["daily"]
draft: false
---

# 芯片日报 {date_str}

今日各大媒体暂未检索到新的芯片与半导体行业重要资讯，请关注明日更新。

---

**提示**：内容由 AI 辅助创作，请以原始来源为准。
"""


def build_news_context(items: list[dict]) -> str:
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(
            f"[{i}] 来源：{item['source']} ({item['time']})\n"
            f"    标题：{item['title']}\n"
            f"    摘要：{item['summary'][:400]}\n"
            f"    链接：{item['url']}"
        )
    return "\n\n".join(lines)


def generate_report(items: list[dict], date_str: str) -> str:
    if not items:
        print("  未找到相关新闻，生成占位日报。")
        return EMPTY_REPORT_TEMPLATE.format(date_str=date_str)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = REPORT_PROMPT.format(
        date_str=date_str,
        count=len(items),
        news_context=build_news_context(items),
    )

    print(f"  调用 Claude 生成日报（原始新闻 {len(items)} 条）...", flush=True)
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    content = msg.content[0].text.strip()

    # 去掉 Claude 可能包裹的 ```markdown ... ``` 代码块
    content = re.sub(r"^```(?:markdown)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)

    return content.strip()


# ──────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────

def main():
    # 支持手动触发时传入日期覆盖
    date_override = os.environ.get("DATE_OVERRIDE", "").strip()
    if date_override:
        try:
            today = datetime.datetime.strptime(date_override, "%Y-%m-%d")
            today = today.replace(tzinfo=BEIJING_TZ)
        except ValueError:
            print(f"日期格式错误: {date_override}，使用今天日期。", file=sys.stderr)
            today = datetime.datetime.now(BEIJING_TZ)
    else:
        today = datetime.datetime.now(BEIJING_TZ)

    date_str = today.strftime("%Y-%m-%d")

    print(f"=== 芯片日报生成器 ===")
    print(f"日期：{date_str}（北京时间）")
    print("开始抓取新闻...")

    items = fetch_news(hours=24)
    print(f"找到 {len(items)} 条相关新闻\n")

    report = generate_report(items, date_str)

    # 写入 Hugo 内容目录
    posts_dir = Path("content/posts")
    posts_dir.mkdir(parents=True, exist_ok=True)
    output_path = posts_dir / f"{date_str}.md"
    output_path.write_text(report, encoding="utf-8")

    print(f"\n✅ 日报已生成：{output_path}（{len(report)} 字符）")


if __name__ == "__main__":
    main()
