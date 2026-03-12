import os
import requests
from telegram import Bot
from telegram.error import TelegramError
import asyncio
import json
import logging
from datetime import datetime
from bs4 import BeautifulSoup
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import schedule

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
POSTED_JOBS_FILE = "posted_jobs.json"

# Browser headers to avoid blocks
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0'
}

def load_posted_jobs():
    """Load previously posted job IDs"""
    try:
        if os.path.exists(POSTED_JOBS_FILE):
            with open(POSTED_JOBS_FILE, 'r') as f:
                data = json.load(f)
                return set(data) if isinstance(data, list) else data
    except Exception as e:
        logger.error(f"Error loading posted jobs: {e}")
    return set()

def save_posted_job(job_id):
    """Save posted job ID"""
    try:
        posted_jobs = list(load_posted_jobs())
        if job_id not in posted_jobs:
            posted_jobs.append(job_id)
            with open(POSTED_JOBS_FILE, 'w') as f:
                json.dump(posted_jobs, f)
    except Exception as e:
        logger.error(f"Error saving posted job: {e}")

def generate_job_id(title, link):
    """Generate unique ID from title and link"""
    combined = f"{title}_{link}".encode('utf-8')
    return hashlib.md5(combined).hexdigest()[:16]

def get_today_date():
    """Get today's date for filtering"""
    return datetime.now().strftime('%Y-%m-%d')

def scrape_website(website_url, website_name):
    """Scrape a single government website"""
    jobs = []
    today = get_today_date()
    
    try:
        logger.info(f"📡 Scanning {website_name}...")
        
        session = requests.Session()
        response = session.get(website_url, headers=HEADERS, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all links and headings that might be job postings
            elements = soup.find_all(['a', 'h2', 'h3', 'h4'])
            
            for element in elements[:50]:  # Limit to first 50 elements
                try:
                    # Extract title and link
                    if element.name == 'a':
                        title = element.get_text(strip=True)
                        link = element.get('href', '')
                    else:
                        link_elem = element.find('a')
                        if link_elem:
                            title = link_elem.get_text(strip=True)
                            link = link_elem.get('href', '')
                        else:
                            title = element.get_text(strip=True)
                            link = ''
                    
                    if not title or not link or len(title) < 10:
                        continue
                    
                    # Make absolute URL
                    if link and not link.startswith('http'):
                        if link.startswith('/'):
                            from urllib.parse import urlparse
                            parsed = urlparse(website_url)
                            link = f"{parsed.scheme}://{parsed.netloc}{link}"
                        else:
                            link = website_url + '/' + link
                    
                    # Filter for job-related keywords
                    job_keywords = ['recruitment', 'notification', 'exam', 'vacancy', 'apply', 'admit', 'result', 'job', 'position', 'post', 'opening']
                    if not any(keyword in title.lower() for keyword in job_keywords):
                        continue
                    
                    job_id = generate_job_id(title, link)
                    
                    job = {
                        'id': job_id,
                        'title': title[:200],
                        'link': link,
                        'source': website_name,
                        'date': today
                    }
                    jobs.append(job)
                    
                except Exception as e:
                    logger.debug(f"  Error parsing element: {e}")
                    continue
            
            logger.info(f"  ✓ {website_name}: {len(jobs)} jobs found")
        else:
            logger.warning(f"  ⚠️ {website_name}: Status {response.status_code}")
            
    except requests.exceptions.Timeout:
        logger.warning(f"  ⏱️ {website_name}: Timeout")
    except requests.exceptions.ConnectionError:
        logger.warning(f"  ❌ {website_name}: Connection error")
    except Exception as e:
        logger.warning(f"  ❌ {website_name}: {str(e)[:50]}")
    
    return jobs

def fetch_all_government_jobs():
    """Fetch jobs from all 53 government websites in parallel"""
    
    # All government websites to scan
    government_websites = [
        # Central Recruitment
        ('https://ssc.nic.in', '📋 SSC'),
        ('https://upsc.gov.in', '🎓 UPSC'),
        ('https://indiarailways.gov.in', '🚂 Railways'),
        ('https://crpf.gov.in', '🎖️ CRPF'),
        ('https://bsf.gov.in', '🛡️ BSF'),
        ('https://itbpolice.nic.in', '🛡️ ITBP'),
        ('https://cisf.gov.in', '🛡️ CISF'),
        ('https://assamrifles.gov.in', '🛡️ Assam Rifles'),
        ('https://ssb.gov.in', '🛡️ SSB'),
        ('https://indiancoastguard.nic.in', '🛡️ Coast Guard'),
        
        # Armed Forces
        ('https://joinindianarmy.nic.in', '🎖️ Army'),
        ('https://joinindiannavy.gov.in', '🎖️ Navy'),
        ('https://airmenselection.cdac.in', '🎖️ Air Force'),
        
        # Banking & Finance
        ('https://ibps.in', '🏦 IBPS'),
        ('https://rrb.nic.in', '🚂 RRB'),
        ('https://epfo.gov.in', '💼 EPFO'),
        
        # Postal & Telecom
        ('https://indiapost.gov.in', '📮 India Post'),
        ('https://bsnl.co.in', '📡 BSNL'),
        
        # Infrastructure
        ('https://delhimetrorail.com', '🚇 DMRC'),
        ('https://aai.aero', '✈️ AAI'),
        ('https://rvnl.org', '🏗️ RVNL'),
        ('https://irctc.co.in', '🚆 IRCTC'),
        
        # Health & Research
        ('https://aiims.edu', '🏥 AIIMS'),
        ('https://icmr.nic.in', '🏥 ICMR'),
        
        # Education
        ('https://nta.ac.in', '🎓 NTA'),
        ('https://dsssb.delhi.gov.in', '🏛️ DSSSB'),
        ('https://csir.res.in', '🔬 CSIR'),
        ('https://drdo.gov.in', '🛡️ DRDO'),
        
        # Energy & Mining
        ('https://ongc.co.in', '⛽ ONGC'),
        ('https://iocl.com', '⛽ IOCL'),
        ('https://gail.co.in', '⛽ GAIL'),
        ('https://coalindia.in', '⛏️ Coal India'),
        ('https://ntpc.co.in', '⚡ NTPC'),
        
        # State PSCs
        ('https://uppsc.up.nic.in', '🏛️ UP PSC'),
        ('https://mpsc.gov.in', '🏛️ Maharashtra PSC'),
        ('https://tspsc.gov.in', '🏛️ Telangana PSC'),
        ('https://kpsc.kar.nic.in', '🏛️ Karnataka PSC'),
        ('https://tnpsc.gov.in', '🏛️ Tamil Nadu PSC'),
        ('https://gpsc.gujarat.gov.in', '🏛️ Gujarat PSC'),
        ('https://bpsc.bih.nic.in', '🏛️ Bihar PSC'),
        ('https://jpsc.nic.in', '🏛️ Jharkhand PSC'),
        ('https://rpsc.rajasthan.gov.in', '🏛️ Rajasthan PSC'),
        ('https://ppsc.gov.in', '🏛️ Punjab PSC'),
        
        # Other Government
        ('https://cbi.gov.in', '🔍 CBI'),
    ]
    
    all_jobs = []
    
    logger.info("=" * 70)
    logger.info(f"🌐 SCANNING {len(government_websites)} GOVERNMENT WEBSITES")
    logger.info("=" * 70)
    
    # Use ThreadPoolExecutor for parallel scanning
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scrape_website, url, name): (url, name) 
                  for url, name in government_websites}
        
        for future in as_completed(futures):
            try:
                jobs = future.result()
                all_jobs.extend(jobs)
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Error in parallel execution: {e}")
    
    # Remove duplicates by ID
    unique_jobs = {}
    for job in all_jobs:
        if job['id'] not in unique_jobs:
            unique_jobs[job['id']] = job
    
    logger.info(f"✓ Total UNIQUE jobs found (TODAY only): {len(unique_jobs)}")
    return list(unique_jobs.values())

def create_message(job):
    """Create message for Telegram"""
    emoji = job['source'].split()[0] if ' ' in job['source'] else '📢'
    
    message = f"""
{emoji} <b>{job['source']}</b>

<b>{job['title']}</b>

━━━━━━━━━━━━━━━━━━
📅 <b>Today:</b> {job['date']}
━━━━━━━━━━━━━━━━━━

<a href="{job['link']}"><b>👉 CLICK TO VIEW & APPLY 👈</b></a>
"""
    return message

async def send_to_channel(message):
    """Send message to Telegram"""
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=message,
            parse_mode='HTML',
            disable_web_page_preview=False
        )
        return True
    except TelegramError as e:
        logger.error(f"Telegram error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error: {e}")
        return False

async def check_and_post_jobs():
    """Main function"""
    logger.info("=" * 70)
    logger.info("🤖 GOVERNMENT JOB BOT - 53 WEBSITES SCANNER (RAILWAY)")
    logger.info("=" * 70)
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        logger.error("❌ Missing Telegram credentials")
        return
    
    logger.info("✓ Credentials verified")
    
    posted_jobs = load_posted_jobs()
    logger.info(f"✓ Cache: {len(posted_jobs)} jobs already posted")
    
    # Fetch jobs from all government websites
    today_jobs = fetch_all_government_jobs()
    
    if not today_jobs:
        logger.warning("⚠️ No jobs found today")
        return
    
    logger.info(f"✓ Checking {len(today_jobs)} UNIQUE jobs from today")
    
    count = 0
    for job in today_jobs:
        if job['id'] not in posted_jobs:
            logger.info(f"📤 NEW: {job['title'][:60]}...")
            message = create_message(job)
            success = await send_to_channel(message)
            
            if success:
                save_posted_job(job['id'])
                count += 1
                await asyncio.sleep(1)
    
    if count == 0:
        logger.info("✓ No new jobs posted at this moment")
    else:
        logger.info(f"✓ Posted {count} NEW jobs! 🎉")
    
    logger.info("=" * 70)
    logger.info("✓ BOT SCAN COMPLETED")
    logger.info("=" * 70)

def job_scheduler():
    """Run the bot on schedule"""
    asyncio.run(check_and_post_jobs())

def main():
    """Main entry point with scheduler"""
    logger.info("🚂 RAILWAY BOT STARTED")
    logger.info("Bot will run every 5 minutes...")
    
    # Schedule the job to run every 5 minutes
    schedule.every(5).minutes.do(job_scheduler)
    
    # Keep the scheduler running
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
