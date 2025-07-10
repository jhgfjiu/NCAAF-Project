"""
Index scraper for NCAA Football player data
Scrapes A-Z player index pages to collect player profile URLs
"""

import re
from typing import List, Dict, Set
from bs4 import BeautifulSoup
from tqdm import tqdm

import config
import utils


class PlayerIndexScraper:
    """Scrapes player index pages to collect player URLs."""
    
    def __init__(self):
        self.logger = utils.setup_logging('index_scraper')
        self.session = utils.create_session()
        self.player_urls = set()
        
    def scrape_letter_index(self, letter: str) -> List[Dict[str, str]]:
        """
        Scrape player index page for a specific letter.
        
        Args:
            letter: Letter to scrape (A-Z)
            
        Returns:
            List of player dictionaries with name and URL
        """
        url = config.PLAYER_INDEX_TEMPLATE.format(letter=letter.lower())
        self.logger.info(f"Scraping index for letter '{letter}': {url}")
        
        # Check cache first
        cache_file = config.STORAGE_DIR / config.INDEX_CACHE_PATTERN.format(letter=letter)
        cached_data = utils.load_data(cache_file, self.logger)
        if cached_data:
            self.logger.info(f"Using cached data for letter '{letter}' ({len(cached_data)} players)")
            return cached_data
        
        response = utils.safe_request(self.session, url, self.logger)
        if not response:
            self.logger.error(f"Failed to retrieve index page for letter '{letter}'")
            return []
        
        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            players = self._extract_players_from_page(soup)
            
            self.logger.info(f"Found {len(players)} players for letter '{letter}'")
            
            # Cache the results
            utils.save_data(players, cache_file, self.logger)
            
            return players
            
        except Exception as e:
            self.logger.error(f"Error parsing index page for letter '{letter}': {e}")
            return []
    
    def _extract_players_from_page(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """
        Extract player information from index page soup.
        
        Args:
            soup: BeautifulSoup object of the index page
            
        Returns:
            List of player dictionaries
        """
        players = []
        
        try:
            # Find all player links - exclude navigation/generic links
            all_links = soup.find_all('a', href=re.compile(r'/cfb/players/'))
            
            # Filter out navigation links and keep only actual player pages
            player_links = []
            for link in all_links:
                href = link.get('href', '')
                # Skip generic/navigation links
                if href in ['/cfb/players/', '/cfb/players'] or 'index' in href:
                    continue
                # Keep links that end with player files (.html with player ID)
                if href.endswith('.html') and len(href.split('/')) >= 4:
                    player_links.append(link)
            
            self.logger.debug(f"Found {len(player_links)} actual player links (filtered from {len(all_links)} total)")
            
            for link in player_links:
                try:
                    player_name = link.get_text(strip=True)
                    player_url = link.get('href')
                    player_id = utils.extract_player_id_from_url(player_url)
                    
                    if player_id and player_name and len(player_name) > 1:
                        # Extract additional info from the parent element
                        parent_text = link.parent.get_text(strip=True) if link.parent else ""
                        
                        players.append({
                            'name': player_name,
                            'url': player_url,
                            'player_id': player_id,
                            'full_url': config.BASE_URL + player_url,
                            'details': parent_text  # Includes school and years
                        })
                        
                        self.logger.debug(f"Added player: {player_name} -> {player_id}")
                        
                except Exception as e:
                    self.logger.debug(f"Error processing player link: {e}")
                    continue
            
            self.logger.info(f"Successfully extracted {len(players)} players from page")
            
        except Exception as e:
            self.logger.error(f"Error extracting players from page: {e}")
        
        return players
    
    def scrape_all_letters(self, letters: List[str] = None) -> Dict[str, List[Dict[str, str]]]:
        """
        Scrape player index pages for all specified letters.
        
        Args:
            letters: List of letters to scrape (defaults to full alphabet)
            
        Returns:
            Dictionary mapping letters to player lists
        """
        if letters is None:
            letters = config.ALPHABET
        
        self.logger.info(f"Starting index scrape for {len(letters)} letters: {letters}")
        
        all_players = {}
        
        for letter in tqdm(letters, desc="Scraping player indexes"):
            try:
                players = self.scrape_letter_index(letter)
                all_players[letter] = players
                
                # Add URLs to master set
                for player in players:
                    self.player_urls.add(player['full_url'])
                    
            except Exception as e:
                self.logger.error(f"Failed to scrape letter '{letter}': {e}")
                all_players[letter] = []
        
        total_players = sum(len(players) for players in all_players.values())
        self.logger.info(f"Index scraping complete. Found {total_players} total players across {len(letters)} letters")
        
        return all_players
    
    def get_all_player_urls(self, letters: List[str] = None) -> List[str]:
        """
        Get all player URLs from index pages in order.
        
        Args:
            letters: List of letters to scrape (defaults to full alphabet)
            
        Returns:
            List of player URLs in the order they appear on pages
        """
        all_player_data = self.scrape_all_letters(letters)
        
        # Collect URLs in order
        ordered_urls = []
        for letter in (letters or config.ALPHABET):
            if letter in all_player_data:
                for player in all_player_data[letter]:
                    if player['full_url'] not in ordered_urls:  # Avoid duplicates
                        ordered_urls.append(player['full_url'])
        
        return ordered_urls
    
    def save_consolidated_index(self, output_file: str = "all_players_index") -> bool:
        """
        Save consolidated player index using unified storage.
        
        Args:
            output_file: Name of output identifier (no extension needed)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.player_urls:
            self.logger.warning("No player URLs to save. Run scrape_all_letters() first.")
            return False

        player_list = sorted(list(self.player_urls))
        
        data = {
            'scraped_at': utils.format_stats_data({})['scraped_at'],
            'total_players': len(player_list),
            'player_urls': player_list
        }
        
        success = utils.save_data(data, output_file, self.logger)
        if success:
            self.logger.info(f"Saved consolidated index with {len(player_list)} players using {config.STORAGE_MODE} storage")
        
        return success


def main():
    """Main function for testing the index scraper."""
    scraper = PlayerIndexScraper()
    
    # Test with a few letters first
    test_letters = ['A', 'B']
    player_data = scraper.scrape_all_letters(test_letters)
    
    # Print summary
    for letter, players in player_data.items():
        print(f"Letter {letter}: {len(players)} players")
        if players:
            print(f"  Sample: {players[0]['name']} -> {players[0]['player_id']}")
    
    # Save consolidated index
    scraper.save_consolidated_index("test_index")


if __name__ == "__main__":
    main()