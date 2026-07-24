import sqlite3
import datetime
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Tuple, Generator
from utils import to_bangla_number
from ledger_logic import status_bn

DEFAULT_DB_PATH = "voice_khata.db"

# ==============================================================================
# 1. DATABASE INITIALIZATION & CONNECTION MANAGERS
# ==============================================================================

@contextmanager
def get_connection(db_path: str = DEFAULT_DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """Context manager supplying a thread-safe SQLite connection with Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize SQLite database schema for entries, sales_transactions, and sale_items tables."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                item TEXT,
                quantity TEXT,
                total_amount_taka REAL,
                paid_amount_taka REAL,
                due_amount_taka REAL NOT NULL,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sales_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT,
                total_amount_taka REAL NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER NOT NULL REFERENCES sales_transactions(id),
                item TEXT NOT NULL,
                quantity TEXT,
                unit_price_taka REAL
            )
        """)
        conn.commit()


# ==============================================================================
# 2. CREDIT LEDGER ENTRIES TABLE (Digital Ledger)
# ==============================================================================

def get_entry(entry_id: int, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Fetch single credit ledger entry by integer ID, appending computed status_bn."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        if row:
            d = dict(row)
            d["status_bn"] = status_bn(d.get("due_amount_taka"))
            return d
        return None


def clean_bangla_name(name: str) -> str:
    """Utility stripping common Bangla grammatical suffixes (কে, এর, রে) for name matching."""
    if not name:
        return ""
    n = name.strip().lower()
    for suffix in ["কে", "এর", "রে"]:
        if n.endswith(suffix) and len(n) > len(suffix) + 1:
            n = n[:-len(suffix)].strip()
    return n


def get_open_entries_by_name(customer_name: str, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """
    Fallback lookup for open entries (due_amount_taka > 0) matching customer name
    used when Gemma 4's matched_entry_id is missing or unverified.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM entries WHERE due_amount_taka > 0 ORDER BY id DESC")
        rows = cursor.fetchall()
        result = []
        target = customer_name.strip()
        clean_target = clean_bangla_name(target)

        for r in rows:
            d = dict(r)
            c_name = d["customer_name"].strip()
            clean_c = clean_bangla_name(c_name)

            if (target.lower() == c_name.lower() or 
                clean_target == clean_c or 
                (len(clean_target) > 1 and clean_target in clean_c) or 
                (len(clean_c) > 1 and clean_c in clean_target)):
                d["status_bn"] = status_bn(d.get("due_amount_taka"))
                result.append(d)
        return result


def get_open_entries(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve all active open credit entries (due_amount_taka > 0) for extraction context."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM entries WHERE due_amount_taka > 0 ORDER BY id DESC")
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["status_bn"] = status_bn(d.get("due_amount_taka"))
            result.append(d)
        return result


def get_all_entries(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Get all entries in credit ledger ordered by ID DESC with status_bn."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM entries ORDER BY id DESC")
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["status_bn"] = status_bn(d.get("due_amount_taka"))
            result.append(d)
        return result


def update_entry_fields(entry_id: int, data: Dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Directly update fields of an entry in SQLite database via manual modal or review edit."""
    now = datetime.datetime.now().isoformat()
    total = data.get("total_amount_taka")
    paid = data.get("paid_amount_taka")
    
    if data.get("due_amount_taka") is not None:
        due = float(data.get("due_amount_taka"))
    elif total is not None and paid is not None:
        due = float(total) - float(paid)
    else:
        due = 0.0

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE entries
            SET customer_name = ?, item = ?, quantity = ?, total_amount_taka = ?, paid_amount_taka = ?, due_amount_taka = ?, updated_at = ?
            WHERE id = ?
        """, (
            data.get("customer_name"),
            data.get("item"),
            data.get("quantity"),
            total,
            paid,
            due,
            now,
            entry_id
        ))
        conn.commit()
    return get_entry(entry_id, db_path)


def delete_entry(entry_id: int, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Delete a credit ledger entry by ID."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        conn.commit()
        return cursor.rowcount > 0


def execute_operation(op: Dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Execute single insert or update operation dictionary returned by compute_ledger_update."""
    now = datetime.datetime.now().isoformat()
    action_op = op.get("op")

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if action_op == "insert":
            cursor.execute("""
                INSERT INTO entries (customer_name, item, quantity, total_amount_taka, paid_amount_taka, due_amount_taka, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                op.get("customer_name"),
                op.get("item"),
                op.get("quantity"),
                op.get("total_amount_taka"),
                op.get("paid_amount_taka"),
                op.get("due_amount_taka"),
                now,
                now
            ))
            conn.commit()
            record_id = cursor.lastrowid
        elif action_op == "update":
            record_id = op["id"]
            cursor.execute("""
                UPDATE entries
                SET item = COALESCE(?, item),
                    quantity = COALESCE(?, quantity),
                    total_amount_taka = ?,
                    paid_amount_taka = ?,
                    due_amount_taka = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                op.get("item"),
                op.get("quantity"),
                op.get("total_amount_taka"),
                op.get("paid_amount_taka"),
                op.get("due_amount_taka"),
                now,
                record_id
            ))
            conn.commit()
        else:
            raise ValueError(f"Unknown operation type: {action_op}")

    return get_entry(record_id, db_path)


def save_ledger_entry(entry_schema: Dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Save confirmed ledger entry via compute_ledger_update, returning updated entry and list of open entries."""
    from ledger_logic import compute_ledger_update
    updates = compute_ledger_update(entry_schema, db_path=db_path)
    
    if isinstance(updates, list):
        saved_records = [execute_operation(u, db_path) for u in updates]
        saved_entry = saved_records[-1] if saved_records else None
        return saved_entry, get_open_entries(db_path)
    else:
        saved_entry = execute_operation(updates, db_path)
        return saved_entry, get_open_entries(db_path)


# ==============================================================================
# 3. SALES TRANSACTIONS & SALE ITEMS TABLES (Daily Sales Log)
# ==============================================================================

def save_sales_transaction(data: Dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Insert 1 row into sales_transactions and 1 row per item into sale_items."""
    now = datetime.datetime.now().isoformat()
    customer_name = data.get("customer_name")
    total_amount_taka = float(data.get("total_amount_taka") or 0.0)
    items = data.get("items") or []

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sales_transactions (customer_name, total_amount_taka, created_at)
            VALUES (?, ?, ?)
        """, (customer_name, total_amount_taka, now))
        transaction_id = cursor.lastrowid

        for item_info in items:
            cursor.execute("""
                INSERT INTO sale_items (transaction_id, item, quantity, unit_price_taka)
                VALUES (?, ?, ?, ?)
            """, (
                transaction_id,
                item_info.get("item"),
                item_info.get("quantity"),
                item_info.get("unit_price_taka")
            ))
        conn.commit()

    return get_today_sales(db_path)


def get_today_sales(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Returns all of today's sales transactions with item lists and today's total sum."""
    today_str = datetime.date.today().isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM sales_transactions 
            WHERE date(created_at) = ? OR substr(created_at, 1, 10) = ?
            ORDER BY id DESC
        """, (today_str, today_str))
        tx_rows = cursor.fetchall()

        transactions = []
        running_total = 0.0

        for r in tx_rows:
            tx = dict(r)
            running_total += tx.get("total_amount_taka", 0.0)
            cursor.execute("SELECT * FROM sale_items WHERE transaction_id = ? ORDER BY id ASC", (tx["id"],))
            item_rows = cursor.fetchall()
            tx["items"] = [dict(item_r) for item_r in item_rows]
            transactions.append(tx)

        return {
            "transactions": transactions,
            "today_total_taka": running_total
        }


def resolve_date_range(range_param: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Tuple[str, str]:
    """Resolves range_param string ('today', '7days', '30days', '90days', 'all', 'custom') to ISO (start_date, end_date)."""
    today = datetime.date.today()
    if range_param == "today":
        d = today.isoformat()
        return d, d
    if range_param == "7days":
        return (today - datetime.timedelta(days=6)).isoformat(), today.isoformat()
    if range_param == "30days":
        return (today - datetime.timedelta(days=29)).isoformat(), today.isoformat()
    if range_param == "90days":
        return (today - datetime.timedelta(days=89)).isoformat(), today.isoformat()
    if range_param == "all":
        return "0001-01-01", today.isoformat()
    if range_param == "custom":
        if not start_date or not end_date:
            raise ValueError("start_date and end_date are required for custom range")
        return start_date, end_date
    raise ValueError("invalid range")


def get_sales_history(range_param: str = "30days", start_date: Optional[str] = None, end_date: Optional[str] = None, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Queries sales transactions in date range resolved by resolve_date_range with attached items."""
    start_d, end_d = resolve_date_range(range_param, start_date, end_date)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM sales_transactions 
            WHERE date(created_at) BETWEEN ? AND ? 
            ORDER BY created_at DESC, id DESC
        """, (start_d, end_d))
        tx_rows = cursor.fetchall()

        transactions = []
        total_amount = 0.0

        for r in tx_rows:
            tx = dict(r)
            total_amount += tx.get("total_amount_taka", 0.0)

            cursor.execute("SELECT * FROM sale_items WHERE transaction_id = ? ORDER BY id ASC", (tx["id"],))
            item_rows = cursor.fetchall()
            tx["items"] = [dict(item_r) for item_r in item_rows]
            transactions.append(tx)

        return {
            "transactions": transactions,
            "summary": {
                "total_amount_taka": total_amount,
                "transaction_count": len(transactions),
                "start_date": start_d,
                "end_date": end_d
            }
        }


# ==============================================================================
# 4. DOMAIN Q&A & BUSINESS SUMMARY CONTEXT AGGREGATORS
# ==============================================================================

def build_ledger_data_context(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Builds DATA_CONTEXT for Digital Ledger Q&A (/ledger/ask) from ALL entries."""
    all_entries = get_all_entries(db_path)
    return {
        "current_date": datetime.date.today().isoformat(),
        "customers": [
            {
                "customer_name": e["customer_name"],
                "total_amount_taka": e.get("total_amount_taka"),
                "paid_amount_taka": e.get("paid_amount_taka"),
                "due_amount_taka": e.get("due_amount_taka")
            }
            for e in all_entries
        ]
    }


def get_today_item_occurrences(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Returns list of items sold today: [{"item": "...", "quantity": "..."}]."""
    today_str = datetime.date.today().isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.item, i.quantity
            FROM sale_items i
            JOIN sales_transactions t ON i.transaction_id = t.id
            WHERE date(t.created_at) = ? OR substr(t.created_at, 1, 10) = ?
            ORDER BY i.id ASC
        """, (today_str, today_str))
        rows = cursor.fetchall()
        return [{"item": r["item"], "quantity": r["quantity"]} for r in rows]


def get_daily_totals_last_30_days(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Returns list of aggregated daily totals for last 30 days: [{"date": "YYYY-MM-DD", "total_amount_taka": float}]."""
    today = datetime.date.today()
    thirty_days_ago = (today - datetime.timedelta(days=29)).isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date(created_at) as d, SUM(total_amount_taka) as total_amount_taka
            FROM sales_transactions
            WHERE date(created_at) >= ?
            GROUP BY d
            ORDER BY d ASC
        """, (thirty_days_ago,))
        rows = cursor.fetchall()
        return [{"date": r["d"], "total_amount_taka": float(r["total_amount_taka"] or 0.0)} for r in rows]


def build_sales_data_context(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Builds DATA_CONTEXT for Nagad Bikri Log Q&A (/sales/ask)."""
    today_str = datetime.date.today().isoformat()
    today_items = get_today_item_occurrences(db_path)
    today_total = get_today_sales(db_path)["today_total_taka"]
    daily_totals = get_daily_totals_last_30_days(db_path)

    return {
        "current_date": today_str,
        "today_items_sold": today_items,
        "today_total_taka": today_total,
        "daily_totals_last_30_days": daily_totals
    }


def sum_sales_transactions_in_range(start_date: str, end_date: str, db_path: str = DEFAULT_DB_PATH) -> float:
    """Sum total cash sales in specified date range."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(SUM(total_amount_taka), 0.0) as total
            FROM sales_transactions
            WHERE date(created_at) BETWEEN ? AND ?
        """, (start_date, end_date))
        row = cursor.fetchone()
        return float(row["total"] if row and row["total"] is not None else 0.0)


def sum_entries_total_created_in_range(start_date: str, end_date: str, db_path: str = DEFAULT_DB_PATH) -> float:
    """Sum total credit sales issued in specified date range."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(SUM(total_amount_taka), 0.0) as total
            FROM entries
            WHERE date(created_at) BETWEEN ? AND ?
        """, (start_date, end_date))
        row = cursor.fetchone()
        return float(row["total"] if row and row["total"] is not None else 0.0)


def sum_all_open_dues(db_path: str = DEFAULT_DB_PATH) -> float:
    """Snapshot total of all current uncollected dues (due_amount_taka > 0)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(SUM(due_amount_taka), 0.0) as total
            FROM entries
            WHERE due_amount_taka > 0
        """)
        row = cursor.fetchone()
        return float(row["total"] if row and row["total"] is not None else 0.0)


def count_unique_customers_in_range(start_date: str, end_date: str, db_path: str = DEFAULT_DB_PATH) -> int:
    """Count unique customer names across sales_transactions and entries in date range."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(DISTINCT customer_name) as count_unique FROM (
                SELECT customer_name FROM sales_transactions
                WHERE date(created_at) BETWEEN ? AND ? AND customer_name IS NOT NULL AND TRIM(customer_name) != ''
                UNION
                SELECT customer_name FROM entries
                WHERE date(created_at) BETWEEN ? AND ? AND customer_name IS NOT NULL AND TRIM(customer_name) != ''
            )
        """, (start_date, end_date, start_date, end_date))
        row = cursor.fetchone()
        return int(row["count_unique"] if row and row["count_unique"] is not None else 0)


def count_distinct_active_days_in_range(start_date: str, end_date: str, db_path: str = DEFAULT_DB_PATH) -> int:
    """Count distinct active business days in specified date range."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(DISTINCT d) as active_days FROM (
                SELECT date(created_at) as d FROM sales_transactions
                WHERE date(created_at) BETWEEN ? AND ?
                UNION
                SELECT date(created_at) as d FROM entries
                WHERE date(created_at) BETWEEN ? AND ?
            )
        """, (start_date, end_date, start_date, end_date))
        row = cursor.fetchone()
        return int(row["active_days"] if row and row["active_days"] is not None else 0)


def get_activity_logs_in_range(start_date: str, end_date: str, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve detailed combined activity log entries (cash transactions & credit entries) ordered DESC."""
    logs = []
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, customer_name, total_amount_taka, created_at
            FROM sales_transactions
            WHERE date(created_at) BETWEEN ? AND ?
            ORDER BY created_at DESC
        """, (start_date, end_date))
        sales_rows = cursor.fetchall()
        for r in sales_rows:
            logs.append({
                "date": r["created_at"][:10],
                "type": "নগদ বিক্রয়",
                "customer_name": r["customer_name"] or "সাধারণ খরিদ্দার",
                "total_amount_taka": float(r["total_amount_taka"]),
                "details": f"মোট নগদ বিক্রি {r['total_amount_taka']} ৳"
            })

        cursor.execute("""
            SELECT id, customer_name, item, quantity, total_amount_taka, paid_amount_taka, due_amount_taka, created_at
            FROM entries
            WHERE date(created_at) BETWEEN ? AND ?
            ORDER BY created_at DESC
        """, (start_date, end_date))
        entry_rows = cursor.fetchall()
        for r in entry_rows:
            item_desc = f"{r['item']} ({r['quantity']})" if r['item'] and r['quantity'] else (r['item'] or "বাকি কেনাকাটা")
            logs.append({
                "date": r["created_at"][:10],
                "type": "বাকি হিসাব",
                "customer_name": r["customer_name"] or "সাধারণ খরিদ্দার",
                "total_amount_taka": float(r["total_amount_taka"] or 0.0),
                "details": f"{item_desc} - মোট: {r['total_amount_taka']} ৳ (জমা: {r['paid_amount_taka']} ৳, বাকি: {r['due_amount_taka']} ৳)"
            })

    logs.sort(key=lambda x: x["date"], reverse=True)
    return logs


def build_business_summary_context(start_date: str, end_date: str, period_label: str, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Build aggregated metrics and activity logs context dictionary for Business Summary."""
    cash_sales_total = sum_sales_transactions_in_range(start_date, end_date, db_path=db_path)
    credit_sales_total = sum_entries_total_created_in_range(start_date, end_date, db_path=db_path)
    current_total_due = sum_all_open_dues(db_path=db_path)
    unique_customers = count_unique_customers_in_range(start_date, end_date, db_path=db_path)
    active_days = count_distinct_active_days_in_range(start_date, end_date, db_path=db_path)
    activity_logs = get_activity_logs_in_range(start_date, end_date, db_path=db_path)

    return {
        "period_label": period_label,
        "total_cash_sales_taka": cash_sales_total,
        "total_credit_sales_issued_taka": credit_sales_total,
        "current_total_due_taka": current_total_due,
        "unique_customers_served": unique_customers,
        "active_business_days": active_days,
        "activity_logs": activity_logs
    }
