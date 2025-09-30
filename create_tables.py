# create_tables.py

from app.db import Base, engine

print("正在创建所有数据库表...")


# 导入所有模型，确保它们的元数据被注册
# 这两行是为了确保 SQLAlchemy 知道所有模型

# 创建所有在 Base.metadata 中注册的表
Base.metadata.create_all(bind=engine)

print("所有数据库表创建完成！")
