"""Report generation — weekly and monthly HTML reports."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from mimir.config import Config
from mimir.notion import NotionStore


def _period_start(period: str) -> datetime:
    now = datetime.now(UTC)
    if period == "month":
        return now.replace(day=1)
    return now - timedelta(days=now.weekday())


def generate(cfg: Config, store: NotionStore, *, period: str = "week") -> Path:
    ds_id = _resolve_ds_id(store, cfg.notion.entries_db_id)
    start = _period_start(period)
    entries = _fetch_entries(store, ds_id, start)

    prefix = "monthly" if period == "month" else "weekly"
    label = _label(start, period)
    path = Path(cfg.report.issues_dir) / f"{prefix}-{label}.html"
    path.parent.mkdir(parents=True, exist_ok=True)

    html = _render(entries, start, period)
    path.write_text(html, encoding="utf-8")
    print(f"Report: {path} ({len(entries)} entries)")

    if cfg.notion.reports_db_id:
        site_url = cfg.report.site_url.rstrip("/") if cfg.report.site_url else ""
        link_url = f"{site_url}/{path.name}" if site_url else str(path)
        _write_record(store, cfg.notion.reports_db_id, label, period, start, link_url, entries)
        print(f"Reports DB: record created for {label}")

    return path


def _label(start: datetime, period: str) -> str:
    if period == "month":
        return start.strftime("%Y-%m")
    iso = start.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _render(entries: list[dict], start: datetime, period: str) -> str:
    if period == "month":
        return _render_monthly(entries, start)
    return _render_weekly(entries, start)


# ═══════════ Weekly ═══════════

def _render_weekly(entries: list[dict], start: datetime) -> str:
    end = start + timedelta(days=6)
    iso = start.isocalendar()
    label = f"{iso[0]}-W{iso[1]:02d}"
    n = _counts(entries)
    td = _topic_dist(entries)
    hottest = td[0] if td else ("—", 0)
    high_n = sum(1 for e in entries if _pr(e, "Priority", "") == "★★★")

    # Top 8 signals, mixed types, by priority then recency
    signals = _pick_signals(entries, 8)

    # Signal rows
    signals_html = "".join(
        f'<div class="signal"><div class="s-dot dot-{_type_class(e)}"></div><div class="s-body">'
        f'<div class="s-type {_type_class(e)}">{_type_short(_tp(e))}</div>'
        f'<div class="s-title"><a href="{_pr(e,"Link","")}" target="_blank" style="color:inherit;text-decoration:none;">{_tl(e)}</a></div>'
        f'<div class="s-meta">{_pr(e,"Authors","")}{" · "+_pr(e,"Venue","") if _pr(e,"Venue","") else ""} · {_pr(e,"Published","")}'
        f'{" · ⭐"+str(_prn(e,"Stars")) if _prn(e,"Stars") else ""} · <span class="s-tag">{_pr(e,"Topic","")}</span></div>'
        f'</div></div>'
        for e in signals
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>AI 周报 {label}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  :root{{--text:#1a1a18;--t2:#5f5e5a;--t3:#9b9a97;--line:#e8e8e5;--bg:#fafafa;--card:#fff}}
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC",sans-serif;background:var(--bg);color:var(--text);line-height:1.5;max-width:680px;margin:0 auto;padding:48px 32px}}
  .header{{margin-bottom:32px}}
  .header .mast{{font-size:11px;font-weight:600;color:var(--t3);letter-spacing:1.5px}}
  .header h1{{font-size:32px;font-weight:700;letter-spacing:-.5px;margin-top:2px}}
  .header .date{{font-size:14px;color:var(--t3);margin-top:2px}}
  .kpi{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:32px}}
  .kpi .k{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px}}
  .kpi .k .v{{font-size:28px;font-weight:700;letter-spacing:-.5px}}
  .kpi .k .l{{font-size:11px;color:var(--t3);margin-top:2px}}
  .chart{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 20px;margin-bottom:32px}}
  #dist{{width:100%;height:160px}}
  .sec{{margin-bottom:36px}}
  .sec h2{{font-size:18px;font-weight:700;margin-bottom:4px}}
  .signal{{display:flex;gap:12px;align-items:flex-start;padding:14px 0;border-bottom:1px solid var(--line)}}
  .signal:last-child{{border-bottom:none}}
  .signal .s-dot{{width:8px;height:8px;border-radius:50%;margin-top:4px;flex-shrink:0}}
  .dot-paper{{background:#4664d9}}
  .dot-repo{{background:#2b8a4e}}
  .dot-news{{background:#c2780a}}
  .signal .s-body{{flex:1}}
  .signal .s-type{{font-size:10px;font-weight:600;margin-bottom:2px}}
  .paper{{color:#4664d9}} .repo{{color:#2b8a4e}} .news{{color:#c2780a}}
  .signal .s-title{{font-size:15px;font-weight:600;line-height:1.4}}
  .signal .s-meta{{font-size:11px;color:var(--t3);margin-top:2px}}
  .s-tag{{font-size:10px;padding:1px 5px;border-radius:3px;background:#f1f1ef;color:var(--t2)}}
  .footer{{margin-top:36px;padding-top:16px;border-top:1px solid var(--line);text-align:center;font-size:11px;color:var(--t3);display:flex;justify-content:center;gap:20px}}
</style></head><body>
<div class="header">
  <div class="mast">AI TECHNOLOGY RADAR · WEEKLY</div>
  <h1>AI 技术周报</h1>
  <div class="date">{label} · {start.strftime('%m/%d')} — {end.strftime('%m/%d')}</div>
</div>
<div class="kpi">
  <div class="k"><div class="v">{n[0]}</div><div class="l">本周新增</div></div>
  <div class="k"><div class="v" style="color:#e03e3e;">{hottest[0][:4] if len(hottest[0])>4 else hottest[0]}</div><div class="l">最热方向 · {hottest[1]}条</div></div>
  <div class="k"><div class="v">{high_n}</div><div class="l">High Priority</div></div>
</div>
<div class="chart"><div id="dist" style="width:100%;height:160px;"></div></div>
<div class="sec"><h2>本周关注</h2>{signals_html}</div>
<div class="footer">
  <span>📄 {n[1]}篇论文</span>
  <span>🛠️ {n[2]}个项目</span>
  <span>📰 {n[3]}条新闻</span>
  <span>周报 · 第 {iso[1]} 期</span>
</div>
<script>
var c=echarts.init(document.getElementById('dist'));
c.setOption({{tooltip:{{show:false}},grid:{{left:60,right:30,top:4,bottom:4}},xAxis:{{show:false}},yAxis:{{type:'category',data:{[t[0] for t in td][::-1]},axisLabel:{{fontSize:10,color:'#9b9a97'}},axisLine:{{show:false}},axisTick:{{show:false}}}},series:[{{type:'bar',barWidth:10,itemStyle:{{borderRadius:[0,3,3,0]}},data:{[t[1] for t in td][::-1]},label:{{show:true,position:'right',fontSize:10,color:'#5f5e5a',formatter:'{{c}}'}}}}]}});
</script></body></html>"""


# ═══════════ Monthly ═══════════

def _render_monthly(entries: list[dict], start: datetime) -> str:
    label = start.strftime("%Y年%m月")
    n = _counts(entries)
    td = _topic_dist(entries)
    hottest = td[0] if td else ("—", 0)

    signals = _pick_signals(entries, 5)

    # Trend line items
    trend = " · ".join(
        f'<span class="tl-item"><span class="tl-hot">{t[0]} ↗</span></span>' if i < 2 else
        f'<span class="tl-item"><span class="tl-flat">{t[0]} →</span></span>'
        for i, t in enumerate(td[:6])
    )

    # Signal cards
    signals_html = "".join(
        f'<div class="signal"><div class="s-num">{i+1:02d}</div><div class="s-body">'
        f'<div class="s-title"><span class="s-type st-{_type_class(e)}">{_type_short(_tp(e))}</span> <a href="{_pr(e,"Link","")}" target="_blank" style="color:inherit;text-decoration:none;">{_tl(e)}</a></div>'
        f'<div class="s-meta">{_pr(e,"Authors","")}{" · "+_pr(e,"Venue","") if _pr(e,"Venue","") else ""} · {_pr(e,"Published","")}'
        f'{" · ⭐"+str(_prn(e,"Stars")) if _prn(e,"Stars") else ""} · <span class="s-tag">{_pr(e,"Topic","")}</span></div>'
        f'<div class="s-summary">{_signal_summary(e)}</div>'
        f'</div></div>'
        for i, e in enumerate(signals)
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>AI 月报 {label}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  :root{{--text:#1a1a18;--t2:#5f5e5a;--t3:#9b9a97;--line:#e8e8e5;--bg:#fafafa;--card:#fff}}
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC",sans-serif;background:var(--bg);color:var(--text);line-height:1.5;max-width:680px;margin:0 auto;padding:48px 32px}}
  .header{{margin-bottom:36px}}
  .header .mast{{font-size:11px;font-weight:600;color:var(--t3);letter-spacing:1.5px}}
  .header h1{{font-size:32px;font-weight:700;letter-spacing:-.5px;margin-top:2px}}
  .header .date{{font-size:14px;color:var(--t3);margin-top:4px}}
  .kpi{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:36px}}
  .kpi .k{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px}}
  .kpi .k .v{{font-size:28px;font-weight:700;letter-spacing:-.5px}}
  .kpi .k .l{{font-size:11px;color:var(--t3);margin-top:2px}}
  .trendline{{display:flex;align-items:center;gap:10px;margin-bottom:36px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 20px}}
  .trendline .tl-label{{font-size:11px;font-weight:600;color:var(--t3);letter-spacing:.5px;min-width:48px}}
  .trendline .tl-items{{display:flex;gap:12px;flex:1;flex-wrap:wrap}}
  .trendline .tl-item{{font-size:12px}}
  .tl-hot{{color:#e03e3e;font-weight:600}}
  .tl-flat{{color:var(--t3)}}
  .chart{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 20px;margin-bottom:40px}}
  #dist{{width:100%;height:200px}}
  .sec{{margin-bottom:40px}}
  .sec h2{{font-size:18px;font-weight:700;margin-bottom:4px}}
  .sec .sub{{font-size:12px;color:var(--t3);margin-bottom:16px}}
  .signal{{display:flex;gap:14px;align-items:flex-start;padding:16px 0;border-bottom:1px solid var(--line)}}
  .signal:last-child{{border-bottom:none}}
  .signal .s-num{{font-size:20px;font-weight:800;color:#e8e8e5;min-width:36px;line-height:1}}
  .signal .s-body{{flex:1}}
  .signal .s-title{{font-size:15px;font-weight:700;line-height:1.4}}
  .signal .s-meta{{font-size:11px;color:var(--t3);margin:2px 0 4px}}
  .signal .s-summary{{font-size:13px;color:var(--t2);line-height:1.6;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
  .s-type{{display:inline-block;font-size:10px;font-weight:600;padding:1px 6px;border-radius:3px;margin-right:4px}}
  .st-paper{{background:#eef2ff;color:#4664d9}}
  .st-repo{{background:#eef9f0;color:#2b8a4e}}
  .st-news{{background:#fef9ee;color:#c2780a}}
  .s-tag{{font-size:10px;padding:1px 6px;border-radius:3px;background:#f1f1ef;color:var(--t2)}}
  a:hover{{text-decoration:underline!important}}
  .footer{{margin-top:40px;padding-top:16px;border-top:1px solid var(--line);text-align:center;font-size:11px;color:var(--t3);display:flex;justify-content:center;gap:20px}}
</style></head><body>
<div class="header">
  <div class="mast">AI TECHNOLOGY RADAR · MONTHLY</div>
  <h1>AI 技术月报</h1>
  <div class="date">{start.strftime('%Y年%m月')}</div>
</div>
<div class="kpi">
  <div class="k"><div class="v">{n[0]}</div><div class="l">收录</div></div>
  <div class="k"><div class="v" style="color:#e03e3e;">{hottest[0][:4] if len(hottest[0])>4 else hottest[0]} ↗</div><div class="l">最热方向 · {hottest[1]}条</div></div>
  <div class="k"><div class="v" style="color:#0f7b6c;">逼近</div><div class="l">开源 vs 闭源</div></div>
</div>
<div class="trendline">
  <div class="tl-label">🧭 趋势</div>
  <div class="tl-items">{trend}</div>
</div>
<div class="sec">
  <h2>📡 本月关键信号</h2>
  <div class="sub">5 个最值得关注的发展</div>
  {signals_html}
</div>
<div class="chart"><div id="dist" style="width:100%;height:200px;"></div></div>
<div class="footer">
  <span>📄 {n[1]}篇论文</span>
  <span>🛠️ {n[2]}个项目</span>
  <span>📰 {n[3]}条新闻</span>
  <span>月刊 · 第 {start.month} 期</span>
</div>
<script>
var c=echarts.init(document.getElementById('dist'));
c.setOption({{tooltip:{{show:false}},grid:{{left:60,right:30,top:4,bottom:4}},xAxis:{{show:false}},yAxis:{{type:'category',data:{[t[0] for t in td][::-1]},axisLabel:{{fontSize:10,color:'#9b9a97'}},axisLine:{{show:false}},axisTick:{{show:false}}}},series:[{{type:'bar',barWidth:10,itemStyle:{{borderRadius:[0,3,3,0]}},data:{[t[1] for t in td][::-1]},label:{{show:true,position:'right',fontSize:10,color:'#5f5e5a',formatter:'{{c}}'}}}}]}});
</script></body></html>"""


def _pick_signals(entries, n):
    """Pick top N cross-type entries, prioritizing high priority and topic diversity."""
    seen_topics = set()
    result = []
    high = [e for e in entries if _pr(e, "Priority", "") == "★★★"]
    high_ids = {id(e) for e in high}
    rest = [e for e in entries if id(e) not in high_ids]
    for e in high + rest:
        topic = _pr(e, "Topic", "")
        if topic not in seen_topics or len(result) < 2:
            result.append(e)
            seen_topics.add(topic)
        if len(result) >= n:
            break
    # Fill remaining if needed
    for e in rest:
        if len(result) >= n:
            break
        if e not in result:
            result.append(e)
    return result[:n]


def _signal_summary(e):
    """One-line summary for monthly signal cards."""
    sig = _pr(e, "Significance", "")
    if sig:
        return sig[:200]
    return _pr(e, "Overview", "")[:200] or _pr(e, "UseCase", "")[:200] or _pr(e, "KeyPoint", "")[:200]


def _type_class(e):
    t = _tp(e)
    if "论文" in t:
        return "paper"
    if "项目" in t:
        return "repo"
    return "news"


def _type_short(t):
    if "论文" in t:
        return "论文"
    if "项目" in t:
        return "项目"
    return "新闻"


# ═══════════ Shared helpers ═══════════

def _counts(entries):
    return (
        len(entries),
        sum(1 for e in entries if _tp(e) == "📄 论文"),
        sum(1 for e in entries if _tp(e) == "🛠️ 项目"),
        sum(1 for e in entries if _tp(e) == "📰 新闻"),
    )


def _topic_dist(entries):
    counts: dict[str, int] = {}
    for e in entries:
        t = _pr(e, "Topic") or "其他"
        counts[t] = counts.get(t, 0) + 1
    return sorted(counts.items(), key=lambda x: -x[1])[:10]


def _pr(page, name, default=""):
    p = page.get("properties", {}).get(name, {})
    t = p.get("type", "")
    if t == "rich_text":
        items = p.get("rich_text", [])
        return (items[0].get("plain_text", "") or default) if items else default
    if t == "select":
        s = p.get("select")
        return s["name"] if s else default
    if t == "title":
        return (p.get("title", [{}])[0].get("plain_text", "") or default)
    if t == "url":
        return p.get("url", default)
    if t == "date":
        d = p.get("date")
        return d.get("start", default)[:10] if d else default
    return default


def _prn(page, name):
    p = page.get("properties", {}).get(name, {})
    return int(p.get("number", 0) or 0)


def _tp(page):
    return _pr(page, "Type", "")


def _tl(page):
    return _pr(page, "Name", "(无标题)")


def _resolve_ds_id(store, db_id):
    store._rate_limit()
    resp = store.client.databases.retrieve(db_id)
    sources = resp.get("data_sources") or []
    if not sources:
        raise RuntimeError("Database has no data_sources")
    return sources[0]["id"]


def _fetch_entries(store, ds_id, since):
    results = []
    cursor = None
    since_iso = since.isoformat()
    while True:
        store._rate_limit()
        resp = store.client.data_sources.query(ds_id, page_size=100, start_cursor=cursor)
        for page in resp.get("results", []):
            pub_date = _pr(page, "Published", "")
            if pub_date and pub_date >= since_iso[:10]:
                results.append(page)
            elif not pub_date and page.get("created_time", "") >= since_iso:
                # Fallback to created_time if Published is missing
                results.append(page)
        cursor = resp.get("next_cursor")
        if not cursor:
            break
    return results


def _pick_highlights(entries, n: int = 5) -> str:
    """Pick top entries for the Highlights field, weighted by priority + content richness."""
    scored = []
    for e in entries:
        pri = _pr(e, "Priority", "")
        score = 3 if pri == "★★★" else 2 if pri == "★★" else 1 if pri == "★" else 0
        if _pr(e, "Significance", ""):
            score += 2
        if _pr(e, "Overview", "") or _pr(e, "KeyPoint", ""):
            score += 1
        scored.append((score, e))
    scored.sort(key=lambda x: -x[0])

    picked = []
    seen_topics: set[str] = set()
    for score, e in scored:
        if len(picked) >= n:
            break
        topic = _pr(e, "Topic", "")
        # Prefer topic diversity, but allow duplicates if score is high enough
        if topic in seen_topics and score < 4:
            continue
        seen_topics.add(topic)
        emoji = _tp(e)[:2] if _tp(e) else "•"
        title = _tl(e)[:60]
        picked.append(f"{emoji} {title}{'...' if len(_tl(e)) > 60 else ''}")
    return " · ".join(picked) if picked else ""


def _write_record(store, reports_db_id, label, period, start, link_url, entries):
    n = _counts(entries)
    td = _topic_dist(entries)
    hottest = td[0][0] if td else ""
    high_n = sum(1 for e in entries if _pr(e, "Priority", "") == "★★★")
    highlights = _pick_highlights(entries)

    props: dict[str, Any] = {
        "Name": {"title": [{"text": {"content": label}}]},
        "Date": {"date": {"start": start.strftime("%Y-%m-%d")}},
        "Period": {"select": {"name": "Weekly" if period == "week" else "Monthly"}},
        "Link": {"url": link_url},
        "Total": {"number": n[0]},
        "Papers": {"number": n[1]},
        "Repos": {"number": n[2]},
        "News": {"number": n[3]},
        "HighPriority": {"number": high_n},
        "Highlights": {"rich_text": [{"text": {"content": highlights[:500]}}]},
    }
    if hottest:
        props["Hottest"] = {"select": {"name": hottest}}

    store._rate_limit()
    store.client.pages.create(
        parent={"database_id": reports_db_id},
        properties=props,
    )
