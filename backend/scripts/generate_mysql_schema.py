"""从 SQLAlchemy 模型生成 MySQL 初始化建表 SQL（含删表语句）。

用法：
    cd backend
    python scripts/generate_mysql_schema.py

输出：backend/scripts/init_mysql_schema.sql
后续修改 app/models.py 后重新运行本脚本即可同步 SQL 文件，
保证 SQL 与 ORM 实体定义始终一致。
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.dialects import mysql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable, DropTable  # noqa: E402

from app.db import Base  # noqa: E402
from app import models  # noqa: E402, F401  (register models on Base.metadata)

DATABASE_NAME = "verda"
OUTPUT_PATH = BACKEND_DIR / "scripts" / "init_mysql_schema.sql"

HEADER = f"""-- =============================================================
-- 智能竞品分析 Agent - MySQL 初始化建表脚本
-- 由 scripts/generate_mysql_schema.py 从 app/models.py 自动生成，请勿手改。
-- 主键统一为 BIGINT 自增；业务 ID（如 task_xxx）暂不引入，后续如需再加独立列。
-- 执行方式（任选其一）：
--   1) mysql -u root -p < scripts/init_mysql_schema.sql
--   2) 在 MySQL 客户端中选中目标库后直接执行本文件
-- 注意：本脚本会先 DROP 再 CREATE，会清空库中既有数据，请确认后执行。
-- =============================================================

CREATE DATABASE IF NOT EXISTS `{DATABASE_NAME}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `{DATABASE_NAME}`;

-- 先关外键检查再删表，避免表间依赖导致删除失败
SET FOREIGN_KEY_CHECKS = 0;
"""


def main() -> None:
    dialect = mysql.dialect()
    parts = [HEADER]

    # 按依赖倒序删表（子表在前）；外键检查已关闭，顺序仅作兜底
    for table in reversed(Base.metadata.sorted_tables):
        parts.append(f"DROP TABLE IF EXISTS {table.name};")

    parts.append("SET FOREIGN_KEY_CHECKS = 1;\n")

    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect)).strip()
        parts.append(ddl + ";")
        # index=True 的列生成独立 CREATE INDEX 语句
        for index in sorted(table.indexes, key=lambda idx: idx.name or ""):
            parts.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
        parts.append("")

    OUTPUT_PATH.write_text("\n".join(parts), encoding="utf-8")
    print(f"written: {OUTPUT_PATH}")
    print(f"tables: {len(Base.metadata.sorted_tables)}")


if __name__ == "__main__":
    main()
