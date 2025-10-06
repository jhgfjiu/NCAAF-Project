"""
Index scraper for NCAA Football player data
Scrapes A-Z player index pages (with pagination) to collect player profile URLs
"""

import re
from typing import List, Dict, Set
from bs4 import BeautifulSoup
from tqdm import tqdm

import config
import utils


class PlayerIndexScraper:
    """Scrapes player index pages (A–Z) to collect player URLs."""

    def __init__(self):
        self.logger = utils.setup_logging('index_scraper')
        self.session = utils.create_session()
        self.player_urls = set()

    def scrape_letter_index(self, letter: str) -> List[Dict[str, str]]:
        """
        Scrape all paginated player index pages for a specific letter.

        Args:
            letter: Letter to scrape (A-Z)

        Returns:
            List of player dictionaries with name, URL, ID, etc.
        """
        self.logger.info(f"Scraping index for letter '{letter}' (with pagination)")

        # Check cache first
        cache_file = config.STORAGE_DIR / config.INDEX_CACHE_PATTERN.format(letter=letter)
        cached_data = utils.load_data(cache_file.stem, self.logger)
        if cached_data:
            if config.STORAGE_MODE == 'couchdb' and 'wrapped' in cached_data and 'data' in cached_data:
                self.logger.info(f"Using cached data for letter '{letter}' ({len(cached_data['data'])} players)")
                return cached_data['data']
            else:
                self.logger.info(f"Using cached data for letter '{letter}' ({len(cached_data)} players)")
                return cached_data

        # Scrape all pages for this letter
        players = self._scrape_letter_pages(letter)

        self.logger.info(f"Found {len(players)} players for letter '{letter}' across all pages")

        # Cache results
        utils.save_data(players, cache_file.stem, self.logger)
        return players

    def _scrape_letter_pages(self, letter: str) -> List[Dict[str, str]]:
        """
        Scrape all paginated index pages for a given letter.
        """
        all_players = []
        page_num = 1

        while True:
            page_suffix = "" if page_num == 1 else f"-{page_num}"
            url = config.PLAYER_INDEX_TEMPLATE.format(letter=letter.lower(), page_suffix=page_suffix)

            self.logger.info(f"Scraping page {page_num} for letter '{letter}': {url}")
            response = utils.safe_request(self.session, url, self.logger)

            # Stop if request fails or page doesn’t exist
            if not response or response.status_code != 200:
                self.logger.info(f"No more pages for '{letter}' (stopped at page {page_num})")
                break

            soup = BeautifulSoup(response.content, 'html.parser')
            players = self._extract_players_from_page(soup)

            if not players:
                self.logger.info(f"No players found on page {page_num} for '{letter}'. Stopping pagination.")
                break

            all_players.extend(players)
            page_num += 1

        return all_players

    def _extract_players_from_page(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """
        Extract player information from an index page soup.
        """
        players = []

        try:
            all_links = soup.find_all('a', href=re.compile(r'/cfb/players/'))
            player_links = []
            for link in all_links:
                href = link.get('href', '')
                if href in ['/cfb/players/', '/cfb/players'] or 'index' in href:
                    continue
                if href.endswith('.html') and len(href.split('/')) >= 4:
                    player_links.append(link)

            self.logger.debug(f"Found {len(player_links)} actual player links (filtered from {len(all_links)} total)")

            for link in player_links:
                try:
                    player_name = link.get_text(strip=True)
                    player_url = link.get('href')
                    player_id = utils.extract_player_id_from_url(player_url)

                    if player_id and player_name and len(player_name) > 1:
                        parent_text = link.parent.get_text(strip=True) if link.parent else ""
                        players.append({
                            'name': player_name,
                            'url': player_url,
                            'player_id': player_id,
                            'full_url': config.BASE_URL + player_url,
                            'details': parent_text  # includes school and years
                        })
                        self.logger.debug(f"Added player: {player_name} -> {player_id}")
                except Exception as e:
                    self.logger.debug(f"Error processing player link: {e}")
                    continue

            self.logger.info(f"Extracted {len(players)} players from page")

        except Exception as e:
            self.logger.error(f"Error extracting players from page: {e}")

        return players

    def scrape_all_letters(self, letters: List[str] = None) -> Dict[str, List[Dict[str, str]]]:
        """
        Scrape player index pages for all specified letters.
        """
        if letters is None:
            letters = config.ALPHABET

        self.logger.info(f"Starting index scrape for {len(letters)} letters: {letters}")

        all_players = {}

        for letter in tqdm(letters, desc="Scraping player indexes"):
            try:
                players = self.scrape_letter_index(letter)
                all_players[letter] = players

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
        """
        all_player_data = self.scrape_all_letters(letters)
        ordered_urls = []

        for letter in (letters or config.ALPHABET):
            if letter in all_player_data:
                for player in all_player_data[letter]:
                    if player['full_url'] not in ordered_urls:
                        ordered_urls.append(player['full_url'])

        return ordered_urls

    def save_consolidated_index(self, output_file: str = "all_players_index") -> bool:
        """
        Save consolidated player index.
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
    """Test entry point for PlayerIndexScraper."""
    scraper = PlayerIndexScraper()
    test_letters = ['A', 'B']
    player_data = scraper.scrape_all_letters(test_letters)

    for letter, players in player_data.items():
        print(f"Letter {letter}: {len(players)} players")
        if players:
            print(f"  Sample: {players[0]['name']} -> {players[0]['player_id']}")

    scraper.save_consolidated_index("test_index")


if __name__ == "__main__":
    main()