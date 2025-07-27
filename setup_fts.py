#!/usr/bin/env python3
"""
Setup Full-Text Search (FTS) for the MLK documents database
"""
import sqlite3
import sys

def setup_fts(db_path):
    """Setup FTS virtual table for document search"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if FTS table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents_fts'")
        if cursor.fetchone():
            print("FTS table already exists, dropping and recreating...")
            cursor.execute("DROP TABLE documents_fts")
        
        # Create FTS virtual table
        cursor.execute("""
            CREATE VIRTUAL TABLE documents_fts USING fts5(
                element_id,
                text,
                record_id,
                metadata_filename,
                metadata_data_source_url,
                content='documents',
                content_rowid='rowid'
            )
        """)
        
        # Populate FTS table with existing data
        print("Populating FTS table with document data...")
        cursor.execute("""
            INSERT INTO documents_fts(element_id, text, record_id, metadata_filename, metadata_data_source_url)
            SELECT element_id, text, record_id, metadata_filename, metadata_data_source_url
            FROM documents
            WHERE text IS NOT NULL AND text != ''
        """)
        
        # Create triggers to keep FTS in sync with main table
        cursor.execute("""
            CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, element_id, text, record_id, metadata_filename, metadata_data_source_url)
                VALUES (new.rowid, new.element_id, new.text, new.record_id, new.metadata_filename, new.metadata_data_source_url);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER documents_ad AFTER DELETE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, element_id, text, record_id, metadata_filename, metadata_data_source_url)
                VALUES ('delete', old.rowid, old.element_id, old.text, old.record_id, old.metadata_filename, old.metadata_data_source_url);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER documents_au AFTER UPDATE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, element_id, text, record_id, metadata_filename, metadata_data_source_url)
                VALUES ('delete', old.rowid, old.element_id, old.text, old.record_id, old.metadata_filename, old.metadata_data_source_url);
                INSERT INTO documents_fts(rowid, element_id, text, record_id, metadata_filename, metadata_data_source_url)
                VALUES (new.rowid, new.element_id, new.text, new.record_id, new.metadata_filename, new.metadata_data_source_url);
            END
        """)
        
        # Optimize FTS table
        cursor.execute("INSERT INTO documents_fts(documents_fts) VALUES('optimize')")
        
        conn.commit()
        
        # Check FTS table statistics
        cursor.execute("SELECT COUNT(*) FROM documents_fts")
        fts_count = cursor.fetchone()[0]
        print(f"FTS setup complete. Indexed {fts_count} documents.")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error setting up FTS: {e}")
        return False

if __name__ == "__main__":
    db_path = "mlk.db"
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    print(f"Setting up FTS for database: {db_path}")
    success = setup_fts(db_path)
    
    if success:
        print("FTS setup completed successfully!")
        sys.exit(0)
    else:
        print("FTS setup failed!")
        sys.exit(1)