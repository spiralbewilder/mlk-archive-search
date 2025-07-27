# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development
```bash
# Install dependencies
pip install flask

# Run the application
python app.py

# Access the application
http://localhost:5000
```

### Testing
```bash
# Run test suite
python test_app.py
```

### Database Optimization
```bash
# Set up Full-Text Search (FTS) for better performance
python setup_fts.py

# With custom database path
python setup_fts.py /path/to/mlk.db
```

## Architecture

This is a Flask web application for searching through 27,000+ declassified FBI documents related to Martin Luther King Jr.

### Core Components

- **app.py**: Main Flask application with embedded HTML template
  - Search endpoint (`/search`) with boolean query support (AND, OR, NOT)
  - Health check endpoint (`/health`)
  - Context extraction around search terms
  - PDF URL generation for S3-hosted documents
  - Fallback from FTS to LIKE queries when FTS unavailable

- **Database Structure**: SQLite database (`mlk.db`) with `documents` table containing:
  - `element_id`, `text`, `record_id`
  - `metadata_filename`, `metadata_data_source_url`
  - Optional FTS virtual table (`documents_fts`) for performance

- **setup_fts.py**: Creates FTS5 virtual table with triggers for automatic sync
- **test_app.py**: Basic test suite using Flask test client

### Key Features

- Boolean search with FTS5 when available, LIKE fallback
- Context snippets with configurable word count (`CONTEXT_WORDS = 10`)
- PDF links generated from S3 URLs (`S3_BASE_URL`)
- Pagination support (limit/offset parameters)
- Real-time AJAX search with highlighting

### Configuration

Edit these variables in app.py:
- `DATABASE_PATH`: Path to SQLite database (default: 'mlk.db')
- `S3_BASE_URL`: Base URL for PDF documents
- `CONTEXT_WORDS`: Words shown around search terms (default: 10)

### Database Requirements

The application expects `mlk.db` SQLite file in the same directory. For optimal performance, run `setup_fts.py` to create FTS indexes.