#!/bin/bash

# 激活虚拟环境
source .venv/bin/activate

# 运行 pytest，并显式指定 Python 路径
PYTHONPATH=. pytest tests/services/test_order_service.py

# 取消激活虚拟环境
deactivate
