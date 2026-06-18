"""
数据库连接管理模块

提供 SQLite 数据库连接支持。
统一通过 get_session() 获取数据库会话。
"""

import os
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session


# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 默认数据库配置
_DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "finance_dw.db"


def get_db_path() -> Path:
    """获取数据库文件路径"""
    db_path = os.environ.get("FINANCE_DW_DB_PATH")
    if db_path:
        return Path(db_path)
    return _DEFAULT_DB_PATH


def _ensure_supported_db_type(db_type: str) -> None:
    if db_type != "sqlite":
        raise NotImplementedError("当前版本仅支持 SQLite；PostgreSQL 迁移尚未实现")


def get_database_url(db_type: str = "sqlite") -> str:
    """
    获取数据库连接URL

    Args:
        db_type: 数据库类型，目前仅支持 sqlite

    Returns:
        数据库连接URL字符串
    """
    _ensure_supported_db_type(db_type)
    # SQLite 默认
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


def get_engine(db_type: str = "sqlite") -> Engine:
    """
    获取 SQLAlchemy 引擎

    Args:
        db_type: 数据库类型

    Returns:
        SQLAlchemy Engine 实例
    """
    _ensure_supported_db_type(db_type)
    url = get_database_url(db_type)
    return create_engine(
        url,
        connect_args={"check_same_thread": False},
        echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
    )


def get_session(db_type: str = "sqlite") -> Session:
    """
    获取数据库会话

    Args:
        db_type: 数据库类型

    Returns:
        SQLAlchemy Session 实例
    """
    engine = get_engine(db_type)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def get_connection(db_type: str = "sqlite"):
    """
    获取原始数据库连接（用于执行原生SQL）

    Args:
        db_type: 数据库类型

    Returns:
        数据库连接对象
    """
    _ensure_supported_db_type(db_type)
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_database(db_type: str = "sqlite", sql_file: Optional[Path] = None) -> None:
    """
    初始化数据库：执行建表脚本

    Args:
        db_type: 数据库类型
        sql_file: SQL脚本路径，默认使用 db/init.sql
    """
    _ensure_supported_db_type(db_type)

    if sql_file is None:
        sql_file = PROJECT_ROOT / "db" / "init.sql"

    if not sql_file.exists():
        raise FileNotFoundError(f"SQL脚本文件不存在: {sql_file}")

    conn = get_connection(db_type)
    cursor = conn.cursor()

    with open(sql_file, "r", encoding="utf-8") as f:
        sql_script = f.read()

    # SQLite 不支持多条 GO 语句，按分号分割执行
    statements = sql_script.split(";")
    for stmt in statements:
        stmt = stmt.strip()
        if stmt and not stmt.upper().startswith("SELECT"):
            try:
                cursor.execute(stmt)
            except Exception as e:
                print(f"执行SQL警告: {e}\n语句: {stmt[:100]}...")

    if db_type == "sqlite":
        _apply_sqlite_schema_migrations(cursor)

    conn.commit()
    conn.close()
    print(f"数据库初始化完成: {get_db_path()}")


def _apply_sqlite_schema_migrations(cursor) -> None:
    """Apply lightweight additive migrations for local SQLite databases."""
    revenue_volume_columns = {
        "data_period": "TEXT",
        "business_period": "TEXT",
        "year": "INTEGER",
        "month": "INTEGER",
        "calendar_quarter": "TEXT",
        "source_quarter_label": "TEXT",
        "campus_name": "TEXT",
        "grade": "TEXT",
        "subject": "TEXT",
        "source_file": "TEXT",
        "source_sheet": "TEXT",
    }

    existing = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(revenue_volume)").fetchall()
    }
    for col_name, col_type in revenue_volume_columns.items():
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE revenue_volume ADD COLUMN {col_name} {col_type}")

    nullable_unique_indexes = [
        (
            "idx_account_balance_unique_coalesced",
            "account_balance",
            "company_code, period, account_code, COALESCE(assist_dimensions, '')",
        ),
        (
            "idx_pl_detail_unique_coalesced",
            "pl_detail",
            "company_code, period, item_code, COALESCE(dept_code, '')",
        ),
        (
            "idx_non_subject_allocation_unique_coalesced",
            "non_subject_allocation",
            "company_code, period, cost_center, COALESCE(account_code, '')",
        ),
    ]
    for index_name, table_name, columns in nullable_unique_indexes:
        try:
            cursor.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
                f"ON {table_name} ({columns})"
            )
        except Exception as e:
            print(f"SQLite唯一索引迁移警告: {index_name}: {e}")


def execute_sql(sql: str, params: Optional[dict] = None, db_type: str = "sqlite") -> pd.DataFrame:
    """
    执行SQL查询并返回 DataFrame

    Args:
        sql: SQL查询语句
        params: 查询参数
        db_type: 数据库类型

    Returns:
        查询结果的 DataFrame
    """
    engine = get_engine(db_type)
    with engine.connect() as conn:
        if params:
            result = pd.read_sql(text(sql), conn, params=params)
        else:
            result = pd.read_sql(sql, conn)
    return result


def table_exists(table_name: str, db_type: str = "sqlite") -> bool:
    """
    检查表是否存在

    Args:
        table_name: 表名
        db_type: 数据库类型

    Returns:
        是否存在
    """
    _ensure_supported_db_type(db_type)
    sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
    df = execute_sql(sql, {"name": table_name}, db_type)
    return len(df) > 0
