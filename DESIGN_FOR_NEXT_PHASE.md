# Migrating NCAAF Player Scraper to CouchDB

This guide explains how to migrate the existing file-based JSON storage system to use **Apache CouchDB** as the backend for storing player statistics.

---

## Why CouchDB?

CouchDB is a schema-less, document-based database that:
- Stores data as JSON documents
- Has a RESTful HTTP API
- Is well-suited for flexible, hierarchical player data
- Handles large sets of independent documents efficiently

---

## Migration Overview

| Component                 | From (Current)             | To (CouchDB)                     |
|--------------------------|----------------------------|----------------------------------|
| Save function            | `save_json()`              | `save_to_couchdb()`              |
| Load function            | `load_json()`              | `get_from_couchdb()`             |
| Existing file check      | `get_existing_player_files()` | `get_existing_doc_ids()`     |
| JSON files (per player)  | `storage/player_data/*.json` | CouchDB documents with `_id` |
| File name (slugified)    | `"john-smith-1.json"`      | `_id: "john-smith-1"`            |

---

## Step-by-Step Migration

### 1. Set Up CouchDB
- Install CouchDB locally or use a hosted service #CouchDB will be installed from a docker container
- Enable CORS and admin credentials
- Create a database (e.g., `ncaaf_players`)

### 2. Define Document Schema

Each player will be stored as a single CouchDB document:

```json
{
  "_id": "holton-ahlers-1",
  "name": "Holton Ahlers",
  "school": "East Carolina",
  "position": "QB",
  "height": "6-3",
  "weight": "230lb",
  "stats": [ { ... } ],
  "scraped_at": "2025-07-08T17:00:00Z"
}
```

### 3. Install Python CouchDB Client

Use one of the following:
```bash
pip install CouchDB       # Official but lower-level
pip install cloudant      # Higher-level IBM client compatible with CouchDB
```

You can also use `requests` manually for custom interactions.

### 4. Update Utility Functions

#### Replace:
- `save_json()` → `save_to_couchdb(doc, db)`
- `load_json()` → `load_from_couchdb(doc_id, db)`
- `get_existing_player_files()` → `list_all_doc_ids(db)`

> Store the CouchDB client or session in a global config or init script.

### 5. Update `main.py` Logic

- Before scraping, check if a player already exists in CouchDB
- On scrape success, call `save_to_couchdb()` instead of saving a `.json` file

### 6. Optional Enhancements

- Add a CLI flag or config option to switch between file and CouchDB modes
- Add CouchDB views for querying by team, season, position, etc.
- Use bulk operations if performance becomes a bottleneck

---

## Example CouchDB Functions

- `get_doc_by_id(_id)`
- `save_doc(doc)`
- `check_if_exists(_id)`
- `get_all_ids()`

These will replace file I/O logic in `utils.py`.

---

## Handling Conflicts

CouchDB uses revision tracking (`_rev`). To update an existing document:
1. Fetch the document first
2. Attach the `_rev` key to your updated document
3. Save

Handle update conflicts gracefully if scraping in parallel or with retries.

---

## Clean-Up

- Optionally delete `storage/player_data/` after verifying CouchDB migration
- Disable or remove unused file-saving functions

---

## Final Checklist

- [ ] CouchDB server running and accessible
- [ ] Python client installed
- [ ] Database created
- [ ] `utils.py` updated to use DB instead of file system
- [ ] `main.py` modified to use new save/load logic
- [ ] Migration tested with a small set of players

---

## References

- [CouchDB Official Docs](https://docs.couchdb.org/en/stable/)
- [Python `CouchDB` Library](https://pypi.org/project/CouchDB/)
- [Cloudant (CouchDB-compatible)](https://pypi.org/project/cloudant/)
