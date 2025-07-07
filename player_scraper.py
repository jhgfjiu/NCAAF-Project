"""
Player scraper for NCAA Football statistics
Visits individual player pages and extracts comprehensive statistics data
"""

import re
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup, Tag
from tqdm import tqdm
import pandas as pd

import config
import utils


class PlayerStatsScraper:
    """Scrapes individual player pages for comprehensive statistics."""
    
    def __init__(self):
        self.logger = utils.setup_logging('player_scraper')
        self.session = utils.create_session()
        
    def scrape_player(self, player_url: str, player_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Scrape comprehensive statistics for a single player.
        
        Args:
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
        
        # Check if already scraped
        output_file = config.PLAYER_DATA_DIR / config.PLAYER_FILE_PATTERN.format(player_id=player_id)
        if output_file.exists():
            self.logger.debug(f"Player {player_id} already scraped, skipping")
            return utils.load_json(output_file, self.logger)
        
        response = utils.safe_request(self.session, player_url, self.logger)
        if not response:
            self.logger.error(f"Failed to retrieve player page: {player_url}")
            return None
        
        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            player_data = self._extract_player_data(soup, player_id, player_url)
            
            if player_data:
                # Format and save data
                formatted_data = utils.format_stats_data(player_data)
                utils.save_json(formatted_data, output_file, self.logger)
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
        data = {
            'player_id': player_id,
            'source_url': player_url,
            'player_info': self._extract_player_info(soup),
            'career_stats': self._extract_career_stats(soup),
            'season_stats': self._extract_season_stats(soup),
            'game_logs': self._extract_game_logs(soup),
            'advanced_stats': self._extract_advanced_stats(soup)
        }
        
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
    
    def scrape_multiple_players(self, player_urls: List[str], resume: bool = True) -> Dict[str, bool]:
        """
        Scrape multiple players with progress tracking.
        
        Args:
            player_urls: List of player URLs to scrape
            resume: Whether to skip already processed players
            
        Returns:
            Dictionary mapping player URLs to success status
        """
        results = {}
        
        # Filter already processed if resuming
        if resume:
            existing_files = utils.get_existing_player_files(self.logger)
            urls_to_process = []
            
            for url in player_urls:
                player_id = utils.extract_player_id_from_url(url)
                if player_id not in existing_files:
                    urls_to_process.append(url)
            
            self.logger.info(f"Resuming scrape: {len(urls_to_process)} new players, "
                           f"{len(existing_files)} already processed")
        else:
            urls_to_process = player_urls
        
        # Process players with progress bar
        for url in tqdm(urls_to_process, desc="Scraping players"):
            try:
                player_data = self.scrape_player(url)
                results[url] = player_data is not None
                
            except Exception as e:
                self.logger.error(f"Error processing player URL {url}: {e}")
                results[url] = False
        
        success_count = sum(results.values())
        self.logger.info(f"Scraping complete: {success_count}/{len(urls_to_process)} players successful")
        
        return results


def main():
    """Main function for testing the player scraper."""
    scraper = PlayerStatsScraper()
    
    # Test with a single player URL
    test_url = "https://www.sports-reference.com/cfb/players/sample-player-1.html"
    
    # In real usage, you would get URLs from index_scraper
    # from index_scraper import PlayerIndexScraper
    # index_scraper = PlayerIndexScraper()
    # player_urls = list(index_scraper.get_all_player_urls(['A']))[:5]  # Test first 5
    
    print("Player scraper ready. Use with URLs from index_scraper.")


if __name__ == "__main__":
    main()