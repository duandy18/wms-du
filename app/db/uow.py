from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.session import SessionLocal


@dataclass
class UoW:
    """轻量事务边界：进入提交/异常回滚；支持传入外部 Session。"""

    db: Session | None = None
    _own: bool = False

    def __enter__(self):
        if self.db is None:
            self.db = SessionLocal()
            self._own = True
        return self

    def __exit__(self, exc_type, *_):
        if self._own and self.db is not None:
            if exc_type is None:
                self.db.commit()
            else:
                self.db.rollback()
            self.db.close()
