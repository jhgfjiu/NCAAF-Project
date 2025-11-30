"""
Unified utility functions for NCAA Football scraper
Handles logging, storage (file & CouchDB), retry logic, and common operations
"""

import json
import logging
import time
import requests
import random
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from urllib.parse import urljoin
import config


# ============================================================================
# LOGGING AND NETWORKING
# ============================================================================

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
    session.headers.update(config.BASE_HEADERS)
    if config.USER_AGENTS:
        session.headers['User-Agent'] = random.choice(config.USER_AGENTS)
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


# ============================================================================
# COUCHDB CLIENT
# ============================================================================

class CouchDBError(Exception):
    """Custom exception for CouchDB operations"""
    pass


class CouchDBClient:
    """CouchDB client for managing player data storage"""
    
    def __init__(self, base_url: str = "http://localhost:5984", 
                 username: str = None, password: str = None,
                 database: str = "ncaaf_players"):
        """
        Initialize CouchDB client
        
        Args:
            base_url: CouchDB server URL
            username: Admin username (if auth required)
            password: Admin password (if auth required)
            database: Database name for player data
        """
        self.base_url = base_url.rstrip('/')
        self.database = database
        self.auth = (username, password) if username and password else None
        self.logger = logging.getLogger('couchdb_client')
        
        # Test connection and create database if needed
        self._ensure_database_exists()
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request to CouchDB with error handling"""
        url = urljoin(self.base_url + '/', endpoint.lstrip('/'))
        
        # Add auth if configured
        if self.auth:
            kwargs['auth'] = self.auth
        
        # Set default headers
        headers = kwargs.get('headers', {})
        headers.setdefault('Content-Type', 'application/json')
        kwargs['headers'] = headers
        
        try:
            response = requests.request(method, url, **kwargs)
            return response
        except requests.exceptions.RequestException as e:
            raise CouchDBError(f"Request failed: {e}")
    
    def _ensure_database_exists(self):
        """Create database if it doesn't exist"""
        try:
            # Check if database exists
            response = self._make_request('HEAD', f'/{self.database}')
            if response.status_code == 200:
                self.logger.info(f"Connected to existing database: {self.database}")
                return
            
            # Create database
            response = self._make_request('PUT', f'/{self.database}')
            if response.status_code == 201:
                self.logger.info(f"Created new database: {self.database}")
            else:
                raise CouchDBError(f"Failed to create database: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"Database setup failed: {e}")
            raise
    
    def save_document(self, doc_id: str, data: Dict[str, Any]) -> bool:
        """Save document to CouchDB"""
        try:
            # Check if document exists to get revision
            existing_doc = self.get_document(doc_id)
            if existing_doc:
                data['_rev'] = existing_doc['_rev']
            
            # Set document ID
            data['_id'] = doc_id
            data['updated_at'] = datetime.now().isoformat()
            
            response = self._make_request(
                'PUT', 
                f'/{self.database}/{doc_id}',
                json=data
            )
            
            if response.status_code in [201, 200]:
                self.logger.debug(f"Saved document: {doc_id}")
                return True
            else:
                self.logger.error(f"Failed to save document {doc_id}: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error saving document {doc_id}: {e}")
            return False
    
    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve document from CouchDB"""
        try:
            response = self._make_request('GET', f'/{self.database}/{doc_id}')
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                self.logger.error(f"Failed to get document {doc_id}: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting document {doc_id}: {e}")
            return None
    
    def document_exists(self, doc_id: str) -> bool:
        """Check if document exists"""
        try:
            response = self._make_request('HEAD', f'/{self.database}/{doc_id}')
            return response.status_code == 200
        except Exception:
            return False
    
    def get_all_document_ids(self) -> List[str]:
        """Get list of all document IDs in database"""
        try:
            response = self._make_request('GET', f'/{self.database}/_all_docs')
            
            if response.status_code == 200:
                data = response.json()
                return [row['id'] for row in data['rows'] if not row['id'].startswith('_')]
            else:
                self.logger.error(f"Failed to get document IDs: {response.status_code}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error getting document IDs: {e}")
            return []
    
    def bulk_save(self, documents: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Save multiple documents in one request"""
        try:
            bulk_data = {'docs': documents}
            
            response = self._make_request(
                'POST',
                f'/{self.database}/_bulk_docs',
                json=bulk_data
            )
            
            if response.status_code == 201:
                results = response.json()
                successful = sum(1 for result in results if 'error' not in result)
                failed = len(results) - successful
                
                self.logger.info(f"Bulk save: {successful} successful, {failed} failed")
                return successful, failed
            else:
                self.logger.error(f"Bulk save failed: {response.status_code}")
                return 0, len(documents)
                
        except Exception as e:
            self.logger.error(f"Error in bulk save: {e}")
            return 0, len(documents)
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete document from CouchDB"""
        try:
            doc = self.get_document(doc_id)
            if not doc:
                return True  # Already doesn't exist
            
            response = self._make_request(
                'DELETE',
                f'/{self.database}/{doc_id}?rev={doc["_rev"]}'
            )
            
            return response.status_code == 200
            
        except Exception as e:
            self.logger.error(f"Error deleting document {doc_id}: {e}")
            return False
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get database information and stats"""
        try:
            response = self._make_request('GET', f'/{self.database}')
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception:
            return {}
    
    def create_index(self, fields: List[str], name: str = None) -> bool:
        """Create an index for querying"""
        try:
            index_data = {
                'index': {'fields': fields},
                'name': name or f"idx_{'_'.join(fields)}",
                'type': 'json'
            }
            
            response = self._make_request(
                'POST',
                f'/{self.database}/_index',
                json=index_data
            )
            
            return response.status_code == 200
            
        except Exception as e:
            self.logger.error(f"Error creating index: {e}")
            return False
    
    def query_by_field(self, field: str, value: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Simple query by field value"""
        try:
            query_data = {
                'selector': {field: value},
                'limit': limit
            }
            
            response = self._make_request(
                'POST',
                f'/{self.database}/_find',
                json=query_data
            )
            
            if response.status_code == 200:
                return response.json().get('docs', [])
            return []
            
        except Exception as e:
            self.logger.error(f"Error querying by {field}={value}: {e}")
            return []


# Global CouchDB client instance
_couchdb_client = None

def get_couchdb_client() -> CouchDBClient:
    """Get or create CouchDB client instance"""
    global _couchdb_client
    if _couchdb_client is None:
        base_url = getattr(config, 'COUCHDB_URL', 'http://localhost:5984')
        username = getattr(config, 'COUCHDB_USERNAME', None)
        password = getattr(config, 'COUCHDB_PASSWORD', None)
        database = getattr(config, 'COUCHDB_DATABASE', 'ncaaf_players')
        
        _couchdb_client = CouchDBClient(base_url, username, password, database)
    
    return _couchdb_client


# ============================================================================
# UNIFIED STORAGE INTERFACE
# ============================================================================

def save_data(data: Dict[str, Any], identifier: str, logger: logging.Logger) -> bool:
    """
    Save data using configured storage backend (file or CouchDB).
    
    Args:
        data: Dictionary to save
        identifier: Player ID or filename (without extension for files)
        logger: Logger instance
        
    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Saving with STORAGE_MODE={config.STORAGE_MODE}")

    identifier = str(identifier)

    if identifier.endswith('.json'):
        identifier = identifier[:-5]

    if config.STORAGE_MODE == 'couchdb':
        if not isinstance(data, dict):
            logger.warning("Auto-wrapping non-dict data before CouchDB save")
            data = {
                "data": data,
                "wrapped": True,
                "saved_at": datetime.now().isoformat()
            }
        return save_to_couchdb(data, identifier, logger)
    else:
        filepath = config.PLAYER_DATA_DIR / f"{identifier}.json"
        return save_json(data, filepath, logger)

def save_bulk_data(documents: List[Dict[str, Any]], logger: logging.Logger) -> bool:
    """
    Save a batch of documents using the configured storage backend.
    Currently only supports CouchDB.
    """
    if config.STORAGE_MODE == 'couchdb':
        try:
            client = get_couchdb_client()
            # Prepare documents for bulk save, ensuring _id is set
            for doc in documents:
                if 'player_id' in doc and '_id' not in doc:
                    doc['_id'] = doc['player_id']
            
            successful, failed = client.bulk_save(documents)
            logger.info(f"Bulk saved to CouchDB: {successful} successful, {failed} failed.")
            return failed == 0
        except Exception as e:
            logger.error(f"Failed to bulk save to CouchDB: {e}")
            return False
    else:
        logger.warning("Bulk saving is only implemented for CouchDB. Saving files individually.")
        success = True
        for doc in documents:
            if 'player_id' in doc:
                if not save_data(doc, doc['player_id'], logger):
                    success = False
        return success

def load_data(identifier: str, logger: logging.Logger) -> Optional[Dict[str, Any]]:
    """
    Load data using configured storage backend (file or CouchDB).
    
    Args:
        identifier: Player ID or filename (without extension for files)
        logger: Logger instance
        
    Returns:
        Loaded data or None if failed
    """
    if config.STORAGE_MODE == 'couchdb':
        return load_from_couchdb(identifier, logger)
    else:
        # Default to file storage
        filepath = config.PLAYER_DATA_DIR / f"{identifier}.json"
        return load_json(filepath, logger)


def data_exists(identifier: str, logger: logging.Logger) -> bool:
    """
    Check if data exists using configured storage backend.
    
    Args:
        identifier: Player ID or filename (without extension for files)
        logger: Logger instance
        
    Returns:
        True if data exists, False otherwise
    """
    if config.STORAGE_MODE == 'couchdb':
        return couchdb_document_exists(identifier, logger)
    else:
        # Default to file storage
        filepath = config.PLAYER_DATA_DIR / f"{identifier}.json"
        return filepath.exists()


def get_existing_data_ids(logger: logging.Logger) -> set:
    """
    Get set of existing data IDs to avoid re-processing.
    
    Args:
        logger: Logger instance
        
    Returns:
        Set of player IDs that already have data
    """
    if config.STORAGE_MODE == 'couchdb':
        return get_existing_couchdb_docs(logger)
    else:
        # Default to file storage
        return get_existing_player_files(logger)


# ============================================================================
# COUCHDB STORAGE FUNCTIONS
# ============================================================================

def save_to_couchdb(data: Dict[str, Any], doc_id: str, logger: logging.Logger) -> bool:
    """Save data to CouchDB."""
    try:
        client = get_couchdb_client()
        success = client.save_document(doc_id, data)
        if success:
            logger.debug(f"Saved to CouchDB: {doc_id}")
        return success
    except Exception as e:
        logger.error(f"Failed to save to CouchDB {doc_id}: {e}")
        return False


def load_from_couchdb(doc_id: str, logger: logging.Logger) -> Optional[Dict[str, Any]]:
    """Load data from CouchDB."""
    try:
        client = get_couchdb_client()
        doc = client.get_document(doc_id)
        if doc:
            logger.debug(f"Loaded from CouchDB: {doc_id}")
        return doc
    except Exception as e:
        logger.error(f"Failed to load from CouchDB {doc_id}: {e}")
        return None


def couchdb_document_exists(doc_id: str, logger: logging.Logger) -> bool:
    """Check if document exists in CouchDB."""
    try:
        client = get_couchdb_client()
        return client.document_exists(doc_id)
    except Exception as e:
        logger.error(f"Failed to check CouchDB document {doc_id}: {e}")
        return False


def get_existing_couchdb_docs(logger: logging.Logger) -> set:
    """Get set of existing CouchDB document IDs."""
    try:
        client = get_couchdb_client()
        doc_ids = client.get_all_document_ids()
        logger.info(f"Found {len(doc_ids)} existing documents in CouchDB")
        return set(doc_ids)
    except Exception as e:
        logger.error(f"Failed to get CouchDB document IDs: {e}")
        return set()


# ============================================================================
# FILE STORAGE FUNCTIONS
# ============================================================================

def save_json(data: Dict[str, Any], filepath: Path, logger: logging.Logger) -> bool:
    """Save data to JSON file with error handling."""
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
    """Load data from JSON file with error handling."""
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


def get_existing_player_files(logger: logging.Logger) -> set:
    """Get set of already processed player IDs to avoid re-scraping."""
    existing_files = set()
    
    try:
        for file_path in config.PLAYER_DATA_DIR.glob("*.json"):
            player_id = file_path.stem
            if not player_id.startswith('index_') and player_id != 'all_players_index' and not player_id.startswith('scraping_summary'):
                existing_files.add(player_id)
            
        logger.info(f"Found {len(existing_files)} existing player files")
        
    except Exception as e:
        logger.error(f"Error checking existing files: {e}")
        
    return existing_files


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def extract_player_id_from_url(url: str) -> Optional[str]:
    """
    Extract player ID from Sports Reference URL.
    
    Example:
        '/cfb/players/john-smith-1.html' -> 'john-smith-1'
    """
    try:
        if '/cfb/players/' in url:
            filename = url.split('/cfb/players/')[-1]
            if filename.endswith('.html'):
                return filename[:-5]  # Remove .html
        return None
    except Exception:
        return None


def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing invalid characters."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename


def format_stats_data(raw_stats: Dict[str, Any]) -> Dict[str, Any]:
    """Format and clean scraped statistics data."""
    formatted = {
        'scraped_at': datetime.now().isoformat(),
        'player_info': raw_stats.get('player_info', {}),
        'career_stats': raw_stats.get('career_stats', {}),
        'season_stats': raw_stats.get('season_stats', []),
        'game_logs': raw_stats.get('game_logs', []),
    }
    
    return formatted