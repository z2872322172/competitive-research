"""6.2 迁移收尾（477/478）：MySQL 模型层测试 + 迁移回归测试。

需要真实 MySQL 时设置 TEST_MYSQL_URL（建库权限），例如：
    TEST_MYSQL_URL="mysql+pymysql://root:***@192.168.150.101:3306"
测试会在该实例上创建并清理专用数据库 verda_test_migration，不影响其他库。
未设置时全部跳过，离线测试套件不受影响。
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app import models

TEST_MYSQL_URL = os.getenv("TEST_MYSQL_URL", "").strip()
TEST_DB_NAME = "verda_test_migration"
DDL_PATH = Path(__file__).resolve().parent.parent / "scripts" / "init_mysql_schema.sql"

requires_mysql = pytest.mark.skipif(
    not TEST_MYSQL_URL,
    reason="TEST_MYSQL_URL 未设置：MySQL 模型层/迁移回归测试需要真实 MySQL 实例",
)


@pytest.fixture(scope="module")
def mysql_db_url():
    """在真实 MySQL 上创建一次性数据库，测试结束销毁。"""
    admin_engine = create_engine(TEST_MYSQL_URL)
    with admin_engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        conn.commit()
    admin_engine.dispose()
    yield f"{TEST_MYSQL_URL.rstrip('/')}/{TEST_DB_NAME}"
    admin_engine = create_engine(TEST_MYSQL_URL)
    with admin_engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))
        conn.commit()
    admin_engine.dispose()


@pytest.fixture()
def ddl_engine(mysql_db_url):
    """每个用例独立建表/清库：回归 DDL 可重复执行。"""
    engine = create_engine(mysql_db_url)
    yield engine
    engine.dispose()


def execute_ddl(engine, ddl_path: Path = DDL_PATH) -> int:
    """按 init_mysql_schema.sql 全量执行（含 DROP IF EXISTS 兜底）。

    跳过 CREATE DATABASE / USE 语句：测试库由 fixture 指定，
    绝不能让脚本里的 USE 把建表重定向到其他数据库。
    """
    sql = ddl_path.read_text(encoding="utf-8")
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    statements = [s.strip() for s in "".join(lines).split(";") if s.strip()]
    executed = 0
    with engine.begin() as conn:
        for statement in statements:
            head = statement.split("\n", 1)[0].strip().upper()
            if head.startswith("CREATE DATABASE") or head.startswith("USE "):
                continue
            conn.execute(text(statement))
            executed += 1
    return executed


@requires_mysql
def test_ddl_script_executes_and_creates_all_tables(ddl_engine):
    """478 迁移回归：DDL 脚本可在全新数据库完整执行，17 张表齐全。"""
    count = execute_ddl(ddl_engine)
    assert count >= 60, "DDL 语句数量异常，脚本可能被截断"

    tables = set(inspect(ddl_engine).get_table_names())
    expected = {table.name for table in models.Base.metadata.sorted_tables}
    missing = expected - tables
    assert not missing, f"DDL 缺表: {missing}"
    assert len(tables) == 17


@requires_mysql
def test_ddl_script_is_idempotent(ddl_engine):
    """478 迁移回归：DDL 含 DROP IF EXISTS，重复执行不报错（幂等重建）。"""
    execute_ddl(ddl_engine)
    execute_ddl(ddl_engine)  # 第二次执行验证幂等
    assert "research_tasks" in inspect(ddl_engine).get_table_names()


@requires_mysql
def test_autoincrement_primary_keys_in_mysql(ddl_engine):
    """477 模型层：自增主键在 MySQL 上为 bigint auto_increment，外键整型一致。"""
    execute_ddl(ddl_engine)
    inspector = inspect(ddl_engine)
    pk_columns = {
        "research_tasks": "id",
        "task_runs": "id",
        "sources": "id",
        "evidence": "id",
        "claims": "id",
        "users": "id",
        "workspace_members": "id",
    }
    for table, column_name in pk_columns.items():
        columns = {c["name"]: c for c in inspector.get_columns(table)}
        pk = columns[column_name]
        assert pk["type"].__class__.__name__ in {"BigInteger", "BIGINT"}, f"{table}.{column_name} 应为 BIGINT"
        assert pk.get("autoincrement") is True, f"{table}.{column_name} 应为自增主键"

    # 外键整型一致：task_runs.task_id 与 research_tasks.id 类型对齐。
    fk_columns = {c["name"]: c for c in inspector.get_columns("task_runs")}
    assert "BIGINT" in str(fk_columns["task_id"]["type"]).upper()


@requires_mysql
def test_large_text_fields_use_mediumtext(ddl_engine):
    """477 模型层：LangGraph checkpoint 等大 JSON 字段为 MEDIUMTEXT（>64KB）。"""
    execute_ddl(ddl_engine)
    inspector = inspect(ddl_engine)
    checkpoint_columns = {c["name"]: str(c["type"]).upper() for c in inspector.get_columns("workflow_checkpoints")}
    for column_name, type_name in checkpoint_columns.items():
        if column_name.endswith("_json"):
            assert "MEDIUMTEXT" in type_name, f"workflow_checkpoints.{column_name} 应为 MEDIUMTEXT，实际 {type_name}"


@requires_mysql
def test_model_roundtrip_with_integer_ids(ddl_engine):
    """477 模型层：自增整型 ID 全链路写入/关联/回读（MySQL 方言）。"""
    execute_ddl(ddl_engine)
    models.Base.metadata.create_all(ddl_engine)  # DDL 已建表，create_all 幂等跳过
    Session = sessionmaker(bind=ddl_engine)
    db = Session()
    try:
        task = models.ResearchTask(
            title="迁移回归任务",
            prompt="调研 A 与 B 的差异",
            scope_json='{"competitors": ["A", "B"]}',
            status="completed",
            workspace_id="ws-test",
            created_by="tester",
            created_at=models.utc_now(),
            updated_at=models.utc_now(),
        )
        db.add(task)
        db.flush()
        assert isinstance(task.id, int) and task.id >= 1, "自增主键应回填为正整数"

        run = models.TaskRun(task_id=task.id, status="succeeded", current_stage="report", iteration_count=1, priority=5, input_snapshot_json="{}", queued_at=models.utc_now())
        source = models.Source(task_id=task.id, url="https://example.com", canonical_url="https://example.com", source_type="official", title="示例来源", publisher="example", retrieved_at=models.utc_now(), content_hash="h" * 16, index_status="indexed", is_primary=True)
        db.add_all([run, source])
        db.flush()

        evidence = models.Evidence(source_id=source.id, quote="A 的定价为每月 20 美元", locator_json='{"para": 1}', evidence_hash="e" * 16, extraction_method="rule", source_version=1, language="zh", quality_score=0.9, created_at=models.utc_now())
        db.add(evidence)
        db.flush()

        claim = models.Claim(
            task_id=task.id,
            subject="A",
            predicate="monthly_pricing",
            value_json='{"amount": 20, "currency": "USD"}',
            claim_type="pricing",
            dimension="定价策略",
            status="verified",
            confidence="high",
            confidence_score=0.9,
            display_text="A 的定价为每月 20 美元",
        )
        db.add(claim)
        db.flush()
        db.add(models.ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id))
        db.commit()

        # 回读验证整型关联链：claim -> evidence -> source -> task。
        loaded = db.get(models.Claim, claim.id)
        assert loaded.evidence_links[0].evidence_id == evidence.id
        assert loaded.evidence_links[0].evidence.source.task_id == task.id
        assert isinstance(loaded.evidence_links[0].evidence.source.id, int)
    finally:
        db.close()


@requires_mysql
def test_utf8mb4_supports_chinese_and_emoji(ddl_engine):
    """477 模型层：utf8mb4 字符集下中文 + emoji 内容写入回读无损。"""
    execute_ddl(ddl_engine)
    Session = sessionmaker(bind=ddl_engine)
    db = Session()
    try:
        text_content = "中文注释与 emoji 🚀 混合内容"
        task = models.ResearchTask(
            title=text_content,
            prompt=text_content,
            scope_json="{}",
            status="draft",
            workspace_id="ws-utf8",
            created_by="tester",
            created_at=models.utc_now(),
            updated_at=models.utc_now(),
        )
        db.add(task)
        db.commit()
        db.expire_all()
        assert db.get(models.ResearchTask, task.id).title == text_content
    finally:
        db.close()
