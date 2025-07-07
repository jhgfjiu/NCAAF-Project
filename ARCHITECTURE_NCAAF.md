# NCAAF Player Statistics Scraper — Architecture Guide

## Project Overview

This project scrapes historical and current **NCAA football player statistics** from [https://www.sports-reference.com/cfb/](https://www.sports-reference.com/cfb/). It extracts structured season-by-season data from individual player pages using `requests` and `BeautifulSoup`, storing results in JSON files for downstream analysis.

---

## Project Structure

```
ncaaf_scraper/
├── main.py                # Orchestrates full scrape process
├── index_scraper.py       # Scrapes A–Z player index pages to get player profile URLs
├── player_scraper.py      # Visits each player URL and extracts stat tables
├── utils.py               # Utility functions (e.g., retry logic, logging, saving)
├── storage/
│   └── player_data/       # Output directory for JSON files per player
├── config.py              # Constants, URL templates, headers, settings
├── requirements.txt       # pip dependencies
└── ARCHITECTURE.md        # This document
```

---

## Key Components

### 1. `index_scraper.py`
- Visits the [player index page](https://www.sports-reference.com/cfb/players/)
- Loops over `A–Z` links
- Collects player name + profile URL pairs
- Output saved as `players_index.json`

```json
[
  { "name": "Holton Ahlers", "url": "https://www.sports-reference.com/cfb/players/holton-ahlers-1.html" },
  ...
]
```

---

### 2. `player_scraper.py`
- Accepts a single player URL
- Extracts:
  - Name, school, position, physical stats (height, weight)
  - Season-by-season stat tables:
    - Passing
    - Rushing & Receiving
    - Defense & Fumbles
    - Punting & Kicking
    - Scoring
- Normalizes each row into a dictionary with metadata
- Output saved to `storage/player_data/{player_slug}.json`

```json
{
  "name": "Holton Ahlers",
  "school": "East Carolina",
  "position": "QB",
  "height": "6-3",
  "weight": "230lb",
  "stats": [
    {
      "season": "2022",
      "type": "passing",
      "team": "East Carolina",
      "cmp": 315,
      "att": 469,
      "yds": 3708,
      "td": 28,
      "int": 5
    }
  ]
}
```

---

### 3. `main.py`
- Loads all player URLs from index
- Loops through each URL
- Applies:
  - Retry/backoff on failure
  - Progress logging
- Can support multithreading for speedup

---

### 4. `utils.py`
Includes:
- `retry_request(url, headers, timeout, max_retries)`
- `slugify(name)` for filename generation
- `save_json(data, path)`
- `log(message)`

---

## Storage Format

- One JSON file per player under `storage/player_data/`
- Optional batch mode: combine all players into a single `all_players.json`
- Future export option: flatten into CSV or load into a database

---

## ⚙️ Configurable Settings (`config.py`)

```python
BASE_URL = "https://www.sports-reference.com"
PLAYER_INDEX_URL = f"{BASE_URL}/cfb/players/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NCAAFScraper/1.0)"
}
SAVE_PATH = "./storage/player_data/"
```

---

## Extension Opportunities

- Add CLI or web UI
- Add a local SQLite/Parquet database writer
- Scrape **Game Logs** or **Splits** from player subpages
- Integrate with `pandas` for direct analytics
- Create scheduled updates with `cron`

---

## Ethics & Limits

- Scrape responsibly with:
  - `time.sleep()` between requests
  - Respect `robots.txt` (which currently permits scraping this data)
- Avoid overloading the site or circumventing access controls

---

## Dependencies

```txt
requests
beautifulsoup4
tqdm
```

Install with:

```bash
pip install -r requirements.txt
```