import feedparser
import requests
import os
import logging
import asyncio
from bs4 import BeautifulSoup
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
FEED_URL = "https://www.sarkarinaukriblog.com/feeds/posts/default"
POSTED_FILE = "posted.txt"

def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
    with open(POSTED_FILE, "r") as f:
        return set(line.strip() for line in f.readlines())

def save_posted(link):
    with open(POSTED_FILE, "a") as f:
        f.write(link + "\n")

def get_job_details(url, entry):
    details = {}
    try:
        # Try to get last date from RSS description first
        summary = entry.get("summary", "") or entry.get("description", "")
        if summary:
            soup_rss = BeautifulSoup(summary, "lxml")
            rss_text = soup_rss.get_text(separator=" ")
            import re
            date_match = re.search(
                r'(last date[:\s]+[\w\s,]+\d{4}|apply before[:\s]+[\w\s,]+\d{4})',
                rss_text, re.IGNORECASE
            )
            if date_match:
                details["last_date"] = date_match.group(0)[:60]

        # Scrape page for other details
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "lxml")
        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        skip_words = ["hot jobs", "sarkari", "recruitment", "naukri",
                      "javascript", "enabled", "click here", "www.", "http"]

        def is_valid(val):
            v = val.lower()
            return not any(s in v for s in skip_words) and len(val) > 2 and len(val) < 80

        for i, line in enumerate(lines):
            ll = line.lower()
            next_line = lines[i+1] if i+1 < len(lines) else ""
            if "total post" in ll or "total vacancy" in ll or "no. of post" in ll:
                if is_valid(next_line):
                    details.setdefault("vacancy", next_line)
            if "pay scale" in ll or "pay matrix" in ll or "grade pay" in ll:
                if is_valid(next_line):
                    details.setdefault("salary", next_line)
            if "qualification" in ll or "educational" in ll:
                if is_valid(next_line):
                    details.setdefault("eligibility", next_line)
            if "last date" in ll and "last date" not in details.get("last_date","").lower():
                if is_valid(next_line):
                    details.setdefault("last_date", next_line)
    except Exception as e:
        logger.warning(f"Could not fetch details: {e}")
    return details

def format_message(title, link, date, details):
    msg = f"🏛️ *{title}*\n\n"
    if details.get("eligibility"):
        msg += f"📋 *Eligibility:* {details['eligibility']}\n"
    if details.get("vacancy"):
        msg += f"💼 *Vacancy:* {details['vacancy']}\n"
    if details.get("salary"):
        msg += f"💰 *Salary:* {details['salary']}\n"
    if details.get("last_date"):
        msg += f"📅 *Last Date:* {details['last_date']}\n"
    elif date:
        msg += f"📅 *Posted:* {date}\n"
    msg += f"🔗 [Apply Here]({link})"
    return msg

async def check_and_post():
    logger.info("Checking for new jobs...")
    bot = Bot(token=BOT_TOKEN)
    posted = load_posted()
    feed = feedparser.parse(FEED_URL)
    new_jobs = 0

    for entry in feed.entries[:10]:
        link = entry.get("link", "")
        title = entry.get("title", "No Title")
        date = entry.get("published", "")
        if link in posted:
            continue
        details = get_job_details(link)
        message = format_message(title, link, date, details)
        try:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=message,
                parse_mode="Markdown",
                disable_web_page_preview=False
            )
            save_posted(link)
            new_jobs += 1
            logger.info(f"Posted: {title}")
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    if new_jobs == 0:
        logger.info("No new jobs found this hour.")

async def main():
    logger.info("Bot started! Running first check now...")
    await check_and_post()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_and_post, "interval", hours=1)
    scheduler.start()
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
