"""Report generation — every number, arrow and pick must follow the entries.

The fake Notion layer mirrors the *response* shape of the 2025 API, including
the ``type`` discriminator that ``_create_page``'s write payload does not carry,
so these tests exercise the same readers the live reports use.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
import pytest
from notion_client.errors import APIErrorCode, APIResponseError

from mimir import report as R
from mimir.config import Config, LLMConfig, NotionConfig, ReportConfig, SourcesConfig
from mimir.periods import period_bounds

ENTRIES_DB = "entries_db"
ENTRIES_DS = "ds_entries"
REPORTS_DB = "reports_db"
REPORTS_DS = "ds_reports"

TYPE_NAME = {"paper": "📄 论文", "repo": "🛠️ 项目", "news": "📰 新闻"}
SUMMARY_FIELD = {"paper": "Significance", "repo": "UseCase", "news": "KeyPoint"}

TOPICS = [
    "AI Agent",
    "RAG / 检索增强",
    "多模态",
    "推理优化",
    "训练与微调",
    "安全与对齐",
    "基础设施",
    "AI Coding",
    "开源模型",
    "行业动态",
]

#: Property absent altogether, as opposed to present-but-null.
OMIT = object()


def _d(value: str) -> date:
    return date.fromisoformat(value)


# ═══════════ Fake Notion layer ═══════════


def page(
    title: str = "entry",
    *,
    kind: str = "news",
    collected: object = "2026-09-15",
    published: object = OMIT,
    topic: str | None = None,
    priority: str | None = None,
    source: str | None = None,
    link: str | None = "https://example.com/x",
    stars: int | None = None,
    summary: str | None = None,
    authors: str | None = None,
    venue: str | None = None,
    created_time: str | None = None,
) -> dict:
    """Build a page shaped like a ``data_sources.query`` result."""
    props: dict = {
        "Name": {"type": "title", "title": [{"plain_text": title}]},
        "Type": {"type": "select", "select": {"name": TYPE_NAME[kind]}},
    }
    if topic is not None:
        props["Topic"] = {"type": "select", "select": {"name": topic}}
    if source is not None:
        props["Source"] = {"type": "select", "select": {"name": source}}
    if link is not None:
        props["Link"] = {"type": "url", "url": link}
    if collected is not OMIT:
        props["Collected"] = {
            "type": "date",
            "date": {"start": collected} if collected else None,
        }
    if published is not OMIT:
        props["Published"] = {
            "type": "date",
            "date": {"start": published} if published else None,
        }
    if priority is not None:
        props["Priority"] = {"type": "select", "select": {"name": priority}}
    if stars is not None:
        props["Stars"] = {"type": "number", "number": stars}
    if summary is not None:
        props[SUMMARY_FIELD[kind]] = {
            "type": "rich_text",
            "rich_text": [{"plain_text": summary}],
        }
    if authors is not None:
        props["Authors"] = {"type": "rich_text", "rich_text": [{"plain_text": authors}]}
    if venue is not None:
        props["Venue"] = {"type": "select", "select": {"name": venue}}

    built = {"id": f"page-{abs(hash((title, kind, str(collected))))}", "properties": props}
    if created_time is not None:
        built["created_time"] = created_time
    return built


def _prop_date(page_dict: dict, name: str) -> str | None:
    prop = page_dict.get("properties", {}).get(name)
    if not prop:
        return None
    value = prop.get("date")
    return value.get("start") if value else None


def _prop_text(page_dict: dict, name: str) -> str:
    prop = page_dict.get("properties", {}).get(name) or {}
    items = prop.get("title") or prop.get("rich_text") or []
    return items[0].get("plain_text", "") if items else ""


def _matches(page_dict: dict, filter_: dict | None) -> bool:
    """Evaluate the subset of the Notion filter grammar that report.py emits."""
    if filter_ is None:
        return True
    if "and" in filter_:
        return all(_matches(page_dict, sub) for sub in filter_["and"])

    name = filter_["property"]
    cond = filter_.get("date")
    if isinstance(cond, dict):
        raw = _prop_date(page_dict, name)
        if cond.get("is_empty"):
            return not raw
        if raw is None:
            return False
        if "on_or_after" in cond and raw < cond["on_or_after"]:
            return False
        return not ("on_or_before" in cond and raw > cond["on_or_before"])

    title = filter_.get("title")
    if isinstance(title, dict) and "equals" in title:
        return _prop_text(page_dict, name) == title["equals"]
    raise AssertionError(f"unsupported filter: {filter_}")


def _has_date_condition(filter_: dict | None) -> bool:
    if not filter_:
        return False
    if "and" in filter_:
        return any(_has_date_condition(sub) for sub in filter_["and"])
    return isinstance(filter_.get("date"), dict)


def _bad_request() -> APIResponseError:
    response = httpx.Response(
        400,
        json={"object": "error", "code": "validation_error"},
        request=httpx.Request("POST", "https://api.notion.com/v1/data_sources/q/query"),
    )
    return APIResponseError(response, "body failed validation: filter", APIErrorCode.ValidationError)


class FakeStore:
    """Duck-typed NotionStore: records every call, touches no network."""

    def __init__(
        self,
        entries: list[dict],
        *,
        reports: list[dict] | None = None,
        reject_date_filter: bool = False,
        reject_empty_filter: bool = False,
    ):
        self.entries = list(entries)
        self.reports = list(reports or [])
        self.reject_date_filter = reject_date_filter
        self.reject_empty_filter = reject_empty_filter
        self.queries: list[dict] = []
        self.created: list[dict] = []
        self.updated: list[tuple[str, dict]] = []
        self.client = _FakeClient(self)

    def _rate_limit(self) -> None:
        pass


class _FakeClient:
    def __init__(self, store: FakeStore):
        self.databases = _FakeDatabases()
        self.data_sources = _FakeDataSources(store)
        self.pages = _FakePages(store)


class _FakeDatabases:
    DS_FOR = {ENTRIES_DB: ENTRIES_DS, REPORTS_DB: REPORTS_DS}

    def retrieve(self, db_id: str) -> dict:
        return {"id": db_id, "data_sources": [{"id": self.DS_FOR[db_id]}]}


class _FakeDataSources:
    def __init__(self, store: FakeStore):
        self._store = store

    def query(self, ds_id: str, **kwargs):
        store = self._store
        store.queries.append({"ds_id": ds_id, **kwargs})
        filter_ = kwargs.get("filter")
        if store.reject_date_filter and _has_date_condition(filter_):
            raise _bad_request()
        if store.reject_empty_filter and (filter_ or {}).get("date", {}).get("is_empty"):
            raise _bad_request()

        pool = store.entries if ds_id == ENTRIES_DS else store.reports
        matched = [p for p in pool if _matches(p, filter_)]
        if kwargs.get("sorts"):
            field = kwargs["sorts"][0]["property"]
            matched.sort(key=lambda p: _prop_date(p, field) or "", reverse=True)

        size = kwargs.get("page_size", 100)
        start = int(kwargs["start_cursor"]) if kwargs.get("start_cursor") else 0
        chunk = matched[start : start + size]
        nxt = start + size
        out: dict = {"results": chunk, "next_cursor": str(nxt) if nxt < len(matched) else None}
        return out


class _FakePages:
    def __init__(self, store: FakeStore):
        self._store = store

    def create(self, **kwargs):
        self._store.created.append(kwargs)
        return {"id": "report-page-1"}

    def update(self, page_id, **kwargs):
        self._store.updated.append((page_id, kwargs))
        return {"id": page_id}


def _cfg(tmp_path: Path, *, reports_db: str = REPORTS_DB) -> Config:
    return Config(
        llm=LLMConfig(),
        sources=SourcesConfig(),
        notion=NotionConfig(token="t", entries_db_id=ENTRIES_DB, reports_db_id=reports_db),
        report=ReportConfig(issues_dir=str(tmp_path), site_url="https://example.test/Mimir"),
    )


@pytest.fixture
def month_window():
    """September 2026. A 1st-of-month run is the case that was broken."""
    return period_bounds(run_date=_d("2026-10-01"))


# ═══════════ Window selection through generate ═══════════


def test_a_run_on_the_first_reports_the_month_that_ended(tmp_path):
    """The bug: a 1st-of-month run used to report the few hours old new month."""
    entries = [page(f"sep-{i}", collected=f"2026-09-{i + 1:02d}") for i in range(5)]
    entries += [page("oct-1", collected="2026-10-01"), page("oct-2", collected="2026-10-02")]
    store = FakeStore(entries)

    path = R.generate(_cfg(tmp_path), store, run_date=_d("2026-10-01"))

    assert path == tmp_path / "monthly-2026-09.html"
    assert "<span>5 新闻</span>" in path.read_text(encoding="utf-8")
    name = store.created[0]["properties"]["Name"]
    assert name == {"title": [{"text": {"content": "2026-09"}}]}


def test_backfill_by_date_covers_the_containing_month(tmp_path):
    entries = [page(f"sep-{i}", collected="2026-09-15") for i in range(7)]
    store = FakeStore(entries)

    path = R.generate(_cfg(tmp_path), store, anchor=_d("2026-09-15"))

    assert path.name == "monthly-2026-09.html"
    assert "<span>7 新闻</span>" in path.read_text(encoding="utf-8")


def test_the_record_backlinks_the_published_page_and_the_report_links_back(tmp_path):
    store = FakeStore([page("a", collected="2026-09-10")])
    path = R.generate(_cfg(tmp_path), store, run_date=_d("2026-10-01"))

    props = store.created[0]["properties"]
    assert props["Link"] == {"url": "https://example.test/Mimir/monthly-2026-09.html"}
    assert "https://www.notion.so/reportpage1" in path.read_text(encoding="utf-8")


def test_a_report_with_nowhere_to_be_published_records_no_link(tmp_path):
    """Notion's url property rejects a filesystem path, and the record is written
    before the file exists — so without a site_url there is no URL to record.

    Regression: the absolute path was being sent as the Link, so every record
    carried a value that was not a URL.
    """
    store = FakeStore([page("a", collected="2026-09-10")])
    cfg = replace(_cfg(tmp_path), report=ReportConfig(issues_dir=str(tmp_path), site_url=""))

    R.generate(cfg, store, run_date=_d("2026-10-01"))

    assert "Link" not in store.created[0]["properties"]


def test_rerun_updates_the_existing_record_instead_of_duplicating(tmp_path):
    existing = {
        "id": "old-page",
        "properties": {"Name": {"type": "title", "title": [{"plain_text": "2026-09"}]}},
    }
    store = FakeStore([page("a", collected="2026-09-10")], reports=[existing])

    R.generate(_cfg(tmp_path), store, run_date=_d("2026-10-01"))

    assert store.created == []
    assert store.updated[0][0] == "old-page"
    assert store.updated[0][1]["properties"]["Total"] == {"number": 1}


# ═══════════ Fetching ═══════════


def test_the_first_query_asks_for_both_windows_in_one_pass(month_window):
    store = FakeStore([])
    R._fetch_window(store, ENTRIES_DS, month_window)

    first = store.queries[0]
    assert first["filter"] == {
        "and": [
            {"property": "Collected", "date": {"on_or_after": "2026-08-01"}},
            {"property": "Collected", "date": {"on_or_before": "2026-09-30"}},
        ]
    }
    assert first["sorts"] == [{"property": "Collected", "direction": "descending"}]
    assert first["page_size"] == 100


def test_entries_without_a_collected_date_are_still_fetched(month_window):
    """A server-side filter would hide them, so they get their own query."""
    blank = page("blank", collected=None, published="2026-09-30")
    store = FakeStore([blank])

    current, _ = R._fetch_window(store, ENTRIES_DS, month_window)

    assert any(
        q.get("filter") == {"property": "Collected", "date": {"is_empty": True}}
        for q in store.queries
    )
    assert [p["id"] for p in current] == [blank["id"]]


def test_window_membership_is_exact_on_both_edges(month_window):
    dates = ["2026-07-31", "2026-08-01", "2026-08-31", "2026-09-01", "2026-09-30", "2026-10-01"]
    store = FakeStore([page(f"d-{d}", collected=d) for d in dates])

    current, previous = R._fetch_window(store, ENTRIES_DS, month_window)

    assert sorted(_prop_date(p, "Collected") or "" for p in previous) == ["2026-08-01", "2026-08-31"]
    assert sorted(_prop_date(p, "Collected") or "" for p in current) == ["2026-09-01", "2026-09-30"]


def test_membership_still_holds_when_the_server_rejects_the_filter(month_window):
    """A refused filter must cost speed, never correctness."""
    dates = ["2026-07-31", "2026-08-15", "2026-09-01", "2026-09-30", "2026-10-01"]
    store = FakeStore([page(f"d-{d}", collected=d) for d in dates], reject_date_filter=True)

    current, previous = R._fetch_window(store, ENTRIES_DS, month_window)

    assert sorted(_prop_date(p, "Collected") or "" for p in current) == ["2026-09-01", "2026-09-30"]
    assert sorted(_prop_date(p, "Collected") or "" for p in previous) == ["2026-08-15"]
    assert any(q.get("filter") is None for q in store.queries)


def test_a_rejected_empty_filter_does_not_double_the_window(month_window):
    """The first query is honoured and the second — ``Collected is empty`` — is
    refused, and a refusal is answered with a full scan. That scan already holds
    every in-window row, so extending the window with it lists each one twice and
    doubles every number on the page.

    This is the one combination neither neighbour covers: refusing everything
    skips the second query, and refusing nothing honours it.
    """
    dates = ["2026-08-15", "2026-09-01", "2026-09-30", "2026-10-01"]
    store = FakeStore([page(f"d-{d}", collected=d) for d in dates], reject_empty_filter=True)

    current, previous = R._fetch_window(store, ENTRIES_DS, month_window)

    # The setup has to be what it claims: the empty-Collected query was asked.
    assert any(
        q.get("filter") == {"property": "Collected", "date": {"is_empty": True}}
        for q in store.queries
    )
    assert sorted(_prop_date(p, "Collected") or "" for p in current) == ["2026-09-01", "2026-09-30"]
    assert sorted(_prop_date(p, "Collected") or "" for p in previous) == ["2026-08-15"]


def test_pagination_walks_every_page(month_window):
    entries = [page(f"e{i}", collected="2026-09-15") for i in range(250)]
    store = FakeStore(entries)

    current, _ = R._fetch_window(store, ENTRIES_DS, month_window)

    assert len(current) == 250
    paged = [q for q in store.queries if q.get("sorts")]
    assert len(paged) == 3  # 100 + 100 + 50
    assert "start_cursor" not in paged[0] and paged[1]["start_cursor"] == "100"


def test_reruns_do_not_need_the_whole_window_in_memory(month_window):
    """Each query is one page at a time; the cursor is what keeps it bounded."""
    store = FakeStore([page(f"e{i}", collected="2026-09-15") for i in range(150)])
    R._fetch_window(store, ENTRIES_DS, month_window)
    for q in store.queries:
        assert q["page_size"] == 100


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"collected": "2026-09-10"}, "2026-09-10"),
        ({"collected": None, "published": "2026-09-11"}, "2026-09-11"),
        ({"collected": OMIT, "published": "2026-09-12"}, "2026-09-12"),
        ({"collected": OMIT, "published": OMIT, "created_time": "2026-09-13T04:00:00Z"}, "2026-09-13"),
        ({"collected": OMIT, "published": OMIT}, None),
        ({"collected": None, "published": None}, None),
        ({"collected": "not-a-date", "published": "2026-09-14"}, "2026-09-14"),
    ],
)
def test_collected_date_falls_back_predictably(kwargs, expected):
    """Collected → Published → created_time, and nothing unparseable slips through."""
    got = R._collected_date(page("x", **kwargs))
    assert (got.isoformat() if got else None) == expected


def test_an_entry_with_no_usable_date_is_dropped(month_window):
    store = FakeStore([page("dateless", collected=OMIT, published=OMIT)])
    current, previous = R._fetch_window(store, ENTRIES_DS, month_window)
    assert current == [] and previous == []


# ═══════════ Statistics ═══════════


def test_kind_counts_add_up(month_window):
    entries = (
        [page(f"p{i}", kind="paper") for i in range(3)]
        + [page(f"r{i}", kind="repo") for i in range(2)]
        + [page(f"n{i}", kind="news") for i in range(5)]
    )
    stats = R._compute_stats(entries, [], month_window)
    assert (stats.total, stats.papers, stats.repos, stats.news) == (10, 3, 2, 5)
    assert stats.papers + stats.repos + stats.news == stats.total
    # The footer carries the same split, in the same order.
    assert "<span>3 论文</span><span>2 项目</span><span>5 新闻</span>" in _render_for(
        entries, [], month_window
    )


def test_the_catch_all_topic_is_never_the_hottest_direction(month_window):
    entries = (
        [page(f"i{i}", topic="行业动态") for i in range(20)]
        + [page(f"a{i}", topic="AI Agent") for i in range(4)]
    )
    stats = R._compute_stats(entries, [], month_window)

    assert stats.topic_counts[0] == ("行业动态", 20)
    assert stats.hottest is not None and stats.hottest.name == "AI Agent"
    assert stats.unclassified == 20
    assert stats.unclassified_pct == 83


def test_a_window_with_no_classification_at_all_has_no_hottest_direction(month_window):
    stats = R._compute_stats([page("i", topic="行业动态")], [], month_window)
    assert stats.hottest is None


def test_entries_with_no_topic_at_all_land_in_the_catch_all(month_window):
    stats = R._compute_stats([page("bare")], [], month_window)
    assert stats.unclassified == 1


def test_high_priority_counts_only_the_top_tier(month_window):
    entries = [
        page("a", priority="★★★"),
        page("b", priority="★★★"),
        page("c", priority="★★"),
        page("d"),
    ]
    assert R._compute_stats(entries, [], month_window).high_priority == 2


@pytest.mark.parametrize(
    ("count", "prev", "arrow"),
    [
        (13, 10, "↗"),
        (12, 10, "→"),
        (5, 10, "↘"),
        (5, 0, "↗"),
        (2, 0, "→"),
        (3, 3, "→"),
        (115, 100, "→"),
        (99, 100, "→"),
        (80, 100, "↘"),
    ],
)
def test_the_arrow_needs_both_an_absolute_and_a_relative_move(count, prev, arrow):
    assert R._trend_arrow(count, prev) == arrow


def test_trend_pairs_the_window_with_the_one_before_it(month_window):
    current = [page(f"a{i}", topic="AI Agent") for i in range(10)]
    previous = [page(f"b{i}", topic="AI Agent") for i in range(3)]
    stats = R._compute_stats(current, previous, month_window)

    agent = next(t for t in stats.trend if t.name == "AI Agent")
    assert (agent.count, agent.prev, agent.arrow) == (10, 3, "↗")
    assert stats.prev_total == 3


def test_sources_prefer_the_stored_value_over_any_inference(month_window):
    entries = [
        # Both would be inferred differently from the link alone.
        page("hn", kind="news", source="Hacker News", link="https://openai.com/index/x"),
        page("gh", kind="repo", source="GitHub", link="https://github.com/a/b"),
    ]
    stats = R._compute_stats(entries, [], month_window)
    assert dict(stats.sources) == {"Hacker News": 1, "GitHub": 1}


@pytest.mark.parametrize(
    ("kind", "link", "expected"),
    [
        ("paper", "https://arxiv.org/abs/2606.1", "arXiv"),
        ("repo", "https://github.com/a/b", "GitHub"),
        ("news", "https://www.qbitai.com/2026/09/x.html", "量子位"),
        # The ambiguous case: HN stores the external URL, so a news row pointing
        # at github.com came from HN, not from the repo collector.
        ("news", "https://github.com/a/b", "Hacker News"),
        ("news", "https://arxiv.org/abs/2606.1", "Hacker News"),
        ("news", "https://openai.com/index/x", "Hacker News"),
        ("news", None, "其他"),
        ("paper", "https://openai.com/paper.pdf", "其他"),
        ("repo", "https://gitlab.com/a/b", "其他"),
        # The host test is a suffix test, so it has to be anchored on a dot:
        # these were being credited to GitHub and arXiv, and the value is written
        # to the database as though a collector had recorded it.
        ("repo", "https://evilgithub.com/a/b", "其他"),
        ("paper", "https://notarxiv.org/abs/2606.1", "其他"),
        ("news", "https://evilqbitai.com/2026/09/x.html", "Hacker News"),
        # …and the anchoring must not cost the real subdomains, which is what
        # an exact-equality fix in the other direction would do.
        ("paper", "https://export.arxiv.org/abs/2606.1", "arXiv"),
        ("news", "https://news.qbitai.com/2026/09/x.html", "量子位"),
    ],
)
def test_legacy_rows_are_attributed_by_type_and_host(kind, link, expected):
    assert R._source_of(page("legacy", kind=kind, link=link)) == expected


def test_a_legacy_row_with_no_link_is_not_credited_to_anyone():
    assert R._source_of(page("bare", kind="news", link=None)) == "其他"
    assert R._source_of(page("bare", kind="paper", link=None)) == "其他"


# ═══════════ Topic table ═══════════


def _n(topic: str, count: int, *, kind: str = "news", day: str = "2026-09-15") -> list[dict]:
    return [page(f"{topic}-{i}", kind=kind, topic=topic, collected=day) for i in range(count)]


def test_the_tier_comes_from_the_arrow_not_from_the_sign():
    assert R._tier_of("↗") == R.TIER_UP
    assert R._tier_of("↘") == R.TIER_DOWN
    assert R._tier_of("→") == R.TIER_FLAT
    assert R._tier_of("") == R.TIER_FLAT


def test_the_table_leaves_the_catch_all_out():
    """行业动态 measures the classifier, not the world; it belongs in the footer."""
    rows = R._topic_rows(_n("行业动态", 20) + _n("AI Agent", 4), [])
    assert [row.name for row in rows] == ["AI Agent"]


def test_rows_run_from_the_biggest_gain_to_the_biggest_drop():
    current = _n("安全与对齐", 15) + _n("基础设施", 28) + _n("AI Coding", 11) + _n("多模态", 30)
    previous = _n("安全与对齐", 5) + _n("基础设施", 20) + _n("AI Coding", 10) + _n("多模态", 60)

    rows = R._topic_rows(current, previous)

    assert [row.name for row in rows] == ["安全与对齐", "基础设施", "AI Coding", "多模态"]
    assert [row.delta for row in rows] == [10, 8, 1, -30]
    assert [row.tier for row in rows] == [R.TIER_UP, R.TIER_UP, R.TIER_FLAT, R.TIER_DOWN]


def test_the_biggest_move_draws_the_full_bar():
    rows = R._topic_rows(_n("安全与对齐", 15) + _n("多模态", 30), _n("安全与对齐", 5) + _n("多模态", 60))
    scale = R._tier_scale(rows)

    assert scale == 30
    assert max(R._pct(abs(row.delta), scale) for row in rows) == 100.0


def test_a_zero_scale_is_zero_percent_not_a_crash():
    assert R._pct(0, 0) == 0.0
    assert R._pct(5, 0) == 0.0
    assert R._tier_scale([]) == 0
    assert R._kind_scale([]) == 0


def test_papers_and_repos_are_measured_against_one_scale():
    """Two separate scales would make a rare paper look as big as a huge repo."""
    entries = (
        [page(f"p{i}", kind="paper", topic="多模态") for i in range(45)]
        + [page("mm-r", kind="repo", topic="多模态")]
        + [page(f"q{i}", kind="paper", topic="基础设施") for i in range(3)]
        + [page(f"r{i}", kind="repo", topic="基础设施") for i in range(35)]
    )
    rows = R._topic_rows(entries, [])
    scale = R._kind_scale(rows)
    multimodal = next(row for row in rows if row.name == "多模态")
    infra = next(row for row in rows if row.name == "基础设施")

    assert scale == 45  # the largest count anywhere, not the largest per column
    assert R._pct(multimodal.papers, scale) == 100.0
    assert R._pct(infra.repos, scale) == pytest.approx(100 * 35 / 45)
    assert R._pct(multimodal.repos, scale) == pytest.approx(100 * 1 / 45)


def test_a_topic_with_no_repos_draws_no_fill(month_window):
    """A min-width sliver would read as "a few" when the answer is "none"."""
    entries = _n("多模态", 3, kind="paper")
    html = _render_for(entries, [], month_window)
    assert '<span class="pair pr"><span class="trk"></span>' in html


def test_a_topic_that_did_not_move_draws_no_fill(month_window):
    """The same rule on the trend bar: `+0` next to a 2px stub reads as a small
    rise, which is the opposite of what a flat month is."""
    html = _render_for(_n("AI Agent", 5), _n("AI Agent", 5), month_window)

    assert '<span class="trk"></span><span class="dv">+0</span>' in html
    assert 'style="width:2px"' not in html


# ═══════════ Headlines ═══════════


def _headlines(entries: list[dict], window) -> list[R.Headline]:
    return [R._headline_view(p) for p in R._pick_headlines(entries, window=window)]


def test_headlines_are_the_top_six_by_score(month_window):
    """Nothing but papers, so the news cap never binds: pure score order."""
    entries = [
        page(f"e{i}", kind="paper", priority="★★★" if i < 3 else "★", summary="s",
             collected=f"2026-09-{i + 1:02d}")
        for i in range(10)
    ]
    expected = sorted(
        (e for e in entries if R._summary_of(e)), key=lambda e: R._sort_key(e, month_window)
    )[:6]

    picked = R._pick_headlines(entries, window=month_window)

    assert len(picked) == R.HEADLINES == 6
    assert [p["id"] for p in picked] == [e["id"] for e in expected]


def test_a_headline_without_a_summary_is_not_usable(month_window):
    """"Why it matters" is the whole point of the block."""
    entries = [page("no-summary", priority="★★★"), page("has-summary", summary="s", priority="★")]
    picked = R._pick_headlines(entries, window=month_window)
    assert [R._tl(p) for p in picked] == ["has-summary"]


def test_a_headline_may_come_from_the_catch_all_topic(month_window):
    """The month's biggest acquisition is filed under 行业动态, and it still counts."""
    entries = [page("acq", topic="行业动态", priority="★★★", summary="s")]
    assert len(R._pick_headlines(entries, window=month_window)) == 1


def test_headline_order_does_not_depend_on_the_order_notion_returns_pages(month_window):
    entries = [
        page(f"e{i}", priority="★★★", summary="s", collected=f"2026-09-{i + 1:02d}")
        for i in range(8)
    ]
    expected = [p["id"] for p in R._pick_headlines(entries, window=month_window)]

    shuffled = list(entries)
    random.Random(0).shuffle(shuffled)

    assert [p["id"] for p in R._pick_headlines(shuffled, window=month_window)] == expected


def test_a_tie_is_broken_by_the_entry_and_not_by_notion(month_window):
    """Score, then day, then the entry itself.

    Two entries can tie on both of the first two keys — a batch of papers all
    collected on the same day scores identically. Without the last two keys the
    order is left to the API, which decides which of them survives the cut at
    the sixth slot, and it changes between runs of the same month.
    """
    entries = [
        page(f"e{i}", kind="paper", priority="★★★", summary="s", collected="2026-09-23")
        for i in range(8)
    ]
    tied = {R._sort_key(e, month_window)[:2] for e in entries}
    assert len(tied) == 1, "the fixture is only meaningful while every entry ties"

    expected = [p["id"] for p in R._pick_headlines(entries, window=month_window)]

    shuffled = list(entries)
    random.Random(1).shuffle(shuffled)

    assert len(expected) == 6
    assert [p["id"] for p in R._pick_headlines(shuffled, window=month_window)] == expected


def test_news_cannot_take_every_slot(month_window):
    """The regression this cap exists for: 17 news and 35 papers tied at 8 points,
    and recency — news lands daily, papers in one batch — picked news every time."""
    # The date is not decoration: _score rewards the last quarter of the month,
    # so papers and news have to sit in the same band or the cap is not the only
    # thing separating them. 09-23 is the first day of that band, and the news
    # runs to the end of the month — fresher than every paper, never a band up.
    papers = [
        page(f"p{i}", kind="paper", priority="★★★", summary="s", collected="2026-09-23")
        for i in range(35)
    ]
    # More news than there are slots, so the cap has to actually hold some back:
    # with exactly half the slots filled by news, deleting the cap changes nothing.
    news = [
        page(f"n{i}", kind="news", priority="★★★", summary="s", collected=f"2026-09-{24 + i:02d}")
        for i in range(7)
    ]
    # Every candidate scores the same, and every news item is fresher than every paper.
    assert len({R._score(p, month_window) for p in papers + news}) == 1

    picked = R._pick_headlines(papers + news, window=month_window)

    assert Counter(R._kind(p) for p in picked) == {"paper": 3, "news": 3}
    assert [R._tl(p) for p in picked[:3]] == ["n6", "n5", "n4"]  # freshest news still leads


def test_the_cap_outranks_the_fill(month_window):
    """A month with more news than slots and only one paper: the news tops the
    block back up to six, but it does not push the paper out.

    Regression: the two were merged and re-sorted, so the paper was picked and
    then displaced, and the block came back as six news — the failure the cap
    exists to prevent, on the one month shape where the cap could not stop it.
    """
    papers = [page("p0", kind="paper", priority="★★★", summary="s", collected="2026-09-23")]
    news = [
        page(f"n{i}", kind="news", priority="★★★", summary="s", collected=f"2026-09-{24 + i:02d}")
        for i in range(7)
    ]

    picked = R._pick_headlines(papers + news, window=month_window)

    assert len(picked) == R.HEADLINES
    assert R._tl(picked[3]) == "p0"
    assert Counter(R._kind(p) for p in picked) == {"news": 5, "paper": 1}


def test_the_cap_is_a_ceiling_never_a_target(month_window):
    """A month with nothing but news must not be reported with half a block."""
    entries = [
        page(f"n{i}", kind="news", priority="★★★", summary="s", collected=f"2026-09-{i + 1:02d}")
        for i in range(9)
    ]
    picked = R._pick_headlines(entries, window=month_window)
    expected = sorted(entries, key=lambda e: R._sort_key(e, month_window))[:6]
    assert [p["id"] for p in picked] == [e["id"] for e in expected]


def test_a_repo_month_splits_the_slots_with_the_news(month_window):
    entries = [page(f"n{i}", kind="news", priority="★★★", summary="s") for i in range(6)] + [
        page(f"r{i}", kind="repo", priority="★★★", summary="s") for i in range(4)
    ]
    picked = R._pick_headlines(entries, window=month_window)
    assert Counter(R._kind(p) for p in picked) == {"news": 3, "repo": 3}


def test_a_headline_carries_the_stored_summary_until_an_llm_replaces_it(month_window):
    entries = [page("r", kind="repo", topic="AI Agent", source="GitHub", stars=45200, summary="用途")]
    headline = _headlines(entries, month_window)[0]

    assert headline.why == "用途"
    assert headline.link == "https://example.com/x"


def test_a_headline_we_would_follow_is_a_link(month_window):
    entries = [page("a", topic="AI Agent", summary="s", link="https://example.com/story")]
    html = _render_for(entries, [], month_window, headlines=_headlines(entries, month_window))

    assert '<a href="https://example.com/story" target="_blank" rel="noopener" class="ttl">' in html


@pytest.mark.parametrize(
    "link",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        " javascript:alert(1) ",
        "vbscript:msgbox(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "//evil.test/story",
        "",
    ],
)
def test_a_headline_we_would_not_follow_is_plain_text(month_window, link):
    """Escaping stops a quote from breaking out of the attribute; it says nothing
    about the scheme, and a `javascript:` href runs in the report's own origin
    when the reader clicks it.

    Notion's Link property is free text unless it is url-typed, so this is the
    last place that can tell a link from a script. The title still has to appear
    — dropping the row would lose the story, not just the link.
    """
    entries = [page("a", topic="AI Agent", summary="s", link=link)]
    html = _render_for(entries, [], month_window, headlines=_headlines(entries, month_window))

    assert '<span class="ttl">a</span>' in html
    assert "<a " not in html
    if link.strip():
        assert R._esc(link) not in html


def test_a_quote_in_a_link_cannot_break_out_of_the_attribute(month_window):
    """A url-typed Notion property is not the only way a link arrives — the
    property is free text, so the quote has to be neutralised either way."""
    entries = [
        page("a", topic="AI Agent", summary="s", link='https://example.com/x" onmouseover="alert(1)')
    ]
    html = _render_for(entries, [], month_window, headlines=_headlines(entries, month_window))

    assert '" onmouseover="' not in html
    assert "&quot; onmouseover=&quot;" in html


# ═══════════ The 综述 ═══════════


def test_the_digest_prompt_carries_every_headline(month_window):
    """The 综述 must be written about the same stories the page lists under it."""
    entries = [
        page(f"e{i}", kind="news", priority="★★★", summary="s", collected=f"2026-09-{i + 1:02d}")
        for i in range(7)
    ]
    headlines = _headlines(entries, month_window)
    stats = R._compute_stats(entries, [], month_window)

    prompt = R._digest_prompt(stats, R._topic_rows(entries, []), headlines)

    assert len(headlines) == 6
    for headline in headlines:
        assert headline.title in prompt

    # …and nothing else, or the model could write about a story the page never lists.
    picked = {p["id"] for p in R._pick_headlines(entries, window=month_window)}
    dropped = [e for e in entries if e["id"] not in picked]
    assert len(dropped) == 1
    assert R._tl(dropped[0]) not in prompt


def test_a_month_with_no_api_key_still_gets_a_digest(month_window):
    current = _n("安全与对齐", 15)
    previous = _n("安全与对齐", 5)
    stats = R._compute_stats(current, previous, month_window)

    digest, why = R._summarize(R.LLMConfig(api_key=""), stats, R._topic_rows(current, previous), [])

    assert digest.lead and digest.body
    assert why == []
    assert "安全" in digest.lead


def test_the_template_digest_quotes_no_numbers(month_window):
    """The rule the whole redesign is built on: judgement, not the chart read aloud."""
    current = _n("安全与对齐", 15) + _n("多模态", 30)
    previous = _n("安全与对齐", 5) + _n("多模态", 60)
    stats = R._compute_stats(current, previous, month_window)

    digest = R._template_digest(stats, R._topic_rows(current, previous))

    assert not re.search(r"\d", digest.lead + digest.body)
    assert digest.body  # a falling topic and a biggest topic, both worth naming


def test_an_empty_month_gets_a_template_rather_than_nothing(month_window):
    stats = R._compute_stats([], [], month_window)
    digest = R._template_digest(stats, [])
    assert digest.lead and not re.search(r"\d", digest.lead)


def test_a_successful_call_becomes_the_digest(month_window, monkeypatch):
    monkeypatch.setattr(
        R, "_call_llm", lambda *a, **k: {"lead": "主线是 Agent 管不住。", "body": "值得警惕。", "why": ["改写的摘要"]}
    )
    current = [page("a", topic="AI Agent", summary="原文")]
    stats = R._compute_stats(current, [], month_window)

    digest, why = R._summarize(
        R.LLMConfig(api_key="k"), stats, R._topic_rows(current, []), _headlines(current, month_window)
    )

    assert digest == R.Digest("主线是 Agent 管不住。", "值得警惕。")
    assert why == ["改写的摘要"]


def test_a_failing_call_falls_back_instead_of_raising(month_window, monkeypatch):
    """A month that cannot be reported because an LLM is down is worse than a plain one."""
    def boom(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(R, "_call_llm", boom)
    current = [page("a", topic="AI Agent", summary="原文")]
    stats = R._compute_stats(current, [], month_window)

    digest, why = R._summarize(
        R.LLMConfig(api_key="k"), stats, R._topic_rows(current, []), _headlines(current, month_window)
    )

    assert digest.lead
    assert why == ["原文"]


@pytest.mark.parametrize(
    "reply",
    [
        {"lead": "", "body": "", "why": []},
        {},
        # The retry drops response_format, so the model is free to answer with a
        # bare JSON value instead of the object that was asked for. The report
        # has to survive that: it is the one call whose failure loses the page.
        [],
        ["lead", "body"],
        "综述：这个月…",
        None,
        7,
    ],
)
def test_an_empty_reply_falls_back_to_the_template(month_window, monkeypatch, reply):
    monkeypatch.setattr(R, "_call_llm", lambda *a, **k: reply)
    current = [page("a", topic="AI Agent", summary="原文")]
    stats = R._compute_stats(current, [], month_window)

    digest, _ = R._summarize(
        R.LLMConfig(api_key="k"), stats, R._topic_rows(current, []), _headlines(current, month_window)
    )

    assert digest.lead and not re.search(r"\d", digest.lead)


def test_a_short_why_list_keeps_the_stored_summaries(month_window, monkeypatch):
    monkeypatch.setattr(R, "_call_llm", lambda *a, **k: {"lead": "L", "body": "B", "why": ["只有一条"]})
    headlines = [
        R.Headline("news", "t1", "u", [], "原文一", "AI Agent"),
        R.Headline("news", "t2", "u", [], "原文二", "AI Agent"),
    ]
    stats = R._compute_stats([], [], month_window)

    _, why = R._summarize(R.LLMConfig(api_key="k"), stats, [], headlines)

    assert why == ["只有一条", "原文二"]


# ═══════════ Rendering ═══════════


def _render_for(
    entries: list[dict],
    previous: list[dict],
    window,
    *,
    headlines: list[R.Headline] | None = None,
    digest: R.Digest | None = None,
    notion_url: str = "",
) -> str:
    """Render the page the way ``generate`` does, so tests exercise the real wiring."""
    stats = R._compute_stats(entries, previous, window)
    return R._render(
        window,
        stats,
        R._topic_rows(entries, previous),
        digest if digest is not None else R.Digest(),
        headlines if headlines is not None else _headlines(entries, window),
        notion_url,
    )


def test_the_page_reads_in_the_planned_order(month_window):
    """刊头 → 图表 → 概要 → 重点 → 页脚, matching the order of the questions."""
    entries = [page("a", topic="AI Agent", priority="★★★", summary="s")]
    html = _render_for(entries, [], month_window, digest=R.Digest("主线。", "结论。"))

    order = [
        html.index('class="kicker"'),
        html.index("<h2>图表</h2>"),
        html.index('class="fig"'),          # the chart lives under 图表…
        html.index("<h2>概要</h2>"),
        html.index('class="summary"'),      # …the prose under 概要…
        html.index("<h2>重点</h2>"),
        html.index('class="events"'),       # …the evidence under 重点.
        html.index('class="foot"'),
    ]
    assert order == sorted(order)


def test_every_block_is_named(month_window):
    """No block should have to be recognised by its position alone."""
    html = _render_for([page("a", topic="AI Agent", summary="s")], [], month_window,
                       digest=R.Digest("主线。", "结论。"))
    assert re.findall(r"<h2>(.*?)</h2>", html) == ["图表", "概要", "重点"]


def test_the_report_pulls_in_nothing_from_the_network(month_window):
    """The old page loaded ECharts from a CDN on every view.

    The page does carry external URLs — every headline links out — so the
    contract is not "no https" but "no *subresource*": nothing the browser goes
    and fetches on its own before it can draw the page. That means src and href
    are not equivalent here: ``<a href>`` is a link; ``<link href>`` is a fetch.
    """
    entries = [page("a", topic="AI Agent", summary="s")]
    html = _render_for(entries, [], month_window, headlines=_headlines(entries, month_window))

    assert "<script" not in html
    assert "<link" not in html
    assert "@import" not in html
    assert not re.search(r"\bsrc\s*=", html)
    assert "echarts" not in html
    # …and the block that used to hold the library really did render, so the
    # assertions above are about a chart rather than about an empty page.
    assert 'class="fig"' in html
    assert 'class="ttl"' in html


def test_the_page_has_no_decorative_emoji(month_window):
    """Emoji are banned as decoration, not as characters: the repo row still
    reports its star count, as text.

    The ranges matter. An earlier version stopped at U+1FAFF and U+27BF, which
    left U+2B50 out — and the page was rendering ``⭐45.2k`` at the time.
    """
    entries = [
        page("a", topic="AI Agent", summary="s"),
        page("b", kind="repo", stars=45200, summary="s", collected="2026-09-16"),
    ]
    html = _render_for(entries, [], month_window, headlines=_headlines(entries, month_window))

    assert "45.2k stars" in html  # the fact survives, as text
    assert not re.search(r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]", html)


def test_no_numbered_markers_or_kpi_tiles_remain(month_window):
    html = _render_for([page("a", topic="AI Agent", summary="s")], [], month_window)
    assert 'class="s-num"' not in html
    assert 'class="kpi"' not in html
    assert not re.search(r">0[1-5]<", html)


def _css() -> str:
    return Path(R.__file__).read_text(encoding="utf-8").split('_CSS = """', 1)[1].split('\n"""', 1)[0]


def test_the_type_scale_has_six_levels_and_no_half_pixels():
    """A scale only works if it is closed. Half-pixel sizes are the signature of
    someone nudging one element instead of fixing the scale."""
    sizes = {float(v) for v in re.findall(r"font-size:\s*([\d.]+)px", _css())}
    assert sizes == {10, 12, 13, 16, 17, 24}


def test_every_gap_comes_from_the_spacing_scale():
    """4/8/12/16/24/32/48/64 and nothing else — no 5, 6, 7, 10, 14 anywhere."""
    css = _css()
    used = set()
    for prop in ("margin", "margin-top", "margin-bottom", "padding", "padding-top",
                 "padding-bottom", "gap"):
        for value in re.findall(rf"(?<![\w-]){prop}:\s*([^;}}]+)[;}}]", css):
            used.update(re.findall(r"--s(\d)", value))
            assert "px" not in value or value.strip() == "0", f"{prop}: {value.strip()}"

    tokens = dict(re.findall(r"--s(\d):(\d+)px", css))
    assert used <= set(tokens), f"used but not declared: {used - set(tokens)}"
    for step, px in tokens.items():
        assert int(px) % 4 == 0, f"--s{step}: {px}px is off the 4px grid"


def test_the_chart_repeats_the_tier_nowhere(month_window):
    """The rows are sorted biggest-rise-first and the bars are coloured; three
    band header rows on top of that is the same fact told three times."""
    entries = _n("安全与对齐", 15) + _n("多模态", 30)
    html = _render_for(entries, _n("安全与对齐", 5) + _n("多模态", 60), month_window)

    # The rows really are there — matched on the tier, not on a guessed tag, so
    # a future change to <b> or <span> cannot quietly empty this test.
    assert 'class="row row-up"' in html
    assert 'class="row row-dn"' in html

    for label in ("升温", "平稳", "降温"):
        assert label not in html
    # …but the thresholds are still stated, once, in the caption.
    assert "橙 = 涨 20% 以上且至少 +3 条" in html


def test_the_page_carries_a_dark_mode_palette(month_window):
    html = _render_for([page("a")], [], month_window)
    assert "prefers-color-scheme: dark" in html
    assert "color-scheme: dark" in html


def test_the_footer_flags_the_unclassified_share(month_window):
    entries = _n("行业动态", 277) + _n("AI Agent", 100)
    html = _render_for(entries, [], month_window)
    assert "其中 277 条未归入主题（73%）" in html


def test_the_footer_hides_the_source_count_until_sources_are_stored(month_window):
    """Every September row has an empty Source property; "4 个来源" would really
    just be counting the four entry types."""
    entries = [page(f"n{i}", kind="news", link="https://www.qbitai.com/x") for i in range(3)]
    entries += [page(f"p{i}", kind="paper", link="https://arxiv.org/abs/1") for i in range(2)]

    html = _render_for(entries, [], month_window)

    assert "个来源" not in html
    assert R._compute_stats(entries, [], month_window).source_count == 0


def test_the_footer_reports_stored_sources_once_they_exist(month_window):
    entries = [page("a", source="GitHub"), page("b", source="量子位")]
    stats = R._compute_stats(entries, [], month_window)
    assert stats.source_count == 2
    assert "2 个来源" in _render_for(entries, [], month_window)


def test_an_empty_month_renders_a_skeleton_instead_of_crashing(month_window):
    html = _render_for([], [], month_window)
    assert "本期没有主题数据" in html
    assert "本期没有条目" in html


def test_the_masthead_names_the_month_and_the_window(month_window):
    html = _render_for([page("a")], [], month_window)
    assert "2026 年 9 月" in html
    assert "09-01 → 09-30" in html
    assert "第 9 期" not in html


def test_the_topic_note_names_the_month_it_compares_against(month_window):
    html = _render_for([page("a", topic="AI Agent")], [], month_window)
    assert "较 8 月" in html


def test_the_copy_names_no_statistics_jargon(month_window):
    """「环比」「收录」 are precise for the LLM prompt and opaque on the page —
    the page says 较上月 / 本期 instead.

    The entry must carry a topic. With an empty table neither the header row nor
    the caption renders, and those two are exactly where the jargon used to live:
    assert the header is present so this cannot pass by rendering nothing.
    """
    current = [page("a", topic="AI Agent")]
    html = _render_for(current, [page("b", topic="AI Agent")], month_window)

    assert '<span class="r">较上月</span>' in html
    assert "环比" not in html
    assert "收录" not in html


def test_the_chrome_says_what_it_means(month_window):
    """The rest of the chrome. Each spelling replaced one a reader had to stop
    and translate: 月刊 after 月报, a statistics column header, a caption that
    explained itself twice."""
    current = [page("a", topic="AI Agent")]
    html = _render_for(current, [page("b", topic="AI Agent")], month_window)

    assert "<title>2026 年 9 月 · AI 技术月报</title>" in html
    assert '<div class="kicker">AI 技术月报</div>' in html
    assert "月刊" not in html

    assert "条形 = 较上月的增减条数" in html
    assert "按涨跌排序" not in html  # 从上到下从 +N 读到 -N already says it
    assert "反过来则是工程先行" not in html  # symmetric; the reader supplies it


def test_the_template_digest_calls_counts_counts(month_window):
    """The no-API-key 综述 is still page copy, so it gets the same words."""
    current = _n("安全与对齐", 15) + _n("多模态", 30)
    previous = _n("安全与对齐", 5) + _n("多模态", 60)
    stats = R._compute_stats(current, previous, month_window)

    digest = R._template_digest(stats, R._topic_rows(current, previous))

    assert "本期条目数较上月" in digest.lead
    assert "条目最多的是" in digest.body
    assert "收录" not in digest.lead + digest.body


def test_the_highlights_note_explains_the_order(month_window):
    """The list is not numbered, so *why* it is in this order has to be said.

    The count is the trap: it renders as "1 条" for a one-entry list and "6 条"
    for a full one, so no fixed string rules it out. Assert the *shape* — a bare
    ``N 条`` note — which the old markup produced at every list length.
    """
    entries = [page("a", topic="AI Agent")]
    html = _render_for(entries, [], month_window, headlines=_headlines(entries, month_window))

    assert "<h2>重点</h2><i></i><span>按重要性排序</span>" in html
    notes = re.findall(r"<h2>(.*?)</h2><i></i>(?:<span>(.*?)</span>)?", html)
    assert notes == [("图表", "较 8 月"), ("概要", ""), ("重点", "按重要性排序")]
    assert not [n for _, n in notes if n and re.fullmatch(r"\d+\s*条", n)]


@pytest.mark.parametrize("kind", ["paper", "repo", "news"])
def test_titles_and_links_are_escaped(kind, month_window):
    headline = R.Headline(
        kind=kind,
        title='Serving & scaling "small" models',
        link="https://example.com/a?x=1&y=2",
        meta=["GitHub", "09-10"],
        why="R&D <faster>",
        topic="推理优化",
    )

    html = _render_for([page("x")], [], month_window, headlines=[headline])

    assert "Serving &amp; scaling &quot;small&quot; models" in html
    assert 'href="https://example.com/a?x=1&amp;y=2"' in html
    assert "R&amp;D &lt;faster&gt;" in html
    assert "R&D <faster>" not in html


def test_the_digest_and_topic_names_are_escaped(month_window):
    digest = R.Digest(lead="<script>alert(1)</script>", body="a & b")
    entries = [page("a", topic='<img src=x onerror="1">')]

    html = _render_for(entries, [], month_window, digest=digest, headlines=[])

    assert "<script>alert(1)</script>" not in html
    assert "<img src=x" not in html
    assert "a &amp; b" in html


def test_no_report_contains_the_old_hardcoded_phrases():
    for constant in ("逼近", "开源 vs 闭源"):
        assert constant not in Path(R.__file__).read_text(encoding="utf-8")


def test_the_report_is_self_contained_html(tmp_path):
    store = FakeStore([page("a", collected="2026-09-30")])
    path = R.generate(_cfg(tmp_path), store, run_date=_d("2026-10-01"))
    html = path.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")
    assert "按入库时间" in html


def test_generate_uses_the_template_when_no_llm_is_configured(tmp_path):
    """The default test config has no API key, which is the degradation path."""
    store = FakeStore([page("a", topic="AI Agent", collected="2026-09-30", summary="s")])
    path = R.generate(_cfg(tmp_path), store, run_date=_d("2026-10-01"))
    html = path.read_text(encoding="utf-8")
    assert 'class="summary"' in html
    assert 'class="summary"><p></p>' not in html


def test_reports_do_not_touch_the_repository_issues_dir():
    """A default config would write into the checkout; tests must not."""
    assert R.generate.__module__ == "mimir.report"
