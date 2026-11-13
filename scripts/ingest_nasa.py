"""Fetch NASA pages listed in data/knowledge_sources.txt and index them into ChromaDB.

Usage:  python scripts/ingest_nasa.py
Requires network access and `pip install chromadb requests`.
"""
import hashlib
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from astro import config  # noqa: E402


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def chunks(text, size=700):
    sentences, cur = re.split(r"(?<=[.!?])\s+", text), ""
    for s in sentences:
        if len(cur) + len(s) > size and cur:
            yield cur.strip()
            cur = ""
        cur += s + " "
    if cur.strip():
        yield cur.strip()


def main():
    import chromadb
    import requests
    urls = [l.strip() for l in (config.DATA_DIR / "knowledge_sources.txt").read_text().splitlines()
            if l.strip() and not l.startswith("#")]
    col = chromadb.PersistentClient(path=str(config.CHROMA_DIR)).get_or_create_collection("astro_science_v2")
    total = 0
    for url in urls:
        try:
            html = requests.get(url, timeout=20, headers={"User-Agent": "AstroPlay-ingest/1.0"}).text
        except Exception as e:
            print(f"SKIP {url}: {e}")
            continue
        p = _Text()
        p.feed(html)
        text = " ".join(p.parts)
        for c in chunks(text):
            if len(c) < 120:
                continue
            cid = hashlib.sha1((url + c).encode()).hexdigest()
            col.upsert(ids=[cid], documents=[c],
                       metadatas=[{"topics": "general", "level": "mid", "lang": "en", "base": cid, "source": url}])
            total += 1
        print(f"OK   {url}")
    print(f"Indexed {total} chunks. Collection size: {col.count()}")


if __name__ == "__main__":
    main()
