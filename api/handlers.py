import os
import sys
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

async def handler(request):
    """Vercel serverless function handler"""
    
    # Import after path is set
    import requests
    from telegram import Bot
    from telegram.error import TelegramError
    import asyncio
    import json
    import logging
    from bs4 import BeautifulSoup
    import hashlib
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Configuration
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
    POSTED_JOBS_FILE = "/tmp/posted_jobs.json"
    
    # Browser headers
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }
    
    def load_posted_jobs():
        """Load previously posted job IDs"""
        try:
            if os.path.exists(POSTED_JOBS_FILE):
                with open(POSTED_JOBS_FILE, 'r') as f:
                    data = json.load(f)
                    return set(data) if isinstance(data, list) else data
        except:
            pass
        return set()
    
    def save_posted_job(job_id):
        """Save posted job ID"""
        try:
            posted_jobs = list(load_posted_jobs())
            if job_id not in posted_jobs:
                posted_jobs.append(job_id)
                with open(POSTED_JOBS_FILE, 'w') as f:
                    json.dump(posted_jobs, f)
        except:
            pass
    
    def generate_job_id(title, link):
        """Generate unique ID"""
        combined = f"{title}_{link}".encode('utf-8')
        return hashlib.md5(combined).hexdigest()[:16]
    
    def scrape_website(website_url, website_name):
        """Scrape a single website"""
        jobs = []
        today = datetime.now().strftime('%Y-%m-%d')
        
        try:
            session = requests.Session()
            response = session.get(website_url, headers=HEADERS, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                elements = soup.find_all(['a', 'h2', 'h3'], limit=50)
                
                for element in elements:
                    try:
                        if element.name == 'a':
                            title = element.get_text(strip=True)
                            link = element.get('href', '')
                        else:
                            link_elem = element.find('a')
                            if link_elem:
                                title = link_elem.get_text(strip=True)
                                link = link_elem.get('href', '')
                            else:
                                continue
                        
                        if not title or not link or len(title) < 10:
                            continue
                        
                        if link and not link.startswith('http'):
                            if link.startswith('/'):
                                from urllib.parse import urlparse
                                parsed = urlparse(website_url)
                                link = f"{parsed.scheme}://{parsed.netloc}{link}"
                        
                        job_keywords = ['recruitment', 'notification', 'exam', 'vacancy', 'apply', 'job', 'position']
                        if not any(keyword in title.lower() for keyword in job_keywords):
                            continue
                        
                        job_id = generate_job_id(title, link)
                        jobs.append({
                            'id': job_id,
                            'title': title[:200],
                            'link': link,
                            'source': website_name,
                            'date': today
                        })
                    except:
                        continue
        except:
            pass
        
        return jobs
    
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
        except:
            return False
    
    # Government websites
    government_websites = [
        ('https://ssc.nic.in', '📋 SSC'),
        ('https://upsc.gov.in', '🎓 UPSC'),
        ('https://indiarailways.gov.in', '🚂 Railways'),
        ('https://crpf.gov.in', '🎖️ CRPF'),
        ('https://bsf.gov.in', '🛡️ BSF'),
        ('https://itbpolice.nic.in', '🛡️ ITBP'),
        ('https://cisf.gov.in', '🛡️ CISF'),
        ('https://joinindianarmy.nic.in', '🎖️ Army'),
        ('https://joinindiannavy.gov.in', '🎖️ Navy'),
        ('https://ibps.in', '🏦 IBPS'),
        ('https://rrb.nic.in', '🚂 RRB'),
        ('https://indiapost.gov.in', '📮 India Post'),
        ('https://bsnl.co.in', '📡 BSNL'),
        ('https://aai.aero', '✈️ AAI'),
        ('https://rvnl.org', '🏗️ RVNL'),
        ('https://aiims.edu', '🏥 AIIMS'),
        ('https://nta.ac.in', '🎓 NTA'),
        ('https://csir.res.in', '🔬 CSIR'),
        ('https://drdo.gov.in', '🛡️ DRDO'),
        ('https://ongc.co.in', '⛽ ONGC'),
        ('https://coalindia.in', '⛏️ Coal India'),
        ('https://ntpc.co.in', '⚡ NTPC'),
        ('https://uppsc.up.nic.in', '🏛️ UP PSC'),
        ('https://mpsc.gov.in', '🏛️ Maharashtra PSC'),
        ('https://tspsc.gov.in', '🏛️ Telangana PSC'),
        ('https://kpsc.kar.nic.in', '🏛️ Karnataka PSC'),
    ]
    
    # Scan all websites in parallel
    all_jobs = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scrape_website, url, name): (url, name) 
                  for url, name in government_websites}
        
        for future in as_completed(futures):
            try:
                jobs = future.result()
                all_jobs.extend(jobs)
                time.sleep(0.3)
            except:
                pass
    
    # Remove duplicates
    unique_jobs = {}
    for job in all_jobs:
        if job['id'] not in unique_jobs:
            unique_jobs[job['id']] = job
    
    # Load posted jobs
    posted_jobs = load_posted_jobs()
    
    # Post new jobs
    count = 0
    for job in list(unique_jobs.values())[:10]:  # Limit to 10 posts per run
        if job['id'] not in posted_jobs:
            emoji = job['source'].split()[0] if ' ' in job['source'] else '📢'
            message = f"""
{emoji} <b>{job['source']}</b>

<b>{job['title']}</b>

━━━━━━━━━━━━━━━━━━
📅 Today: {job['date']}
━━━━━━━━━━━━━━━━━━

<a href="{job['link']}"><b>👉 APPLY NOW 👈</b></a>
"""
            
            success = await send_to_channel(message)
            if success:
                save_posted_job(job['id'])
                count += 1
                await asyncio.sleep(0.5)
    
    return {
        'statusCode': 200,
        'body': f'Posted {count} new jobs from {len(unique_jobs)} jobs found'
    }
