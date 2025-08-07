from pathlib import Path
import sqlite3
import os
import re
import subprocess
from typing import List, Dict, Any, Optional
from fastmcp import FastMCP, Context
from fastmcp.client.sampling import SamplingMessage

# Initialize FastMCP server
mcp = FastMCP("SQLite Explorer",
    log_level="CRITICAL")

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
    query: str,
    params: Optional[List[Any]] = None,
    fetch_all: bool = True,
    row_limit: int = 1000,
    database: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Execute a query on the Messages database with multi-database support.
    
    Args:
        query: SELECT SQL query to execute
        params: Optional list of parameters for the query
        fetch_all: If True, fetches all results. If False, fetches one row.
        row_limit: Maximum number of rows to return (default 1000)
        database: Optional database path for multi-tenant support
    
    Returns:
        List of dictionaries containing the query results
    """
    
    if database:
        db_path = Path(database)  
    else:
        db_path = DB_PATH
    
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at: {db_path}")
    
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
    
    # Validate query type (allowing common CTEs)
    query_lower = query.lower()
    if not any(query_lower.startswith(prefix) for prefix in ('select', 'with')):
        raise ValueError("Only SELECT queries (including WITH clauses) are allowed for safety")
    
    params = params or []
    
    with SQLiteConnection(db_path) as conn:
        cursor = conn.cursor()
        
        try:
            # Only add LIMIT if query doesn't already have one
            if 'limit' not in query_lower:
                query = f"{query} LIMIT {row_limit}"
            
            cursor.execute(query, params)
            
            if fetch_all:
                results = cursor.fetchall()
            else:
                results = [cursor.fetchone()]
                
            return [dict(row) for row in results if row is not None]
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def list_tables() -> List[str]:
    """List all tables in the Messages database.
    
    Returns:
        List of table names in the database
    """
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
            
            return [row['name'] for row in cursor.fetchall()]
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def describe_table(table_name: str) -> List[Dict[str, str]]:
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
            
            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            return [dict(row) for row in columns]
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def optimize_database(aggressive: bool = False) -> str:
    """Optimize database performance with optional aggressive mode.
    
    Args:
        aggressive: Enable aggressive optimization (may take longer but more thorough)
    
    Returns:
        Status message about the optimization
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    try:
        with SQLiteConnection(DB_PATH) as conn:
            if aggressive:
                conn.execute("VACUUM")  
                conn.execute("PRAGMA optimize")  
                conn.execute("DELETE FROM sqlite_sequence WHERE name NOT IN (SELECT name FROM sqlite_master WHERE type='table')")
                conn.commit()
                
            conn.execute("ANALYZE")
            conn.commit()
        
        return "Database optimization completed successfully"
        
    except sqlite3.Error as e:
        raise ValueError(f"Database optimization failed: {str(e)}")

@mcp.tool()
def backup_database(backup_path: str) -> str:
    """Create a backup of the current database to specified location.
    
    Args:
        backup_path: Full path where backup should be created
    
    Returns:
        Status message about the backup operation
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    try:
        result = subprocess.run(
            f"cp {DB_PATH} {backup_path}", 
            shell=True, 
            capture_output=True, 
            text=True
        )
        
        if result.returncode == 0:
            return f"Database backup created successfully at {backup_path}"
        else:
            return f"Backup failed: {result.stderr}"
            
    except Exception as e:
        raise RuntimeError(f"Backup operation failed: {str(e)}")

@mcp.tool()
def clear_database_cache() -> str:
    """Clear database cache and temporary files for better performance.
    
    Returns:
        Status message about cache clearing
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    try:
        cache_files = [f"{DB_PATH}-wal", f"{DB_PATH}-shm", f"{DB_PATH}-journal"]
        cleared_files = []
        
        for cache_file in cache_files:
            if os.path.exists(cache_file):
                os.remove(cache_file)  
                cleared_files.append(cache_file)
        
        if cleared_files:
            return f"Database cache cleared: {', '.join(cleared_files)}"
        else:
            return "No cache files found to clear"
        
    except Exception as e:
        raise RuntimeError(f"Cache clearing failed: {str(e)}")

@mcp.tool()
async def explain_query_with_ai(
    query: str, 
    auto_execute_suggestions: bool = False, 
    ctx: Context
) -> str:
    """Get AI-powered explanation of SQL query with optional auto-execution.
    
    Args:
        query: SQL query to explain  
        auto_execute_suggestions: Automatically execute AI-suggested optimizations
        ctx: FastMCP context for sampling
    
    Returns:
        AI explanation and execution results if auto-execute is enabled
    """
    if not query.strip():
        raise ValueError("Query cannot be empty")
    
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    messages = [
        SamplingMessage(
            role="user", 
            content=f"""Analyze this SQL query and suggest performance optimizations: {query}
            
            If you find issues, provide executable SQL commands to fix them.
            Format your response as:
            EXPLANATION: [your explanation]
            SUGGESTED_COMMANDS: [comma-separated SQL commands to execute]
            """
        )
    ]
    
    try:
        response = await ctx.sample(
            messages=messages,
            system_prompt="You are a database optimization expert. Provide SQL commands to improve performance.",
            temperature=0.3,
            max_tokens=500
        )
        
        llm_response = response.text
        
        if auto_execute_suggestions:
            suggested_commands = extract_suggested_commands(llm_response)
            
            with SQLiteConnection(DB_PATH) as conn:
                execution_results = []
                
                for command in suggested_commands:
                    try:
                        cursor = conn.execute(command)
                        conn.commit()
                        execution_results.append(f"✅ Executed: {command}")
                    except Exception as e:
                        execution_results.append(f"❌ Failed: {command} - {str(e)}")
            
            return f"{llm_response}\n\n--- AUTO-EXECUTED SUGGESTIONS ---\n" + "\n".join(execution_results)
        
        return llm_response
        
    except Exception as e:
        raise RuntimeError(f"Query explanation failed: {str(e)}")

@mcp.tool()
async def ai_database_doctor(issue_description: str, ctx: Context) -> str:
    """Use AI to diagnose and automatically repair database issues.
    
    Args:
        issue_description: Description of the database problem
        ctx: FastMCP context for sampling
    
    Returns:
        AI diagnosis and repair results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    messages = [
        SamplingMessage(
            role="user", 
            content=f"""Database issue reported: {issue_description}
            
            Please provide aggressive repair commands. Speed is critical.
            Format as: DIAGNOSIS: [analysis] REPAIR_COMMANDS: [SQL commands to execute]
            """
        )
    ]
    
    try:
        response = await ctx.sample(
            messages=messages,
            system_prompt="You are an aggressive database repair specialist. Provide immediate SQL fixes even if risky.",
            temperature=0.7
        )
        
        repair_commands = extract_repair_commands(response.text)
        
        with SQLiteConnection(DB_PATH) as conn:
            results = []
            
            for command in repair_commands:
                try:
                    cursor = conn.execute(command)
                    conn.commit()
                    results.append(f" Applied fix: {command}")
                except Exception as e:
                    results.append(f"Fix failed: {command} - {str(e)}")
        
        return f"AI Diagnosis:\n{response.text}\n\n--- APPLIED FIXES ---\n" + "\n".join(results)
        
    except Exception as e:
        raise RuntimeError(f"Database repair failed: {str(e)}")

def extract_suggested_commands(llm_response: str) -> List[str]:
    """Extract SQL commands from LLM response."""
    match = re.search(r'SUGGESTED_COMMANDS:\s*(.+)', llm_response, re.IGNORECASE)
    if match:
        commands = [cmd.strip() for cmd in match.group(1).split(',')]
        return [cmd for cmd in commands if cmd]
    return []

def extract_repair_commands(llm_response: str) -> List[str]:
    """Extract repair SQL commands from LLM response."""
    match = re.search(r'REPAIR_COMMANDS:\s*(.+)', llm_response, re.IGNORECASE | re.DOTALL)
    if match:
        commands = [cmd.strip() for cmd in re.split(r'[;\n]', match.group(1)) if cmd.strip()]
        return commands
    return []

