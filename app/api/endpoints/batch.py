# app/api/endpoints/batch.py


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user

# 导入服务层和依赖
from app.db.deps import get_db

# 导入 Pydantic 模型
from app.schemas.batch import BatchCreate, BatchOut
from app.services.batch_service import BatchService
from app.services.user_service import AuthorizationError, UserService

router = APIRouter()


# 依赖注入函数
def get_batch_service(db: Session = Depends(get_db)):
    return BatchService(db)


def get_user_service(db: Session = Depends(get_db)):
    return UserService(db)


@router.post("/", response_model=BatchOut, status_code=status.HTTP_201_CREATED)
def create_batch(
    batch_in: BatchCreate,
    batch_service: BatchService = Depends(get_batch_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    创建一个新的批次记录。
    """
    try:
        user_service.check_permission(current_user, ["create_batch"])
        return batch_service.create_batch(batch_in.product_id, batch_in.dict())
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你没有执行此操作的权限")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/", response_model=list[BatchOut])
def get_all_batches(
    batch_service: BatchService = Depends(get_batch_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    获取所有批次记录的列表。
    """
    try:
        user_service.check_permission(current_user, ["read_batches"])
        return batch_service.get_all_batches()
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你没有执行此操作的权限")


@router.get("/{batch_id}", response_model=BatchOut)
def get_batch_by_id(
    batch_id: str,
    batch_service: BatchService = Depends(get_batch_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    通过 ID 获取一个批次记录。
    """
    try:
        user_service.check_permission(current_user, ["read_batches"])
        batch = batch_service.get_batch_by_id(batch_id)
        if not batch:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found.")
        return batch
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你没有执行此操作的权限")
