import re
import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PresaleRadarBot/1.0)"
}

def fetch_laylo_and_seated_signups():
    """Fetches real-time Laylo, Seated, and Official Artist Presale Signup announcements via Google & Bing News RSS (never blocked on GitHub Actions)."""
    discovered = []
    seen_ids = set()

    rss_feeds = [
        "https://news.google.com/rss/search?q=%22presale%22+%22sign+up%22+OR+%22artist+presale%22+tour+when:2d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=%22laylo.com%22+OR+%22seated.com%22+presale+when:7d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=%22presale+registration%22+OR+%22verified+fan%22+tour+2026+2027+when:3d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=%22tickets+go+on+sale%22+%22presale%22+tour+when:2d&hl=en-GB&gl=GB&ceid=GB:en",
    ]

    for feed_url in rss_feeds:
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue

            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:20]:
                title_el = item.find("title")
                link_el = item.find("link")
                pub_el = item.find("pubDate")

                title = title_el.text.strip() if title_el is not None and title_el.text else ""
                link = link_el.text.strip() if link_el is not None and link_el.text else ""
                pub_date = pub_el.text.strip() if pub_el is not None and pub_el.text else "Recent"

                if not title or not link:
                    continue

                uid = hashlib.sha256(title.lower().encode()).hexdigest()[:16]
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)

                clean_title = title.split(" - ")[0].strip()
                platform = "Laylo / Seated" if ("laylo" in title.lower() or "seated" in title.lower()) else "Presale Signup / Tour"

                discovered.append({
                    "id": f"news_{uid}",
                    "artist": clean_title[:85],
                    "event_name": title[:110],
                    "venue": platform,
                    "city": "US / UK / Global",
                    "date": f"Announced: {pub_date[:16]}",
                    "has_presale": True,
                    "presale_name": platform,
                    "presale_start": datetime.now(timezone.utc).isoformat(),
                    "public_start": None,
                    "reg_link": link,
                    "source": platform
                })
        except Exception as e:
            print(f"⚠️ RSS feed warning: {e}")

    print(f"✅ Found {len(discovered)} live Presale Signup & Tour announcements.")
    return discovered
