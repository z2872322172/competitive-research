from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.schemas import ResearchPlanSuggestionOut
from app.services import research_planning


def test_clarify_plan_adapts_questions_to_research_prompt():
    with TestClient(app) as client:
        response = client.post(
            "/v1/research-plans/clarify",
            json={"prompt": "调研 Trae、Cursor、Windsurf 在 AI 编程 IDE 市场的定价和用户口碑"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["research_type"] == "competitive_research"
    assert body["detected_domain"] == "AI 原生 IDE / AI 代码编辑器"
    assert {"Trae", "Cursor", "Windsurf"}.issubset(body["competitors"])
    assert "定价策略" in body["dimensions"]
    assert "用户口碑" in body["dimensions"]
    assert len(body["questions"]) <= 5
    assert all(item["question"] for item in body["questions"])


def test_clarify_plan_flags_missing_research_subject():
    with TestClient(app) as client:
        response = client.post("/v1/research-plans/clarify", json={"prompt": "分析未来三个月的市场趋势"})

    assert response.status_code == 200
    body = response.json()
    assert body["warnings"]
    assert any(item["key"] == "research_subject" for item in body["questions"])


def test_parse_llm_research_plan_repairs_wrapped_json():
    plan = research_planning.parse_research_plan_content(
        """
        ```json
        {
          "plan": {
            "research_question": "研究 AI 编程助手市场",
            "domain": "AI 原生 IDE / AI 代码编辑器",
            "intent": "竞品对比与定位",
            "research_type": "competitive_research",
            "competitors": ["Cursor", "Trae", "Cursor"],
            "research_aspects": ["技术能力", "定价策略"],
            "source_preferences": ["官方网站", "专业评测"],
            "time_range": "recent_6_months",
            "report_depth": "detailed",
            "output_format": "markdown",
            "questions": [
              {
                "key": "decision goal",
                "label": "决策目标",
                "question": "这份研究要支持什么决策？",
                "type": "single_choice",
                "options": ["产品规划", "采购决策"],
                "required": true
              }
            ],
            "assumptions": ["用户关注近期竞争态势"],
            "warnings": []
          }
        }
        ```
        """,
        max_questions=3,
    )

    assert plan.detected_domain == "AI 原生 IDE / AI 代码编辑器"
    assert plan.competitors == ["Cursor", "Trae"]
    assert plan.dimensions == ["技术能力", "定价策略"]
    assert plan.questions[0].key == "decision_goal"
    assert plan.questions[0].answer_type == "single_choice"


def test_llm_planner_failure_falls_back_to_heuristic_plan():
    class BrokenPlanner:
        def plan(self, *, prompt: str, max_questions: int) -> ResearchPlanSuggestionOut:
            raise RuntimeError("upstream timeout")

    plan = research_planning.build_clarification_plan(
        "调研 Trae、Cursor 的定价策略",
        settings=Settings(research_planner_provider="llm", llm_api_key="test-key"),
        planner=BrokenPlanner(),
    )

    assert plan.research_type == "competitive_research"
    assert {"Trae", "Cursor"}.issubset(plan.competitors)
    assert any("LLM 规划暂不可用" in warning for warning in plan.warnings)


def test_build_llm_planner_requires_explicit_provider_and_key():
    assert research_planning.build_llm_planner(Settings(research_planner_provider="heuristic", llm_api_key="test")) is None
    assert research_planning.build_llm_planner(Settings(research_planner_provider="llm", llm_api_key="")) is None
