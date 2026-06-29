"""
数据库初始化脚本 — 创建库和表

用法:
    python init_db.py
"""
import pymysql
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE

# 1. 创建数据库（如果不存在）
conn = pymysql.connect(
    host=MYSQL_HOST, port=MYSQL_PORT,
    user=MYSQL_USER, password=MYSQL_PASSWORD
)
conn.cursor().execute(
    f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
)
conn.close()
print(f"[OK] 数据库 {MYSQL_DATABASE} 已就绪")

# 2. 创建表
from models.db_models import init_db
init_db()
print("[OK] 所有表已就绪")
