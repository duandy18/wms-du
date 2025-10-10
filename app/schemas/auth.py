from pydantic import BaseModel, EmailStr, field_validator

# 常量：用于解决 PLR2004 (Magic number) 警告
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 32


class RegisterIn(BaseModel):
    """用户注册时提供的输入数据模型。"""

    username: str
    email: EmailStr
    password: str

    @field_validator("username", mode="before")
    @classmethod
    def username_trim(cls, v: str) -> str:
        """确保用户名字段在处理前被清理和验证长度。"""
        v = v.strip()
        if not (MIN_USERNAME_LENGTH <= len(v) <= MAX_USERNAME_LENGTH):
            raise ValueError(f"username length must be {MIN_USERNAME_LENGTH}-{MAX_USERNAME_LENGTH}")
        return v


class LoginIn(BaseModel):
    """用户登录时提供的输入数据模型。"""

    username: str | None = None
    email: EmailStr | None = None
    password: str

    @field_validator("username", mode="before")
    @classmethod
    def username_trim(cls, v: str | None) -> str | None:
        """清除用户名字段的空白字符。"""
        if v is None:
            return None
        return v.strip()

    @field_validator("username", mode="after")
    @classmethod
    def require_username_or_email(cls, v: str | None, info) -> str | None:
        """验证用户名和邮箱至少有一个被提供。"""
        email = info.data.get("email")
        if v is None and email is None:
            raise ValueError("Must provide either username or email.")
        return v


class TokenOut(BaseModel):
    """JWT 令牌的输出模型。"""

    access_token: str
    token_type: str


class TokenData(BaseModel):
    """存储在 JWT 内部的数据模型。"""

    sub: str | None = None  # sub 字段通常存储用户 ID
    username: str | None = None
    is_admin: bool | None = False
