"""
Main orchestration script for NCAA Football scraper
Coordinates index scraping and player data extraction for academic research
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional
import json

import config
import utils
from index_scraper import PlayerIndexScraper
from player_scraper import PlayerStatsScraper


class NCAAFootballScraper:
    """Main coordinator for the NCAA Football scraping process."""
    
    def __init__(self):
        self.logger = utils.setup_logging('main_scraper')
        self.index_scraper = PlayerIndexScraper()
        self.player_scraper = PlayerStatsScraper()
        
    def run_full_scrape(self, letters: Optional[List[str]] = None, 
                       resume: bool = True, max_players: Optional[int] = None) -> bool:
        """
        Run the complete scraping process: index -> players -> save results.
        
        Args:
            letters: List of alphabet letters to scrape (None for all)
            resume: Whether to resume from existing progress
            max_players: Maximum number of players to scrape (None for all)
            
        Returns:
            True if scraping completed successfully
        """
        self.logger.info("Starting NCAA Football scraper")
        self.logger.info(f"Configuration: letters={letters}, resume={resume}, max_players={max_players}")
        
        try:
            # Phase 1: Scrape player indexes
            self.logger.info("=== PHASE 1: Scraping Player Indexes ===")
            player_urls = self._run_index_scraping(letters)
            
            if not player_urls:
                self.logger.error("No player URLs found. Aborting.")
                return False
            
            # Convert to list if needed and maintain order
            if not isinstance(player_urls, list):
                player_urls = list(player_urls)
                
            self.logger.info(f"Total URLs found: {len(player_urls)}")
            
            # Limit players if specified (take first N as they appear on page)
            if max_players and len(player_urls) > max_players:
                player_urls = player_urls[:max_players]
                self.logger.info(f"Limited to first {max_players} players as they appear on page")
                self.logger.info(f"Processing players: {[url.split('/')[-1].replace('.html', '') for url in player_urls]}")
            
            # Phase 2: Scrape individual players
            self.logger.info("=== PHASE 2: Scraping Individual Players ===")
            success = self._run_player_scraping(player_urls, resume)
            
            # Phase 3: Generate summary report
            self.logger.info("=== PHASE 3: Generating Summary Report ===")
            self._generate_summary_report()
            
            if success:
                self.logger.info("NCAA Football scraping completed successfully!")
            else:
                self.logger.warning("Scraping completed with some errors. Check logs for details.")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Fatal error in scraping process: {e}")
            return False
    
    def _run_index_scraping(self, letters: Optional[List[str]] = None) -> List[str]:
        """Run the index scraping phase and return player URLs."""
        try:
            # Get player URLs from index pages (now returns list in order)
            player_urls = self.index_scraper.get_all_player_urls(letters)
            
            # Save consolidated index
            self.index_scraper.save_consolidated_index()
            
            self.logger.info(f"Index scraping complete: {len(player_urls)} players found")
            
            # Debug: Show first few URLs found
            if player_urls:
                self.logger.info(f"First 5 URLs found: {player_urls[:5]}")
            
            return player_urls
            
        except Exception as e:
            self.logger.error(f"Error in index scraping phase: {e}")
            return []
    
    def _run_player_scraping(self, player_urls: List[str], resume: bool = True) -> bool:
        """Run the player scraping phase."""
        try:
            results = self.player_scraper.scrape_multiple_players(player_urls, resume)
            
            success_count = sum(results.values())
            total_count = len(results)
            failed_count = total_count - success_count
            success_rate = (success_count / total_count * 100) if total_count > 0 else 0
            
            self.logger.info(f"Player scraping results: {success_count}/{total_count} "
                           f"players successful ({success_rate:.1f}%)")
            
            # Log failed players for debugging
            if failed_count > 0:
                failed_urls = [url for url, success in results.items() if not success]
                self.logger.warning(f"Failed to scrape {failed_count} players:")
                for url in failed_urls[:5]:  # Show first 5 failed
                    player_id = url.split('/')[-1].replace('.html', '')
                    self.logger.warning(f"  - {player_id}")
                if len(failed_urls) > 5:
                    self.logger.warning(f"  ... and {len(failed_urls) - 5} more")
            
            # Consider successful if at least 80% succeed
            return success_rate >= 80.0
            
        except Exception as e:
            self.logger.error(f"Error in player scraping phase: {e}")
            return False
    
    def _generate_summary_report(self) -> None:
        """Generate a summary report of the scraping results."""
        try:
            # Get player count based on storage mode
            if config.STORAGE_MODE == 'couchdb':
                existing_data = utils.get_existing_data_ids(self.logger)
                total_players = len(existing_data)
                
                # Sample some players for data quality check
                sample_size = min(10, total_players)
                sample_players = []
                
                if existing_data:
                    client = utils.get_couchdb_client()
                    sample_ids = list(existing_data)[:sample_size]
                    
                    for player_id in sample_ids:
                        player_data = client.get_document(player_id)
                        if player_data:
                            sample_players.append({
                                'player_id': player_data.get('player_info', {}).get('name', player_id),
                                'seasons': len(player_data.get('season_stats', [])),
                                'has_career_stats': bool(player_data.get('career_stats')),
                                'has_game_logs': bool(player_data.get('game_logs')),
                                'doc_size_kb': round(len(str(player_data)) / 1024, 1)  # Approximate size
                            })
            else:
                # File-based storage
                existing_data = utils.get_existing_data_ids(self.logger)
                total_players = len(existing_data)
                
                # Sample some players for data quality check
                sample_size = min(10, total_players)
                sample_players = []
                
                sample_ids = list(existing_data)[:sample_size]
                for player_id in sample_ids:
                    player_data = utils.load_data(player_id, self.logger)
                    if player_data:
                        # For file storage, calculate file size
                        file_path = config.PLAYER_DATA_DIR / f"{player_id}"
                        file_size = file_path.stat().st_size / 1024 if file_path.exists() else 0
                        
                        sample_players.append({
                            'player_id': player_data.get('player_info', {}).get('name', player_id),
                            'seasons': len(player_data.get('season_stats', [])),
                            'has_career_stats': bool(player_data.get('career_stats')),
                            'has_game_logs': bool(player_data.get('game_logs')),
                            'file_size_kb': round(file_size, 1)
                        })
            
            # Create summary report
            report = {
                'scrape_summary': {
                    'total_players_scraped': total_players,
                    'storage_mode': config.STORAGE_MODE,
                    'storage_location': str(config.PLAYER_DATA_DIR) if config.STORAGE_MODE == 'file' else config.COUCHDB_URL,
                    'sample_players': sample_players
                },
                'data_quality': {
                    'avg_seasons_per_player': sum(p['seasons'] for p in sample_players) / len(sample_players) if sample_players else 0,
                    'players_with_career_stats': sum(1 for p in sample_players if p['has_career_stats']),
                    'players_with_game_logs': sum(1 for p in sample_players if p['has_game_logs']),
                    'avg_data_size_kb': sum(p.get('file_size_kb', p.get('doc_size_kb', 0)) for p in sample_players) / len(sample_players) if sample_players else 0
                },
                'configuration': {
                    'request_delay': config.REQUEST_DELAY,
                    'max_retries': config.MAX_RETRIES,
                    'headers': config.HEADERS['User-Agent'],
                    'storage_mode': config.STORAGE_MODE
                }
            }
            
            # Save report using unified storage
            report_success = utils.save_data(report, "scraping_summary", self.logger)
            
            # Log summary
            self.logger.info("=== SCRAPING SUMMARY ===")
            self.logger.info(f"Storage mode: {config.STORAGE_MODE}")
            self.logger.info(f"Total players scraped: {total_players}")
            self.logger.info(f"Average seasons per player: {report['data_quality']['avg_seasons_per_player']:.1f}")
            self.logger.info(f"Average data size: {report['data_quality']['avg_data_size_kb']:.1f} KB")
            
            if report_success:
                self.logger.info(f"Summary report saved using {config.STORAGE_MODE} storage")
            
        except Exception as e:
            self.logger.error(f"Error generating summary report: {e}")
    
    def run_index_only(self, letters: Optional[List[str]] = None) -> bool:
        """Run only the index scraping phase."""
        self.logger.info("Running index scraping only")
        player_urls = self._run_index_scraping(letters)
        return len(player_urls) > 0
    
    def run_players_only(self, max_players: Optional[int] = None, resume: bool = True) -> bool:
        """Run only the player scraping phase using existing index."""
        self.logger.info("Running player scraping only")
        
        # Load existing index using unified storage
        index_data = utils.load_data("all_players_index", self.logger)
        
        if not index_data or 'player_urls' not in index_data:
            self.logger.error("No existing player index found. Run index scraping first.")
            return False
        
        player_urls = index_data['player_urls']
        
        if max_players and len(player_urls) > max_players:
            player_urls = player_urls[:max_players]
        
        return self._run_player_scraping(player_urls, resume)


def create_argument_parser():
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="NCAA Football Statistics Scraper for Academic Research",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full scrape of all players (file storage)
  python main.py --full
  
  # Full scrape using CouchDB storage
  python main.py --full --storage couchdb
  
  # Scrape only players with names starting with A and B
  python main.py --full --letters A B
  
  # Resume interrupted scrape with first 100 players
  python main.py --full --max-players 100 --resume
  
  # Only scrape player indexes
  python main.py --index-only
  
  # Only scrape player data (requires existing index)
  python main.py --players-only --max-players 50
        """
    )
    
    # Main operation modes
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--full', action='store_true',
                          help='Run complete scraping process (index + players)')
    mode_group.add_argument('--index-only', action='store_true',
                          help='Only scrape player indexes')
    mode_group.add_argument('--players-only', action='store_true',
                          help='Only scrape player data (requires existing index)')
    
    # Configuration options
    parser.add_argument('--letters', nargs='+', metavar='LETTER',
                       help='Specific letters to scrape (e.g., A B C)')
    parser.add_argument('--max-players', type=int, metavar='N',
                       help='Maximum number of players to scrape')
    parser.add_argument('--no-resume', action='store_true',
                       help='Start fresh instead of resuming existing progress')
    
    # Storage backend selection
    parser.add_argument('--storage', choices=['file', 'couchdb'], default='file',
                       help='Storage backend to use (default: file)')
    
    return parser


def main():
    """Main entry point for the NCAA Football scraper."""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Set storage mode from command line argument
    config.STORAGE_MODE = args.storage
    
    # Validate letters
    if args.letters:
        args.letters = [letter.upper() for letter in args.letters]
        invalid_letters = [l for l in args.letters if l not in config.ALPHABET]
        if invalid_letters:
            print(f"Error: Invalid letters: {invalid_letters}")
            sys.exit(1)
    
    # Test CouchDB connection if using CouchDB storage
    if config.STORAGE_MODE == 'couchdb':
        try:
            client = utils.get_couchdb_client()
            db_info = client.get_database_info()
            print(f"✅ Connected to CouchDB database: {client.database}")
            print(f"   Documents: {db_info.get('doc_count', 0)}")
            print(f"   Size: {db_info.get('data_size', 0)} bytes")
        except Exception as e:
            print(f"❌ Failed to connect to CouchDB: {e}")
            print("Make sure CouchDB is running and accessible at the configured URL")
            sys.exit(1)
    
    # Create scraper instance
    scraper = NCAAFootballScraper()
    
    # Run appropriate scraping mode
    try:
        if args.full:
            success = scraper.run_full_scrape(
                letters=args.letters,
                resume=not args.no_resume,
                max_players=args.max_players
            )
        elif args.index_only:
            success = scraper.run_index_only(letters=args.letters)
        elif args.players_only:
            success = scraper.run_players_only(
                max_players=args.max_players,
                resume=not args.no_resume
            )
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()