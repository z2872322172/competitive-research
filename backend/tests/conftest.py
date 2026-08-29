import os
from pathlib import Path

# 测试环境隔离：在导入 app 之前强制注入封闭配置。
# 原因：app.db 在模块导入时创建引擎并绑定 DATABASE_URL，app.config 的 Settings 会读取本机 .env；
# 若本机 .env 配置了 MySQL / TASK_MODE=celery（真实联调场景），测试会连上真实中间件而失败。
# 真实环境变量优先级高于 .env 文件，故在此处覆盖可保证测试始终封闭运行。
os.environ["DATABASE_URL"] = "sqlite:///./verda_test.db"
# 存量测试面向无登录态的离线行为（X-Workspace-Id 头过滤语义）；
# 鉴权强制与用户隔离由 test_auth_isolation.py 通过 AUTH_MODE_OVERRIDE=strict 专门验证。
os.environ["AUTH_MODE"] = "disabled"

# 主键改为自增整型后，跨会话残留数据会出现 ID 撞车（例如旧 checkpoint 的 run_id 被新 run 复用），
# 因此每个测试会话开始前清空测试库，保证会话间隔离。
Path("verda_test.db").unlink(missing_ok=True)
os.environ["TASK_MODE"] = "inline"
# Elasticsearch 同理：.env 可能指向真实虚拟机，测试必须封闭运行。
# 指向本机未监听端口让检索/索引确定性地走 DB 降级或失败吞掉路径，不依赖外部环境。
os.environ["ELASTICSEARCH_URL"] = "http://localhost:9200"
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault("LLM_API_KEY", "")
# Langfuse 同理：.env 指向虚拟机（192.168.150.101:3000），虚拟机不在线时
# 每次 trace 上报都要等待 TCP 连接超时（约 21s），导致测试极慢。
# 清空三要素让 observability.get_langfuse() 走 no-op 路径（见 app/services/observability.py）。
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""
os.environ["LANGFUSE_HOST"] = ""
# MinIO 同理：指向本机未监听端口让连接立即失败（ECONNREFUSED），
# FallbackArtifactStorage 立即降级到本地存储，避免每次读写白等 10s 超时。
os.environ["MINIO_ENDPOINT"] = "http://localhost:9000"
