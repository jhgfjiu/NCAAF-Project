"""
Configuration file for NCAA Football scraper
Contains URLs, headers, settings, and constants for academic research
"""

import os
from pathlib import Path

# Base URLs and endpoints
BASE_URL = "https://www.sports-reference.com"
CFB_BASE_URL = f"{BASE_URL}/cfb"

# Player index URLs (A-Z pages)
# Player index URL template (supports pagination)
PLAYER_INDEX_TEMPLATE = f"{CFB_BASE_URL}/players/{{letter}}-index{{page_suffix}}.html"

# Player profile URL template
PLAYER_URL_TEMPLATE = f"{CFB_BASE_URL}/players/{{player_id}}.html"

# Request headers for academic research
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
]

BASE_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Referer': 'https://www.sports-reference.com/',
    'DNT': '1',
}

# Rate limiting settings (respectful scraping)
REQUEST_DELAY = 0.3  # seconds between requests
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds to wait before retry

# Project structure
PROJECT_ROOT = Path(__file__).parent
STORAGE_DIR = PROJECT_ROOT / "storage"
PLAYER_DATA_DIR = STORAGE_DIR / "player_data"
LOGS_DIR = STORAGE_DIR / "logs"

# Ensure directories exist
STORAGE_DIR.mkdir(exist_ok=True)
PLAYER_DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Alphabet for index scraping
ALPHABET = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

# HTML selectors for data extraction
SELECTORS = {
    'player_links': 'table#players tbody tr td a[href*="/cfb/players/"]',
    'stats_tables': 'table.stats_table',
    'player_name': 'h1[itemprop="name"]',
    'player_info': 'div#meta div p',
}

# File naming patterns
PLAYER_FILE_PATTERN = "{player_id}.json"
INDEX_CACHE_PATTERN = "player_index_{letter}.json"

# Logging configuration
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'INFO'

# Session configuration
SESSION_TIMEOUT = 30  # seconds
MAX_CONCURRENT_REQUESTS = 1  # Conservative for academic research

# CouchDB Configuration
COUCHDB_URL = os.getenv('COUCHDB_URL')
COUCHDB_USERNAME = os.getenv('COUCHDB_USERNAME')
COUCHDB_PASSWORD = os.getenv('COUCHDB_PASSWORD')
COUCHDB_DATABASE = os.getenv('COUCHDB_DATABASE')
BATCH_SIZE = 300

# Storage mode: 'file' or 'couchdb'
STORAGE_MODE = os.getenv("STORAGE_MODE", "couchdb").lower()