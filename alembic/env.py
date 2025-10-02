import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# 导入你的应用模型 (注意：这行必须在顶部)
from app.db import Base

# 将你的项目根目录添加到 Python 路径，确保可以导入 app 模块
sys.path.insert(0, ".")
sys.path.insert(0, "..")


# Alembic Config
config = context.config

# 如果你的 alembic.ini 中有 logger 配置，可以加载
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 这里是你的数据库连接 URL，从环境变量中获取
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))

# 你的所有模型都注册在 Base.metadata 中
target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
