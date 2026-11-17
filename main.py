import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

from fetchers.ticketmaster import fetch_ticketmaster_events
from fetchers.social_discovery import fetch_x_twitter_announcements
from fetchers.laylo_seated import fetch_laylo_and_seated_signups
from engine import verify_and_rank_events, filter_new_and_save_to_db
from discord_notifier import send_discord_event_report

load_dotenv(override=True)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

PREFERRED_ARTISTS = [
    "Taylor Swift", "Drake", "Coldplay", "Oasis", "Stray Kids",
    "Bruno Mars", "The Weeknd", "Sabrina Carpenter", "Bad Bunny", "Morgan Wallen",
    "Olivia Rodrigo", "Billie Eilish", "Kendrick Lamar", "Lady Gaga", "Post Malone",
    "Ed Sheeran", "Beyonce", "Ariana Grande", "Travis Scott", "Dua Lipa"
]

def send_hourly_high_sale_radar(ranked_events):
    """Sends an hourly update of Top High-Demand Upcoming Sales & Presales to Discord in English."""
    if not DISCORD_WEBHOOK_URL:
        return

    high_sales = [ev for ev in ranked_events if ev.get("has_presale") or ev.get("rank_score", 0) >= 80]
    if not high_sales:
        high_sales = ranked_events[:8]

    lines = []
    for i, ev in enumerate(high_sales[:8], 1):
        status_tag = "🎟️ PRESALE" if ev.get("has_presale") else "🔥 PUBLIC SALE"
        lines.append(
            f"**{i}. {ev['artist']}** — {ev['city']} ({status_tag})\n"
            f"   ⏰ {ev['date']}\n"
            f"   🔗 [Signup / Ticket Link]({ev['reg_link']})"
        )

    summary_text = "\n\n".join(lines) if lines else "No high-demand upcoming sales currently in the queue."

    payload = {
        "embeds": [
            {
                "title": "⚡ HOURLY HIGH-DEMAND SALE & PRESALE RADAR",
                "description": (
                    f"Live hourly update — top upcoming high-demand sales and active presale signups:\n\n"
                    f"{summary_text}"
                ),
                "color": 15105570,
                "footer": {
                    "text": f"Hourly Radar • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                }
            }
        ]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print("⚡ Hourly High-Sale Radar sent to Discord!")
    except Exception as e:
        print(f"⚠️ Failed to send hourly radar: {e}")

def run_discovery_pipeline():
    now_utc = datetime.now(timezone.utc)
    print(f"🚀 Starting Hourly Presale & High-Sale Radar at {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}...")
    all_raw_events = []

    print("🔍 Scanning Ticketmaster & Live Nation for Upcoming Presales & Sales...")
    all_raw_events.extend(fetch_ticketmaster_events(size=200))

    print("🔍 Scanning Laylo & Seated for Active Presale RSVP Signups...")
    all_raw_events.extend(fetch_laylo_and_seated_signups())

    print("🔍 Scanning X (Twitter) Announcements...")
    all_raw_events.extend(fetch_x_twitter_announcements())

    print(f"📦 Total upcoming sale/presale events found: {len(all_raw_events)}")

    ranked_events = verify_and_rank_events(all_raw_events, preferred_artists=PREFERRED_ARTISTS)
    print(f"🛡️ Verified & ranked upcoming sales: {len(ranked_events)}")

    brand_new_events = filter_new_and_save_to_db(ranked_events)
    print(f"🆕 Brand-new presale/sale alerts to send: {len(brand_new_events)}")

    if brand_new_events:
        send_discord_event_report(
            brand_new_events[:15],
            report_title="🆕 NEW PRESALE SIGNUP / TOUR ANNOUNCEMENT DETECTED!"
        )

    send_hourly_high_sale_radar(ranked_events)

if __name__ == "__main__":
    run_discovery_pipeline()
