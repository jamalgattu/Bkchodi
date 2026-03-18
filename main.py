import feedparser
import requests
import os
import logging
from bs4 import BeautifulSoup
from telegram import Bot
from apscheduler.schedulers.blocking import BlockingScheduler

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

def get_job_details(url):
    details = {}
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "lxml")
        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        for i, line in enumerate(lines):
            ll = line.lower()
            if "vacancy" in ll or "post" in ll and i+1 < len(lines):
                details["vacancy"] = lines[i+1][:80]
            if "salary" in ll or "pay scale" in ll and i+1 < len(lines):
                details["salary"] = lines[i+1][:80]
            if "eligibility" in ll or "qualification" in ll and i+1 < len(lines):
                details["eligibility"] = lines[i+1][:80]
            if "last date" in ll or "closing date" in ll and i+1 < len(lines):
                details["last_date"] = lines[i+1][:80]
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

def check_and_post():
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
            bot.send_message(
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

scheduler = BlockingScheduler()
scheduler.add_job(check_and_post, "interval", hours=1)

logger.info("Bot started! Running first check now...")
check_and_post()
scheduler.start()
