import os
import requests
from datetime import datetime, timezone

TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY")
BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"

def parse_iso(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None

def fetch_ticketmaster_events(size=200):
    if not TICKETMASTER_API_KEY:
        print("❌ ERROR: TICKETMASTER_API_KEY is missing in GitHub Secrets!")
        return []

    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    collected = []
    seen_ids = set()

    # Fetch upcoming sales & newly announced presales across US, UK, Canada, EU, AU
    queries = [
        {"countryCode": "US", "classificationName": "Music", "onsaleStartDateTime": now_str, "size": 200},
        {"countryCode": "GB", "classificationName": "Music", "onsaleStartDateTime": now_str, "size": 150},
        {"countryCode": "CA", "classificationName": "Music", "onsaleStartDateTime": now_str, "size": 100},
        {"countryCode": "AU", "classificationName": "Music", "onsaleStartDateTime": now_str, "size": 100},
        {"countryCode": "DE", "classificationName": "Music", "onsaleStartDateTime": now_str, "size": 100},
        # Also catch Comedy (like David Cross) & newly announced events with future presales
        {"countryCode": "US,GB,CA,AU", "classificationName": "Comedy", "onsaleStartDateTime": now_str, "size": 100},
    ]

    for q in queries:
        params = {"apikey": TICKETMASTER_API_KEY, **q}
        try:
            resp = requests.get(BASE_URL, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"⚠️ Ticketmaster API error ({resp.status_code}): {resp.text[:150]}")
                continue

            events = resp.json().get("_embedded", {}).get("events", [])
            for ev in events:
                ev_id = ev.get("id")
                if not ev_id or ev_id in seen_ids:
                    continue

                sales = ev.get("sales", {})
                public_sale = sales.get("public", {})
                public_start = parse_iso(public_sale.get("startDateTime"))

                presales = sales.get("presales", [])
                upcoming_presales = []
                for p in presales:
                    p_start = parse_iso(p.get("startDateTime"))
                    p_end = parse_iso(p.get("endDateTime"))
                    if (p_start and p_start > now_utc) or (p_start and p_end and p_start <= now_utc <= p_end):
                        upcoming_presales.append({
                            "name": p.get("name", "Presale"),
                            "start": p_start,
                            "end": p_end,
                            "url": p.get("url") or ev.get("url")
                        })

                has_future_public = bool(public_start and public_start > now_utc)
                if not upcoming_presales and not has_future_public:
                    continue

                seen_ids.add(ev_id)

                attractions = ev.get("_embedded", {}).get("attractions", [])
                artist_name = attractions[0].get("name") if attractions else ev.get("name", "Unknown Artist")

                venues = ev.get("_embedded", {}).get("venues", [])
                venue = venues[0] if venues else {}
                city = venue.get("city", {}).get("name", "")
                country = venue.get("country", {}).get("countryCode", "")
                venue_name = venue.get("name", "")
                location_str = f"{city}, {country}".strip(", ")

                upcoming_presales.sort(key=lambda x: x["start"] or now_utc)
                best_presale = upcoming_presales[0] if upcoming_presales else None

                if best_presale:
                    sale_info = f"Presale ({best_presale['name']}): {best_presale['start'].strftime('%Y-%m-%d %H:%M UTC')}"
                    reg_link = best_presale["url"] or ev.get("url", "")
                else:
                    sale_info = f"Public Sale: {public_start.strftime('%Y-%m-%d %H:%M UTC')}"
                    reg_link = ev.get("url", "")

                collected.append({
                    "id": ev_id,
                    "artist": artist_name,
                    "event_name": ev.get("name", artist_name),
                    "venue": venue_name,
                    "city": location_str,
                    "date": sale_info,
                    "has_presale": bool(best_presale),
                    "presale_name": best_presale["name"] if best_presale else None,
                    "presale_start": best_presale["start"].isoformat() if best_presale and best_presale["start"] else None,
                    "public_start": public_start.isoformat() if public_start else None,
                    "reg_link": reg_link,
                    "source": "Ticketmaster"
                })
        except Exception as e:
            print(f"⚠️ Ticketmaster exception: {e}")

    print(f"✅ Ticketmaster verified upcoming sales/presales: {len(collected)}")
    return collected
