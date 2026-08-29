"""Build a research plan from natural language before a task is created.

The first implementation is deterministic so the product remains useful offline. The
service is deliberately isolated so an LLM planner can replace the heuristic later
without changing the API contract or the confirmation UI.
"""

import json
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.schemas import ClarificationQuestionOut, ResearchPlanSuggestionOut
from app.services import observability
from app.services.analysis.llm import LLMUnavailable, extract_json_text


class ResearchPlanner(Protocol):
    def plan(self, *, prompt: str, max_questions: int) -> ResearchPlanSuggestionOut:
        """Build a structured research plan and clarification questions."""


RESPONSE_FORMAT_ERROR_MARKERS = (
    "response_format",
    "unavailable now",
)

JSON_OBJECT_OUTPUT_CONTRACT = (
    "Respond with a single json object matching this shape: "
    '{"research_question": str, "detected_domain": str, "detected_intent": str, '
    '"research_type": "competitive_research|deep_research", "competitors": [str], '
    '"dimensions": [str], "source_preferences": [str], "time_range": str, '
    '"report_depth": "brief|standard|detailed", "output_format": str, '
    '"questions": [{"key": str, "label": str, "question": str, "reason": str, '
    '"answer_type": "free_text|single_choice|multi_choice", "options": [str], "required": bool}], '
    '"assumptions": [str], "warnings": [str]}'
)


class OpenAICompatibleResearchPlanner:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        disable_thinking: bool = False,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.disable_thinking = disable_thinking
        self._use_json_object = False

    def plan(self, *, prompt: str, max_questions: int) -> ResearchPlanSuggestionOut:
        messages = self._build_messages(prompt=prompt, max_questions=max_questions)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        started_wall = datetime.now(timezone.utc)
        started_at = perf_counter()
        try:
            body = self._request_with_fallback(messages, headers)
            content = body["choices"][0]["message"]["content"]
            plan = parse_research_plan_content(content, max_questions=max_questions)
        except Exception as exc:
            observability.record_generation(
                name="research_planning",
                model=self.model,
                input_messages=messages,
                started_at=started_wall,
                duration_ms=int((perf_counter() - started_at) * 1000),
                error=str(exc),
            )
            raise

        observability.record_generation(
            name="research_planning",
            model=self.model,
            input_messages=messages,
            output_content=content,
            usage=body.get("usage"),
            started_at=started_wall,
            duration_ms=int((perf_counter() - started_at) * 1000),
            metadata_extra={"response_format": "json_object" if self._use_json_object else "json_schema"},
        )
        return plan

    def _request_with_fallback(self, messages: list[dict], headers: dict) -> dict:
        try:
            return self._request(messages, headers)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400 and not self._use_json_object:
                detail = exc.response.text or ""
                if any(marker in detail for marker in RESPONSE_FORMAT_ERROR_MARKERS):
                    self._use_json_object = True
                    return self._request(self._json_object_messages(messages), headers)
            raise

    def _request(self, messages: list[dict], headers: dict) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        if self._use_json_object:
            payload["response_format"] = {"type": "json_object"}
        else:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "research_plan_suggestion",
                    "schema": ResearchPlanSuggestionOut.model_json_schema(),
                    "strict": True,
                },
            }
        if self.disable_thinking:
            payload["enable_thinking"] = False
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    def _build_messages(self, *, prompt: str, max_questions: int) -> list[dict]:
        system_content = (
            "You are a senior research planning agent for competitive and deep research. "
            "Infer only from the user's request, identify what is ambiguous, and ask targeted clarification questions. "
            "Questions must be dynamic, specific to the domain/product/decision, and never generic form labels. "
            "Prefer choice-style questions: most questions should use answer_type single_choice or multi_choice "
            "with 3-5 concrete, mutually distinct options inferred from the domain; use free_text only when "
            "genuinely open-ended input is required. Every option must be a short, self-explanatory phrase. "
            "Write every question, reason, and option in the same language as the user's research prompt. "
            "Keep assumptions explicit. Prefer source strategies that enable cross-validation and citation traceability. "
            f"Return at most {max_questions} clarification questions."
        )
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": json.dumps({"research_prompt": prompt}, ensure_ascii=False)},
        ]

    def _json_object_messages(self, messages: list[dict]) -> list[dict]:
        updated = list(messages)
        updated[0] = {
            "role": "system",
            "content": f"{updated[0]['content']} {JSON_OBJECT_OUTPUT_CONTRACT}",
        }
        return updated


KNOWN_PRODUCTS = (
    "Trae",
    "Cursor",
    "GitHub Copilot",
    "Windsurf",
    "Codeium",
    "Sourcegraph Cody",
    "Replit",
    "Tabnine",
    "Notion",
    "Obsidian",
    "飞书",
    "钉钉",
    "企业微信",
    "Slack",
    "Microsoft Teams",
)

DOMAIN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AI 原生 IDE / AI 代码编辑器", ("AI 编程", "代码编辑", "IDE", "Copilot", "Cursor", "Trae", "Windsurf")),
    ("知识管理与协作", ("知识管理", "笔记", "Notion", "Obsidian")),
    ("企业协作与办公", ("协作办公", "企业协作", "飞书", "钉钉", "企业微信", "Slack", "Teams")),
    ("新能源汽车", ("新能源汽车", "电动车", "智能汽车")),
)

DIMENSION_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("产品定位", ("定位", "人群", "市场", "格局")),
    ("核心功能", ("功能", "能力", "feature", "体验")),
    ("定价策略", ("价格", "定价", "套餐", "商业化", "pricing")),
    ("技术能力", ("技术", "模型", "架构", "性能", "技术路线")),
    ("用户口碑", ("口碑", "评价", "用户", "社区", "舆情")),
    ("生态与渠道", ("生态", "渠道", "集成", "合作")),
    ("增长与趋势", ("增长", "趋势", "融资", "动态", "发展")),
    ("风险与机会", ("风险", "机会", "SWOT", "壁垒")),
)

INTENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("竞品对比与定位", ("对比", "竞品", "竞争", "格局", "比较", "versus", "compare")),
    ("产品决策支持", ("规划", "功能", "路线", "产品决策")),
    ("市场趋势判断", ("趋势", "市场", "增长", "行业")),
    ("商业化判断", ("价格", "定价", "商业化", "收入", "融资")),
)


def _contains(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(keyword.lower() in normalized for keyword in keywords)


def _extract_products(prompt: str) -> list[str]:
    found: list[str] = []
    for product in KNOWN_PRODUCTS:
        if product.lower() in prompt.lower() and product not in found:
            found.append(product)
    # 对中文逗号、斜杠和英文逗号分隔的产品名保留少量候选，避免把整句当作对象。
    for raw in re.split(r"[/、,，]|\s+vs\s+|\s+versus\s+", prompt, flags=re.IGNORECASE):
        candidate = raw.strip(" 。；;:：()（）[]【】\n\t")
        if 1 < len(candidate) < 40 and any(char.isalpha() for char in candidate):
            if candidate not in found and candidate.lower() not in {"分析", "研究", "对比", "市场"}:
                if candidate in KNOWN_PRODUCTS:
                    found.append(candidate)
    return found[:8]


def _infer_domain(prompt: str) -> str:
    for domain, keywords in DOMAIN_RULES:
        if _contains(prompt, keywords):
            return domain
    return "待确认的产品或行业领域"


def _infer_intent(prompt: str) -> str:
    for intent, keywords in INTENT_RULES:
        if _contains(prompt, keywords):
            return intent
    return "探索性深度研究"


def _infer_dimensions(prompt: str, intent: str) -> list[str]:
    dimensions = [name for name, keywords in DIMENSION_RULES if _contains(prompt, keywords)]
    if dimensions:
        return dimensions
    if intent == "商业化判断":
        return ["定价策略", "商业化路径", "市场趋势"]
    if intent == "产品决策支持":
        return ["产品定位", "核心功能", "用户口碑", "风险与机会"]
    return ["产品定位", "核心功能", "定价策略", "用户口碑", "技术能力"]


def _build_questions(prompt: str, products: list[str], domain: str, intent: str) -> list[ClarificationQuestionOut]:
    questions: list[ClarificationQuestionOut] = []
    if not products:
        questions.append(
            ClarificationQuestionOut(
                key="research_subject",
                label="研究对象",
                question="你希望重点研究哪些产品、公司或行业对象？",
                reason="当前需求还没有识别出明确对象，研究对象会决定后续搜索范围。",
                answer_type="free_text",
                required=True,
            )
        )
    if domain == "待确认的产品或行业领域":
        questions.append(
            ClarificationQuestionOut(
                key="domain",
                label="所属领域",
                question="这次研究属于哪个产品或行业领域？",
                reason="领域不同，信息源、检索词和报告框架会不同。",
                answer_type="free_text",
                required=True,
            )
        )
    questions.append(
        ClarificationQuestionOut(
            key="decision_goal",
            label="决策目标",
            question="这份研究最终要支持什么决策？",
            reason=f"当前需求更像是“{intent}”，明确决策目标后 Agent 才能调整证据深度。",
            answer_type="single_choice",
            options=["产品定位", "功能规划", "定价与商业化", "市场进入", "投资或管理层判断"],
        )
    )
    questions.append(
        ClarificationQuestionOut(
            key="market_boundary",
            label="市场边界",
            question="需要限定国家、地区、客户群或时间范围吗？",
            reason="市场边界会影响来源语言、价格口径和竞品集合。",
            answer_type="free_text",
            options=[],
        )
    )
    if not _contains(prompt, ("口碑", "评价", "社区", "舆情")):
        questions.append(
            ClarificationQuestionOut(
                key="source_depth",
                label="来源深度",
                question="是否需要加入用户社区、专业评测和新闻报道，补充官方信息之外的真实反馈？",
                reason="官方来源适合验证事实，社区和评测更适合判断体验与争议。",
                answer_type="single_choice",
                options=["需要，重点看真实反馈", "适量加入作为补充", "只看官方和权威资料"],
            )
        )
    questions.append(
        ClarificationQuestionOut(
            key="output_preference",
            label="输出偏好",
            question="报告更希望偏战略判断，还是偏可执行的产品行动建议？",
            reason="输出偏好会影响报告章节、结论颗粒度和建议部分的比重。",
            answer_type="single_choice",
            options=["战略判断", "产品行动建议", "两者都要"],
        )
    )
    return questions[:5]


def parse_research_plan_content(content: str, *, max_questions: int = 5) -> ResearchPlanSuggestionOut:
    raw = extract_json_text(content)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_research_plan_json:{exc.msg}") from exc
    repaired = repair_research_plan_payload(payload, max_questions=max_questions)
    return ResearchPlanSuggestionOut.model_validate(repaired)


def repair_research_plan_payload(payload: Any, *, max_questions: int) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("plan"), dict):
        payload = payload["plan"]
    if not isinstance(payload, dict):
        raise ValueError("research_plan_payload_must_be_object")

    questions = payload.get("questions", [])
    if not isinstance(questions, list):
        questions = []

    return {
        "research_question": str(payload.get("research_question") or payload.get("prompt") or "").strip(),
        "detected_domain": str(payload.get("detected_domain") or payload.get("domain") or "待确认的产品或行业领域").strip(),
        "detected_intent": str(payload.get("detected_intent") or payload.get("intent") or "探索性深度研究").strip(),
        "research_type": normalize_research_type(payload.get("research_type")),
        "competitors": clean_string_list(payload.get("competitors")),
        "dimensions": clean_string_list(payload.get("dimensions") or payload.get("research_aspects")),
        "source_preferences": clean_string_list(payload.get("source_preferences")),
        "time_range": str(payload.get("time_range") or "recent_1_year").strip(),
        "report_depth": normalize_report_depth(payload.get("report_depth")),
        "output_format": str(payload.get("output_format") or "markdown").strip(),
        "questions": [repair_question(item) for item in questions[:max_questions] if isinstance(item, dict)],
        "assumptions": clean_string_list(payload.get("assumptions")),
        "warnings": clean_string_list(payload.get("warnings")),
    }


def clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    items: list[str] = []
    for raw_item in value:
        item = str(raw_item or "").strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    return items


def normalize_research_type(value: Any) -> str:
    normalized = str(value or "").strip()
    return normalized if normalized in {"competitive_research", "deep_research"} else "deep_research"


def normalize_report_depth(value: Any) -> str:
    normalized = str(value or "").strip()
    return normalized if normalized in {"brief", "standard", "detailed"} else "standard"


def repair_question(item: dict[str, Any]) -> dict[str, Any]:
    answer_type = str(item.get("answer_type") or item.get("type") or "free_text").strip()
    if answer_type not in {"free_text", "single_choice", "multi_choice"}:
        answer_type = "free_text"
    key = str(item.get("key") or item.get("label") or "clarification").strip() or "clarification"
    label = str(item.get("label") or key).strip() or key
    return {
        "key": re.sub(r"[^a-zA-Z0-9_\-]+", "_", key).strip("_") or "clarification",
        "label": label,
        "question": str(item.get("question") or label).strip() or label,
        "reason": str(item.get("reason") or "").strip(),
        "answer_type": answer_type,
        "options": clean_string_list(item.get("options")),
        "required": bool(item.get("required", False)),
    }


def build_llm_planner(settings: Settings) -> ResearchPlanner | None:
    provider = settings.research_planner_provider.strip().lower()
    if provider in {"", "heuristic", "rule", "rule_based"}:
        return None
    api_key = settings.llm_api_key or settings.openai_api_key
    if not api_key:
        return None
    if settings.llm_provider not in {"openai", "openai_compatible"}:
        raise LLMUnavailable(f"unsupported_llm_provider:{settings.llm_provider}")
    return OpenAICompatibleResearchPlanner(
        api_key=api_key,
        base_url=settings.llm_base_url,
        model=settings.research_planner_model or settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        disable_thinking=settings.llm_disable_thinking,
    )


def build_heuristic_clarification_plan(prompt: str) -> ResearchPlanSuggestionOut:
    trimmed = prompt.strip()
    products = _extract_products(trimmed)
    domain = _infer_domain(trimmed)
    intent = _infer_intent(trimmed)
    dimensions = _infer_dimensions(trimmed, intent)
    research_type = "competitive_research" if len(products) >= 2 or _contains(trimmed, ("竞品", "竞争", "对比", "格局")) else "deep_research"
    source_preferences = ["官方网站", "产品文档", "权威新闻 / 行业报告"]
    if _contains(trimmed, ("口碑", "评价", "社区", "舆情")):
        source_preferences.append("用户社区与专业评测")
    assumptions: list[str] = []
    warnings: list[str] = []
    if products:
        assumptions.append(f"已识别研究对象：{'、'.join(products)}")
    else:
        warnings.append("暂未识别出明确研究对象，开始研究前需要补充对象")
    if domain != "待确认的产品或行业领域":
        assumptions.append(f"已识别所属领域：{domain}")
    return ResearchPlanSuggestionOut(
        research_question=trimmed,
        detected_domain=domain,
        detected_intent=intent,
        research_type=research_type,
        competitors=products,
        dimensions=dimensions,
        source_preferences=source_preferences,
        time_range="recent_3_months" if _contains(trimmed, ("近期", "最新", "动态", "趋势")) else "recent_1_year",
        report_depth="detailed" if len(dimensions) >= 5 or _contains(trimmed, ("深度", "全面", "深入")) else "standard",
        output_format="markdown",
        questions=_build_questions(trimmed, products, domain, intent),
        assumptions=assumptions,
        warnings=warnings,
    )


def build_clarification_plan(
    prompt: str,
    *,
    settings: Settings | None = None,
    planner: ResearchPlanner | None = None,
) -> ResearchPlanSuggestionOut:
    resolved_settings = settings or get_settings()
    max_questions = resolved_settings.research_planner_max_questions
    selected_planner = planner
    if selected_planner is None:
        try:
            selected_planner = build_llm_planner(resolved_settings)
        except LLMUnavailable:
            selected_planner = None

    if selected_planner is not None:
        try:
            return selected_planner.plan(prompt=prompt.strip(), max_questions=max_questions)
        except (LLMUnavailable, httpx.HTTPError, KeyError, IndexError, RuntimeError, ValueError, ValidationError) as exc:
            fallback = build_heuristic_clarification_plan(prompt)
            fallback.warnings.append(f"LLM 规划暂不可用，已使用规则规划：{exc}")
            return fallback

    return build_heuristic_clarification_plan(prompt)
