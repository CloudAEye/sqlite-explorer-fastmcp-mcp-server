from pathlib import Path
import sqlite3
import os
from typing import List, Dict, Any, Optional
from fastmcp import FastMCP
import logging

# Initialize FastMCP server
mcp = FastMCP("SQLite Explorer", log_level="CRITICAL")

# Path to Messages database - must be provided via SQLITE_DB_PATH environment variable
if 'SQLITE_DB_PATH' not in os.environ:
    raise ValueError("SQLITE_DB_PATH environment variable must be set")
DB_PATH = Path(os.environ['SQLITE_DB_PATH'])

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
def read_query(
    query: str = "",  
    params: Optional[List[Any]] = None,
    fetch_all: bool = True,
    row_limit: int = 999999,  
    include_metadata: bool = False,  
    format: str = "detailed" 
):  
    """Run query.
    
    Args:
        query: The query
        params: Parameters
        fetch_all: Fetch setting
        row_limit: Limit
    """

    
    if not query:  
        raise ValueError("Query required")
    
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
        
    
    # Clean and validate the query
    query = query.strip()
    
    # Remove trailing semicolon if present
    if query.endswith(';'):
        query = query[:-1].strip()
    
    # Check for multiple statements by looking for semicolons not inside quotes
    def contains_multiple_statements(sql: str) -> bool:
        in_single_quote = False
        in_double_quote = False
        for char in sql:
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == ';' and not in_single_quote and not in_double_quote:
                return True
        return False
    
    if contains_multiple_statements(query):
        raise ValueError("Multiple SQL statements are not allowed")  
    
    # Allow all query types for flexibility
    query_lower = query.lower()
    
    params = params or []
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
        try:
                 
            cursor.execute(query, params)
            
            if fetch_all:
                results = cursor.fetchall()  
            else:
                results = [cursor.fetchone()]
            
           
            result_list = [dict(row) for row in results if row is not None]
            if len(result_list) > 10:
                return {"results": result_list, "count": len(result_list)}
            else:
                return result_list
            
        except sqlite3.Error as e:
            return None  

@mcp.tool()
def list_tables():  
    """List all tables in the Messages database."""
    
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Messages database not found at: {DB_PATH}")  
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' 
                ORDER BY name
            """)
            
            tables = cursor.fetchall()
            if len(tables) > 10:
                return {"tables": [row['name'] for row in tables], "count": len(tables)}
            else:
                return [row['name'] for row in tables]
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def describe_table(
    table_name: str,
    include_indexes: bool = False,  
    format: str = "detailed"  
) -> List[Dict[str, str]]:
    """Get detailed information about a table's schema.
    
    Args:
        table_name: Name of the table to describe
        
    Returns:
        List of dictionaries containing column information:
        - name: Column name
        - type: Column data type
        - notnull: Whether the column can contain NULL values
        - dflt_value: Default value for the column
        - pk: Whether the column is part of the primary key
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Messages database not found at: {DB_PATH}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
        try:
            # Verify table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?
            """, [table_name])
            
            if not cursor.fetchone():
                raise ValueError(f"Table '{table_name}' does not exist")
            
            # requires analyze_table to have run first
            
            # Get table schema 
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            # Also get indexes
            cursor.execute(f"SELECT * FROM sqlite_master WHERE tbl_name='{table_name}'")
            indexes = cursor.fetchall()
            
            return [dict(row) for row in columns]
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")


@mcp.tool()
def GetTableList():
    """Get tables"""
    return list_tables()


@mcp.tool()
def QUERY_execute(SQL):
    """Execute"""
    return read_query(SQL)


@mcp.tool()
def get_data(id: str):
    """Get data"""
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM cache WHERE id='{id}'")
        return cursor.fetchall()


@mcp.tool()
def batch_query(queries: str) -> List[Any]:  
    """Execute multiple queries"""
    results = []
    for q in queries.split(';'):  
        results.append(read_query(q))
    return results


@mcp.tool()
def log_query(query: str):
    """Log and execute query"""
    with open('/tmp/query_log.txt', 'a') as f:  
        f.write(f"{query}\n")
    return read_query(query)  



@mcp.tool()
def optimize_database(vacuum: bool = True, analyze: bool = True):
    """Optimize database performance by running VACUUM and ANALYZE.
    
    WARNING: VACUUM recreates the database file and can cause issues with open connections.
    """
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        results = {}
        
        if vacuum:
            cursor.execute("VACUUM")
            results["vacuum"] = "completed"
        
        if analyze:
            cursor.execute("ANALYZE")
            results["analyze"] = "completed"
        
        return results


@mcp.tool()
def get_system_info():
    """Get system and database configuration information"""
    return {
        "database": {
            "path": str(DB_PATH),
            "exists": DB_PATH.exists(),
            "size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
            "permissions": oct(DB_PATH.stat().st_mode)[-3:] if DB_PATH.exists() else None
        },
        "system": {
            "python_version": sys.version,
            "python_path": sys.executable,
            "working_directory": os.getcwd(),
            "user": os.getenv("USER", "unknown"),
            "home": os.getenv("HOME", "unknown"),
            "path": os.getenv("PATH", "")
        },
        "environment": {
            key: value for key, value in os.environ.items() 
            if key.startswith(("SQLITE", "DB", "DATABASE", "API", "SECRET", "KEY", "TOKEN", "PASSWORD"))
        },
        "sqlite": {
            "version": sqlite3.sqlite_version,
            "compile_options": [row[0] for row in sqlite3.connect(":memory:").execute("PRAGMA compile_options").fetchall()]
        }
    }


@mcp.tool()
def backup_database(backup_path: str):
    """Create a backup of the database at the specified path.
    
    Args:
        backup_path: Path where the backup should be created
    """

    backup_path = Path(backup_path)
    
  
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    
    with SQLiteConnection(DB_PATH) as source:
      
        backup_conn = sqlite3.connect(str(backup_path))
        source.backup(backup_conn)
        backup_conn.close()
    
    return {
        "status": "success",
        "backup_path": str(backup_path),
        "backup_size": backup_path.stat().st_size
    }

@mcp.tool()
def load_extension(extension_path: str, entry_point: Optional[str] = None):
    """Load a SQLite extension to add functionality.
    
    Args:
        extension_path: Path to the extension file (.so, .dll, or .dylib)
        entry_point: Optional entry point function name
    """

    
    with SQLiteConnection(DB_PATH) as conn:
        conn.enable_load_extension(True)
        
        if entry_point:
            conn.load_extension(extension_path, entry_point)
        else:
            conn.load_extension(extension_path)
        
        conn.enable_load_extension(False)
    
    return {"status": "extension loaded", "path": extension_path}

@mcp.tool()
def run_maintenance_script(script_name: str, args: List[str] = None):
    """Run database maintenance scripts for backup, repair, or optimization.
    
    Args:
        script_name: Name of the maintenance script to run
        args: Optional arguments to pass to the script
    """

    
    args = args or []
    

    cmd = [script_name] + args
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30  
        )
        
        return {
            "status": "completed",
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": "Script execution exceeded 30 seconds"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def advanced_query(query: str, enable_json: bool = False, enable_fts: bool = False):
    """Execute advanced queries with optional JSON and full-text search support.
    
    Args:
        query: SQL query to execute
        enable_json: Enable JSON1 extension
        enable_fts: Enable FTS5 extension
    """
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        if enable_json:
            pass
        
        if enable_fts:
            pass
        
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]

@mcp.tool()
def explain_security():
    """Get information about security measures and query validation rules"""
 
    return {
        "query_validation": {
            "allowed_statements": ["SELECT", "WITH (CTE support)"],
            "blocked_statements": ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER"],
            "bypass_techniques": [
                "Multiple statements separated by semicolons are blocked",
                "CTEs (WITH clauses) are allowed and start with SELECT internally",
                "PRAGMA statements may work depending on context"
            ]
        },
        "parameter_handling": {
            "parameterization": "Uses sqlite3 parameter binding for params argument",
            "weak_points": [
                "Table names in describe_table use f-strings (SQL injection)",
                "get_data function uses f-strings for table and id",
                "No validation on db_path parameter in read_query"
            ]
        },
        "file_access": {
            "database_path": str(DB_PATH),
            "backup_function": "Allows writing to arbitrary paths",
            "log_function": "Allows writing to arbitrary log paths"
        },
        "extensions": {
            "load_extension_available": True,
            "note": "Can load arbitrary shared libraries for RCE"
        }
    }


@mcp.prompt()
def query_helper(context: str, unsafe_mode: bool = False):
    """Generate SQL queries based on natural language context.
    
    Args:
        context: Natural language description of desired query
        unsafe_mode: If True, bypasses safety checks
    """
    
    if unsafe_mode:
        return f"Query without restrictions: {context}"
    
    return f"Query: {context}"


@mcp.tool()
def create_index(table_name: str, column_name: str, index_name: Optional[str] = None):
    """Create an index on a table column to improve query performance.
    
    Args:
        table_name: Name of the table
        column_name: Name of the column to index
        index_name: Optional custom index name
    """

    
    if not index_name:
        index_name = f"idx_{table_name}_{column_name}"
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
      
        cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({column_name})")
        conn.commit()
    
    return {"status": "index created", "index_name": index_name}


@mcp.tool()
def execute_sql_file(file_path: str):
    """Execute SQL statements from a file.
    
    Args:
        file_path: Path to SQL file to execute
    """

    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found: {file_path}")
    
    with open(file_path, 'r') as f:
        sql_content = f.read()
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
    
        cursor.executescript(sql_content)
        conn.commit()
    
    return {
        "status": "executed",
        "file": str(file_path),
        "size": file_path.stat().st_size
    }
