import re
import hashlib
import requests
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
}

def fetch_laylo_and_seated_signups():
    """Scans live public tour announcements & presale feeds for Laylo, Seated, and Artist Presale RSVP links."""
    discovered = []
    seen_urls = set()

    # Search public JSON feeds for newly posted Laylo & Seated presale signup links
    search_endpoints = [
        "https://www.reddit.com/search.json?q=site%3Alaylo.com+OR+site%3Asignup.seated.com&sort=new&t=week&limit=50",
        "https://www.reddit.com/r/popheads+r/indieheads+r/Concerts+r/aclfestival/search.json?q=presale+signup+OR+laylo+OR+seated&restrict_sr=on&sort=new&t=week&limit=50",
    ]

    link_pattern = re.compile(r"https?://(?:www\.)?(?:laylo\.com/[A-Za-z0-9_./-]+|signup\.seated\.com/[A-Za-z0-9_./-]+|livemu\.sc/[A-Za-z0-9_./-]+|presale\.ticketmaster\.com/[A-Za-z0-9_./-]+)")

    for url in search_endpoints:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue

            posts = resp.json().get("data", {}).get("children", [])
            for item in posts:
                post = item.get("data", {})
                title = post.get("title", "").strip()
                selftext = post.get("selftext", "")
                post_url = post.get("url", "")
                combined = f"{title} {post_url} {selftext}"

                matches = link_pattern.findall(combined)
                for reg_link in matches:
                    clean_link = reg_link.rstrip(").,;\"'")
                    if clean_link in seen_urls:
                        continue
                    seen_urls.add(clean_link)

                    platform = "Laylo RSVP" if "laylo.com" in clean_link else ("Seated Signup" if "seated.com" in clean_link else "Official Presale Signup")
                    uid = hashlib.sha256(clean_link.encode()).hexdigest()[:16]

                    discovered.append({
                        "id": f"rsvp_{uid}",
                        "artist": title[:80] if title else "New Tour Presale",
                        "event_name": f"{platform} — {title[:90]}",
                        "venue": platform,
                        "city": "Global / Multi-City",
                        "date": f"Active Signup ({platform})",
                        "has_presale": True,
                        "presale_name": platform,
                        "presale_start": datetime.now(timezone.utc).isoformat(),
                        "public_start": None,
                        "reg_link": clean_link,
                        "source": platform
                    })
        except Exception as e:
            print(f"⚠️ Laylo/Seated scan warning: {e}")

    print(f"✅ Found {len(discovered)} live Laylo / Seated / Official Presale RSVP links.")
    return discovered
