"""GitHub Trending parsing — the star count must be the total, not the weekly gain."""

from __future__ import annotations

from mimir.sources.github import _parse

# Structure copied from https://github.com/trending: the row shows "N stars this
# week" in the right-hand span and the true total in the stargazers link.
TRENDING_HTML = """
<html><body>
<article class="Box-row">
  <h2 class="h3 lh-condensed"><a href="/caddyserver/caddy">caddy</a></h2>
  <p class="col-9 color-fg-muted my-1 pr-4">Fast and extensible multi-platform web server.</p>
  <div class="f6 color-fg-muted mt-2">
    <a href="/caddyserver/caddy/stargazers">77,517</a>
    <span class="d-inline-block float-sm-right">1,320 stars this week</span>
  </div>
</article>
<article class="Box-row">
  <h2 class="h3 lh-condensed"><a href="/tiann/KernelSU">KernelSU</a></h2>
  <p class="col-9 color-fg-muted my-1 pr-4">A Kernel based root solution for Android</p>
  <div class="f6 color-fg-muted mt-2">
    <a href="/tiann/KernelSU/stargazers">18,964</a>
    <span class="d-inline-block float-sm-right">238 stars this week</span>
  </div>
</article>
</body></html>
"""


def test_parse_stores_the_total_star_count():
    entries = _parse(TRENDING_HTML, 10)

    assert [e.extra["stars"] for e in entries] == [77517, 18964]
    assert [e.title for e in entries] == ["caddyserver/caddy", "tiann/KernelSU"]
    assert entries[0].link == "https://github.com/caddyserver/caddy"
    assert entries[0].source == "github_trending"
    assert entries[0].entry_type.value == "repo"


def test_limit_is_honoured():
    assert len(_parse(TRENDING_HTML, 1)) == 1


def test_a_row_without_a_stargazers_link_reports_no_count():
    """Omit the number rather than substitute the weekly gain for it."""
    html = TRENDING_HTML.replace('<a href="/tiann/KernelSU/stargazers">18,964</a>', "")
    entries = _parse(html, 10)
    assert entries[1].extra["stars"] == 0
