"use strict";
const token = document.querySelector('meta[name="review-token"]').content;
const node = (tag, text) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n; };
const pretty = value => JSON.stringify(value, null, 2);
function details(parent, title, text, open=false) {
  const d = node("details"); d.open = open; d.append(node("summary", title), node("pre", text)); parent.append(d);
}
function section(part) {
  const s = node("section"); s.dataset.section = part.key; s.append(node("h2", part.title));
  for (const text of part.paragraphs) s.append(node("p", text));
  if (part.columns.length) {
    if (!part.rows.length) s.append(node("p", "本视图无此项；以检查状态为准，不表示检查通过。"));
    else {
      const wrap = node("div"); wrap.className = "table-scroll";
      const table = node("table"), head = node("thead"), tr = node("tr"), body = node("tbody");
      for (const text of part.columns) { const th = node("th", text); th.scope = "col"; tr.append(th); }
      head.append(tr);
      for (const row of part.rows) { const r = node("tr"); for (const text of row) r.append(node("td", text)); body.append(r); }
      table.append(head, body); wrap.append(table); s.append(wrap);
    }
  }
  details(s, "完整数据 / 原件详情", part.detail, part.open_detail);
  document.getElementById("panels").append(s);
}
async function api(path, action) {
  const response = await fetch(path, {method: action ? "POST" : "GET", cache: "no-store",
    headers: {"X-Review-Token": token, ...(action ? {"Content-Type":"application/json"} : {})},
    ...(action ? {body: JSON.stringify(action)} : {})});
  const body = await response.json();
  if (!response.ok) throw new Error(`${body.code}: ${body.reason}`);
  return body;
}
function input(form, label, rows=3) {
  const l = node("label", label), t = node("textarea"); t.rows = rows; l.append(t); form.append(l); return t;
}
function actionForm(title, view, actor, build) {
  const f = node("form"); f.append(node("h3", title));
  const result = node("p"); result.className = "result"; result.setAttribute("role", "status");
  const fields = build(f);
  const send = node("button", "提交记录"); send.type = "submit";
  const cancel = node("button", "取消草稿"); cancel.type = "button";
  cancel.onclick = () => { f.reset(); result.textContent = "已取消草稿；未提交。"; result.className = "result"; };
  f.append(send, cancel, result);
  f.onsubmit = async event => {
    event.preventDefault(); send.disabled = true; cancel.disabled = true;
    result.className = "result"; result.textContent = "正在保存，尚未收到回执…";
    try {
      const action = {schema_version: view.schema_version, id: crypto.randomUUID(), project_id: view.project_id,
        request_ref: view.request_ref, candidate_ref: view.candidate_ref, expected_review_ref: view.review_ref,
        question_ref: null, actor, text: "", targets: [], proposal_base64: null, ...fields()};
      const receipt = await api("/api/action", action);
      if (!["recorded", "already_recorded"].includes(receipt.status)) throw new Error("unexpected_receipt: 未收到记录确认");
      result.className = "result success";
      result.textContent = "已记录（未修订、未接受，候选未变）。请在新窗口读取最新记录后继续。\n" + pretty(receipt);
    } catch (error) {
      result.className = "result error";
      result.textContent = "未获得成功回执；草稿保留，不自动重发。请查看最新记录核对是否已落盘。\n" + error.message;
    } finally { send.disabled = false; cancel.disabled = false; }
  };
  document.getElementById("forms").append(f);
}
function forms(view, actor, whole) {
  for (const q of view.questions) {
    actionForm(`问题 ${q.id} · ${q.text}`, view, actor, f => {
      f.append(node("p", `状态：${q.status}；解决状态：${q.resolution}`));
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
}
document.getElementById("layout").onclick = () => document.getElementById("panels").classList.toggle("single");
(async () => {
  try {
    const {view, presentation, actor, whole_candidate} = await api("/api/review");
    const identity = {project_id:view.project_id, actor, review_ref:view.review_ref,
      request_ref:view.request_ref, source_ref:view.source_ref, candidate_ref:view.candidate_ref,
      definition_ref:view.definition_ref, revision_status:view.revision_status,
      requirement_fidelity:view.requirement_fidelity, instance_conformance:view.instance_conformance,
      next_candidate_ref:view.next_candidate_ref};
    const identitySection = document.getElementById("identity");
    identitySection.append(node("p", `项目 ${view.project_id} · 审阅版本 ${view.review_ref.revision} · 候选版本 ${view.candidate_ref.revision}（未变）`),
      node("p", `形式检查 ${view.inspection.status} · 用户确认 ${view.confirmations.length} 条 · 修订 ${view.revision_status} · 归属 ${actor}`),
      node("p", `意图忠实性 ${view.requirement_fidelity} · 实例检查 ${view.instance_conformance}`));
    details(identitySection, "完整身份、版本与哈希", pretty(identity));
    for (const part of presentation) section(part);
    forms(view, actor, whole_candidate);
    document.getElementById("load-state").textContent = "已读取并核验本地保存记录。此页绑定所列版本。";
  } catch (error) {
    const state = document.getElementById("load-state"); state.className = "error";
    state.textContent = "读取失败；未使用缓存或空候选替代。" + error.message;
  }
})();
