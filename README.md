# MLK Archive Search

A simple web application for searching through 27,000+ declassified FBI documents related to Martin Luther King Jr.

## Quick Start

1. **Install Python 3.7+** and clone this repository

2. **Install dependencies:**
   ```bash
   pip install flask
   ```

3. **Get the database file:**
   - You need the `mlk.db` SQLite database file (not included)
   - Place it in the same directory as `app.py`

4. **Run the application:**
   ```bash
   python app.py
   ```

5. **Open your browser to:** `http://localhost:5000`

## Search Examples

- **Basic:** `FBI` or `Birmingham`
- **Boolean:** `FBI AND Birmingham`, `MLK OR King`
- **Phrases:** `"Eric S. Galt"`, `"Safe Deposit Box"`
- **Exclude:** `MLK NOT FBI`

## Features

- Boolean search with AND, OR, NOT operators
- Phrase search with quotes
- Context snippets around search terms
- Direct links to PDF documents
- Responsive web interface
- Real-time AJAX search with pagination

## Optional: Performance Optimization

For faster searches on large databases:
```bash
python setup_fts.py
```

## Testing

```bash
python test_app.py
```

## Files

- `app.py` - Main Flask web application
- `setup_fts.py` - Database optimization script
- `test_app.py` - Basic test suite
- `requirements.txt` - Python dependencies

## Database Schema

The app expects a SQLite database with this structure:
```sql
CREATE TABLE documents (
   element_id TEXT,
   text TEXT,
   metadata_filename TEXT,
   metadata_data_source_url TEXT,
   record_id TEXT,
   -- other fields...
);
```

## Configuration

Edit these variables in `app.py` if needed:
- `DATABASE_PATH` - Path to your SQLite database
- `S3_BASE_URL` - Base URL for PDF documents
- `CONTEXT_WORDS` - Number of words shown around search terms

## API

**Search:** `GET /search?q=<query>&limit=<limit>&offset=<offset>`

**Health:** `GET /health`

## License

MIT License - see LICENSE file