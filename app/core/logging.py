# app/core/logging.py
import logging
import sys


def setup_logging(level: str = "INFO", json: bool = False) -> None:
    """
    极简统一日志：
    - 根 logger 设级别
    - 单一 stdout handler，避免重复输出
    - 预留 json 开关（暂不实现）
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    # 清已有 handlers，避免重复
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(handler)

    # 静音过于啰嗦的第三方（可按需增减）
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if level.upper() == "DEBUG" else logging.WARNING
    )
