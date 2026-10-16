"""Free news + sentiment. No API key needed (GDELT)."""
import requests, time
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()
_cache = {}  # symbol -> (ts, score, headlines)

def sentiment_score(text):
    return _analyzer.polarity_scores(text or "")["compound"]

def get_news_sentiment(symbol, max_items=8):
    """Returns (score -1..1, headlines[]). Cached 15 min."""
    now = time.time()
    if symbol in _cache and now - _cache[symbol][0] < 900:
        _, s, h = _cache[symbol]
        return s, h
    headlines, scores = [], []
    try:
        # GDELT DOC API — free, no key
        r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc",
                         params={"query": symbol, "mode": "ArtList",
                                 "maxrecords": max_items, "format": "json",
                                 "timespan": "24h"},
                         timeout=12)
        arts = r.json().get("articles", [])
        for a in arts:
            t = a.get("title", "")
            if t:
                headlines.append(t)
                scores.append(sentiment_score(t))
    except Exception:
        pass
    score = sum(scores) / len(scores) if scores else 0.0
    _cache[symbol] = (now, score, headlines)
    return score, headlines
