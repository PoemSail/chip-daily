#!/usr/bin/env python3
"""
芯片日报 v2 — 多源聚合 + AI双阶段智能筛选
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 0 : 从所有源抓取原始条目（RSS / YouTube / Bilibili / WeChat / Twitter）
Phase 1 : DeepSeek 批量评分（仅发标题，~300 token，极省）
Phase 2 : DeepSeek 生成精选日报（top 条目，max 5000 token output）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os, re, sys, json, datetime, feedparser
from openai import OpenAI
from pathlib import Path

BEIJING_TZ = datetime.timezone(datetime.timedelta(hours=8))

# RSSHub 公共节点（如自建则改为自己的地址）
RSSHUB = os.environ.get("RSSHUB_BASE", "https://rsshub.app").rstrip("/")

# ══════════════════════════════════════════════════════
# 多源配置
# 新增源只需在此列表中添加一行即可
# ══════════════════════════════════════════════════════
SOURCES = [

    # ── 英文半导体专业媒体 ──────────────────────────────
    {"name": "EE Times",
     "url":  "https://www.eetimes.com/feed/"},
    {"name": "Semiconductor Engineering",
     "url":  "https://semiengineering.com/feed/"},
    {"name": "IEEE Spectrum",
     "url":  "https://spectrum.ieee.org/feeds/feed.rss"},
    {"name": "Tom's Hardware",
     "url":  "https://www.tomshardware.com/feeds/all"},
    {"name": "The Register Hardware",
     "url":  "https://www.theregister.com/hardware/headlines.atom"},
    {"name": "Electronic Design",
     "url":  "https://www.electronicdesign.com/rss"},
    {"name": "EE News Europe",
     "url":  "https://www.eenewseurope.com/rss/rss.xml"},
    {"name": "Ars Technica Tech Lab",
     "url":  "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"name": "AnandTech",
     "url":  "https://www.anandtech.com/rss/"},

    # ── 中文半导体媒体 ──────────────────────────────────
    {"name": "EE Times China",
     "url":  "https://www.eet-china.com/rss.xml"},
    {"name": "EEWORLD 新闻",
     "url":  "https://www.eeworld.com.cn/rss/news.xml"},
    {"name": "与非网",
     "url":  "https://www.eefocus.com/rss/article.xml"},
    {"name": "爱集微",
     "url":  "https://www.aijiwu.com/rss.xml"},

    # ── YouTube 半导体频道（原生 RSS，免费无限制）──────────
    # Asianometry：最权威的半导体供应链/地缘分析频道
    {"name": "Asianometry (YT)",
     "url":  "https://www.youtube.com/feeds/videos.xml?channel_id=UC1LpSxNMgBDgmMCDNABnbdA"},
    # IEEE Spectrum 官方频道
    {"name": "IEEE Spectrum (YT)",
     "url":  "https://www.youtube.com/feeds/videos.xml?channel_id=UCO_gBdHekc74feh0bWqKJ_A"},
    # Anton's Tech Corner：CPU/GPU 微架构深度分析
    {"name": "Anton's Tech Corner (YT)",
     "url":  "https://www.youtube.com/feeds/videos.xml?channel_id=UCB8bJo40yCiPdI9MdkX5cLg"},
    # EE Times 官方 YouTube
    {"name": "EE Times (YT)",
     "url":  "https://www.youtube.com/feeds/videos.xml?channel_id=UCP3bPuR8PADmZAqC7DpJUeA"},

    # ── Bilibili 半导体 UP主（via RSSHub）──────────────
    # 半导体行业观察（B站号 482904468，可按需更新）
    {"name": "半导体行业观察 (B站)",
     "url":  f"{RSSHUB}/bilibili/user/video/482904468"},
    # 芯片揭秘（B站号 1516793）
    {"name": "芯片揭秘 (B站)",
     "url":  f"{RSSHUB}/bilibili/user/video/1516793"},
    # 极客湾 Geekerwan（B站号 25876945，含芯片测评分析）
    {"name": "极客湾 (B站)",
     "url":  f"{RSSHUB}/bilibili/user/video/25876945"},

    # ── 微信公众号（via RSSHub，覆盖有限，按需添加）──────
    # 半导体行业观察（公众号 biz 编码）
    {"name": "半导体行业观察 (微信)",
     "url":  f"{RSSHUB}/wechat/mp/article/MzI3NDAzMTQzNA=="},
    # 芯谋研究
    {"name": "芯谋研究 (微信)",
     "url":  f"{RSSHUB}/wechat/mp/article/MzU1MDE4OTkwNg=="},
    # 集微网
    {"name": "集微网 (微信)",
     "url":  f"{RSSHUB}/wechat/mp/article/MzI1NTAyNjYzMg=="},

    # ── Twitter/X 半导体账号（via RSSHub，需公共节点可用）─
    {"name": "EETimes (X)",
     "url":  f"{RSSHUB}/twitter/user/EETimes"},
    {"name": "SemiEngineering (X)",
     "url":  f"{RSSHUB}/twitter/user/SemiEngineering"},
    {"name": "IEEESpectrum (X)",
     "url":  f"{RSSHUB}/twitter/user/IEEESpectrum"},
    # 芯片相关华人 KOL（可按需更换）
    {"name": "芯片观察室 (X)",
     "url":  f"{RSSHUB}/twitter/user/chipwatchcn"},
]

# ══════════════════════════════════════════════════════
# Phase 0  —  抓取原始条目
# ══════════════════════════════════════════════════════

def _parse_time(entry) -> datetime.datetime:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime.datetime(*val[:6], tzinfo=datetime.timezone.utc)
            except Exception:
                pass
    return datetime.datetime.now(datetime.timezone.utc)

def _strip(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()

def fetch_raw(hours: int = 24) -> list[dict]:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    raw: list[dict] = []

    for src in SOURCES:
        try:
            feed = feedparser.parse(src["url"])
            count = 0
            for e in feed.entries:
                pub = _parse_time(e)
                if pub < cutoff:
                    continue
                title   = _strip(e.get("title", ""))
                url     = e.get("link", "")
                summary = _strip(e.get("summary", e.get("description", "")))[:350]
                if not title or not url:
                    continue
                raw.append({
                    "title":   title,
                    "url":     url,
                    "summary": summary,
                    "source":  src["name"],
                    "time":    pub.astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M"),
                })
                count += 1
            if count:
                print(f"  [{src['name']}] {count} 条")
        except Exception as exc:
            # 非核心源（RSSHub）失败不影响主流程
            print(f"  [{src['name']}] 跳过: {exc}", file=sys.stderr)

    # 按 URL 去重，按时间降序
    seen: set[str] = set()
    result: list[dict] = []
    for item in sorted(raw, key=lambda x: x["time"], reverse=True):
        if item["url"] not in seen:
            seen.add(item["url"])
            result.append(item)

    print(f"\n  原始条目合计: {len(result)} 条")
    return result


# ══════════════════════════════════════════════════════
# Phase 1  —  AI 批量评分（仅用标题，极省 token）
# ══════════════════════════════════════════════════════

_SCORE_SYS = "你是半导体行业资深分析师，对行业动态有深刻理解。"

_SCORE_USER = """\
对下列新闻条目评估「与芯片/半导体行业的相关性与重要性」，输出纯 JSON 数组，\
不要任何额外文字。

评分标准（整数 1-10）：
10 — 重大技术突破或行业格局性事件（新晶体管架构、全球首发制程量产、重大政策出台）
8-9 — 重要公司战略/并购/重大融资/核心技术进展
6-7 — 常规产品发布/市场数据/行业分析
4-5 — 边缘相关（消费电子、软件、非核心芯片内容）
1-3 — 无关

输出格式示例（严格 JSON，键名 i=序号, s=分数）：
[{{"i":0,"s":9}},{{"i":1,"s":3}},{{"i":2,"s":7}}]

新闻列表：
{items}"""

def ai_score(raw: list[dict], client: OpenAI) -> list[dict]:
    """用极少 token 批量打分，过滤并排序"""
    if not raw:
        return []

    # 只发标题 + 来源，最省 token
    lines = "\n".join(
        f"[{i}] {it['title']} （来源：{it['source']}）"
        for i, it in enumerate(raw)
    )

    resp = client.chat.completions.create(
        model="deepseek-chat",
        max_tokens=len(raw) * 12 + 50,  # 每条约 10 token，留余量
        temperature=0.0,
        messages=[
            {"role": "system", "content": _SCORE_SYS},
            {"role": "user",   "content": _SCORE_USER.format(items=lines)},
        ],
    )

    raw_json = resp.choices[0].message.content.strip()
    # 有时模型会用 ```json ... ``` 包裹
    raw_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json).strip()

    try:
        scores = json.loads(raw_json)
        score_map = {s["i"]: s["s"] for s in scores}
    except Exception as e:
        print(f"  评分 JSON 解析失败: {e}，全部保留", file=sys.stderr)
        score_map = {i: 6 for i in range(len(raw))}

    for i, item in enumerate(raw):
        item["score"] = score_map.get(i, 0)

    # 保留评分 >= 6 的条目，按分数倒序，最多 20 条供下一阶段使用
    filtered = sorted(
        [it for it in raw if it.get("score", 0) >= 6],
        key=lambda x: x["score"],
        reverse=True,
    )[:20]

    print(f"  评分 >= 6 保留: {len(filtered)} 条（top score: {filtered[0]['score'] if filtered else 'N/A'}）")
    return filtered


# ══════════════════════════════════════════════════════
# Phase 2  —  生成日报（精准 token 控制）
# ══════════════════════════════════════════════════════

_REPORT_SYS = "你是「芯片日报」主编，文风专业、简洁，中文输出。"

_REPORT_USER = """\
今日日期：{date_str}（北京时间）

以下是经 AI 评分筛选的半导体行业新闻，评分越高越重要：

{news}

━━ 生成要求 ━━
1. 从中精选 **8-12 条**，宁缺毋滥，质量优先
2. 概览区每条一行：- 简短描述 [↗](URL) `#序号`
3. 正文每条 **3-5 句话**，直接陈述核心事实，不写废话
4. 数字用 **粗体**，技术术语用 `代码格式`
5. 分类（无内容则省略该节）：要闻 / 芯片设计 / 半导体制造 / 产业动态 / 技术前沿 / 政策法规
6. 严格遵守 Hugo frontmatter 格式

直接输出 Markdown，不要任何额外说明：

---
title: "{date_str}"
date: {date_str}T12:00:00+08:00
tags: ["daily"]
draft: false
---

# 芯片日报 {date_str}

## 概览

### 要闻
（2-4 条最高分新闻）

### （其他分类，无则删除）

---

## [新闻标题](URL) `#1`
> **一句话摘要（≤20字）**

正文 3-5 句。

相关链接：
- <URL>

---

（重复以上格式，最多 12 条）

---
**提示**：内容由 AI 辅助创作，请以原始来源为准。"""

_EMPTY = """\
---
title: "{date_str}"
date: {date_str}T12:00:00+08:00
tags: ["daily"]
draft: false
---

# 芯片日报 {date_str}

今日各源暂无符合标准的半导体行业资讯，请关注明日更新。

---
**提示**：内容由 AI 辅助创作，请以原始来源为准。
"""

def generate_report(items: list[dict], date_str: str, client: OpenAI) -> str:
    if not items:
        return _EMPTY.format(date_str=date_str)

    news_block = "\n\n".join(
        f"[评分 {it['score']}] {it['source']} | {it['time']}\n"
        f"标题: {it['title']}\n"
        f"摘要: {it['summary'][:280]}\n"
        f"链接: {it['url']}"
        for it in items
    )

    resp = client.chat.completions.create(
        model="deepseek-chat",
        max_tokens=5000,
        temperature=0.25,
        messages=[
            {"role": "system", "content": _REPORT_SYS},
            {"role": "user",   "content": _REPORT_USER.format(date_str=date_str, news=news_block)},
        ],
    )

    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", text).strip()
    return text


# ══════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════

def main():
    date_override = os.environ.get("DATE_OVERRIDE", "").strip()
    if date_override:
        try:
            today = datetime.datetime.strptime(date_override, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)
        except ValueError:
            print("日期格式错误，使用今日", file=sys.stderr)
            today = datetime.datetime.now(BEIJING_TZ)
    else:
        today = datetime.datetime.now(BEIJING_TZ)

    date_str = today.strftime("%Y-%m-%d")

    print(f"╔══ 芯片日报 v2 ══ {date_str} ══╗")

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    print("\n[Phase 0] 抓取各源内容...")
    raw = fetch_raw(hours=24)

    print("\n[Phase 1] AI 批量评分（仅用标题）...")
    scored = ai_score(raw, client)

    print("\n[Phase 2] 生成精选日报...")
    report = generate_report(scored, date_str, client)

    out_path = Path("content/posts") / f"{date_str}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    print(f"\n✅ 完成: {out_path}（{len(report)} 字符）")
    print(f"   Token 预估: Phase1 ~{len(raw)*8} + Phase2 ~{len(scored)*120 + 1200} ≈ {len(raw)*8 + len(scored)*120 + 1200}")


if __name__ == "__main__":
    main()
