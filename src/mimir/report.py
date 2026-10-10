"""Report generation — the monthly HTML report.

Every number, arrow and highlight in the output is derived from the entries in
the reporting window; nothing is hardcoded. The window itself comes from
``mimir.periods`` and is always a complete month, and membership is decided
against the ``Collected`` date (when Mimir ingested the item), which is the same
basis the Notion "new today" views use.
"""

from __future__ import annotations

import html
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from litellm import completion
from notion_client.errors import APIResponseError

from mimir.config import Config, LLMConfig
from mimir.enrich import _parse_response
from mimir.notion import SOURCE_OTHER, _priority_label, _topic_label, infer_source
from mimir.periods import Period, cst_today, period_bounds

# The catch-all topic is also where unclassified entries land, so it is excluded
# from "hottest direction" and reported separately instead.
CATCH_ALL_TOPIC = _topic_label("industry")

# Derived from notion.py so the labels cannot drift apart from what is stored.
PRIORITY_WEIGHT = {
    _priority_label("high"): 3,
    _priority_label("medium"): 2,
    _priority_label("low"): 1,
}

TOPIC_SHORT = {
    _topic_label("ai_agent"): "Agent",
    _topic_label("rag"): "RAG",
    _topic_label("inference"): "推理",
    _topic_label("training"): "训练",
    _topic_label("safety"): "安全",
    _topic_label("infra"): "基础设施",
    _topic_label("ai_coding"): "AI Coding",
    _topic_label("open_models"): "开源",
    _topic_label("multimodal"): "多模态",
    CATCH_ALL_TOPIC: "行业",
}

KIND_LABEL = {"paper": "论文", "repo": "项目", "news": "新闻"}

# A topic counts as trending only if the move is worth noticing in absolute
# terms AND meaningful relative to its own baseline.
TREND_MIN_DELTA = 3
TREND_RATIO = 0.20

# The three tiers the chart ranks by. Ordered strongest-first, which is also the
# order the rows are listed in: the chart reads as one slope from the biggest
# gain down to the biggest drop, and the tier needs no header row of its own.
TIER_UP, TIER_FLAT, TIER_DOWN = "up", "flat", "down"
TIER_ORDER = (TIER_UP, TIER_FLAT, TIER_DOWN)
TIER_LABEL = {TIER_UP: "升温", TIER_FLAT: "平稳", TIER_DOWN: "降温"}

# Headlines are the month's biggest stories, cross-type, ranked by _sort_key.
# No per-type quota: scoring already balances the types on its own.
HEADLINES = 6

# Used only for rows collected before the Source property existed.
UNKNOWN_SOURCE = SOURCE_OTHER


# ═══════════ Result types ═══════════


class ReportStore(Protocol):
    """The slice of :class:`~mimir.notion.NotionStore` report generation needs.

    Narrow on purpose: it is also the shape a test double has to satisfy.
    """

    client: Any

    def _rate_limit(self) -> None: ...


@dataclass(frozen=True)
class TrendItem:
    name: str
    short: str
    count: int
    prev: int
    arrow: str

    @property
    def direction(self) -> str:
        return {"↗": "up", "↘": "down"}.get(self.arrow, "flat")


@dataclass(frozen=True)
class TopicRow:
    """One topic as the table shows it: the move, and what the topic is made of.

    ``papers``/``repos`` are counts, not shares — the renderer puts them on one
    shared scale so the two columns can be compared across rows.
    """

    name: str
    short: str
    count: int
    prev: int
    delta: int
    arrow: str
    tier: str
    papers: int
    repos: int


@dataclass(frozen=True)
class Headline:
    """One entry under 重大事件. ``why`` is the LLM's line when there is one,
    and the entry's own stored summary when there is not."""

    kind: str
    title: str
    link: str
    meta: list[str]
    why: str
    topic: str

    @property
    def kind_label(self) -> str:
        return KIND_LABEL.get(self.kind, "新闻")


@dataclass(frozen=True)
class Digest:
    """The 综述. Two paragraphs on purpose: one long block is a wall of text."""

    lead: str = ""
    body: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.lead.strip() or self.body.strip())


@dataclass(frozen=True)
class Stats:
    window: Period
    total: int
    papers: int
    repos: int
    news: int
    prev_total: int
    high_priority: int
    topic_counts: list[tuple[str, int]]
    trend: list[TrendItem]
    hottest: TrendItem | None
    unclassified: int
    #: Distinct values of the *stored* Source property. Empty until the backfill
    #: runs, which is why the footer only names a source count once it is real.
    sources: list[tuple[str, int]]

    @property
    def source_count(self) -> int:
        return len(self.sources)

    @property
    def unclassified_pct(self) -> int:
        return round(100 * self.unclassified / self.total) if self.total else 0


# ═══════════ Entry point ═══════════


def generate(
    cfg: Config,
    store: ReportStore,
    *,
    run_date: date | None = None,
    anchor: date | None = None,
) -> Path:
    """Render the report for the resolved month and publish its Notion record."""
    window = period_bounds(run_date=run_date or cst_today(), anchor=anchor)

    ds_id = _resolve_ds_id(store, cfg.notion.entries_db_id)
    current, previous = _fetch_window(store, ds_id, window)
    stats = _compute_stats(current, previous, window)
    rows = _topic_rows(current, previous)
    headlines = [_headline_view(p) for p in _pick_headlines(current, window=window)]

    # The 综述 is written against exactly these headlines, so the two blocks
    # cannot end up describing different months.
    digest, why = _summarize(cfg.llm, stats, rows, headlines)
    headlines = [
        replace(headline, why=why[i] or headline.why) if i < len(why) else headline
        for i, headline in enumerate(headlines)
    ]

    path = Path(cfg.report.issues_dir) / f"monthly-{window.label}.html"
    path.parent.mkdir(parents=True, exist_ok=True)

    notion_url = ""
    if cfg.notion.reports_db_id:
        site_url = cfg.report.site_url.rstrip("/") if cfg.report.site_url else ""
        # Notion's url property rejects a bare filesystem path, and the write
        # happens before the file does — so with no site_url there is no link to
        # record, only a path on this machine, which is not a URL.
        link_url = f"{site_url}/{path.name}" if site_url else ""
        reports_ds_id = _resolve_ds_id(store, cfg.notion.reports_db_id)
        action, page_id = _write_record(
            store, cfg.notion.reports_db_id, reports_ds_id, window, stats, rows, headlines, link_url
        )
        if page_id:
            notion_url = f"https://www.notion.so/{page_id.replace('-', '')}"
        print(f"Reports DB: record {action} for {window.label}")

    path.write_text(_render(window, stats, rows, digest, headlines, notion_url), encoding="utf-8")
    print(f"Report: {path} ({stats.total} entries · {window})")
    return path


# ═══════════ Fetching ═══════════


def _resolve_ds_id(store: ReportStore, db_id: str) -> str:
    """Resolve a database's data source id (2025 API)."""
    store._rate_limit()
    resp = store.client.databases.retrieve(db_id)
    sources = resp.get("data_sources") or []
    if not sources:
        raise RuntimeError("Database has no data_sources")
    return sources[0]["id"]


def _fetch_window(
    store: ReportStore, ds_id: str, window: Period
) -> tuple[list[dict], list[dict]]:
    """Fetch the entries in ``window`` and in the period before it.

    The two windows are contiguous, so one scan covers both. The server-side
    filter is only a page-count optimisation: membership is decided client-side
    by :func:`_collected_date`, so an API that refuses the filter degrades to a
    slower scan rather than to a wrong report.
    """
    lower = window.prev_start.isoformat()
    upper = window.end.isoformat()

    pages, filtered = _query(
        store,
        ds_id,
        filter_={
            "and": [
                {"property": "Collected", "date": {"on_or_after": lower}},
                {"property": "Collected", "date": {"on_or_before": upper}},
            ]
        },
        sorts=[{"property": "Collected", "direction": "descending"}],
    )
    if filtered:
        # A server-side filter hides entries with no Collected date, so ask for
        # them explicitly and keep the Published/created_time fallback alive.
        # If *this* query is rejected too, _query hands back a full scan, which
        # already contains every in-window row — extending with it would put each
        # of them in the list twice and double every number on the page.
        extra, honoured = _query(
            store, ds_id, filter_={"property": "Collected", "date": {"is_empty": True}}
        )
        pages = pages + extra if honoured else extra

    # Defence in depth: a page id twice is never right, whatever the API did.
    seen: set[str] = set()
    unique: list[dict] = []
    for page in pages:
        pid = page.get("id")
        if pid and pid in seen:
            continue
        if pid:
            seen.add(pid)
        unique.append(page)
    pages = unique

    current: list[dict] = []
    previous: list[dict] = []
    for page in pages:
        day = _collected_date(page)
        if day is None:
            continue
        if window.start <= day <= window.end:
            current.append(page)
        elif window.prev_start <= day <= window.prev_end:
            previous.append(page)
    return current, previous


def _query(
    store: ReportStore, ds_id: str, *, filter_: dict, sorts: list[dict] | None = None
) -> tuple[list[dict], bool]:
    """Run one paginated query. Returns (pages, server_filter_honoured)."""
    try:
        return _paginate(store, ds_id, filter_=filter_, sorts=sorts), True
    except APIResponseError as exc:
        print(f"  ! data_sources.query rejected the filter ({exc}); falling back to a full scan")
        return _paginate(store, ds_id, filter_=None, sorts=None), False


def _paginate(
    store: ReportStore, ds_id: str, *, filter_: dict | None, sorts: list[dict] | None
) -> list[dict]:
    results: list[dict] = []
    cursor: str | None = None
    while True:
        kwargs: dict = {"page_size": 100}
        if filter_ is not None:
            kwargs["filter"] = filter_
        if sorts:
            kwargs["sorts"] = sorts
        if cursor:
            kwargs["start_cursor"] = cursor
        store._rate_limit()
        resp = store.client.data_sources.query(ds_id, **kwargs)
        results.extend(resp.get("results", []))
        cursor = resp.get("next_cursor")
        if not cursor:
            return results


def _collected_date(page: dict) -> date | None:
    """The date an entry belongs to: Collected, else Published, else created."""
    for raw in (
        _pr(page, "Collected"),
        _pr(page, "Published"),
        page.get("created_time", ""),
    ):
        if raw:
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                continue
    return None


# ═══════════ Statistics ═══════════


def _compute_stats(entries: list[dict], prev_entries: list[dict], window: Period) -> Stats:
    """Derive everything the renderers show. Pure: no I/O, deterministic."""
    kinds = Counter(_kind(e) for e in entries)
    prev_topics = Counter(_topic_of(e) for e in prev_entries)
    topics = Counter(_topic_of(e) for e in entries)
    ordered = sorted(topics.items(), key=lambda kv: (-kv[1], kv[0]))

    trend = [
        TrendItem(
            name=name,
            short=_short_topic(name),
            count=count,
            prev=prev_topics.get(name, 0),
            arrow=_trend_arrow(count, prev_topics.get(name, 0)),
        )
        for name, count in ordered
    ]
    hottest = next((item for item in trend if item.name != CATCH_ALL_TOPIC), None)

    # Stored values only. The inferred fallback would report four "sources" that
    # are really just the four entry types, which is not what a source count means.
    sources = Counter(s for s in (_pr(e, "Source") for e in entries) if s)
    return Stats(
        window=window,
        total=len(entries),
        papers=kinds["paper"],
        repos=kinds["repo"],
        news=kinds["news"],
        prev_total=len(prev_entries),
        high_priority=sum(1 for e in entries if _pr(e, "Priority", "") == _priority_label("high")),
        topic_counts=ordered,
        trend=trend,
        hottest=hottest,
        unclassified=topics.get(CATCH_ALL_TOPIC, 0),
        sources=sorted(sources.items(), key=lambda kv: (-kv[1], kv[0])),
    )


def _trend_arrow(count: int, prev: int) -> str:
    """▲/▼ only when the move clears both an absolute and a relative floor."""
    delta = count - prev
    if delta >= TREND_MIN_DELTA and delta >= TREND_RATIO * prev:
        return "↗"
    if delta <= -TREND_MIN_DELTA and delta <= -TREND_RATIO * prev:
        return "↘"
    return "→"


def _topic_of(page: dict) -> str:
    return _pr(page, "Topic") or CATCH_ALL_TOPIC


def _short_topic(name: str) -> str:
    return TOPIC_SHORT.get(name, name)


def _source_of(page: dict) -> str:
    """Which collector produced the entry.

    ``Source`` is authoritative once present; older rows fall back to
    :func:`~mimir.notion.infer_source`, which uses the entry type because the
    link alone is not enough — Hacker News stores the external article URL.

    The two are not the same kind of fact, and nothing here can tell them apart:
    a value written by ``scripts/backfill_source.py`` is an inference that has
    been promoted to a stored one. That matters to the *count* in the footer,
    which is deliberately stored-values-only — see ``_compute_stats``.
    """
    return _pr(page, "Source") or infer_source(_tp(page), _pr(page, "Link"))


# ═══════════ Topic table ═══════════


def _tier_of(arrow: str) -> str:
    return {"↗": TIER_UP, "↘": TIER_DOWN}.get(arrow, TIER_FLAT)


def _topic_rows(entries: list[dict], prev_entries: list[dict]) -> list[TopicRow]:
    """The month's real topics, strongest move first.

    The catch-all is excluded: ``行业动态`` is where unclassified entries land,
    so it measures the classifier, not the world. Its share is reported in the
    footer instead.

    Ordering is tier, then ``delta`` descending, so the table reads top to
    bottom as one slope — biggest gain down to biggest drop.
    """
    topics = Counter(_topic_of(e) for e in entries)
    before = Counter(_topic_of(e) for e in prev_entries)
    kinds: dict[str, Counter] = defaultdict(Counter)
    for entry in entries:
        kinds[_topic_of(entry)][_kind(entry)] += 1

    rows = []
    for name, count in topics.items():
        if name == CATCH_ALL_TOPIC:
            continue
        prev = before.get(name, 0)
        arrow = _trend_arrow(count, prev)
        rows.append(
            TopicRow(
                name=name,
                short=_short_topic(name),
                count=count,
                prev=prev,
                delta=count - prev,
                arrow=arrow,
                tier=_tier_of(arrow),
                papers=kinds[name]["paper"],
                repos=kinds[name]["repo"],
            )
        )
    rows.sort(key=lambda row: (TIER_ORDER.index(row.tier), -row.delta, row.name))
    return rows


def _pct(value: int, scale: int) -> float:
    """Share of a shared scale. A zero scale is 0%, never a ZeroDivisionError."""
    return 100.0 * value / scale if scale > 0 else 0.0


def _tier_scale(rows: list[TopicRow]) -> int:
    """One scale for every trend bar: the largest move sets the width."""
    return max((abs(row.delta) for row in rows), default=0)


def _kind_scale(rows: list[TopicRow]) -> int:
    """One scale shared by the 论文 and 项目 columns, so they compare."""
    return max((max(row.papers, row.repos) for row in rows), default=0)


# ═══════════ Headline selection ═══════════


def _score(page: dict, window: Period) -> int:
    score = PRIORITY_WEIGHT.get(_pr(page, "Priority", ""), 0)
    if _summary_of(page):
        score += 2
    if any(_pr(page, f) for f in _SUMMARY_FIELDS):
        score += 1

    day = _collected_date(page)
    if day is not None and window.end > window.start:
        position = (day - window.start).days / (window.end - window.start).days
        score += 2 if position >= 0.75 else 1 if position >= 0.25 else 0

    if _kind(page) == "repo" and _prn(page, "Stars") >= 1000:
        score += 1
    return score


_SUMMARY_FIELDS = ("Significance", "Overview", "UseCase", "KeyPoint")


def _summary_of(page: dict) -> str:
    for field in ("Significance", "Overview", "UseCase", "KeyPoint"):
        text = _pr(page, field)
        if text:
            return text
    return ""


def _sort_key(page: dict, window: Period) -> tuple:
    """Score, then recency, then title, then link.

    The last two keys exist to make the order *total*. Without them two entries
    tying on score and day fall back to whatever order the API returned, which
    decides which of them survives the cut at the sixth slot.
    """
    day = _collected_date(page) or date.min
    return (-_score(page, window), -day.toordinal(), _tl(page), _pr(page, "Link"))


def _pick_headlines(
    entries: list[dict], *, window: Period, n: int = HEADLINES
) -> list[dict]:
    """The month's biggest stories: top ``n`` by score, most important first.

    News is capped at half the slots. The score alone does not balance itself:
    on September's real data the 8-point tier holds 17 news and 35 papers, and
    the tie-break is recency — news is collected every day while papers arrive
    in one daily batch, so ranking by score hands over every slot to the
    headline writers. This is the cap, not a per-type quota: papers and repos
    still compete on score for the remaining half, and a month with no papers
    fills its slots from whatever it has.

    The catch-all topic *is* allowed here (本月最大的收购案 lives in it) — the
    table excludes it because the table is about classification quality, and
    this list is about what actually happened.

    Entries with no summary are skipped: a headline with no "why it matters" is
    not usable.
    """
    news_cap = n // 2
    ranked = sorted((e for e in entries if _summary_of(e)), key=lambda e: _sort_key(e, window))

    picked: list[dict] = []
    held_back: list[dict] = []
    news = 0
    for page in ranked:
        if _kind(page) == "news":
            if news >= news_cap:
                held_back.append(page)
                continue
            news += 1
        picked.append(page)
        if len(picked) == n:
            return picked

    # The cap is a ceiling, not a target: a month with nothing but news still
    # gets a full block rather than half of one, so the held-back stories top the
    # block back up. Topping up is the only thing they may do — re-sorting the
    # two lists together lets a held-back story outrank an entry that already
    # made the cut, and with two papers and seven news the block came back as
    # six news with both papers silently gone, which is the outcome the cap is
    # for. The seam is the one place the order is not by score: a topped-up
    # story sits below the papers the cap promoted above it.
    return picked + held_back[: n - len(picked)]


def _headline_view(page: dict) -> Headline:
    kind = _kind(page)
    day = _collected_date(page)
    meta: list[str] = []

    if kind == "paper":
        meta.extend(x for x in (_pr(page, "Authors"), _pr(page, "Venue")) if x)
    else:
        source = _source_of(page)
        if source != UNKNOWN_SOURCE:
            meta.append(source)

    if day is not None:
        meta.append(day.strftime("%m-%d"))

    if kind == "repo" and _prn(page, "Stars"):
        meta.append(f"{_format_stars(_prn(page, 'Stars'))} stars")
    elif kind == "news" and _pr(page, "Verification"):
        meta.append(_pr(page, "Verification"))

    return Headline(
        kind=kind,
        title=_tl(page),
        link=_pr(page, "Link"),
        meta=meta,
        why=_summary_of(page),
        topic=_topic_of(page),
    )


def _format_stars(stars: int) -> str:
    if stars >= 1000:
        return f"{stars / 1000:.1f}k"
    return str(stars)


def _highlights(headlines: list[Headline], limit: int = 6) -> str:
    return " · ".join(f"{h.kind_label} {h.title}" for h in headlines[:limit])


# ═══════════ The 综述 ═══════════


SUMMARY_SYSTEM = """\
你是 AI 技术月报的主编。给定本月主题统计和已选定的重大事件，写本期的综述。

规则：
- 只写判断，不复述数字。正文里禁止出现任何数字、百分比、条数、涨跌幅。
- 不要罗列下面已经给出的大事，读者紧接着就会看到那份清单。
- lead 两句，说本月的主线是什么；body 两句，说结论或值得警惕的地方。
- 平实、具体，不喊口号，不用"赋能""生态""里程碑"这类空词。
- 严禁编造输入里没有的事实。

返回 strict JSON：{"lead":"...","body":"...","why":["..."]}
why 与输入的事件顺序一一对应，每条一句话说明为什么重要（不超过 60 字）。"""


def _digest_prompt(stats: Stats, rows: list[TopicRow], headlines: list[Headline]) -> str:
    """The user message.

    The counts are here so the model can see the direction of travel; the count
    of headlines is here so the 综述 can only be written about the same stories
    the page lists underneath it. A 综述 that cites events missing from the list
    is the failure mode this is guarding against.
    """
    lines = [
        f"窗口：{stats.window}",
        f"本月收录 {stats.total} 条，上月 {stats.prev_total} 条。",
        "",
        "主题（收录量 / 上月）：",
    ]
    lines += [
        f"- {row.name} {row.count}（上月 {row.prev}，{row.delta:+d}，{TIER_LABEL[row.tier]}）"
        for row in rows
    ]
    lines += ["", "已选定的重大事件（综述只能围绕这些写）："]
    for i, headline in enumerate(headlines, 1):
        lines.append(f"{i}. [{headline.kind_label}] {headline.title}")
        if headline.why:
            lines.append(f"   摘要：{headline.why}")
    return "\n".join(lines)


def _template_digest(stats: Stats, rows: list[TopicRow]) -> Digest:
    """The 综述 with no LLM behind it. Names the moves, still without numbers."""
    if not rows:
        return Digest(lead="本期没有主题数据。")
    rising = "、".join(r.short for r in rows if r.tier == TIER_UP)
    falling = "、".join(r.short for r in rows if r.tier == TIER_DOWN)
    biggest = max(rows, key=lambda r: r.count)

    if stats.total > stats.prev_total:
        move = "回升"
    elif stats.total < stats.prev_total:
        move = "回落"
    else:
        move = "与上月持平"

    lead = f"本期条目数较上月{move}。"
    lead += f"{rising} 升温最明显。" if rising else "没有明显升温的方向。"
    body = f"{falling} 回落最多。" if falling else ""
    body += f"条目最多的是 {biggest.short}。"
    return Digest(lead=lead, body=body)


def _call_llm(cfg: LLMConfig, user: str) -> dict[str, Any]:
    """One JSON-mode completion, mirroring :class:`~mimir.enrich.Enricher`."""
    params: dict[str, Any] = {
        "model": f"{cfg.provider}/{cfg.model}",
        "messages": [
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "api_key": cfg.api_key,
    }
    if cfg.base_url:
        params["api_base"] = cfg.base_url
    try:
        response = completion(**params)
    except Exception as exc:
        if "response_format" in str(exc).lower():
            params.pop("response_format", None)
            response = completion(**params)
        else:
            raise
    return _parse_response(response.choices[0].message.content or "")


def _why_lines(raw: Any, stored: list[str]) -> list[str]:
    """One line per headline. Anything missing or malformed keeps the stored
    summary, so a partial reply still renders a complete list."""
    out = list(stored)
    if isinstance(raw, list):
        for i, item in enumerate(raw[: len(out)]):
            text = str(item).strip()
            if text:
                out[i] = text
    return out


def _summarize(
    cfg: LLMConfig, stats: Stats, rows: list[TopicRow], headlines: list[Headline]
) -> tuple[Digest, list[str]]:
    """Write the 综述 and one "why" line per headline.

    Always returns something. With no API key, or when the call fails, the
    template paragraph and the entries' own stored summaries stand in — a month
    that cannot be reported because an LLM is down is worse than a plain one.
    """
    fallback = _template_digest(stats, rows)
    stored = [headline.why for headline in headlines]
    if not cfg.api_key or not headlines:
        return fallback, stored

    try:
        data = _call_llm(cfg, _digest_prompt(stats, rows, headlines))
    except Exception as exc:  # noqa: BLE001 — the fallback is the point
        print(f"  ! 综述 generation failed ({exc}); falling back to the template")
        return fallback, stored

    if not isinstance(data, dict):
        # The retry drops response_format, so the model is free to answer with a
        # bare JSON array or string. Crashing here would lose the whole report.
        print(f"  ! 综述 came back as {type(data).__name__}, not an object; using the template")
        return fallback, stored

    digest = Digest(
        lead=str(data.get("lead", "")).strip(),
        body=str(data.get("body", "")).strip(),
    )
    return (fallback if digest.is_empty else digest), _why_lines(data.get("why"), stored)


# ═══════════ Rendering ═══════════


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


#: Only these become anchors. Escaping stops a quote from breaking out of the
#: attribute, but it says nothing about the scheme — and a `javascript:` href
#: runs in the report's own origin when the reader clicks it.
_SAFE_SCHEMES = ("http://", "https://")


def _safe_url(value: object) -> str:
    """The URL when it is one we will link to, else ``""``.

    Notion's Link property is free text unless it is url-typed, so this is the
    last place that can tell a link from a script.
    """
    url = str(value or "").strip()
    return url if url.lower().startswith(_SAFE_SCHEMES) else ""


def _headline_title(headline: Headline) -> str:
    """The story title — as a link when we would follow it, otherwise as text."""
    url = _safe_url(headline.link)
    if not url:
        return f'<span class="ttl">{_esc(headline.title)}</span>'
    return (
        f'<a href="{_esc(url)}" target="_blank" rel="noopener" '
        f'class="ttl">{_esc(headline.title)}</a>'
    )


#: Tier → the CSS suffix. ``flat`` is spelled ``ft`` because the bar class is
#: "flat" and the two would otherwise be indistinguishable at a glance.
_TIER_CLASS = {TIER_UP: "up", TIER_FLAT: "ft", TIER_DOWN: "dn"}

_CAPTION = (
    "条形 = 较上月的增减条数，从上到下从 {top:+d} 读到 {bottom:+d}。"
    "橙 = 涨 {ratio:.0%} 以上且至少 +{min_delta} 条，青 = 跌同幅度，灰 = 未过阈值。"
    "论文 / 项目共用一条比例尺：左长右短即「研究跑在工程前面」。"
)


def _masthead(window: Period, stats: Stats) -> str:
    span = f"{window.start.strftime('%m-%d')} → {window.end.strftime('%m-%d')}"
    return (
        '<div class="kicker">AI 技术月报</div>'
        f"<h1>{window.start.year} 年 {window.start.month} 月</h1>"
        f'<div class="meta">{span} · 按入库时间 · {stats.total} 条</div>'
    )


def _section(title: str, note: str) -> str:
    """`标签 ——— 右侧注释`. A block with nothing to note gets no span, so its
    rule still runs to the right edge and all three labels stay aligned."""
    tail = f"<span>{_esc(note)}</span>" if note else ""
    return f'<div class="sec"><h2>{_esc(title)}</h2><i></i>{tail}</div>'


def _summary_block(digest: Digest) -> str:
    """Two paragraphs. Skipped entirely rather than rendered empty."""
    if digest.is_empty:
        return ""
    paras = "".join(
        f"<p>{_esc(part)}</p>" for part in (digest.lead, digest.body) if part.strip()
    )
    return f'<div class="summary">{paras}</div>'


def _kind_bar(css: str, value: int, scale: int) -> str:
    """One 论文/项目 cell: a bar on the shared scale plus the exact count.

    A zero renders no fill at all — a ``min-width`` sliver would read as "a few"
    when the answer is "none".
    """
    fill = f'<span class="fl" style="width:{_pct(value, scale):.0f}%"></span>' if value else ""
    return (
        f'<span class="pair {css}"><span class="trk">{fill}</span>'
        f'<span class="n">{value}</span></span>'
    )


def _topic_table(rows: list[TopicRow]) -> str:
    """The chart: every topic, its move, and what the topic is made of.

    Rows are already sorted biggest-rise-first, so the tier needs no header row
    of its own — the order *is* the tier, and the bar colour repeats it. The
    thresholds are stated once in the caption instead of three times above the
    rows.
    """
    if not rows:
        return '<div class="fig"><p class="cap">本期没有主题数据。</p></div>'

    tier_scale = _tier_scale(rows)
    kind_scale = _kind_scale(rows)
    out = [
        '<div class="fig">',
        '<div class="hd"><span></span><span></span><span class="r">较上月</span>'
        '<span class="r c4">本期</span><span class="r">论文</span>'
        '<span class="r c6">项目</span></div>',
    ]

    for row in rows:
        # The same rule the 论文/项目 bars follow: a zero renders no fill, because
        # the 2px min-width sliver would read as a small move when there was none.
        fill = (
            f'<span class="fl" style="width:{_pct(abs(row.delta), tier_scale):.0f}%"></span>'
            if row.delta
            else ""
        )
        out.append(
            f'<div class="row row-{_TIER_CLASS[row.tier]}">'
            f'<span class="nm" title="{_esc(row.name)}">{_esc(row.short)}</span>'
            f'<span class="trk">{fill}</span>'
            f'<span class="dv">{row.delta:+d}</span>'
            f'<span class="ct">{row.count}</span>'
            f"{_kind_bar('pa', row.papers, kind_scale)}"
            f"{_kind_bar('pr', row.repos, kind_scale)}"
            "</div>"
        )

    caption = _esc(
        _CAPTION.format(
            top=rows[0].delta,
            bottom=rows[-1].delta,
            ratio=TREND_RATIO,
            min_delta=TREND_MIN_DELTA,
        )
    )
    out.append(f'<p class="cap">{caption}</p></div>')
    return "".join(out)


def _headline_list(headlines: list[Headline]) -> str:
    if not headlines:
        return '<li class="ev"><div class="why">本期没有条目。</div></li>'

    items = []
    for headline in headlines:
        why = f'<div class="why">{_esc(headline.why)}</div>' if headline.why else ""
        meta = " · ".join(_esc(part) for part in headline.meta)
        meta_html = f'<div class="meta">{meta}</div>' if meta else ""
        items.append(
            '<li class="ev">'
            f'<div class="ih"><span class="chip c-{headline.kind}">'
            f"{_esc(headline.kind_label)}</span>{_headline_title(headline)}</div>"
            f"{why}{meta_html}</li>"
        )
    return "".join(items)


def _footnote(stats: Stats, notion_url: str) -> str:
    parts = [
        f"<span>{stats.papers} 论文</span>",
        f"<span>{stats.repos} 项目</span>",
        f"<span>{stats.news} 新闻</span>",
    ]
    if stats.unclassified:
        parts.append(
            f"<span>其中 {stats.unclassified} 条未归入主题"
            f"（{stats.unclassified_pct}%）</span>"
        )
    if stats.source_count:
        parts.append(f"<span>{stats.source_count} 个来源</span>")

    link = (
        f'<a class="lk" href="{_esc(notion_url)}" target="_blank" rel="noopener">'
        "Notion 完整数据 →</a>"
        if notion_url
        else ""
    )
    return f'<div class="foot"><div class="r">{"".join(parts)}</div>{link}</div>'


def _render(
    window: Period,
    stats: Stats,
    rows: list[TopicRow],
    digest: Digest,
    headlines: list[Headline],
    notion_url: str,
) -> str:
    """The whole page: three named blocks between a masthead and a footnote.

    图表 → 概要 → 重点: the shape of the month, what it means, and the evidence.
    Every block carries its own label, so nothing has to be inferred from
    position, and the masthead stays quiet enough not to compete with them.
    """
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{window.start.year} 年 {window.start.month} 月 · AI 技术月报</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
{_masthead(window, stats)}
{_section("图表", f"较 {int(window.prev_label[-2:])} 月")}
{_topic_table(rows)}
{_section("概要", "")}
{_summary_block(digest)}
{_section("重点", "按重要性排序")}
<ul class="events">{_headline_list(headlines)}</ul>
{_footnote(stats, notion_url)}
</div></body></html>"""

_CSS = """
:root{
  color-scheme: light;
  --bg:#fbfbfa; --text:#1a1a18; --t2:#5f5e5a; --t3:#9b9a97;
  --line:#e9e8e5; --line-soft:#f2f1ee; --track:#f1f0ed;
  /* 语义色（饱和）—— 只表示涨跌方向 */
  --up:#c2410c; --flat:#b0aea7; --down:#0f766e;
  /* 分类色（低饱和）—— 只表示条目类型 */
  --paper:#5a6ac9; --repo:#4a7d5c; --news:#8a6a3a;
  --paper-bg:#eef0fb; --repo-bg:#edf5ef; --news-bg:#f7f2e9;
  /* 间距：只用 4 的倍数，没有例外 */
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px; --s7:48px; --s8:64px;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --bg:#191918; --text:#ecebe8; --t2:#a3a29d; --t3:#75746f;
    --line:#33322f; --line-soft:#2a2927; --track:#2b2a28;
    --up:#f08a52; --flat:#5c5b57; --down:#4fb3a5;
    --paper:#9aa9ff; --repo:#72c893; --news:#d9b478;
    --paper-bg:#22253c; --repo-bg:#16291d; --news-bg:#2e2716;
  }
}
/* 字阶：6 级，每级一个职责。没有第 7 级，没有半像素。
   24 刊头月份 · 17 概要 · 16 重点标题 · 13 主题名/说明 · 12 元信息 · 10 标签 */
*{box-sizing:border-box}
body{margin:0; background:var(--bg); color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","PingFang SC",sans-serif;
  font-size:13px; line-height:1.6; -webkit-font-smoothing:antialiased}
.wrap{max-width:680px; margin:0 auto; padding:var(--s8) var(--s5)}
a{color:inherit; text-decoration:none}
a:hover .ttl{text-decoration:underline; text-underline-offset:2px}

/* 刊头 —— 框架，不是块。安静，不跟三个块抢 */
.kicker{font-size:10px; font-weight:700; letter-spacing:.2em; color:var(--t3)}
h1{margin:var(--s3) 0 0; font-size:24px; font-weight:650; line-height:1.25; letter-spacing:-.01em}
.meta{margin-top:var(--s2); font-size:12px; color:var(--t3); font-variant-numeric:tabular-nums}

/* 段标签 —— 三个块共用同一套：标签 ——— 右侧注释 */
.sec{margin:var(--s8) 0 var(--s5); display:flex; align-items:center; gap:var(--s3)}
.sec h2{margin:0; font-size:10px; font-weight:700; letter-spacing:.16em; color:var(--text);
  white-space:nowrap}
.sec i{flex:1; height:1px; background:var(--line)}
.sec span{font-size:10px; color:var(--t3); white-space:nowrap; font-variant-numeric:tabular-nums}

/* 图表 —— 全页唯一的图。落在页面底色上，不套卡片 */
.fig{display:grid; align-items:center; gap:0 var(--s3);
  grid-template-columns:5.4em 1fr 2.9em 2.3em 4.5em 4.5em}
.fig > .hd, .fig > .row{grid-column:1/-1; display:grid; align-items:center;
  gap:0 var(--s3); grid-template-columns:5.4em 1fr 2.9em 2.3em 4.5em 4.5em}
.hd{padding-bottom:var(--s2); border-bottom:1px solid var(--line)}
.hd span{font-size:10px; letter-spacing:.12em; color:var(--t3)}
.hd .r{text-align:right}
.row{padding:var(--s1) 0}
.nm{font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.trk{height:10px; border-radius:2px; background:var(--track); overflow:hidden; display:block}
.fl{height:100%; border-radius:2px; display:block; min-width:2px}
.dv{font-size:13px; font-weight:650; text-align:right; font-variant-numeric:tabular-nums}
.ct{font-size:12px; color:var(--t3); text-align:right; font-variant-numeric:tabular-nums}
.row-up .fl{background:var(--up)}   .row-up .dv{color:var(--up)}
.row-dn .fl{background:var(--down)} .row-dn .dv{color:var(--down)}
.row-ft .fl{background:var(--flat)} .row-ft .dv{color:var(--t3)}
.row-ft .nm{color:var(--t2)}
.pair{display:grid; grid-template-columns:1fr 2em; align-items:center; gap:var(--s2)}
.pair .trk{height:7px}
.pair .n{font-size:12px; text-align:right; font-variant-numeric:tabular-nums}
.pair.pa .fl{background:var(--paper)} .pair.pa .n{color:var(--paper)}
.pair.pr .fl{background:var(--repo)}  .pair.pr .n{color:var(--repo)}
.cap{grid-column:1/-1; margin:var(--s4) 0 0; padding-top:var(--s3);
  border-top:1px solid var(--line-soft); font-size:12px; line-height:1.7; color:var(--t3)}

/* 概要 —— 全页唯一的长文，也是唯一需要被"读"的块 */
.summary p{margin:0 0 var(--s5); font-size:17px; line-height:1.9; letter-spacing:-.004em}
.summary p:last-child{margin-bottom:0}

/* 重点 —— 全页唯一能点的块 */
.events{margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:var(--s5)}
.ev{display:flex; flex-direction:column; gap:var(--s1)}
.ih{display:flex; align-items:baseline; gap:var(--s2)}
.chip{flex:none; font-size:10px; font-weight:650; letter-spacing:.05em; line-height:1;
  padding:var(--s1) var(--s2); border-radius:4px}
.c-paper{color:var(--paper); background:var(--paper-bg)}
.c-repo {color:var(--repo);  background:var(--repo-bg)}
.c-news {color:var(--news);  background:var(--news-bg)}
.ttl{font-size:16px; font-weight:650; line-height:1.5}
.why{font-size:13px; line-height:1.75; color:var(--t2)}
.ev .meta{font-size:12px; color:var(--t3); font-variant-numeric:tabular-nums}

/* 页脚 —— 框架：数据从哪来、有多干净 */
.foot{margin-top:var(--s8); padding-top:var(--s4); border-top:1px solid var(--line);
  font-size:12px; color:var(--t3); line-height:1.9; font-variant-numeric:tabular-nums}
.foot .r{display:flex; flex-wrap:wrap; gap:0 var(--s5)}
.foot .lk{display:inline-block; margin-top:var(--s3); color:var(--t2);
  border-bottom:1px solid var(--line)}

/* 移动端只改布局，不改字阶 —— 刻度在断点里也必须是一套 */
@media (max-width:600px){
  .fig, .fig > .hd, .fig > .row{
    grid-template-columns:4.6em 1fr 2.6em 2.1em 3.8em 3.8em; gap:0 var(--s2)}
}
@media (max-width:430px){
  .wrap{padding:var(--s7) var(--s4)}
  .fig, .fig > .hd, .fig > .row{grid-template-columns:4.2em 1fr 2.4em 3.2em 3.2em; gap:0 var(--s2)}
  /* 本期列让位；论文/项目 从条形降级为数字对 —— 信息不丢 */
  .fig .ct, .hd .c4{display:none}
  /* 数字对对齐右齐的表头，否则两列数字会往左跑 */
  .pair{display:block; text-align:right}
  .pair .trk{display:none}
}
"""


# ═══════════ Notion records ═══════════


def _hottest(rows: list[TopicRow]) -> TopicRow | None:
    """The topic to name as the month's direction.

    A rising topic wins outright — "hottest" should mean "moving", and the
    biggest topic by volume is often just the biggest and going nowhere. With
    nothing rising it falls back to that biggest topic, which is what the
    Reports DB meant by it before.
    """
    if not rows:
        return None
    return next((row for row in rows if row.tier == TIER_UP), None) or max(
        rows, key=lambda row: row.count
    )


def _write_record(
    store: ReportStore,
    reports_db_id: str,
    reports_ds_id: str,
    window: Period,
    stats: Stats,
    rows: list[TopicRow],
    headlines: list[Headline],
    link_url: str,
) -> tuple[str, str | None]:
    """Create or update this period's record. Returns (action, page_id)."""
    props: dict[str, Any] = {
        "Name": {"title": [{"text": {"content": window.label}}]},
        "Date": {"date": {"start": window.start.strftime("%Y-%m-%d")}},
        "Period": {"select": {"name": "Monthly"}},
        "Total": {"number": stats.total},
        "Papers": {"number": stats.papers},
        "Repos": {"number": stats.repos},
        "News": {"number": stats.news},
        "HighPriority": {"number": stats.high_priority},
        "Highlights": {"rich_text": [{"text": {"content": _highlights(headlines)[:500]}}]},
    }
    hottest = _hottest(rows)
    if hottest:
        props["Hottest"] = {"select": {"name": hottest.name}}
    if link_url:
        props["Link"] = {"url": link_url}

    existing_id = _find_report(store, reports_ds_id, window.label)
    if existing_id:
        store._rate_limit()
        store.client.pages.update(existing_id, properties=props)
        return "updated", existing_id

    store._rate_limit()
    page = store.client.pages.create(parent={"database_id": reports_db_id}, properties=props)
    return "created", page.get("id")


def _find_report(store: ReportStore, reports_ds_id: str, label: str) -> str | None:
    """Find an existing report page by Name, so reruns update instead of duplicate."""
    store._rate_limit()
    resp = store.client.data_sources.query(
        reports_ds_id,
        page_size=1,
        filter={"property": "Name", "title": {"equals": label}},
    )
    results = resp.get("results", [])
    return results[0]["id"] if results else None


# ═══════════ Property readers ═══════════


def _pr(page: dict, name: str, default: str = "") -> str:
    p = page.get("properties", {}).get(name, {})
    t = p.get("type", "")
    if t == "rich_text":
        items = p.get("rich_text", [])
        return (items[0].get("plain_text", "") or default) if items else default
    if t == "select":
        s = p.get("select")
        return s["name"] if s else default
    if t == "status":
        s = p.get("status")
        return s["name"] if s else default
    if t == "title":
        items = p.get("title", [])
        return (items[0].get("plain_text", "") or default) if items else default
    if t == "url":
        return p.get("url") or default
    if t == "date":
        d = p.get("date")
        return d.get("start", default)[:10] if d else default
    return default


def _prn(page: dict, name: str) -> int:
    p = page.get("properties", {}).get(name, {})
    return int(p.get("number", 0) or 0)


def _tp(page: dict) -> str:
    return _pr(page, "Type", "")


def _tl(page: dict) -> str:
    return _pr(page, "Name", "(无标题)")


def _kind(page: dict) -> str:
    """paper / repo / news, matched loosely so an emoji tweak cannot zero a count."""
    label = _tp(page)
    if "论文" in label:
        return "paper"
    if "项目" in label:
        return "repo"
    return "news"
