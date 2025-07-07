"""
Utility functions for NCAA Football scraper
Handles logging, file I/O, retry logic, and common operations
"""

import json
import logging
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import config


def setup_logging(name: str = 'ncaaf_scraper') -> logging.Logger:
    """Set up logging configuration for the scraper."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.LOG_LEVEL))
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # File handler
    log_file = config.LOGS_DIR / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(config.LOG_FORMAT)
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def create_session() -> requests.Session:
    """Create a configured requests session for web scraping."""
    session = requests.Session()
    session.headers.update(config.HEADERS)
    session.timeout = config.SESSION_TIMEOUT
    return session


def safe_request(session: requests.Session, url: str, logger: logging.Logger) -> Optional[requests.Response]:
    """
    Make a safe HTTP request with retry logic and rate limiting.
    
    Args:
        session: Configured requests session
        url: URL to request
        logger: Logger instance
        
    Returns:
        Response object or None if all retries failed
    """
    for attempt in range(config.MAX_RETRIES):
        try:
            logger.debug(f"Requesting {url} (attempt {attempt + 1})")
            
            # Rate limiting
            time.sleep(config.REQUEST_DELAY)
            
            response = session.get(url)
            response.raise_for_status()
            
            logger.debug(f"Successfully retrieved {url}")
            return response
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed for {url} (attempt {attempt + 1}): {e}")
            
            if attempt < config.MAX_RETRIES - 1:
                logger.info(f"Retrying in {config.RETRY_DELAY} seconds...")
                time.sleep(config.RETRY_DELAY)
            else:
                logger.error(f"All retry attempts failed for {url}")
                
    return None


def save_json(data: Dict[str, Any], filepath: Path, logger: logging.Logger) -> bool:
    """
    Save data to JSON file with error handling.
    
    Args:
        data: Dictionary to save
        filepath: Path where to save the file
        logger: Logger instance
        
    Returns:
        True if successful, False otherwise
    """
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        logger.debug(f"Saved data to {filepath}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save data to {filepath}: {e}")
        return False


def load_json(filepath: Path, logger: logging.Logger) -> Optional[Dict[str, Any]]:
    """
    Load data from JSON file with error handling.
    
    Args:
        filepath: Path to JSON file
        logger: Logger instance
        
    Returns:
        Loaded data or None if failed
    """
    try:
        if not filepath.exists():
            logger.debug(f"File does not exist: {filepath}")
            return None
            
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        logger.debug(f"Loaded data from {filepath}")
        return data
        
    except Exception as e:
        logger.error(f"Failed to load data from {filepath}: {e}")
        return None


def extract_player_id_from_url(url: str) -> Optional[str]:
    """
    Extract player ID from Sports Reference URL.
    
    Args:
        url: Player URL from Sports Reference
        
    Returns:
        Player ID or None if extraction failed
        
    Example:
        '/cfb/players/john-smith-1.html' -> 'john-smith-1'
    """
    try:
        if '/cfb/players/' in url:
            # Extract filename without .html extension
            filename = url.split('/cfb/players/')[-1]
            if filename.endswith('.html'):
                return filename[:-5]  # Remove .html
        return None
    except Exception:
        return None


def get_existing_player_files(logger: logging.Logger) -> set:
    """
    Get set of already processed player IDs to avoid re-scraping.
    
    Args:
        logger: Logger instance
        
    Returns:
        Set of player IDs that already have data files
    """
    existing_files = set()
    
    try:
        for file_path in config.PLAYER_DATA_DIR.glob("*.json"):
            player_id = file_path.stem
            existing_files.add(player_id)
            
        logger.info(f"Found {len(existing_files)} existing player files")
        
    except Exception as e:
        logger.error(f"Error checking existing files: {e}")
        
    return existing_files


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename safe for filesystem
    """
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename


def format_stats_data(raw_stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format and clean scraped statistics data.
    
    Args:
        raw_stats: Raw statistics dictionary
        
    Returns:
        Cleaned and formatted statistics
    """
    formatted = {
        'scraped_at': datetime.now().isoformat(),
        'player_info': raw_stats.get('player_info', {}),
        'career_stats': raw_stats.get('career_stats', {}),
        'season_stats': raw_stats.get('season_stats', []),
        'game_logs': raw_stats.get('game_logs', []),
    }
    
    return formatted