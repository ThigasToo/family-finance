from sqlalchemy.orm import Session

from app.models import MonthlyFinancialSnapshot


def invalidate_all_monthly_snapshots(
    db: Session,
    user_id: int,
) -> int:
    """Remove todos os snapshots mensais derivados de um usuário."""

    return (
        db.query(MonthlyFinancialSnapshot)
        .filter(MonthlyFinancialSnapshot.user_id == user_id)
        .delete(synchronize_session=False)
    )


def invalidate_monthly_snapshot(
    db: Session,
    user_id: int,
    month: str,
) -> int:
    """Remove somente o snapshot mensal informado."""

    return (
        db.query(MonthlyFinancialSnapshot)
        .filter(
            MonthlyFinancialSnapshot.user_id == user_id,
            MonthlyFinancialSnapshot.month == month,
        )
        .delete(synchronize_session=False)
    )
