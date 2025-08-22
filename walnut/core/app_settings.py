from __future__ import annotations

"""
Helpers for storing and retrieving global app settings (e.g., OIDC config).
"""

from typing import Any, Dict, Optional
import logging

from walnut.database.engine import engine, SessionLocal
from walnut.database.models import Base, AppSetting

logger = logging.getLogger(__name__)


def _ensure_table():
    try:
        # Create only our table if not present
        AppSetting.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        logger.warning("Failed to ensure app_settings table: %s", e)


def get_setting(key: str) -> Optional[Dict[str, Any]]:
    _ensure_table()
    session = SessionLocal()
    try:
        row = session.query(AppSetting).filter(AppSetting.key == key).first()
        return row.value if row else None
    finally:
        session.close()


def set_setting(key: str, value: Dict[str, Any]) -> None:
    _ensure_table()
    session = SessionLocal()
    try:
        row = session.query(AppSetting).filter(AppSetting.key == key).first()
        if row is None:
            row = AppSetting(key=key, value=value)
            session.add(row)
        else:
            row.value = value
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

