"use strict";
const token = document.querySelector('meta[name="review-token"]').content;
const node = (tag, text) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n; };
const pretty = value => JSON.stringify(value, null, 2);
function details(parent, title, text, open=false) {
  const d = node("details"); d.open = open; d.append(node("summary", title), node("pre", text)); parent.append(d);
}
function section(part, parent=document.getElementById("panels")) {
  const s = node("section"); s.dataset.section = part.key; s.append(node("h2", part.title));
  for (const text of part.paragraphs) s.append(node("p", text));
  if (part.columns.length) {
    if (!part.rows.length) s.append(node("p", "本视图无此项；以检查状态为准，不表示检查通过。"));
    else {
      const wrap = node("div"); wrap.className = "table-scroll";
      const table = node("table"), head = node("thead"), tr = node("tr"), body = node("tbody");
      for (const text of part.columns) { const th = node("th", text); th.scope = "col"; tr.append(th); }
      head.append(tr);
      for (const row of part.rows) {
        const r=node("tr");
        row.forEach((text,i)=>{const td=node("td",text);
          if(part.columns[i]==="状态" && ["satisfied","violated","unknown","error","not_applicable"].includes(text)) td.dataset.status=text;
          r.append(td);});
        body.append(r);
      }
      table.append(head, body); wrap.append(table); s.append(wrap);
    }
  }
  details(s, "完整数据 / 原件详情", part.detail, part.open_detail);
  for (const child of part.children || []) section(child, s);
  parent.append(s);
}
async function api(path, action) {
  const response = await fetch(path, {method: action ? "POST" : "GET", cache: "no-store",
    headers: {"X-Review-Token": token, ...(action ? {"Content-Type":"application/json"} : {})},
    ...(action ? {body: typeof action === "string" ? action : JSON.stringify(action)} : {})});
  const body = await response.json();
  if (!response.ok) throw new Error(`${body.code}: ${body.reason}`);
  return body;
}
function input(form, label, rows=3) {
  const l = node("label", label), t = node("textarea"); t.rows = rows; l.append(t); form.append(l); return t;
}
function submitForm(title, build, consume, describe, operation) {
  const f = node("form"); f.append(node("h3", title));
  f.dataset.operation = operation;
  const result = node("div"); result.className = "result"; result.setAttribute("role", "status");
  const fields = build(f);
  const send = node("button", {"save-project":"保存实例", "check-project":"检查库存完整性", "check-eligibility":"仅检查资格", "clarification":"记录外加澄清", "revision-proposal":"登记修订产物", "adopt-proposal":"采纳提案"}[operation] || "提交记录"); send.type = "submit";
  const cancel = node("button", "取消草稿"); cancel.type = "button";
  cancel.onclick = () => { f.reset(); result.textContent = "已取消草稿；未提交。"; result.className = "result"; };
  f.append(send, cancel, result);
  f.onsubmit = async event => {
    event.preventDefault(); send.disabled = true; cancel.disabled = true;
    result.className = "result"; result.textContent = operation.startsWith("check-")?"正在检查，尚未收到结果…":"正在保存，尚未收到回执…";
    try {
      const receipt = await consume(fields());
      result.className = "result success";
      result.replaceChildren();
      describe(result, receipt);
    } catch (error) {
      result.className = "result error";
      result.textContent = "未获得成功回执；草稿保留，不自动重发。请查看最新记录核对是否已落盘。\n" + error.message;
    } finally { send.disabled = false; cancel.disabled = false; }
  };
  document.getElementById("forms").append(f);
}
function binding(view, actor) {
  return {id:crypto.randomUUID(), project_id:view.project_id, request_ref:view.request_ref,
    candidate_ref:view.candidate_ref, expected_review_ref:view.review_ref, actor};
}
function recorded(receipt) {
  if (!["recorded", "already_recorded"].includes(receipt.status)) throw new Error("unexpected_receipt: 未收到记录确认");
  return receipt;
}
function saved(result, receipt) {
  result.append(node("p", "已记录（未修订、未接受，候选未变）。请在新窗口读取最新记录后继续。"));
  details(result, "保存回执与版本绑定", pretty(receipt));
}
function actionForm(title, view, actor, build) {
  submitForm(title, build, async fields => recorded(await api("/api/action", {
    schema_version:"model-review/0.1", ...binding(view, actor), question_ref:null, text:"", targets:[], proposal_base64:null, ...fields
  })), saved, "review-action");
}
function forms(view, actor, whole) {
  const definition=view.inspection.status==="valid"?view.inspection.checks.candidate.definition:null;
  for (const q of view.questions) {
    actionForm(`问题 ${q.id} · ${q.text}`, view, actor, f => {
      f.append(node("p", `${q.kind==="external_clarification"?"外加澄清；更正："+(q.correction || "（空）"):"候选原问题或原件诊断"}；状态：${q.status}；解决状态：${q.resolution}`));
      const l = node("label", "动作"), select = node("select");
      for (const [value, label] of [["answer", "答复"], ["decline", "拒答"]]) {
        const option = node("option", label); option.value = value; select.append(option);
      }
      l.append(select); f.append(l);
      const t = input(f, "答复或拒答说明（拒答可留空）");
      return () => ({kind:select.value, question_ref:q.ref, text:t.value});
    });
  }
  actionForm("明确目标逐项确认", view, actor, f => {
    const targets = [[whole, "整体候选原件（已看过；不表示合法或接受）"]];
    for (const term of view.terms) {
      targets.push([term.id, `术语 ${term.name}`]);
      for (const field of term.fields) targets.push([field.id, `字段 ${term.name} / ${field.name}`]);
    }
    for (const [key, label] of [["relations","关系"],["rules","规则"],["residuals","残余"]]) {
      for (const item of view[key]) targets.push([item.id, `${label} ${item.name || item.text || item.id}`]);
    }
    const boxes = targets.map(([id, label]) => {
      const l = node("label"), c = node("input"); c.type = "checkbox"; c.value = id;
      l.append(c, document.createTextNode(`${label} [${id}]`)); f.append(l); return c;
    });
    const t = input(f, "确认说明（可空）");
    return () => ({kind:"confirm", targets:boxes.filter(c=>c.checked).map(c=>c.value), text:t.value});
  });
  actionForm("完整候选修订提案 · 仅待采纳", view, actor, f => {
    const t = input(f, "修改理由"), proposal = input(f, "完整候选 JSON / 原文本（UTF-8；非法内容也留档检查）", 12);
    return () => {
      const bytes = new TextEncoder().encode(proposal.value);
      if (bytes.length > 256 * 1024) throw new Error("unsupported: 提案超过 256 KiB");
      let binary = ""; for (const b of bytes) binary += String.fromCharCode(b);
      return {kind:"propose_edit", text:t.value, proposal_base64:btoa(binary)};
    };
  });
  submitForm("记录外加问题、更正与回答", f=>{
    f.append(node("p",`这是新的外加澄清，绑定当前父候选与审阅。回答归属为 ${actor}（启动时标记，非认证）。原始来源不改写，解释不作为用户原话。`));
    const fields={};
    for(const [key,label] of [["question_text","外加问题原话"],["question_actor","问题提出者归属"],
      ["correction_text","更正原话（无则留空）"],["correction_actor","更正归属（有更正时必填）"],
      ["response_text","回答或拒答原话"],["interpretation_text","单独解释（可空，不是用户逐字原话）"],
      ["interpretation_actor","解释者归属（有解释时必填）"]])fields[key]=input(f,label,2);
    const label=node("label","回应类型"),kind=node("select");
    for(const [value,text] of [["answer","回答"],["decline","拒答（原话可空）"]]){const o=node("option",text);o.value=value;kind.append(o);}
    label.append(kind);f.append(label);
    return ()=>Object.fromEntries([...Object.entries(fields).map(([key,t])=>[key,t.value]),["response_kind",kind.value]]);
  },async fields=>recorded(await api("/api/clarification",{schema_version:"model-review-clarification/0.1",...binding(view,actor),...fields})),
    saved,"clarification");
  submitForm("登记已有回答修订产物",f=>{
    f.append(node("p","这里只登记已经取得的完整产物，不调用语言服务。登记后当前候选仍不变，必须另行复核并明确采纳。生成来源标记 not_verified 不是模型调用认证。"));
    const payload=input(f,"产物绑定 JSON：action_refs、revision_ref、response_ref、proposal_base64、method_instructions",10);
    details(f,"填写约定","五个字段全部必需。action_refs 选取实际保存问答引用；revision_ref 取 A 已准备材料的 ref；response_ref 取产物来源引用；proposal_base64 是未修复、未重写原始响应字节的 base64；method_instructions 必须是生成该产物时冻结的方法原文，不能用当前提示补入旧历史。父候选、请求和审阅绑定使用本页所见版本，不从此输入替换。完整引用均含 project_id / artifact_id / revision / content_hash。没有产物时不填造候选。");
    return ()=>{
      const value=JSON.parse(payload.value),keys=["action_refs","revision_ref","response_ref","proposal_base64","method_instructions"];
      if(!value || Array.isArray(value) || Object.keys(value).length!==keys.length || !keys.every(k=>Object.hasOwn(value,k)))throw new Error("绑定材料必须且仅含指定五个字段；不得补造历史方法。");
      return value;
    };
  },async fields=>recorded(await api("/api/revision/proposal",{schema_version:"model-review-revision-proposal/0.1",...binding(view,actor),...fields})),
    (result,receipt)=>{result.append(node("p","修订产物已登记；当前候选未变、尚未采纳。请在新窗口查看原件与诊断，再明确选择是否采纳。"));details(result,"登记回执",pretty(receipt));},"revision-proposal");
  if (view.definition_ref !== null) {
    submitForm("保存实例（不自动判为通过）", f => {
      const l=node("label", "实例用途"), purpose=node("select");
      for (const [value,label] of [["example","示例"],["counterexample","反例"],["project","项目实例"]]) {
        const o=node("option", label); o.value=value; purpose.append(o);
      }
      l.append(purpose); f.append(l, node("p", "用途只标记输入意图；反例检查违反仍显示 violated。缺失、未知和 null 不互相替换。"));
      const project=input(f,"完整实例 JSON（数值按输入原文提交）",12);
      const template=node("button","填入结构模板（尚无实例）"); template.type="button";
      template.onclick=()=>{project.value=pretty({schema_version:"finite-project/0.1",id:"",version:"1",
        definition:view.definition_ref,objects:[],links:[],population_complete:false});};
      f.append(template);
      details(f,"必须绑定的定义",pretty(view.definition_ref));
      return ()=>({purpose:purpose.value, projectText:project.value});
    },async fields=>{
      const envelope={schema_version:"model-review-project/0.1",...binding(view,actor),purpose:fields.purpose};
      // Never parse/reserialize ProjectModel numbers through JS Number.
      const raw=JSON.stringify(envelope).slice(0,-1)+',"project":'+fields.projectText+'}';
      if (new TextEncoder().encode(raw).length>512*1024) throw new Error("unsupported: 实例提交超过 512 KiB");
      return recorded(await api("/api/project",raw));
    },(result,receipt)=>{
      result.append(node("p","实例已保存；尚未执行本页检查，不表示规则通过。请从新窗口读取后选择检查。"));
      details(result,"保存回执与版本绑定",pretty(receipt));
    },"save-project");
  } else {
    document.getElementById("forms").append(node("p","候选原件未通过形式检查，无法保存可执行实例；仍可回答或提交修订提案。"));
  }
  for (const entry of view.projects) {
    submitForm(`检查库存完整性 · ${entry.project.id}`, f=>{
      f.append(node("p",`用途 ${entry.purpose}；检查结构与库存不变量，不运行资格操作。结果不保存为跨版本报告，也不证明历史保留。`));
      details(f,"实例与检查绑定",pretty({project_ref:entry.ref,definition_ref:entry.definition_ref,
        candidate_ref:entry.candidate_ref,expected_review_ref:view.review_ref}));
      return ()=>({project_ref:entry.ref,expected_review_ref:view.review_ref});
    },query=>api("/api/project/check",query),(result,response)=>{
      if(response.check.status!=="checked") throw new Error("unexpected_receipt: 未收到检查报告");
      result.append(node("p","本次检查已执行；请逐项查看 satisfied / violated / unknown / error / not_applicable，不等于整体语义通过。"));
      section(response.presentation,result);
      details(result,"完整检查结果及绑定（精确原值）",response.exact_details);
    },"check-project");
    if(definition && definition.schema_version==="finite-domain/0.2") {
      submitForm(`操作资格检查 · ${entry.project.id}`,f=>{
        f.append(node("p","仅检查所选操作与目标的资格；不会提交、执行操作或改变实例，也不证明历史已保留。库存完整性请单独检查。"));
        const choices=[];
        for(const [key,label,values] of [["operation","操作标识",[...new Set(view.rules.filter(r=>r.scope==="eligibility").map(r=>r.operation))]],
          ["target","目标对象",entry.project.objects.map(o=>o.id)]]){
          const l=node("label",label),s=node("select");s.dataset.field=key;const empty=node("option","请明确选择");empty.value="";s.append(empty);
          for(const value of values){const option=node("option",value);option.value=value;s.append(option);}l.append(s);f.append(l);choices.push([key,s]);
        }
        return ()=>{const values=Object.fromEntries(choices.map(([key,s])=>[key,s.value]));
          if(!values.operation || !values.target)throw new Error("请明确选择操作与目标，尚未检查。");
          return {project_ref:entry.ref,expected_review_ref:view.review_ref,...values};};
      },query=>api("/api/project/eligibility",query),(result,response)=>{
        if(response.check.status!=="checked" || response.check.scope!=="eligibility" || response.check.action_execution!=="not_run")throw new Error("unexpected_receipt: 资格检查回执不完整");
        result.append(node("p",`操作 ${response.check.operation} · 目标 ${response.check.target} · 仅资格检查；操作执行 not_run，未提交。`));
        section(response.presentation,result);details(result,"资格/实例/候选/审阅绑定及完整结果",response.exact_details);
      },"check-eligibility");
    }
  }
  for (const proposal of view.proposals) {
    if (proposal.inspection.status!=="valid") {
      document.getElementById("forms").append(node("p",`提案 ${proposal.ref.artifact_id} 未通过形式检查，不能采纳。原件及诊断仍在提案详情中。`));
      continue;
    }
    submitForm(`明确采纳提案 ${proposal.ref.artifact_id}`,f=>{
      f.append(node("p","此操作将建立后继候选；旧原件、回答与未决留在历史中。新候选不会继承旧确认或实例检查结果；合法不代表忠实表达需求。"));
      details(f,"即将采纳的完整原件",proposal.text);
      details(f,"采纳前候选与提案来源",pretty({candidate_ref:view.candidate_ref,proposal_ref:proposal.ref,
        based_on_review_ref:proposal.based_on_review_ref,provenance:proposal.provenance}));
      if(proposal.revision_context)details(f,"生成时冻结的方法身份",pretty({version:proposal.revision_context.method_instructions_version,
        sha256:proposal.revision_context.method_instructions_sha256,revision_ref:proposal.revision_context.ref}));
      const reason=input(f,"采纳理由（必填）");
      const label=node("label"), consent=node("input");consent.type="checkbox";
      label.append(consent,document.createTextNode("我已复核完整提案，明确建立后继候选"));f.append(label);
      return ()=>{if(!consent.checked)throw new Error("尚未明确采纳；未提交。");return {text:reason.value};};
    },async fields=>recorded(await api("/api/adopt",{schema_version:"model-review-adoption/0.1",...binding(view,actor),
      proposal_ref:proposal.ref,text:fields.text})),(result,receipt)=>{
      if(!receipt.next_candidate_ref)throw new Error("unexpected_receipt: 缺少后继候选引用");
      result.append(node("p",`采纳已记录：候选版本 ${view.candidate_ref.revision} → ${receipt.next_candidate_ref.revision}。这不表示需求语义通过。`));
      const link=node("a","在新窗口查看后继候选与历史");link.href="/#candidate="+encodeURIComponent(receipt.next_candidate_ref.revision);
      link.target="_blank";link.rel="noopener";result.append(link);details(result,"采纳回执与来源绑定",pretty(receipt));
    },"adopt-proposal");
  }
}
function revisionExport(view) {
  const panel=node("section");panel.id="revision-export";panel.append(node("h2","导出回答修订材料"),
    node("p","选择已保存的答复或拒答。下载包含原文、候选原件、问题、回答和完整审阅绑定；尚未调用语言服务，不会产生新候选。历史回答保留原候选来源。"));
  const choices=[];
  if([...view.history.map(h=>h.view),view].some(v=>v.actions.some(a=>a.action.schema_version==="model-review-clarification/0.1")))
    panel.append(node("p","此处现有下载只包含普通答复/拒答。外加澄清的执行修订材料由 A 的独立入口准备，本页未接该下载接口；它们仍完整保存在审阅与历史中。"));
  for(const snapshot of [...view.history.map(h=>h.view),view]) for(const entry of snapshot.actions) {
    if(!["answer","decline"].includes(entry.action.kind))continue;
    const label=node("label"),box=node("input");box.type="checkbox";
    const question=snapshot.questions.find(q=>q.ref.artifact_id===entry.action.question_ref.artifact_id);
    label.append(box,document.createTextNode(`候选 ${snapshot.candidate_ref.revision} · ${question?question.text:entry.action.question_ref.artifact_id} · ${entry.action.kind==="answer"?"答复":"拒答"} · ${entry.action.text || "（空拒答）"}`));
    panel.append(label);details(panel,"问题、动作及来源引用",pretty({question_ref:entry.action.question_ref,action_ref:entry.provenance.action_ref,
      candidate_ref:entry.action.candidate_ref,source_ref:snapshot.source_ref}));choices.push({box,ref:entry.provenance.action_ref});
  }
  if(!choices.length)panel.append(node("p","尚无已保存的答复或拒答；提交后在新窗口读取再选择。"));
  const button=node("button","下载完整修订材料"),result=node("div");button.type="button";result.setAttribute("role","status");
  button.onclick=async()=>{
    button.disabled=true;result.className="result";result.textContent="正在核验所选记录…";
    try {
      const refs=choices.filter(x=>x.box.checked).map(x=>x.ref);
      if(!refs.length)throw new Error("请选择至少一条已保存的答复或拒答。");
      const response=await api("/api/revision/export",{expected_review_ref:view.review_ref,action_refs:refs});
      // Download the exact server string, never reconstruct numbers from parsed envelope data.
      const url=URL.createObjectURL(new Blob([response.envelope_text],{type:"application/json;charset=utf-8"}));
      const link=node("a","再次下载完整材料");link.href=url;link.download="revision-context.json";
      result.replaceChildren(node("p","材料已核验并准备下载；等待后续调用，尚无新候选。"),link);
      details(result,"完整导出材料（精确原文）",response.envelope_text);link.click();
      // Keep the link usable for this page; release old URLs when making another export.
      if(panel.dataset.downloadUrl)URL.revokeObjectURL(panel.dataset.downloadUrl);
      panel.dataset.downloadUrl=url;
    }catch(error){result.className="result error";result.textContent="导出失败；选择保留，不自动重试。\n"+error.message;}
    finally{button.disabled=false;}
  };
  panel.append(button,result);document.getElementById("offline-tools").append(panel);
}
function applicationAssessment(parent, assessment) {
  parent.replaceChildren(node("h3",assessment.generation_ready?"配置已就绪，尚未生成应用":"配置仍是草稿，请处理以下阻碍"));
  const names={missing_spec_confirmation:"尚未明确确认这份确切配置",spec_confirmation_binding:"确认与配置内容不匹配，需重新准备并明确确认",
    missing_successful_public_acceptance:"缺少完整实例且全部满足或不适用的公开成功样例",acceptance_outcome_mismatch:"公开样例的预期与实际检查不一致",
    initial_project_not_successful:"初始实例含违反、未知、错误或不完整人口",missing_initial_data_decision:"请选择已保存初始实例，或填写不使用初始数据的理由",
    required_domain_residual:"候选仍有必须处理的残余",unresolved_candidate_issues:"候选问题尚未解决",required_unresolved:"配置仍有必须解决的事项",
    unsupported_requirements:"配置仍含当前不支持的需求",candidate_rejected:"候选未通过形式检查",missing_edit_scope:"请明确可编辑的实体、字段和关系",
    missing_config_evidence:"请为全部七类配置填写来源与理由",missing_public_acceptance:"请填写公开验收样例及完整检查预期",
    public_acceptance_binding:"公开样例来源、内容摘要或说明不完整",missing_storage:"请明确本地保存配置",missing_access:"请明确访问和允许的操作",
    missing_tasks:"编辑、检查、保存、载入四类任务尚未齐全",missing_or_duplicate_views:"视图缺失或标识重复",missing_or_duplicate_tasks:"任务缺失或标识重复",
    unsafe_storage_path:"保存位置必须是安全的相对 JSON 路径",initial_project_binding:"初始实例不属于当前候选与定义"};
  for(const code of assessment.blockers)parent.append(node("p",names[code] || (code.startsWith("binding:")?"配置绑定已过期："+code.slice(8):"请核对配置项："+code)));
  details(parent,"完整就绪检查与配置内容摘要",pretty(assessment));
}
async function applicationEditor(view, template) {
  const panel=node("section");panel.id="application-spec";
  if(template===null) {
    panel.append(node("h2","当前候选不支持应用配置"),node("p","应用配置入口仅支持旧版有限定义。当前新版本或非法候选不能填旧版表单、准备、确认或保存应用配置；原件仍可审阅。资格检查不能替代应用许可。"));
    document.getElementById("offline-tools").append(panel);return;
  }
  panel.append(node("h2","准备应用配置"),node("p","先编辑并保存草稿，再准备未用过的下一版本。阅读准备后的完整配置，主动确认后再次保存，并在新窗口重新读取就绪结果。此处不生成或运行应用。"),
    node("p","配置必须明确初始数据、可编辑内容、四种任务、视图、保存位置、访问方式和公开验收样例，并逐项提供真实来源。未知或负向检查不会变成通过。"));
  const guide=`所有顶层字段均保留。id 为同一应用的稳定标识，version 每次更改保存须使用新值；五个来源/审阅引用必须与当前记录一致，不能任意填 hash。
initial_project_ref：选择本页已保存实例的 ref；否则 null 并写 no_initial_data_reason（两者不能同时填写）。
edit_scope：{entities:[实体ID],fields:[字段ID],relations:[关系ID]}。
views：[{id,title,entities,fields,relations}]；必须覆盖编辑范围。
tasks：[{id,action,view_id}]；action 包含 edit、check、save、load，view_id 指向 views 的 id。
storage：{kind:"local_json",relative_path:"你明确选择的相对文件.json",retention:"retain_all_versions"}。
access：{bind:"127.0.0.1",audience:"single_local_user",credential:"session_token",allowed_actions:["edit","check","save","load"]}；这是明确选择，模板不会替你授权。
evidence：[{area,ref,quote,reason}]；area 覆盖 initial_project、edit_scope、tasks、views、storage、access、acceptance。ref 取原文或实际保存动作引用，quote 必须是该来源的完整原话，reason 写配置依据。来源匹配不代表理解正确，仍需你复核。
acceptance_cases：[{ref,description,public:true,steps:["edit","check","save","load"],project,expected_outcomes:[{obligation,target,status}]}]。project 是完整实例；expected_outcomes 按实际检查报告完整顺序填写，不能省略 unknown/error。至少一例人口完整且全部 satisfied/not_applicable。ref 含 project_id、artifact_id、revision、content_hash；准备按钮计算内容摘要，可先填 64 个0。它不会生成检查预期或改掉不利结果。
required_unresolved / unsupported_requirements：字符串数组，如实保留未解决/不支持需求。confirmation_refs 由明确确认回执写入。
JSON 内的 Int64 数值按原文处理；不要用浏览器 Number 重建配置。准备按钮只改变显式版本号、公开样例摘要；确认仅更新审阅及确认引用。`;
  details(panel,"字段结构与填写方法",guide);
  details(panel,"可引用的原文及实际用户记录",pretty({source_ref:view.source_ref,source_text:view.source_text,
    saved_projects:view.projects.map(p=>({ref:p.ref,purpose:p.purpose,id:p.project.id})),
    actions:[...view.history.map(h=>h.view),view].flatMap(v=>v.actions.filter(a=>a.action.schema_version==="model-review/0.1").map(a=>({ref:a.provenance.action_ref,text:a.action.text})))}));
  const editor=input(panel,"完整应用配置 JSON（保留精确数值）",22);editor.id="spec-json";
  const next=input(panel,"准备时使用的版本号（留空保留当前；改动后保存须用未使用过的版本）",1);next.id="spec-version";
  const templateButton=node("button","填入未配置结构模板"),save=node("button","保存当前草稿"),prepare=node("button","准备确切配置"),confirm=node("button","明确确认这份配置");
  for(const b of [templateButton,save,prepare,confirm])b.type="button";
  save.id="spec-save";prepare.id="spec-prepare";confirm.id="spec-confirm";
  const consentLabel=node("label"),consent=node("input");consent.type="checkbox";consent.id="spec-consent";
  consentLabel.append(consent,document.createTextNode("我已阅读下方准备后的完整配置，明确同意此内容作为应用配置（一般候选确认不算）"));
  const preview=node("div"),assessment=node("div"),result=node("div");preview.id="spec-preview";assessment.id="spec-assessment";
  result.id="spec-result";result.className="result";result.setAttribute("role","status");
  panel.append(templateButton,save,prepare,preview,consentLabel,confirm,assessment,result);
  document.getElementById("offline-tools").append(panel);
  let head=null,prepared=null,loaded=false;
  const invalidate=()=>{prepared=null;consent.checked=false;confirm.disabled=true;preview.replaceChildren(node("p","输入改变后需要重新准备并阅读配置。"));};
  editor.oninput=invalidate;next.oninput=invalidate;
  consent.onchange=()=>{confirm.disabled=!prepared || !consent.checked;};
  templateButton.onclick=()=>{editor.value=template || "";invalidate();};
  const body=extra=>JSON.stringify({expected_spec_ref:head,...extra}).slice(0,-1)+',"spec":'+editor.value+'}';
  async function run(work) {
    if(!loaded)return;
    for(const control of [templateButton,save,prepare,confirm,editor,next,consent])control.disabled=true;
    result.className="result";result.textContent="正在核验；尚未收到成功回执…";
    try{await work();}catch(error){result.className="result error";result.textContent="操作失败；草稿保留，不自动换版本或重发。请从新窗口核对最新记录。\n"+error.message;}
    finally{for(const control of [templateButton,save,prepare,editor,next,consent])control.disabled=false;confirm.disabled=!prepared || !consent.checked;}
  }
  prepare.onclick=()=>run(async()=>{
    const response=await api("/api/spec/prepare",body({next_version:next.value.trim() || null}));
    editor.value=response.spec_text;next.value="";prepared={text:response.spec_text,hash:response.content_hash};consent.checked=false;
    preview.replaceChildren(node("h3","请阅读即将确认的完整配置"));details(preview,"确切配置内容",response.spec_text,true);
    applicationAssessment(assessment,response.assessment);result.textContent="准备完成；尚未确认，也未保存。请阅读配置后主动勾选确认。";
  });
  confirm.onclick=()=>run(async()=>{
    if(!prepared || !consent.checked || prepared.text!==editor.value)throw new Error("请重新准备并明确确认当前内容。");
    const response=await api("/api/spec/confirm",body({content_hash:prepared.hash,id:crypto.randomUUID()}));
    recorded(response.receipt);editor.value=response.spec_text;invalidate();assessment.replaceChildren();
    result.replaceChildren(node("p","确切配置确认已记录；应用草稿尚未保存，请点击保存当前草稿。其他旧表单仍绑定旧审阅版本。"));
    details(result,"真实确认回执",pretty(response.receipt));
  });
  save.onclick=()=>run(async()=>{
    const response=recorded(await api("/api/spec/save",body({})));
    head=response.spec_ref;editor.value=response.spec_text;invalidate();applicationAssessment(assessment,response.assessment);
    result.replaceChildren(node("p","应用配置已保存；请在新窗口重新读取。就绪仅代表当前检查无阻碍，尚未生成或验收应用。"));
    details(result,"已保存版本与历史引用",pretty({spec_ref:head,history_refs:response.history_refs}));
  });
  try {
    const response=await api("/api/spec");
    if(response.status==="not_saved") {editor.value=template || "";result.textContent="尚无已保存配置；模板未选择权限、任务或数据。先填写 id、version 与所需内容。";}
    else {head=response.spec_ref;editor.value=response.spec_text;applicationAssessment(assessment,response.assessment);
      result.textContent=`已重新读取配置版本 ${head.revision}。修改保存前请准备新的版本。`;
      details(panel,"已保存配置版本链",pretty({spec_ref:head,history_refs:response.history_refs}));}
    loaded=true;invalidate();templateButton.disabled=!template;
  }catch(error){result.className="result error";result.textContent="配置读取失败；未使用空草稿替代。"+error.message;
    for(const b of [templateButton,save,prepare,confirm])b.disabled=true;}
}
document.getElementById("layout").onclick = () => document.getElementById("panels").classList.toggle("single");
(async () => {
  try {
    const {view, presentation, history_presentation, actor, whole_candidate, spec_template} = await api("/api/review");
    const versions=[...view.history.map((entry,i)=>({view:entry.view,presentation:history_presentation[i],adoption:entry.adoption})),
      {view,presentation,adoption:null}];
    const select=document.getElementById("version-select");
    for(let i=0;i<versions.length;i++) {
      const v=versions[i].view,option=node("option",`候选 ${v.candidate_ref.revision} · 审阅 ${v.review_ref.revision}${i===versions.length-1?"（本页载入的当前版本）":"（历史，只读）"}`);
      option.value=String(i);select.append(option);
    }
    function show(index) {
    const selected=versions[index],v=selected.view,current=index===versions.length-1;
    document.getElementById("panels").replaceChildren();
    document.getElementById("identity").replaceChildren(node("h2","身份与状态"));
    document.getElementById("actions").hidden=!current;
    document.getElementById("version-state").textContent=current?"当前候选；提交仍绑定本页载入版本，外部变化会产生冲突。":"历史候选只读；返回当前版本后原草稿仍保留。旧实例结果不适用于后继候选。";
    const source=document.getElementById("adoption-source");source.replaceChildren();
    if(index>0) {
      const origin=view.history[index-1].adoption;
      source.append(node("p",`由候选 ${origin.candidate_ref.revision} 经 ${origin.actor} 明确采纳而来。理由：${origin.text}`));
      details(source,"此版本的完整采纳来源",pretty(origin));
    }
    if(selected.adoption)details(source,"从此历史版本建立后继的采纳记录",pretty(selected.adoption));
    if(v.parent_candidate_ref)details(source,"前序候选引用",pretty(v.parent_candidate_ref));
    const identity = {project_id:v.project_id, actor, review_ref:v.review_ref,
      request_ref:v.request_ref, source_ref:v.source_ref, candidate_ref:v.candidate_ref,
      definition_ref:v.definition_ref, revision_status:v.revision_status,
      requirement_fidelity:v.requirement_fidelity, instance_conformance:v.instance_conformance,
      next_candidate_ref:v.next_candidate_ref};
    const identitySection = document.getElementById("identity");
    identitySection.append(node("p", `项目 ${v.project_id} · 审阅版本 ${v.review_ref.revision} · 候选版本 ${v.candidate_ref.revision}`),
      node("p", `形式检查 ${v.inspection.status} · 用户确认 ${v.confirmations.length} 条 · 修订 ${v.revision_status} · 归属 ${actor}`),
      node("p", `意图忠实性 ${v.requirement_fidelity} · 已保存实例检查状态 ${v.instance_conformance}（即时报告见检查表单，不缓存为通过结论）`));
    details(identitySection, "完整身份、版本与哈希", pretty(identity));
    for (const part of selected.presentation) section(part);
    }
    select.onchange=()=>show(Number(select.value));
    const requested=new URLSearchParams(location.hash.slice(1)).get("candidate");
    const requestedIndex=versions.findIndex(x=>x.view.candidate_ref.revision===requested);
    select.value=String(requestedIndex<0?versions.length-1:requestedIndex);show(Number(select.value));
    forms(view, actor, whole_candidate);
    revisionExport(view);
    await applicationEditor(view,spec_template);
    document.getElementById("load-state").textContent = "已读取并核验本地保存记录。此页绑定所列版本。";
  } catch (error) {
    const state = document.getElementById("load-state"); state.className = "error";
    state.textContent = "读取失败；未使用缓存或空候选替代。" + error.message;
  }
})();
