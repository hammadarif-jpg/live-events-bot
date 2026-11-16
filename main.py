import os
from datetime import datetime
from dotenv import load_dotenv

from fetchers.ticketmaster import fetch_ticketmaster_events
from fetchers.social_discovery import fetch_x_twitter_announcements
from engine import verify_and_rank_events, filter_new_and_save_to_db
from discord_notifier import send_discord_event_report

load_dotenv(override=True)

PREFERRED_ARTISTS = [
    "Taylor Swift", "Drake", "Coldplay", "Oasis", "Stray Kids",
    "Bruno Mars", "The Weeknd", "Sabrina Carpenter", "Bad Bunny", "Morgan Wallen",
    "Olivia Rodrigo", "Billie Eilish", "Kendrick Lamar", "Lady Gaga", "Post Malone"
]

def run_discovery_pipeline():
    print(f"🚀 Starting Presale & Upcoming Sale Radar at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...")
    all_raw_events = []

    # 1. Fetch ONLY Upcoming Presales & Future Public Sales with Direct Signup Links
    print("🔍 Scanning Ticketmaster & Live Nation for Upcoming Presales & Sales...")
    all_raw_events.extend(fetch_ticketmaster_events(size=100))

    # 2. Fetch Official X (Twitter) Alerts if token is set
    all_raw_events.extend(fetch_x_twitter_announcements())

    print(f"📦 Total upcoming sale/presale events found: {len(all_raw_events)}")

    # 3. Verify, Deduplicate & Rank
    ranked_events = verify_and_rank_events(all_raw_events, preferred_artists=PREFERRED_ARTISTS)
    print(f"🛡️ Verified & ranked upcoming sales: {len(ranked_events)}")

    # 4. Save new discoveries to Supabase
    brand_new_events = filter_new_and_save_to_db(ranked_events)
    print(f"🆕 Brand-new presale/sale alerts to send: {len(brand_new_events)}")

    # 5. Send Top 15 Presale & Upcoming Sale Alerts to Discord
    top_to_send = brand_new_events[:15]
    if top_to_send:
        send_discord_event_report(top_to_send, report_title="🎟️ NEW PRESALE SIGNUPS & UPCOMING TICKET SALES")
    else:
        print("✅ No duplicate alerts sent. Waiting for new tour/presale announcements!")

if __name__ == "__main__":
    run_discovery_pipeline()