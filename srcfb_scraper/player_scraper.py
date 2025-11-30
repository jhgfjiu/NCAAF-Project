"""
Player scraper for NCAA Football statistics
Visits individual player pages and extracts comprehensive statistics data
"""

import re
import asyncio
import aiohttp
import random
from typing import Dict, List, Optional, Any, Tuple
from bs4 import BeautifulSoup, Tag
from tqdm import tqdm
import pandas as pd
import os

import config
import utils

from index_scraper import PlayerIndexScraper

proxies = os.getenv("PROXIES", "").split(",")
proxies = [p.strip() for p in proxies if p.strip()]

class RateLimiter:
    """Enforce a minimum interval between any requests."""
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last_time = 0

    async def wait(self):
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_time
            wait_for = max(0, self.min_interval - elapsed)
            await asyncio.sleep(wait_for)
            self._last_time = asyncio.get_event_loop().time()

class PlayerStatsScraper:
    """Scrapes individual player pages for comprehensive statistics."""
    
    def __init__(self):
        self.logger = utils.setup_logging('player_scraper')
        
    async def _fetch(self, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore,
                 url: str, rate_limiter: RateLimiter, retries: int = 5) -> Optional[str]:
        """
        Fetch a URL with retries, full jitter, 429 handling, and global rate limiting.
        """
        base_backoff = 2      # seconds
        max_backoff = 60      # seconds
        proxy = None  # Ensure proxy is defined for logging in exception blocks

        async with semaphore:
            for attempt in range(retries):
                try:
                    # Global pacing: wait before every request
                    await rate_limiter.wait()

                    # Small random pre-request jitter
                    await asyncio.sleep(random.uniform(0.5, 2))

                    # Set up headers with a rotating user agent
                    headers = {
                        **config.BASE_HEADERS,
                        'User-Agent': random.choice(config.USER_AGENTS)
                    }
                    
                    # Pick a random proxy
                    proxy = random.choice(proxies) if proxies else None

                    async with session.get(url, timeout=30, headers=headers, proxy=proxy) as response:
                        if response.status == 429:
                            # Respect Retry-After header if provided
                            retry_after = response.headers.get("Retry-After")
                            if retry_after is not None:
                                try:
                                    retry_after = int(retry_after)
                                except ValueError:
                                    retry_after = random.uniform(60, 180)
                            else:
                                retry_after = random.uniform(60, 180)

                            retry_after = min(retry_after, 300)
                            # Full jitter
                            jittered_sleep = random.uniform(0, retry_after)
                            self.logger.warning(
                                f"429 Too Many Requests for {url} (Proxy: {proxy}). "
                                f"Retrying after {jittered_sleep:.2f}s"
                            )
                            await asyncio.sleep(jittered_sleep)
                            continue

                        response.raise_for_status()
                        self.logger.debug(f"Successfully fetched {url} on attempt {attempt + 1}")
                        return await response.text()

                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if attempt < retries - 1:
                        backoff = min(max_backoff, base_backoff * (2 ** attempt))
                        delay = random.uniform(0, backoff)
                        self.logger.warning(
                            f"Attempt {attempt + 1}/{retries} failed for {url}: {e} (Proxy: {proxy}). "
                            f"Retrying in {delay:.2f}s"
                        )
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(f"All {retries} attempts failed for {url}: {e} (Proxy: {proxy})")
                        return None

    async def scrape_player(self, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, player_url: str, rate_limiter: RateLimiter, player_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Scrape comprehensive statistics for a single player asynchronously.
        
        Args:
            session: aiohttp client session
            semaphore: asyncio semaphore for concurrency control
            player_url: Full URL to player page
            player_id: Player ID (extracted from URL if not provided)
            
        Returns:
            Dictionary containing all player statistics or None if failed
        """
        if not player_id:
            player_id = utils.extract_player_id_from_url(player_url)
            
        if not player_id:
            self.logger.error(f"Could not extract player ID from URL: {player_url}")
            return None
        
        self.logger.debug(f"Scraping player: {player_id}")
        
        html_content = await self._fetch(session, semaphore, player_url, rate_limiter)
        if not html_content:
            self.logger.error(f"Failed to retrieve player page: {player_url}")
            return None
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            player_data = self._extract_player_data(soup, player_id, player_url)
            
            if player_data:
                # Format and save data
                formatted_data = utils.format_stats_data(player_data)
                utils.save_data(formatted_data, player_id, self.logger)
                self.logger.info(f"Successfully scraped player: {player_id}")
                return formatted_data
            else:
                self.logger.warning(f"No data extracted for player: {player_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error scraping player {player_id}: {e}")
            return None
    
    def _extract_player_data(self, soup: BeautifulSoup, player_id: str, player_url: str) -> Dict[str, Any]:
        """
        Extract all available data from player page.
        
        Args:
            soup: BeautifulSoup object of player page
            player_id: Player identifier
            player_url: Original player URL
            
        Returns:
            Dictionary containing all extracted player data
        """
        self.logger.debug(f"Starting data extraction for player: {player_id}")
        
        # Extract each data type
        player_info = self._extract_player_info(soup)
        self.logger.debug(f"Player info extracted: {player_info}")
        
        season_stats = self._extract_season_stats(soup)
        self.logger.info(f"Season stats extraction complete: {len(season_stats)} tables found")
        
        career_stats = self._extract_career_stats(soup)
        self.logger.debug(f"Career stats extracted: {len(career_stats)} tables")
        
        game_logs = self._extract_game_logs(soup)
        self.logger.debug(f"Game logs extracted: {len(game_logs)} logs")
        
        advanced_stats = self._extract_advanced_stats(soup)
        self.logger.debug(f"Advanced stats extracted: {len(advanced_stats)} tables")
        
        data = {
            'player_id': player_id,
            'source_url': player_url,
            'player_info': player_info,
            'career_stats': career_stats,
            'season_stats': season_stats,
            'game_logs': game_logs,
            'advanced_stats': advanced_stats
        }
        
        self.logger.info(f"Data extraction complete for {player_id}: "
                        f"info={'✓' if player_info else '✗'}, "
                        f"season_stats={len(season_stats)}, "
                        f"career_stats={len(career_stats)}, "
                        f"game_logs={len(game_logs)}")
        
        return data
    
    def _extract_player_info(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract basic player information (name, position, school, etc.)."""
        info = {}
        
        try:
            # Player name
            name_elem = soup.find('h1', {'itemprop': 'name'}) or soup.find('h1')
            if name_elem:
                info['name'] = name_elem.get_text(strip=True)
            
            # Meta information (position, height, weight, etc.)
            meta_div = soup.find('div', {'id': 'meta'})
            if meta_div:
                # Look for specific patterns in meta div
                meta_paragraphs = meta_div.find_all('p')
                for p in meta_paragraphs:
                    text = p.get_text(strip=True)
                    
                    # Extract position
                    if 'Position:' in text:
                        info['position'] = text.replace('Position:', '').strip()
                    elif text.startswith('Position:'):
                        info['position'] = text.replace('Position:', '').strip()
                    
                    # Extract other basic info
                    elif 'Height:' in text:
                        info['height'] = text.replace('Height:', '').strip()
                    elif 'Weight:' in text:
                        info['weight'] = text.replace('Weight:', '').strip()
                    elif 'Born:' in text:
                        info['born'] = text.replace('Born:', '').strip()
                    elif 'High School:' in text:
                        info['high_school'] = text.replace('High School:', '').strip()
            
            # Extract school information more carefully
            # Look for school links within the main content area, not navigation
            main_content = soup.find('div', {'id': 'content'}) or soup.find('main') or soup.body
            if main_content:
                # Find school links that are in the player's actual data
                school_links = main_content.find_all('a', href=re.compile(r'/cfb/schools/'))
                
                # Filter out navigation and repeated entries
                unique_schools = []
                seen_schools = set()
                
                for link in school_links:
                    school_name = link.get_text(strip=True)
                    
                    # Skip navigation elements and generic terms
                    if (school_name.lower() in ['schools', 'school'] or 
                        len(school_name) < 2 or
                        school_name in seen_schools):
                        continue
                    
                    # Check if this school link is in the player's data context
                    # (not in navigation or footer)
                    parent_context = str(link.parent) if link.parent else ""
                    if ('nav' not in parent_context.lower() and 
                        'footer' not in parent_context.lower() and
                        'menu' not in parent_context.lower()):
                        unique_schools.append(school_name)
                        seen_schools.add(school_name)
                
                if unique_schools:
                    info['schools'] = unique_schools
                    info['primary_school'] = unique_schools[0]  # First school is usually primary
            
        except Exception as e:
            self.logger.debug(f"Error extracting player info: {e}")
        
        return info
    
    def _extract_season_stats(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract season-by-season statistics tables."""
        season_stats = []
        
        try:
            # Find all statistics tables in the main content area
            main_content = soup.find('div', {'id': 'content'}) or soup.body
            if not main_content:
                return season_stats
                
            stats_tables = main_content.find_all('table', class_='stats_table')
            
            self.logger.debug(f"Found {len(stats_tables)} potential stats tables")
            
            for table in stats_tables:
                try:
                    # Get table caption/title
                    caption = table.find('caption')
                    table_name = caption.get_text(strip=True) if caption else 'Unknown'
                    
                    self.logger.debug(f"Processing table: '{table_name}'")
                    
                    # Skip only very specific non-stats tables
                    skip_terms = ['game log', 'game finder', 'splits finder', 'navigation', 'menu']
                    should_skip = any(skip in table_name.lower() for skip in skip_terms)
                    
                    if should_skip:
                        self.logger.debug(f"Skipping table: {table_name}")
                        continue
                    
                    # Extract table data
                    table_data = self._parse_stats_table(table)
                    if table_data and len(table_data) > 0:
                        season_stats.append({
                            'table_name': table_name,
                            'data': table_data
                        })
                        self.logger.info(f"Successfully extracted table '{table_name}' with {len(table_data)} rows")
                    else:
                        self.logger.warning(f"Table '{table_name}' had no extractable data")
                        
                except Exception as e:
                    self.logger.error(f"Error processing stats table: {e}")
                    continue
        
        except Exception as e:
            self.logger.error(f"Error extracting season stats: {e}")
        
        return season_stats
    
    def _extract_career_stats(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract career totals and averages."""
        career_stats = {}
        
        try:
            # Look for career summary tables
            for table in soup.find_all('table', class_='stats_table'):
                caption = table.find('caption')
                if caption and 'career' in caption.get_text().lower():
                    career_data = self._parse_stats_table(table)
                    if career_data:
                        career_stats[caption.get_text(strip=True)] = career_data
        
        except Exception as e:
            self.logger.debug(f"Error extracting career stats: {e}")
        
        return career_stats
    
    def _extract_game_logs(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract game-by-game statistics if available."""
        game_logs = []
        
        try:
            # Look for game log tables
            for table in soup.find_all('table', class_='stats_table'):
                caption = table.find('caption')
                if caption and 'game log' in caption.get_text().lower():
                    game_data = self._parse_stats_table(table)
                    if game_data:
                        game_logs.append({
                            'season': caption.get_text(strip=True),
                            'games': game_data
                        })
        
        except Exception as e:
            self.logger.debug(f"Error extracting game logs: {e}")
        
        return game_logs
    
    def _extract_advanced_stats(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract advanced statistics and analytics."""
        advanced_stats = {}
        
        try:
            # Look for advanced stats sections
            for table in soup.find_all('table', class_='stats_table'):
                caption = table.find('caption')
                if caption:
                    caption_text = caption.get_text().lower()
                    if any(adv in caption_text for adv in ['advanced', 'analytics', 'efficiency']):
                        table_data = self._parse_stats_table(table)
                        if table_data:
                            advanced_stats[caption.get_text(strip=True)] = table_data
        
        except Exception as e:
            self.logger.debug(f"Error extracting advanced stats: {e}")
        
        return advanced_stats
    
    def _parse_stats_table(self, table: Tag) -> List[Dict[str, str]]:
        """
        Parse a statistics table into structured data.
        
        Args:
            table: BeautifulSoup table element
            
        Returns:
            List of dictionaries representing table rows
        """
        rows_data = []
        
        try:
            # Get headers - try multiple approaches
            headers = []
            
            # Try thead first
            thead = table.find('thead')
            if thead:
                header_rows = thead.find_all('tr')
                # Sometimes headers span multiple rows, take the last one
                if header_rows:
                    for th in header_rows[-1].find_all(['th', 'td']):
                        header_text = th.get_text(strip=True)
                        if header_text:
                            headers.append(header_text)
            
            # If no thead, try first tr
            if not headers:
                first_row = table.find('tr')
                if first_row:
                    for th in first_row.find_all(['th', 'td']):
                        header_text = th.get_text(strip=True)
                        if header_text:
                            headers.append(header_text)
            
            self.logger.debug(f"Found {len(headers)} headers: {headers[:10]}...")
            
            if not headers:
                self.logger.warning("No headers found in table")
                return rows_data
            
            # Get data rows from tbody
            tbody = table.find('tbody')
            if tbody:
                data_rows = tbody.find_all('tr')
            else:
                # If no tbody, get all rows except the first (header)
                all_rows = table.find_all('tr')
                data_rows = all_rows[1:] if len(all_rows) > 1 else []
            
            self.logger.debug(f"Found {len(data_rows)} data rows")
            
            for row in data_rows:
                # Skip header rows within tbody (they have scope='col')
                if row.find('th', {'scope': 'col'}):
                    continue
                
                cells = row.find_all(['td', 'th'])
                if len(cells) > 0:
                    row_data = {}
                    
                    # Match cells to headers
                    for i, cell in enumerate(cells):
                        if i < len(headers):
                            cell_text = cell.get_text(strip=True)
                            row_data[headers[i]] = cell_text
                    
                    # Only add rows with meaningful data (not empty or just dashes)
                    if any(value and value not in ['-', '', '—'] for value in row_data.values()):
                        rows_data.append(row_data)
                        self.logger.debug(f"Added row: {list(row_data.values())[:5]}...")
        
        except Exception as e:
            self.logger.error(f"Error parsing stats table: {e}")
        
        return rows_data
    
    async def scrape_multiple_players(
    self,
    session: aiohttp.ClientSession,
    player_urls: List[str],
    resume: bool = True,
    concurrency: Optional[int] = None
) -> Dict[str, bool]:
        """
        Scrape multiple players asynchronously with dynamic throttling and progress tracking.
        """
        if concurrency is None:
            concurrency = config.MAX_CONCURRENT_REQUESTS

        rate_limiter = RateLimiter(min_interval=3.0)
        
        results = {}

        # Filter already processed
        existing_data = utils.get_existing_data_ids(self.logger) if resume else set()
        urls_to_process = [url for url in player_urls if utils.extract_player_id_from_url(url) not in existing_data]

        self.logger.info(f"Starting scrape: {len(urls_to_process)} new players, {len(existing_data)} already processed")
        if not urls_to_process:
            return {}

        semaphore = asyncio.Semaphore(concurrency)
        tasks = {asyncio.create_task(self.scrape_player(session, semaphore, url, rate_limiter)) for url in urls_to_process}
        task_to_url = {task: url for task, url in zip(tasks, urls_to_process)}

        with tqdm(total=len(tasks), desc="Scraping players") as pbar:
            pending = tasks
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    url = task_to_url[task]
                    try:
                        player_data = task.result()
                        results[url] = player_data is not None
                    except Exception as e:
                        self.logger.error(f"Error processing {url}: {e}")
                        results[url] = False
                    pbar.update(1)

                # Dynamic concurrency: if >30% of last batch were 429, temporarily reduce concurrency
                recent_failures = sum(1 for t in done if task_to_url[t] in results and not results[task_to_url[t]])
                if recent_failures / max(1, len(done)) > 0.3:
                    old_value = semaphore._value
                    semaphore._value = max(1, semaphore._value - 1)
                    self.logger.info(f"High failure rate detected, reducing concurrency from {old_value} to {semaphore._value}")

        success_count = sum(1 for ok in results.values() if ok)
        self.logger.info(f"Scraping complete: {success_count}/{len(urls_to_process)} players successful")

        return results

async def main():
    """Main function to scrape players end-to-end using index_scraper."""
    scraper = PlayerStatsScraper()
    index_scraper = PlayerIndexScraper()
    
    # Step 1: get some player URLs (test with A only for now)
    player_urls = list(index_scraper.get_all_player_urls(['A']))[:10]  # first 10 players
    
    print(f"Discovered {len(player_urls)} player URLs from index scraper.")
    
    # Step 2: scrape stats for those players
    # This main function is for testing and needs a session if called directly.
    # For simplicity, we assume it's run via the main orchestrator.
    # If you want to run this file directly, you'd need to create a session here.
    # async with aiohttp.ClientSession() as session:
    #     results = await scraper.scrape_multiple_players(session, player_urls)
    
    # The following line will fail if run directly, as it's missing the session argument.
    # It is kept this way because the primary entry point is main.py
    # results = await scraper.scrape_multiple_players(player_urls)
    
    # To make this file runnable, we can do this for a simple test:
    async with aiohttp.ClientSession() as session:
        results = await scraper.scrape_multiple_players(session, player_urls)


    # Step 3: summarize results
    success_count = sum(1 for status in results.values() if status)
    print(f"Scraping complete: {success_count}/{len(results)} players successfully scraped")
    print("Sample results:")
    for url, ok in list(results.items())[:3]:  # show first 3
        print(f"  {url}: {'OK' if ok else 'FAILED'}")

if __name__ == "__main__":
    asyncio.run(main())
