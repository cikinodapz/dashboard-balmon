from __future__ import annotations

import os
from typing import Optional, Dict, Any


def build_postgres_url(host: str, port: int | str, db: str, user: str, password: str) -> str:
    port = int(port) if port else 5432
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def get_engine_from_params(params: Dict[str, Any]):
    try:
        from sqlalchemy import create_engine
    except Exception as e:
        raise RuntimeError("SQLAlchemy is required. Install with: pip install sqlalchemy psycopg2-binary") from e

    url = build_postgres_url(
        host=params.get("host", "localhost"),
        port=params.get("port", 5432),
        db=params.get("database", "postgres"),
        user=params.get("user", "postgres"),
        password=params.get("password", "18agustuz203")
    )
    return create_engine(url, pool_pre_ping=True)


def write_dataframe(df, table_name: str, engine, if_exists: str = "replace", schema: Optional[str] = None):
    import pandas as pd

    # Ensure datetime columns are proper dtype
    for col in df.columns:
        if isinstance(df[col].dtype, pd.core.dtypes.dtypes.DatetimeTZDtype) or "datetime" in str(df[col].dtype):
            df[col] = pd.to_datetime(df[col], errors="coerce")

    df.to_sql(table_name, engine, schema=schema, if_exists=if_exists, index=False, method=None)

