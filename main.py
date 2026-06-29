"""
企业知识库智能问答系统 — 启动入口

用法:
    python main.py              # 默认 http://localhost:8000
    python main.py --port 9000  # 自定义端口
    python main.py --reload     # 开发模式热重载
"""
import sys
import io

# ═══════════════════════════════════════════════════════════
# 必须放在最前面：禁止生成 .pyc + 清理历史缓存
# ═══════════════════════════════════════════════════════════
sys.dont_write_bytecode = True

import shutil
from pathlib import Path

_project_root = Path(__file__).resolve().parent
_cache_count = 0
for _d in _project_root.rglob("__pycache__"):
    shutil.rmtree(_d, ignore_errors=True)
    _cache_count += 1
for _f in _project_root.rglob("*.pyc"):
    _f.unlink(missing_ok=True)
    _cache_count += 1
if _cache_count:
    print(f"[startup] 已清理 {_cache_count} 个缓存")

# Windows 中文编码修复
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="企业知识库智能问答系统")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    print("=" * 50)
    print("  企业知识库智能问答系统")
    print("  http://%s:%d" % (args.host, args.port))
    print("  API 文档: http://%s:%d/docs" % (args.host, args.port))
    print("=" * 50)

    uvicorn.run(
        "app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
