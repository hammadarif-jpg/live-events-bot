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
        print("⚠️ Missing TICKETMASTER_API_KEY")
        return []

    now_utc = datetime.now(timezone.utc)
    collected = []
    seen_ids = set()

    # Scan major tour markets (US, UK, Canada, Germany, France, Netherlands, Australia)
    # and sort by date/relevance to catch newly announced tours & presales
    queries = [
        {"countryCode": "US", "classificationName": "Music", "sort": "onSaleStartDate,asc", "size": 200},
        {"countryCode": "GB", "classificationName": "Music", "sort": "onSaleStartDate,asc", "size": 150},
        {"countryCode": "CA", "classificationName": "Music", "sort": "onSaleStartDate,asc", "size": 100},
        {"countryCode": "DE,FR,NL,ES,IT,AU", "classificationName": "Music", "sort": "onSaleStartDate,asc", "size": 150},
        # Also catch brand-new announced tours where public onsale might still be TBD but presale is live
        {"countryCode": "US,GB,CA", "classificationName": "Music", "sort": "date,asc", "size": 200},
    ]

    for q in queries:
        params = {
            "apikey": TICKETMASTER_API_KEY,
            "onsaleStartDateTime": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            **q
        }
        # For the date-sorted query, don't restrict onsaleStartDateTime so TBD public sales with active presales are caught!
        if q.get("sort") == "date,asc":
            params.pop("onsaleStartDateTime", None)
            params["startDateTime"] = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            resp = requests.get(BASE_URL, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"⚠️ Ticketmaster API warning ({resp.status_code}): {resp.text[:120]}")
                continue

            events = resp.json().get("_embedded", {}).get("events", [])
            for ev in events:
                ev_id = ev.get("id")
                if not ev_id or ev_id in seen_ids:
                    continue

                sales = ev.get("sales", {})
                public_sale = sales.get("public", {})
                public_start = parse_iso(public_sale.get("startDateTime"))
                is_tbd = public_sale.get("startTBD", False)

                # Check ALL upcoming presales on this event
                presales = sales.get("presales", [])
                upcoming_presales = []
                for p in presales:
                    p_start = parse_iso(p.get("startDateTime"))
                    p_end = parse_iso(p.get("endDateTime"))
                    # Keep if presale starts in future OR is currently open right now!
                    if (p_start and p_start > now_utc) or (p_start and p_end and p_start <= now_utc <= p_end):
                        upcoming_presales.append({
                            "name": p.get("name", "Presale"),
                            "start": p_start,
                            "end": p_end,
                            "url": p.get("url") or ev.get("url")
                        })

                # Strict Future Filter: Must have an upcoming/active presale OR a future public sale
                has_future_public = bool(public_start and public_start > now_utc)
                if not upcoming_presales and not has_future_public:
                    continue

                seen_ids.add(ev_id)

                # Extract artist & venue info
                attractions = ev.get("_embedded", {}).get("attractions", [])
                artist_name = attractions[0].get("name") if attractions else ev.get("name", "Unknown Artist")

                venues = ev.get("_embedded", {}).get("venues", [])
                venue = venues[0] if venues else {}
                city = venue.get("city", {}).get("name", "")
                country = venue.get("country", {}).get("countryCode", "")
                venue_name = venue.get("name", "")
                location_str = f"{city}, {country}".strip(", ")

                # Pick earliest upcoming presale if available
                upcoming_presales.sort(key=lambda x: x["start"] or now_utc)
                best_presale = upcoming_presales[0] if upcoming_presales else None

                if best_presale:
                    sale_info = f"Presale ({best_presale['name']}): {best_presale['start'].strftime('%Y-%m-%d %H:%M UTC')}"
                    reg_link = best_presale["url"] or ev.get("url", "")
                elif has_future_public:
                    sale_info = f"Public Sale: {public_start.strftime('%Y-%m-%d %H:%M UTC')}"
                    reg_link = ev.get("url", "")
                else:
                    sale_info = "Upcoming Presale / TBD"
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
            print(f"⚠️ Error fetching Ticketmaster batch: {e}")

    print(f"✅ Fetched {len(collected)} verified upcoming presale/sale events across US/UK/EU/CA/AU.")
    return collected
