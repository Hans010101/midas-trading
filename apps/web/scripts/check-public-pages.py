"""Verify the public HTML the deployed Worker serves to readers and crawlers."""
import json
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

BASE = "https://midastrade.asia"


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lang = None
        self.canonical = None
        self.headings = 0
        self.ids = set()
        self.links = set()
        self.schemas = []
        self.in_schema = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "html":
            self.lang = attrs.get("lang")
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")
        if tag == "a":
            self.links.add(attrs.get("href"))
        if tag == "h1":
            self.headings += 1
        if tag == "h3":
            self.ids.add(attrs.get("id"))
        if tag == "script":
            self.in_schema = attrs.get("type") == "application/ld+json"

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_schema = False

    def handle_data(self, data):
        if self.in_schema:
            schema = json.loads(data)
            self.schemas.extend(schema if isinstance(schema, list) else [schema])


def fetch(path):
    request = Request(BASE + path, headers={"User-Agent": "Midas-DeploymentMonitor/1.0"})
    return urlopen(request, timeout=30)


def check(path):
    with fetch(path) as response:
        page = Document()
        page.feed(response.read().decode("utf-8"))
    assert page.canonical == BASE + path, (path, page.canonical)
    assert page.headings == 1, (path, page.headings)
    assert page.lang == ("en" if path.startswith("/en/") else "zh-CN"), (path, page.lang)
    return page


if __name__ == "__main__":
    check("/lab/assistant")
    check("/en/privacy")
    check("/en/academy/article/C8")
    for market in ("cn", "us", "hk", "crypto"):
        page = check(f"/{market}-market")
        assert any(link and link.startswith(f"/{market}/") for link in page.links), market
    for prefix in ("", "/en"):
        path = prefix + "/academy/glossary"
        page = check(path)
        glossary = next(s for s in page.schemas if s.get("@type") == "DefinedTermSet")
        terms = glossary["hasDefinedTerm"]
        assert terms and len({t["url"] for t in terms}) == len(terms), path
        for term in terms:
            url = term["url"]
            anchor = urlsplit(url).fragment
            assert url == term["@id"] and url.startswith(BASE + path + "#"), url
            assert unquote(anchor) in page.ids and "#" + anchor in page.links, url
        print(f"{path}: {len(terms)} unique definitions with working permalinks")
    for path in ("/academy/article/missing-lesson", "/en/academy/article/missing-lesson",
                 "/academy/stage/missing-stage", "/en/academy/stage/missing-stage", "/us/INVALID%40%40"):
        try:
            with fetch(path) as response:
                raise AssertionError(f"{path} returned HTTP {response.status}")
        except HTTPError as error:
            assert error.code == 404, (path, error.code)
    for path in ("/us/PLTR", "/us/BRK.B", "/us-preview?symbol=PLTR"):
        with fetch(path) as response:
            assert "noindex" in response.headers.get("X-Robots-Tag", ""), path
    check("/academy/stage/basics")
    with fetch("/us/aapl") as response:
        assert response.geturl() == BASE + "/us/AAPL", response.geturl()
