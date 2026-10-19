"""Free news + sentiment. No API key needed (Yahoo Finance RSS, Google News fallback)."""
import requests, time, re, html
from concurrent.futures import ThreadPoolExecutor, wait
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()
_cache = {}  # symbol -> (ts, score, headlines)
CACHE_TTL = 900
BATCH_TIMEOUT = 20
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def sentiment_score(text):
    return _analyzer.polarity_scores(text or "")["compound"]


def _titles_from_rss(xml, max_items):
    titles = []
    for m in re.finditer(r"<item\b.*?</item>", xml, re.S | re.I):
        t = re.search(r"<title>(.*?)</title>", m.group(0), re.S | re.I)
        if t:
            raw = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t.group(1), flags=re.S)
            title = html.unescape(raw).strip()
            if title:
                titles.append(title)
        if len(titles) >= max_items:
            break
    return titles


def _fetch(symbol, max_items=6):
    headlines = []
    urls = [
        f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
        f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=8, headers=UA)
            if r.status_code == 200 and "<item" in r.text:
                headlines = _titles_from_rss(r.text, max_items)
                if headlines:
                    break
        except Exception:
            continue
    scores = [sentiment_score(t) for t in headlines]
    score = sum(scores) / len(scores) if scores else 0.0
    return score, headlines


def get_news_sentiment(symbol, max_items=6):
    """Returns (score -1..1, headlines[]). Cached 15 min. Never raises."""
    now = time.time()
    hit = _cache.get(symbol)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1], hit[2]
    try:
        score, headlines = _fetch(symbol, max_items)
    except Exception:
        return 0.0, []
    _cache[symbol] = (now, score, headlines)
    return score, headlines


def get_sentiments(symbols, timeout=BATCH_TIMEOUT):
    """Batch version, bounded by `timeout` seconds total."""
    out = {s: (0.0, []) for s in symbols}
    now = time.time()
    todo = [s for s in symbols
            if not (_cache.get(s) and now - _cache[s][0] < CACHE_TTL)]
    for s in symbols:
        if s not in todo:
            out[s] = (_cache[s][1], _cache[s][2])
    if not todo:
        return out
    # NOTE: never use `with` here — context-manager exit would wait for hung
    # workers and defeat the timeout. Shutdown without waiting instead.
    ex = ThreadPoolExecutor(max_workers=min(4, len(todo)))
    try:
        futs = {ex.submit(_fetch, s): s for s in todo}
        done, _ = wait(futs.keys(), timeout=timeout)
        for f in done:
            s = futs[f]
            try:
                score, headlines = f.result()
            except Exception:
                continue
            _cache[s] = (time.time(), score, headlines)
            out[s] = (score, headlines)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return out
