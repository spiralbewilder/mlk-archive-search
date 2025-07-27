#!/usr/bin/env python3
"""
MLK Archive Search Web Application
A simple Flask web app for searching through MLK declassified documents
"""
import sqlite3
import json
import re
import os
from flask import Flask, request, jsonify, render_template_string
from urllib.parse import quote

app = Flask(__name__)

# Configuration from environment variables
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-key-change-in-production')
DATABASE_PATH = os.environ.get('DATABASE_PATH', 'mlk.db')
S3_BASE_URL = os.environ.get('S3_BASE_URL', 'https://example-transformations-mlk-archive.s3.amazonaws.com/mlk-archive/')
CONTEXT_WORDS = int(os.environ.get('CONTEXT_WORDS', '10'))  # Number of words before/after search term

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def extract_context(text, search_terms, max_lines=5):
    """Extract context around search terms showing up to max_lines of text"""
    if not text or not search_terms:
        # Show up to max_lines when no search terms
        lines = text.split('\n')[:max_lines]
        result = '\n'.join(lines)
        if len(text.split('\n')) > max_lines:
            result += "..."
        return process_prefix(result)
    
    # Split text into lines for better context
    lines = text.split('\n')
    
    contexts = []
    for term in search_terms:
        term_lower = term.lower().strip('"')
        
        # Find the line containing the search term
        for line_idx, line in enumerate(lines):
            if term_lower in line.lower():
                # If line is very long, focus on the part with the search term
                if len(line) > 300:  # Long line, extract around the term
                    term_pos = line.lower().find(term_lower)
                    start_char = max(0, term_pos - 150)
                    end_char = min(len(line), term_pos + 150)
                    
                    focused_line = line[start_char:end_char]
                    if start_char > 0:
                        focused_line = "..." + focused_line
                    if end_char < len(line):
                        focused_line = focused_line + "..."
                    
                    # Use this focused line plus a few surrounding lines
                    start_line = max(0, line_idx - 1)
                    end_line = min(len(lines), line_idx + 3)
                    
                    context_lines = lines[start_line:line_idx] + [focused_line] + lines[line_idx+1:end_line]
                    context = '\n'.join(context_lines)
                else:
                    # Normal line length, get surrounding context
                    start_line = max(0, line_idx - 1)
                    end_line = min(len(lines), start_line + max_lines)
                    
                    # If we have room, expand backwards
                    if end_line - start_line < max_lines and start_line > 0:
                        start_line = max(0, end_line - max_lines)
                    
                    context_lines = lines[start_line:end_line]
                    context = '\n'.join(context_lines)
                    
                    # Add ellipsis if we truncated
                    if start_line > 0:
                        context = "..." + context
                    if end_line < len(lines):
                        context = context + "..."
                
                contexts.append(context)
                break  # Only get first occurrence for now
    
    result = contexts[0] if contexts else '\n'.join(lines[:max_lines])
    if not contexts and len(lines) > max_lines:
        result += "..."
    
    return process_prefix(result)

def process_prefix(text):
    """Simply remove 'Prefix: This chunk' and keep the descriptive text"""
    if not text.startswith('Prefix: This chunk'):
        return text
    
    # Remove "Prefix: This chunk" and keep the rest
    cleaned_text = re.sub(r'^Prefix: This chunk\s*', '', text)
    
    return cleaned_text

def parse_boolean_query(query):
    """Parse boolean search query with proper FTS5 escaping"""
    query = query.strip()
    
    # Convert common boolean operators to FTS syntax
    query = re.sub(r'\bAND\b', ' AND ', query, flags=re.IGNORECASE)
    query = re.sub(r'\bOR\b', ' OR ', query, flags=re.IGNORECASE)
    query = re.sub(r'\bNOT\b', ' NOT ', query, flags=re.IGNORECASE)
    
    # Split query into tokens, preserving quoted phrases
    tokens = re.findall(r'"[^"]*"|\S+', query)
    
    processed_tokens = []
    for token in tokens:
        # Skip boolean operators
        if token.upper() in ['AND', 'OR', 'NOT']:
            processed_tokens.append(token)
        elif token.startswith('"') and token.endswith('"'):
            # Quoted phrase - escape special FTS characters inside
            inner = token[1:-1]
            escaped = escape_fts_special_chars(inner)
            processed_tokens.append(f'"{escaped}"')
        else:
            # Regular term - escape special FTS characters
            escaped = escape_fts_special_chars(token)
            processed_tokens.append(escaped)
    
    return ' '.join(processed_tokens)

def escape_fts_special_chars(text):
    """Escape special characters for FTS5 queries"""
    # FTS5 special characters that need escaping: " * : < > [ ] { } ( ) - + ^ ~
    # We'll quote terms that contain problematic characters
    if re.search(r'[.*:><\[\]{}()\-+^~]', text):
        # Remove existing quotes and escape internal quotes
        escaped = text.replace('"', '""')
        return f'"{escaped}"'
    return text

def search_documents(query, limit=50, offset=0):
    """Search documents using FTS"""
    conn = get_db_connection()
    
    try:
        # First try to use FTS if available
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents_fts'")
        has_fts = cursor.fetchone() is not None
        
        if has_fts:
            # Use FTS search - simplified for performance
            fts_query = parse_boolean_query(query)
            sql = """
                SELECT rowid, element_id, text, record_id, 
                       metadata_filename, metadata_data_source_url,
                       rank
                FROM documents_fts
                WHERE documents_fts MATCH ?
                ORDER BY rank
                LIMIT ? OFFSET ?
            """
            cursor.execute(sql, (fts_query, limit, offset))
        else:
            # Fallback to LIKE search
            like_query = f"%{query}%"
            sql = """
                SELECT rowid, element_id, text, record_id, 
                       metadata_filename, metadata_data_source_url
                FROM documents
                WHERE text LIKE ?
                ORDER BY rowid
                LIMIT ? OFFSET ?
            """
            cursor.execute(sql, (like_query, limit, offset))
        
        results = cursor.fetchall()
        
        # Extract search terms for context
        search_terms = re.findall(r'"[^"]+"|\S+', query)
        search_terms = [term.strip('"') for term in search_terms if not term.upper() in ['AND', 'OR', 'NOT']]
        
        # Deduplicate by filename and filter for results that actually contain search terms
        seen_files = set()
        formatted_results = []
        for row in results:
            filename = row['metadata_filename'] or 'Unknown'
            if filename in seen_files:
                continue
            
            # Check if any search term actually appears in the text (case-insensitive)
            text_lower = row['text'].lower()
            has_search_term = any(term.lower().strip('"') in text_lower for term in search_terms)
            
            if not has_search_term:
                continue  # Skip results that don't actually contain the search terms
                
            seen_files.add(filename)
            
            context = extract_context(row['text'], search_terms)
            
            # Construct PDF URL
            pdf_url = ""
            if row['metadata_data_source_url']:
                # Convert s3:// URL to HTTPS S3 URL
                s3_url = row['metadata_data_source_url']
                if s3_url.startswith('s3://example-transformations-mlk-archive/mlk-archive/'):
                    filename = s3_url.replace('s3://example-transformations-mlk-archive/mlk-archive/', '')
                    pdf_url = S3_BASE_URL + quote(filename)
                else:
                    pdf_url = s3_url  # Use as-is if not expected format
            elif row['metadata_filename']:
                pdf_url = S3_BASE_URL + quote(row['metadata_filename'])
            
            formatted_results.append({
                'element_id': row['element_id'],
                'context': context,
                'pdf_url': pdf_url,
                'filename': row['metadata_filename'] or 'Unknown',
                'record_id': row['record_id']
            })
        
        # Get total count for pagination - simplified for performance
        if has_fts:
            cursor.execute("SELECT COUNT(*) FROM documents_fts WHERE documents_fts MATCH ?", (fts_query,))
        else:
            cursor.execute("SELECT COUNT(*) FROM documents WHERE text LIKE ?", (like_query,))
        
        total_count = cursor.fetchone()[0]
        
        return {
            'results': formatted_results,
            'total': total_count,
            'query': query,
            'limit': limit,
            'offset': offset
        }
        
    except Exception as e:
        return {
            'error': str(e),
            'results': [],
            'total': 0,
            'query': query
        }
    finally:
        conn.close()

@app.route('/')
def index():
    """Main search page"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/search')
def search():
    """Search API endpoint"""
    query = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 50)), 100)  # Cap at 100
    offset = int(request.args.get('offset', 0))
    
    if not query:
        return jsonify({'error': 'Query parameter "q" is required', 'results': [], 'total': 0})
    
    if len(query) < 2:
        return jsonify({'error': 'Query must be at least 2 characters', 'results': [], 'total': 0})
    
    results = search_documents(query, limit, offset)
    return jsonify(results)

@app.route('/health')
def health():
    """Health check endpoint"""
    return {'status': 'ok', 'database': DATABASE_PATH}

# HTML Template (embedded for simplicity)
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MLK Archive Search</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .search-container {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .search-box {
            width: 100%;
            padding: 12px;
            font-size: 16px;
            border: 2px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        .search-button {
            background-color: #007cba;
            color: white;
            padding: 12px 24px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            margin-top: 10px;
        }
        .search-button:hover {
            background-color: #005a87;
        }
        .search-help {
            margin-top: 10px;
            font-size: 14px;
            color: #666;
        }
        .results-container {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 20px;
        }
        .result-item {
            border-bottom: 1px solid #eee;
            padding: 15px 0;
        }
        .result-item:last-child {
            border-bottom: none;
        }
        .result-context {
            margin-bottom: 10px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .result-meta {
            font-size: 14px;
            color: #666;
        }
        .pdf-link {
            color: #007cba;
            text-decoration: none;
            font-weight: bold;
        }
        .pdf-link:hover {
            text-decoration: underline;
        }
        .loading {
            text-align: center;
            padding: 20px;
            color: #666;
        }
        .error {
            color: #d32f2f;
            background-color: #ffebee;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
        }
        .results-info {
            margin-bottom: 15px;
            padding: 10px;
            background-color: #f0f8ff;
            border-radius: 4px;
            font-size: 14px;
        }
        .pagination {
            text-align: center;
            margin-top: 20px;
        }
        .pagination button {
            margin: 0 5px;
            padding: 8px 16px;
            border: 1px solid #ddd;
            background: white;
            cursor: pointer;
            border-radius: 4px;
        }
        .pagination button:hover {
            background-color: #f0f0f0;
        }
        .pagination button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>MLK Archive Document Search</h1>
        <p>Search through 27,000+ declassified FBI documents related to Martin Luther King Jr.</p>
    </div>

    <div class="search-container">
        <input type="text" id="searchInput" class="search-box" placeholder="Enter search terms (e.g., 'FBI AND Birmingham', 'Eric Galt', '\"Safe Deposit Box\"')">
        <button onclick="performSearch()" class="search-button">Search Documents</button>
        
        <div class="search-help">
            <strong>Search Tips:</strong>
            • Use quotes for exact phrases: "Eric S. Galt"
            • Combine terms with AND, OR, NOT: FBI AND Birmingham
            • Search is case-insensitive
        </div>
    </div>

    <div id="resultsContainer" class="results-container" style="display: none;">
        <div id="resultsInfo" class="results-info"></div>
        <div id="resultsContent"></div>
        <div id="pagination" class="pagination"></div>
    </div>

    <script>
        let currentQuery = '';
        let currentOffset = 0;
        const resultsPerPage = 20;

        // Enter key support
        document.getElementById('searchInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                performSearch();
            }
        });

        function performSearch(offset = 0) {
            const query = document.getElementById('searchInput').value.trim();
            if (!query || query.length < 2) {
                alert('Please enter at least 2 characters to search');
                return;
            }

            currentQuery = query;
            currentOffset = offset;

            const resultsContainer = document.getElementById('resultsContainer');
            const resultsContent = document.getElementById('resultsContent');
            
            resultsContainer.style.display = 'block';
            resultsContent.innerHTML = '<div class="loading">Searching documents...</div>';

            const searchUrl = `/search?q=${encodeURIComponent(query)}&limit=${resultsPerPage}&offset=${offset}`;

            fetch(searchUrl)
                .then(response => response.json())
                .then(data => {
                    displayResults(data);
                })
                .catch(error => {
                    resultsContent.innerHTML = `<div class="error">Search failed: ${error.message}</div>`;
                });
        }

        function displayResults(data) {
            const resultsInfo = document.getElementById('resultsInfo');
            const resultsContent = document.getElementById('resultsContent');
            const pagination = document.getElementById('pagination');

            if (data.error) {
                resultsContent.innerHTML = `<div class="error">${data.error}</div>`;
                resultsInfo.innerHTML = '';
                pagination.innerHTML = '';
                return;
            }

            // Results info
            const startResult = currentOffset + 1;
            const endResult = Math.min(currentOffset + data.results.length, data.total);
            resultsInfo.innerHTML = `Found ${data.total} documents. Showing ${startResult}-${endResult}.`;

            // Results content
            if (data.results.length === 0) {
                resultsContent.innerHTML = '<div>No documents found matching your search.</div>';
            } else {
                const resultsHtml = data.results.map(result => `
                    <div class="result-item">
                        <div class="result-context">${highlightSearchTerms(result.context, currentQuery)}</div>
                        <div class="result-meta">
                            ${result.pdf_url ? `<a href="${result.pdf_url}" target="_blank" class="pdf-link">📄 View PDF: ${result.filename}</a>` : `File: ${result.filename}`}
                            <br>Document ID: ${result.element_id}
                        </div>
                    </div>
                `).join('');
                
                resultsContent.innerHTML = resultsHtml;
            }

            // Pagination
            updatePagination(data.total);
        }

        function highlightSearchTerms(text, query) {
            // Simple highlighting - extract terms from query and highlight them
            const terms = query.match(/"[^"]+"|\\S+/g) || [];
            let highlightedText = text;
            
            terms.forEach(term => {
                // Remove quotes and skip boolean operators
                let cleanTerm = term.replace(/"/g, '');
                if (/^(AND|OR|NOT)$/i.test(cleanTerm)) {
                    return; // Skip boolean operators
                }
                
                if (cleanTerm.length > 1) {
                    const regex = new RegExp(`(${escapeRegex(cleanTerm)})`, 'gi');
                    highlightedText = highlightedText.replace(regex, '<strong style="background-color: yellow;">$1</strong>');
                }
            });
            
            return highlightedText;
        }

        function escapeRegex(string) {
            return string.replace(/[.*+?^${}()|\\[\]]/g, '\\$&');
        }

        function updatePagination(total) {
            const pagination = document.getElementById('pagination');
            const totalPages = Math.ceil(total / resultsPerPage);
            const currentPage = Math.floor(currentOffset / resultsPerPage) + 1;

            if (totalPages <= 1) {
                pagination.innerHTML = '';
                return;
            }

            let paginationHtml = '';

            // Previous button
            if (currentPage > 1) {
                paginationHtml += `<button onclick="performSearch(${(currentPage - 2) * resultsPerPage})">Previous</button>`;
            }

            // Page numbers (show max 5 pages around current)
            const startPage = Math.max(1, currentPage - 2);
            const endPage = Math.min(totalPages, currentPage + 2);

            if (startPage > 1) {
                paginationHtml += `<button onclick="performSearch(0)">1</button>`;
                if (startPage > 2) paginationHtml += '<span>...</span>';
            }

            for (let i = startPage; i <= endPage; i++) {
                const isActive = i === currentPage ? ' style="background-color: #007cba; color: white;"' : '';
                paginationHtml += `<button onclick="performSearch(${(i - 1) * resultsPerPage})"${isActive}>${i}</button>`;
            }

            if (endPage < totalPages) {
                if (endPage < totalPages - 1) paginationHtml += '<span>...</span>';
                paginationHtml += `<button onclick="performSearch(${(totalPages - 1) * resultsPerPage})">${totalPages}</button>`;
            }

            // Next button
            if (currentPage < totalPages) {
                paginationHtml += `<button onclick="performSearch(${currentPage * resultsPerPage})">Next</button>`;
            }

            pagination.innerHTML = paginationHtml;
        }
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)