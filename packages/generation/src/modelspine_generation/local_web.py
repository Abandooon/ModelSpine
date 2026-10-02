"""Deterministic local-project-web/0.1 plan and static page; no filesystem writes."""
from dataclasses import dataclass
from html import escape

from modelspine_protocols import digest, require, to_data
from modelspine_protocols.application import assess_application

TEMPLATE = "local-project-web-template/0.1"


@dataclass(frozen=True)
class LocalWebPlan:
    spec: dict
    spec_ref: dict
    definition: dict
    initial_project: dict | None
    assessment: dict
    input_hash: str


def plan(spec, spec_ref, verified_review_view, *, checker):
    assessment = assess_application(spec, verified_review_view, checker=checker)
    require(assessment["generation_ready"], "generation blocked: " + ",".join(assessment["blockers"]), "draft")
    require(spec_ref.content_hash == digest(spec) and spec_ref.project_id == spec.project_id
            and spec_ref.artifact_id == "application/" + spec.id and spec_ref.revision == spec.version,
            "spec reference mismatch", "conflict")
    definition = verified_review_view["inspection"]["checks"]["candidate"]["definition"]
    initial = None
    if spec.initial_project_ref is not None:
        initial = next(p["project"] for p in verified_review_view["projects"] if p["ref"] == to_data(spec.initial_project_ref))
    inputs = {"spec": to_data(spec), "spec_ref": to_data(spec_ref), "definition": definition,
              "initial_project": initial, "review_hash": digest(verified_review_view)}
    return LocalWebPlan(inputs["spec"], inputs["spec_ref"], definition, initial, assessment, digest(inputs))


def render(plan):
    """Views and task labels come only from the approved spec; JSON stays text."""
    options = "".join('<option value="' + escape(v["id"], quote=True) + '">' + escape(v["title"]) + '</option>'
                      for v in plan.spec["views"])
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Local project editor</title>
<link rel="stylesheet" href="/style.css"><main><h1>Local project editor</h1>
<p>Edit the complete ProjectModel JSON. Values are checked on the server; saving is explicit.</p>
<label>View <select id="view">''' + options + '''</select></label>
<p id="scope"></p><p id="version">Connect using the session URL printed by the service.</p>
<label for="project">ProjectModel JSON (integer digits are preserved)</label>
<textarea id="project" spellcheck="false" rows="22"></textarea><div id="tasks"></div>
<p id="status" role="status"></p><pre id="report"></pre>
<p>All saved versions are retained locally. Migration and automatic rollback are unsupported.</p>
</main><script src="/client.js"></script></html>'''
    return {"index.html": page.encode("utf-8"), "client.js": CLIENT.encode("utf-8"),
            "style.css": STYLE.encode("utf-8")}


CLIENT = r'''"use strict";
const token = location.hash.slice(1);
history.replaceState(null, "", "/");
let revision = null, settings = null;
const el = id => document.getElementById(id);
async function request(route, body) {
  const response = await fetch(route, {method: body === undefined ? "GET" : "POST",
    headers: {"X-Session-Token": token, ...(body === undefined ? {} : {"Content-Type":"application/json"})},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}), redirect: "error"});
  const result = await response.json();
  el("status").textContent = String(response.status) + " " + result.status;
  el("report").textContent = JSON.stringify(result.report || result, null, 2);
  if (!response.ok) throw new Error(result.message || result.status);
  return result;
}
function tasks() {
  const view = settings.views.find(v => v.id === el("view").value);
  el("scope").textContent = "Editable in this view: " + JSON.stringify({entities:view.entities, fields:view.fields, relations:view.relations});
  el("tasks").replaceChildren();
  for (const task of settings.tasks.filter(t => t.view_id === view.id)) {
    const button = document.createElement("button"); button.textContent = task.id + " (" + task.action + ")";
    button.dataset.action = task.action;
    button.onclick = async () => {
      try {
        if (task.action === "edit") { el("project").focus(); return; }
        const body = {task_id:task.id, expected_revision:revision, project_text:el("project").value};
        const result = await request("/api/" + task.action, body);
        if (task.action === "load" || task.action === "save") {
          revision = result.revision; el("project").value = result.project_text === null ? "" : result.project_text;
          el("version").textContent = "Saved revision: " + revision;
        }
      } catch (error) { el("status").textContent += " — " + error.message; }
    };
    el("tasks").append(button);
  }
}
el("view").onchange = tasks;
request("/api/state").then(result => { settings=result.settings; revision=result.revision;
  el("project").value=result.project_text === null ? "" : result.project_text;
  el("version").textContent="Saved revision: " + revision; tasks();
}).catch(error => {el("status").textContent += " — " + error.message;});
'''

STYLE = '''body{font:16px system-ui;background:#f3f5f7;color:#172334;margin:0}main{max-width:1000px;margin:2rem auto;padding:1.5rem;background:white;border-radius:12px}textarea{box-sizing:border-box;width:100%;font:14px monospace;margin:1rem 0}button,select{font:inherit;padding:.6rem;margin:.3rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf1f5;padding:1rem}#status{font-weight:bold}'''
