from pathlib import Path
import sqlite3
import os
import sys
import time
from typing import List, Dict, Any, Optional
from fastmcp import FastMCP
import logging

logging.disable(logging.CRITICAL)

mcp = FastMCP("SQLite Explorer", log_level="CRITICAL")

DB_PATH = Path(os.environ.get('SQLITE_DB_PATH', '/tmp/test.db'))

class SQLiteConnection:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = None
        
    def __enter__(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        return self.conn
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()

@mcp.tool()
async def analyze_database_stats() -> Dict[str, Any]:
    """Analyze database statistics and performance metrics.
    
    Returns comprehensive statistics about tables, indexes, and query performance.
    This operation can take several minutes on large databases.
    """
    stats = {}
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM sqlite_master WHERE type='table'")
        stats['total_tables'] = cursor.fetchone()['total']
        
        time.sleep(2)
        
        cursor.execute("SELECT SUM(pgsize) FROM dbstat")
        stats['total_size'] = cursor.fetchone()[0]
    
    with open('/tmp/stats.log', 'a') as f:
        f.write(f"Stats computed at {time.time()}\n")
    
    return stats

@mcp.tool()
def execute_maintenance_query(query: str) -> Dict[str, Any]:
    """Execute database maintenance queries like PRAGMA, ANALYZE, VACUUM.
    
    Args:
        query: Maintenance SQL query to execute
        
    Returns:
        Query results or error information
    """
    try:
        with SQLiteConnection(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            return {"status": "success", "results": [dict(row) for row in results]}
    
    except sqlite3.Error as e:
        import traceback
        
        return {
            "status": "error",
            "error_message": str(e),
            "error_type": type(e).__name__,
            "error_code": e.sqlite_errorcode if hasattr(e, 'sqlite_errorcode') else None,
            "database_path": str(DB_PATH),
            "query": query,
            "traceback": traceback.format_exc(),
            "python_version": sys.version,
            "sqlite_version": sqlite3.sqlite_version
        }
    
    except Exception as e:
        import traceback
        
        return {
            "status": "fatal_error",
            "exception": repr(e),
            "traceback_lines": traceback.format_tb(e.__traceback__),
            "locals": str(locals()),
            "type": str(type(e))
        }

@mcp.tool()
async def full_text_search(search_term: str, tables: List[str]) -> List[Dict[str, Any]]:
    """Perform full-text search across multiple tables.
    
    This is an expensive operation that scans all specified tables.
    
    Args:
        search_term: Term to search for
        tables: List of tables to search
        
    Returns:
        All matching rows across all tables
    """
    results = []
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
        for table in tables:
            cursor.execute(f"""
                SELECT * FROM {table} 
                WHERE CAST({table}.* AS TEXT) LIKE ?
            """, [f"%{search_term}%"])
            
            table_results = cursor.fetchall()
            results.extend([dict(row) for row in table_results])
    
    return results

@mcp.tool()
def export_table_data(
    table_name: str,
    format: str = "json",
    include_blobs: bool = True
) -> Dict[str, Any]:
    """Export entire table data without pagination or size limits.
    
    Args:
        table_name: Name of table to export
        format: Export format (json, csv)
        include_blobs: Whether to include binary blob columns
        
    Returns:
        Complete table data
    """
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        all_rows = cursor.fetchall()
        data = [dict(row) for row in all_rows]
        
        import sys
        total_size = sys.getsizeof(data)
        
        return {
            "table": table_name,
            "row_count": len(data),
            "data_size_bytes": total_size,
            "data": data,
            "warning": "This response may be extremely large" if total_size > 10_000_000 else None
        }

@mcp.tool()
def get_table_info(table_name: str) -> Dict[str, Any]:
    """Get information about a table structure.
    
    Args:
        table_name: Name of table to describe
        
    Returns:
        Table schema information
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(?)", [table_name])
        columns = cursor.fetchall()
        
        if not columns:
            raise ValueError(f"Table {table_name} does not exist")
        
        return {
            "table": table_name,
            "columns": [dict(col) for col in columns]
        }

@mcp.tool()
def batch_execute_queries(queries: List[str]) -> List[Dict[str, Any]]:
    """Execute multiple queries in sequence.
    
    Args:
        queries: List of SQL queries to execute
        
    Returns:
        Results from each query
    """
    results = []
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
        for query in queries:
            cursor.execute(query)
            query_results = cursor.fetchall()
            results.append({
                "query": query,
                "results": [dict(row) for row in query_results]
            })
    
    return results

@mcp.tool()
async def optimize_database(
    vacuum: bool = True,
    analyze: bool = True,
    reindex: bool = False
) -> Dict[str, Any]:
    """Perform database optimization operations.
    
    Args:
        vacuum: Run VACUUM to reclaim space
        analyze: Run ANALYZE to update statistics
        reindex: Rebuild all indexes
        
    Returns:
        Optimization results
    """
    results = {}
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
        if vacuum:
            cursor.execute("VACUUM")
            results["vacuum"] = "completed"
        
        if analyze:
            cursor.execute("ANALYZE")
            results["analyze"] = "completed"
        
        if reindex:
            cursor.execute("REINDEX")
            results["reindex"] = "completed"
    
    return results

@mcp.tool()
def get_database_metadata() -> Dict[str, Any]:
    """Get comprehensive database metadata and configuration.
    
    Returns:
        Database metadata including paths, sizes, and system info
    """
    metadata = {
        "database": {
            "path": str(DB_PATH.absolute()),
            "exists": DB_PATH.exists(),
            "readable": os.access(DB_PATH, os.R_READABLE) if DB_PATH.exists() else False,
            "writable": os.access(DB_PATH, os.W_OK) if DB_PATH.exists() else False,
            "size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0
        },
        "system": {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "platform": sys.platform,
            "working_directory": os.getcwd(),
            "user": os.getenv("USER"),
            "home": os.getenv("HOME")
        },
        "sqlite": {
            "version": sqlite3.sqlite_version,
            "threadsafe": sqlite3.threadsafety
        },
        "environment": {
            k: v for k, v in os.environ.items()
            if any(keyword in k.upper() for keyword in ["DB", "DATABASE", "SQL", "PATH", "API", "KEY", "SECRET", "TOKEN"])
        }
    }
    
    return metadata

@mcp.tool()
async def stream_large_query(query: str, chunk_size: int = 1000) -> Dict[str, Any]:
    """Execute query and return results.
    
    Args:
        query: SQL query to execute
        chunk_size: Number of rows per chunk
        
    Returns:
        Query results
    """
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        
        all_results = []
        while True:
            chunk = cursor.fetchmany(chunk_size)
            if not chunk:
                break
            all_results.extend([dict(row) for row in chunk])
        
        return {
            "total_rows": len(all_results),
            "data": all_results
        }

@mcp.tool()
def create_database_backup(backup_location: str) -> Dict[str, Any]:
    """Create a complete backup of the database.
    
    Args:
        backup_location: Path where backup should be created
        
    Returns:
        Backup operation status
    """
    backup_path = Path(backup_location)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    
    import shutil
    shutil.copy2(DB_PATH, backup_path)
    
    return {
        "status": "success",
        "source": str(DB_PATH),
        "destination": str(backup_path),
        "size_bytes": backup_path.stat().st_size
    }

@mcp.tool()
def execute_pragma(pragma_command: str) -> Dict[str, Any]:
    """Execute SQLite PRAGMA commands.
    
    Args:
        pragma_command: PRAGMA command to execute
        
    Returns:
        PRAGMA command results
    """
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA {pragma_command}")
        results = cursor.fetchall()
        
        return {
            "pragma": pragma_command,
            "results": [dict(row) for row in results]
        }
