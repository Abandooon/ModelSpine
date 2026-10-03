"""Static review shell. Untrusted review data is fetched and rendered as text."""
from html import escape
import json
from pathlib import Path


def project_instance(model: dict) -> list[dict]:
    """Display the public finite ProjectModel exactly; never infer slot values."""
    def part(key, title, columns, rows, value, paragraphs=()):
        return {"key":key, "title":title, "columns":columns, "rows":rows,
                "paragraphs":list(paragraphs), "open_detail":False,
                "detail":json.dumps(value, ensure_ascii=False, indent=2)}
    rows = []
    for obj in model["objects"]:
        if not obj["slots"]:
            rows.append([obj["id"], obj["entity"], "无已提供字段", "缺失不等于 null", "—"])
        for slot in obj["slots"]:
            rows.append([obj["id"], obj["entity"], slot["field"], slot["state"],
                         json.dumps(slot["value"], ensure_ascii=False)])
    return [part("instance_objects", "实例对象与字段", ["对象 ID", "术语 ID", "字段 ID", "值状态", "精确值"], rows, model,
                 ["实例 " + model["id"] + " · 版本 " + model["version"],
                  "对象集合：" + ("声明完整" if model["population_complete"] else "不完整；缺失对象仍可能影响检查")]),
            part("instance_links", "实例关系", ["关系 ID", "源对象", "目标对象"],
                 [[link["relation"], link["source"], link["target"]] for link in model["links"]], model["links"])]


def project_report(report: dict) -> dict:
    """Keep each checker's outcome, including unknown/error/not_applicable."""
    return {"key":"instance_report", "title":"实例检查结果", "open_detail":False,
            "paragraphs":["检查器：" + report["checker"], "意图忠实性：" + report["requirement_fidelity"],
                          "逐项结果仅适用于报告绑定的定义与实例，不代表需求语义已确认。"],
            "columns":["检查义务", "目标", "状态", "原因"],
            "rows":[[r["obligation"], r["target"], r["status"], r["reason"]] for r in report["outcomes"]],
            "detail":json.dumps(report, ensure_ascii=False, indent=2)}


def format_expression(expr: dict, schema_version: str = "finite-domain/0.1") -> str:
    """Versioned syntax only; no evaluation, unit conversion or simplification."""
    if schema_version not in ("finite-domain/0.1", "finite-domain/0.2"):
        raise ValueError("unsupported expression version: " + str(schema_version))
    v2 = schema_version == "finite-domain/0.2"
    op = expr["op"]
    if op == "literal":
        return json.dumps(expr["value"], ensure_ascii=False)
    if not v2 and op in ("field", "count"):
        return op + "(" + json.dumps(expr["symbol"], ensure_ascii=False) + ")"
    common = {"not", "is_null", "eq", "lt", "le", "and", "or", "implies"}
    if op not in common | ({"self", "var", "get", "navigate", "filter", "count", "instant", "duration", "add", "sub"} if v2 else set()):
        raise ValueError("unsupported expression operator for " + schema_version + ": " + op)
    if op == "self":
        return "self"
    if op == "var":
        return "var(" + json.dumps(expr["symbol"], ensure_ascii=False) + ")"
    if op in ("instant", "duration"):
        return op + "(" + json.dumps(expr["value"], ensure_ascii=False) + (" seconds" if op == "duration" else "") + ")"
    args = [format_expression(arg, schema_version) for arg in expr["args"]]
    if v2 and op in ("get", "navigate"):
        return op + "(" + args[0] + ", " + json.dumps(expr["symbol"], ensure_ascii=False) + ")"
    if v2 and op == "filter":
        return "filter(" + args[0] + ", " + json.dumps(expr["symbol"], ensure_ascii=False) + " => " + args[1] + ")"
    if v2 and op == "count":
        return "count(" + args[0] + ")"
    if op in ("not", "is_null"):
        return op.upper() + "(" + args[0] + ")"
    symbols = {"eq":"=", "lt":"<", "le":"<=", "and":"AND", "or":"OR", "implies":"IMPLIES", "add":"+", "sub":"-"}
    return "(" + args[0] + " " + symbols[op] + " " + args[1] + ")"


def definition_version(view: dict) -> str | None:
    """Read A's verified definition identity; never infer a version from operators."""
    if view["inspection"]["status"] != "valid":
        return None
    return view["inspection"]["checks"]["candidate"]["definition"]["schema_version"]


def project_review(view: dict) -> list[dict]:
    """Text/table projection only. Exact JSON and integer spelling stay available."""
    sections = []
    def add(title, key, *, paragraphs=(), columns=(), rows=(), open_detail=False):
        value = view[key]
        sections.append({"title":title, "key":key, "paragraphs":list(paragraphs),
                         "columns":list(columns), "rows":list(rows), "open_detail":open_detail,
                         "detail":value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)})
    add("需求原文", "source_text", paragraphs=[view["source_text"]])
    term_rows = []
    names = {t["id"]: t["name"] + " [" + t["id"] + "]" for t in view["terms"]}
    for term in view["terms"]:
        if not term["fields"]:
            term_rows.append([names[term["id"]], "无字段", "—", "—", "—"])
        for field in term["fields"]:
            term_rows.append([names[term["id"]], field["name"] + " [" + field["id"] + "]", field["value_type"],
                              "必填" if field["required"] else "可省略", "可空" if field["nullable"] else "不可空"])
    add("术语与字段", "terms", columns=["术语 / ID", "字段 / ID", "类型", "必填性", "可空性"], rows=term_rows)
    def bounds(b):
        return str(b["minimum"]) + ".." + ("无上限" if b["maximum"] == "unbounded" else str(b["maximum"]))
    add("关系与双向基数", "relations", columns=["关系 / ID", "源 → 目标", "每个源对应目标数", "每个目标对应源数"],
        rows=[[r["name"] + " [" + r["id"] + "]", names[r["source"]] + " → " + names[r["target"]],
               bounds(r["targets_per_source"]), bounds(r["sources_per_target"])] for r in view["relations"]])
    version = definition_version(view)
    v2 = version == "finite-domain/0.2"
    rule_rows = []
    for rule in view["rules"]:
        scope = ([{"invariant":"库存完整性 invariant", "eligibility":"操作资格 eligibility"}.get(rule["scope"], "未支持作用域"),
                  rule["operation"] or "无操作"] if v2 else [])
        try:
            expressions = [format_expression(rule[key], version) for key in ("applies", "assertion", "unless")]
        except ValueError as exc:
            expressions = [str(exc), "未解释；请查看完整原件", "未解释"]
        rule_rows.append([rule["id"], names[rule["context"]], *scope, *expressions])
    add("规则", "rules", paragraphs=["仅格式化表达式，不求值或自动解释；括号保留 AND/OR 组合。定义版本：" + str(version),
        "库存关系基数与过滤后的资格计数独立。资格检查不是执行提交，也不能证明已保留历史。UTC 时间保留原始整秒，不转本地时区。" ] if v2 else
        ["仅格式化 finite 表达式，不求值或自动解释。字段与计数保留稳定 ID；括号保留 AND/OR 组合。" +
         (" 未支持定义版本：" + str(version) if version not in (None, "finite-domain/0.1") else "")],
        columns=["规则 ID", "上下文", *(["作用域", "操作标识"] if v2 else []), "适用 applies", "断言 assertion", "例外 unless"], rows=rule_rows)
    kinds={"candidate_issue":"候选中的原问题", "inspection_diagnostic":"原件诊断问题", "external_clarification":"外加澄清（独立记录）"}
    add("问题与回答状态", "questions", columns=["问题 ID", "来源类别", "问题", "回答状态", "解决状态"],
        rows=[[q["id"], kinds.get(q.get("kind", "candidate_issue"), "未支持问题类别"), q["text"],
               {"open":"未回答", "answer_recorded":"答复已记录", "declined":"已拒答"}[q["status"]],
               q["resolution"] + "（仍未决）"] for q in view["questions"]])
    add("候选未决项", "issues", columns=["ID", "类别", "说明", "相关元素", "问题"],
        rows=[[i["id"], i["kind"], i["text"], ", ".join(i["related_ids"]), i["question"] or "无提问"] for i in view["issues"]])
    add("残余", "residuals", columns=["ID", "语义族", "说明", "必要性", "状态"],
        rows=[[r["id"], r["family"], r["text"], "必要" if r["required"] else "非必要", "保留未决；不因确认清除"] for r in view["residuals"]])
    inspection = view["inspection"]
    add("形式检查与诊断", "inspection", paragraphs=["候选形式检查：" + inspection["status"],
        "意图忠实性：" + view["requirement_fidelity"], "实例检查：" + view["instance_conformance"]],
        columns=["诊断代码", "消息"], rows=[[d["code"], d["message"]] for d in inspection["diagnostics"]])
    revision = view["inspection"].get("checks", {}).get("candidate", {}).get("schema_version") == "typed-domain-revision/0.1"
    trace_rows = []
    for trace in view["traces"]:
        for evidence in trace["evidence"]:
            if not revision:
                trace_rows.append([trace["element"], "原始来源 source", str(evidence["start_line"]) + "–" + str(evidence["end_line"]) + " 行", evidence["quote"]])
            elif evidence["kind"] == "source":
                span = evidence["span"]
                trace_rows.append([trace["element"], "原始来源 source", evidence["source_ref"]["artifact_id"] + " · " + str(span["start_line"]) + "–" + str(span["end_line"]) + " 行", span["quote"]])
            elif evidence["kind"] == "action":
                trace_rows.append([trace["element"], "用户动作 action · " + evidence["part"],
                                   evidence["action_ref"]["artifact_id"] + " / 问题 " + evidence["question_ref"]["artifact_id"], evidence["quote"]])
            else:
                trace_rows.append([trace["element"], "未支持来源类型", "未解释", "见完整详情"])
    add("来源追踪", "traces", paragraphs=["原始来源与后续动作分开；总领解释不是用户逐字原话。完整引用及原件在详情中。"],
        columns=["元素 ID", "来源类别", "引用 / 位置", "原话"], rows=trace_rows)
    add("用户确认", "confirmations", paragraphs=["仅登记用户看过的目标；不改变形式检查或接受候选。"],
        columns=["目标", "归属", "说明"], rows=[[", ".join(c["targets"]), c["provenance"]["actor"], c["provenance"]["text"]] for c in view["confirmations"]])
    add("修订提案", "proposals", paragraphs=["登记只推进审阅记录，当前候选未变；只有明确采纳合法提案才建立后继候选。语言生成来源未因登记而被认证。"], columns=["提案 ID", "采纳状态", "检查", "说明"],
        rows=[[p["ref"]["artifact_id"], p["adoption"], p["inspection"]["status"],
               p["provenance"]["text"] if p["provenance"]["kind"] == "user_action" else "外部修订产物；生成来源 not_verified"] for p in view["proposals"]])
    action_rows, clarification_rows = [], []
    for record in view["actions"]:
        action = record["action"]
        schema = action["schema_version"]
        if schema == "model-review/0.1":
            action_rows.append([action["id"], action["kind"], action["actor"], action["text"]])
        elif schema == "model-review-clarification/0.1":
            action_rows.append([action["id"], "外加澄清 · " + action["response_kind"], action["actor"], action["response_text"]])
            for label, owner, text in (("外加问题",action["question_actor"],action["question_text"]),
                    ("更正",action["correction_actor"],action["correction_text"]),
                    ("答复" if action["response_kind"] == "answer" else "拒答",action["actor"],action["response_text"]),
                    ("解释（非用户原话）",action["interpretation_actor"],action["interpretation_text"])):
                clarification_rows.append([action["id"],label,owner or "未提供",text or "（空）"])
        elif schema == "model-review-revision-proposal/0.1":
            action_rows.append([action["id"],"修订产物登记",action["actor"],"待明确采纳；生成来源 not_verified"])
        else:
            action_rows.append([action["id"],"未支持动作版本：" + schema,action["actor"],"见完整原件"])
    add("已保存动作", "actions", columns=["动作 ID", "类型", "归属", "用户原话"],
        rows=action_rows)
    if clarification_rows:
        sections.append({"key":"external_clarifications", "title":"外加澄清与分别归属", "columns":["动作 ID", "部分", "归属标记", "原文内容"],
                         "rows":clarification_rows, "paragraphs":["以下是独立外加记录，不改写原始来源；解释不当作用户原话或候选通过。归属标记不是身份认证。"],
                         "open_detail":False, "detail":json.dumps([a for a in view["actions"] if a["action"]["schema_version"] == "model-review-clarification/0.1"], ensure_ascii=False, indent=2)})
    if view.get("revision_context") is not None:
        context_rows = []
        for response in view["revision_context"]["responses"]:
            action = response["action"]
            if action["schema_version"] == "model-review-clarification/0.1":
                parts = [("外加问题", action["question_actor"], action["question_text"]),
                         ("更正", action["correction_actor"], action["correction_text"]),
                         (action["response_kind"], action["actor"], action["response_text"]),
                         ("解释（非用户原话）", action["interpretation_actor"], action["interpretation_text"])]
            else:
                parts = [("原问题", "候选问题", response["verbatim"]["question"]),
                         (action["kind"], action["actor"], action["text"])]
            context_rows.extend([[response["action_ref"]["artifact_id"], label, owner or "未提供", text or "（空）"]
                                for label, owner, text in parts])
        add("当前候选的回答修订来源", "revision_context", paragraphs=["以下是父版本的问答来源；原始请求与来源仍独立保留。解释不是用户原话；引用这些材料不等于用户确认候选或业务执行成功。"],
            columns=["父版本动作", "部分", "归属标记", "内容"], rows=context_rows)
    add("原响应文本", "candidate_text", paragraphs=["UTF-8 替换仅供显示；精确字节见下方 base64。"], open_detail=inspection["status"] == "rejected")
    add("原响应精确字节（base64）", "candidate_base64")
    for index, entry in enumerate(view["projects"]):
        sections.append({"key":"saved_project", "title":"已保存实例 · " + entry["project"]["id"],
                         "paragraphs":["用途：" + entry["purpose"] + " · 归属：" + entry["actor"],
                                       "保存不等于通过检查。报告须对当前候选重新执行，不跨候选继承。"],
                         "columns":["绑定", "标识", "版本"],
                         "rows":[[key, entry[key]["artifact_id"], entry[key]["revision"]] for key in
                                 ("ref", "request_ref", "candidate_ref", "definition_ref", "based_on_review_ref")],
                         "detail":json.dumps(entry, ensure_ascii=False, indent=2), "open_detail":False})
        for part in project_instance(entry["project"]):
            part["key"] += "_" + str(index)
            sections.append(part)
    return sections


def spec_template(view: dict) -> str | None:
    """Unconfigured structural draft; no invented permission or initial-data decision."""
    if definition_version(view) != "finite-domain/0.1":
        return None
    return json.dumps({"schema_version":"local-project-web/0.1", "id":"", "version":"",
        **{key:view[key] for key in ("project_id", "request_ref", "source_ref", "definition_ref", "candidate_ref", "review_ref")},
        "initial_project_ref":None, "no_initial_data_reason":None, "edit_scope":None, "tasks":[], "views":[],
        "storage":None, "access":None, "evidence":[], "acceptance_cases":[], "confirmation_refs":[],
        "required_unresolved":[], "unsupported_requirements":[]}, ensure_ascii=False, indent=2)


def review_page(action_token: str) -> str:
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="review-token" content="''' + escape(action_token, quote=True) + '''">
<title>ModelSpine · 候选审阅</title><link rel="stylesheet" href="/review.css">
<script src="/review.js" defer></script></head><body>
<header><p>ModelSpine / 有限前置审阅</p><h1>理解候选，记录你的判断</h1>
<p>形式检查、用户确认、实例检查分别展示。记录意见不会改变候选；明确采纳合法提案后才建立后继版本。</p>
<p class="notice">可离线保存和检查实例、采纳合法提案、导出修订材料及准备应用配置。未知和未决仍需处理；此页不调用语言服务或生成应用代码。</p>
<nav><a href="/" target="_blank" rel="noopener">在新窗口读取最新记录</a>
<button id="layout" type="button">切换单列 / 双列</button></nav>
<p>每页固定所见版本；保存后从新窗口继续。旧页草稿保留，冲突不会自动换版本重发。操作人名称仅用于标记意见归属。</p>
</header><main><p id="load-state" role="status">正在核验本地记录…</p>
<section id="versions"><h2>候选版本与来源</h2><label>查看版本<select id="version-select"></select></label><p id="version-state"></p><div id="adoption-source"></div></section>
<section id="identity"><h2>身份与状态</h2></section>
<div id="panels" class="columns"></div><section id="actions"><h2>提交用户动作</h2>
<p>提交绑定该页所见目标；取消只清空本表单草稿。实例保存、实例检查与候选采纳各自执行，不等于语义通过。完整提案可保留非法 JSON。</p>
<div id="forms"></div><div id="offline-tools"></div></section></main><footer>意见保存后仍需处理；形式检查不能证明候选忠实表达了你的需求。应用配置就绪也不表示应用已生成或验收。</footer>
</body></html>'''


def review_asset(name: str) -> bytes:
    if name not in ("review.js", "review.css"):
        raise ValueError("unknown review asset")
    return Path(__file__).with_name(name).read_bytes()
