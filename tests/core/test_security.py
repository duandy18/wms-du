from datetime import UTC, datetime, timedelta

import jwt
import pytest
from passlib.context import CryptContext

# 导入待测试的模块
from app.core.security import (
    JWT_ALG,
    JWT_EXPIRE_MINUTES,
    JWT_SECRET,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)

# Pytest 配置: 忽略已知警告，保持测试输出干净
pytestmark = pytest.mark.filterwarnings(
    "ignore::DeprecationWarning:crypt",  # 忽略 passlib 依赖的标准库 crypt 警告
    "ignore::DeprecationWarning:argon2",  # 忽略 argon2 库版本访问警告
    "ignore::PendingDeprecationWarning",  # 忽略其他 passlib/jwt 可能产生的待定警告
)


# 使用 CryptContext 验证 hash_password 的输出
# 确保密码哈希配置与 app/core/security.py 中的一致
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


class TestSecurity:
    """测试 app/core/security.py 中所有安全相关函数。"""

    def test_hash_and_verify_password(self):
        """测试密码哈希和验证的正确性。"""
        plain_password = "securepassword123"  # pragma: allowlist secret

        # 1. 验证哈希函数是否生成有效的哈希
        hashed_password = hash_password(plain_password)
        assert hashed_password is not None
        assert pwd_context.identify(hashed_password) in ["argon2", "bcrypt"]

        # 2. 验证密码验证是否成功
        assert verify_password(plain_password, hashed_password) is True

        # 3. 验证错误密码是否失败
        assert verify_password("wrongpassword", hashed_password) is False

    def test_jwt_token_creation_and_decoding(self):
        """测试 JWT 令牌的创建、编码和解码。"""
        user_id = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
        username = "testuser"

        # 创建令牌
        token = create_access_token(user_id, extra={"username": username, "is_admin": True})
        assert isinstance(token, str)
        assert len(token) > 0

        # 解码令牌
        payload = decode_token(token)

        # 验证标准字段和额外字段
        assert payload["sub"] == user_id
        assert payload["username"] == username
        assert payload["is_admin"] is True
        assert "exp" in payload
        assert "iat" in payload

    def test_jwt_token_expiration(self):
        """测试 JWT 令牌是否正确设置了过期时间。"""
        user_id = "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

        # 创建令牌
        token = create_access_token(user_id)
        payload = decode_token(token)

        # 验证过期时间是否合理（在未来）
        exp_timestamp = payload["exp"]
        exp_dt = datetime.fromtimestamp(exp_timestamp, tz=UTC)

        now = datetime.now(tz=UTC)
        expected_expiry_time = now + timedelta(minutes=JWT_EXPIRE_MINUTES + 1)  # 加1分钟留出裕量

        # 令牌应该在当前时间之后过期
        assert exp_dt > now

        # 令牌的过期时间应该大致符合配置的分钟数
        assert exp_dt < expected_expiry_time

        # 验证过期后是否无法解码
        # 模拟令牌过期
        expired_payload = {
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int((now - timedelta(minutes=1)).timestamp()),  # 设为过去 1 分钟
        }
        expired_token = jwt.encode(expired_payload, JWT_SECRET, algorithm=JWT_ALG)

        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(expired_token)
