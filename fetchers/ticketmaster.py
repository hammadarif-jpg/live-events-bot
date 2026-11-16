import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(override=True)

TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY")

def parse_iso_utc(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None

def fetch_ticketmaster_events(keyword="", size=100):
    """Scans US events on Ticketmaster/Live Nation and extracts ONLY sales/presales whose START time is in the FUTURE."""
    if not TICKETMASTER_API_KEY:
        print("⚠️ Warning: TICKETMASTER_API_KEY missing in .env")
        return []

    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    normalized_events = []

    for page in range(5):
        params = {
            "apikey": TICKETMASTER_API_KEY,
            "countryCode": "US",
            "startDateTime": now_iso,
            "sort": "relevance,desc",
            "size": size,
            "page": page
        }
        if keyword:
            params["keyword"] = keyword

        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"❌ Ticketmaster API Error (Page {page}): {e}")
            break

        raw_events = data.get("_embedded", {}).get("events", [])
        if not raw_events:
            break

        for item in raw_events:
            name = item.get("name", "Unknown Event")
            event_url = item.get("url", "")
            if not event_url:
                continue

            sales = item.get("sales", {})
            public_info = sales.get("public", {})
            pub_start_raw = public_info.get("startDateTime", "")
            pub_dt = parse_iso_utc(pub_start_raw)
            pub_start_clean = pub_start_raw[:16].replace("T", " ") + " UTC" if pub_start_raw else "TBD"

            presales = sales.get("presales", [])
            upcoming_presales = []
            signup_link = event_url
            has_future_presale = False

            for p in presales:
                p_name = p.get("name", "Presale")
                p_start = p.get("startDateTime", "")
                p_url = p.get("url", "")
                p_start_dt = parse_iso_utc(p_start)

                # STRICT CHECK: Only include presales whose START time is strictly in the FUTURE
                if p_start_dt and p_start_dt > now_utc:
                    has_future_presale = True
                    if p_url and p_url.startswith("http"):
                        signup_link = p_url
                    p_clean = p_start[:16].replace("T", " ") + " UTC"
                    upcoming_presales.append(f"• **{p_name}:** Starts {p_clean}")

            # STRICT CHECK: Public sale START time must also be strictly in the FUTURE
            has_future_public = bool(pub_dt and pub_dt > now_utc)

            # Block any event whose presales AND public sale have ALREADY started or sold out
            if not has_future_presale and not has_future_public:
                continue

            dates = item.get("dates", {})
            start_info = dates.get("start", {})
            event_date = start_info.get("localDate", "TBD")
            event_time = start_info.get("localTime", "TBD")
            timezone_str = dates.get("timezone", "US Local")

            venues = item.get("_embedded", {}).get("venues", [{}])
            venue = venues[0] if venues else {}
            venue_name = venue.get("name", "TBD Venue")
            city = venue.get("city", {}).get("name", "Unknown City")
            state = venue.get("state", {}).get("stateCode", "")
            location = f"{city}, {state}".strip(", ")

            attractions = item.get("_embedded", {}).get("attractions", [])
            artist = attractions[0].get("name", name) if attractions else name

            presale_summary = "\n".join(upcoming_presales[:4]) if upcoming_presales else "No Presale (Direct Public Sale Upcoming)"
            promoter = item.get("promoter", {}).get("name", "")
            platform_label = "Live Nation / Ticketmaster" if "LIVE NATION" in promoter.upper() else "Ticketmaster"

            normalized_events.append({
                "name": name,
                "artist": artist,
                "date": f"Public Sale Starts: {pub_start_clean} | Show Date: {event_date}",
                "time": f"{event_time} ({timezone_str})",
                "venue": venue_name,
                "city": location,
                "platform": platform_label,
                "status": "UPCOMING PRESALE / SIGNUP" if has_future_presale else "UPCOMING PUBLIC SALE",
                "presale": presale_summary,
                "public_sale": pub_start_clean,
                "has_presale": has_future_presale,
                "reg_link": signup_link,
                "ticket_link": event_url,
                "source": "Ticketmaster / Live Nation Official",
                "popularity_score": 90 if has_future_presale else 70
            })

    return normalized_events
