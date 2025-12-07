#!/usr/bin/env python3
"""
列出当前 FastAPI 应用中注册的所有路由。
在项目根目录执行：  python scripts/list_routes.py
"""

try:
    # 导入你的 FastAPI 实例
    from app.main import app
except Exception as e:
    print("❌ 无法导入 app.main.app，请确认 FastAPI 主程序位置。")
    print("错误信息：", e)
    raise SystemExit(1)

print("✅ FastAPI 路由列表 (path, methods, name):\n")

# 遍历所有 routes
for r in app.routes:
    try:
        methods = ",".join(sorted(r.methods))
        print(f"{methods:<10}  {r.path:<40}  →  {r.name}")
    except Exception:
        pass

print("\n🔍 可重点查找以下关键字：scan / receive / putaway / commit\n")
