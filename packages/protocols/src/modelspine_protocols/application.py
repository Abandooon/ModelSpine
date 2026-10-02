"""Closed contract for one local ProjectModel editor, not a general ApplicationSpec."""
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from modelspine_protocols import ArtifactRef, checked, decode, digest, require, to_data, validate_artifact_ref
from modelspine_protocols.domain_language import DomainDefinition, ProjectModel
from modelspine_protocols.review import WHOLE_CANDIDATE

Action = Literal["edit", "check", "save", "load"]
ACTIONS = {"edit", "check", "save", "load"}
AREAS = {"initial_project", "edit_scope", "tasks", "views", "storage", "access", "acceptance"}


@dataclass(frozen=True)
class EditScope:
    entities: tuple[str, ...]
    fields: tuple[str, ...]
    relations: tuple[str, ...]


@dataclass(frozen=True)
class WebTask:
    id: str
    action: Action
    view_id: str


@dataclass(frozen=True)
class WebView:
    id: str
    title: str
    entities: tuple[str, ...]
    fields: tuple[str, ...]
    relations: tuple[str, ...]


@dataclass(frozen=True)
class LocalStorage:
    kind: Literal["local_json"]
    relative_path: str
    retention: Literal["retain_all_versions"]


@dataclass(frozen=True)
class LocalAccess:
    bind: Literal["127.0.0.1"]
    audience: Literal["single_local_user"]
    credential: Literal["session_token"]
    allowed_actions: tuple[Action, ...]


@dataclass(frozen=True)
class ConfigEvidence:
    area: Literal["initial_project", "edit_scope", "tasks", "views", "storage", "access", "acceptance"]
    ref: ArtifactRef
    quote: str
    reason: str


@dataclass(frozen=True)
class ExpectedOutcome:
    obligation: str
    target: str
    status: Literal["satisfied", "violated", "unknown", "not_applicable", "error"]


@dataclass(frozen=True)
class PublicAcceptance:
    ref: ArtifactRef
    description: str
    public: bool
    steps: tuple[Action, ...]
    project: ProjectModel
    expected_outcomes: tuple[ExpectedOutcome, ...]


@dataclass(frozen=True)
class LocalWebSpec:
    schema_version: Literal["local-project-web/0.1"]
    id: str
    version: str
    project_id: str
    request_ref: ArtifactRef
    source_ref: ArtifactRef
    definition_ref: ArtifactRef
    candidate_ref: ArtifactRef
    review_ref: ArtifactRef
    initial_project_ref: ArtifactRef | None
    no_initial_data_reason: str | None
    edit_scope: EditScope | None
    tasks: tuple[WebTask, ...]
    views: tuple[WebView, ...]
    storage: LocalStorage | None
    access: LocalAccess | None
    evidence: tuple[ConfigEvidence, ...]
    acceptance_cases: tuple[PublicAcceptance, ...]
    confirmation_refs: tuple[ArtifactRef, ...]
    required_unresolved: tuple[str, ...]
    unsupported_requirements: tuple[str, ...]


def spec_content_hash(spec):
    body = to_data(checked(spec, LocalWebSpec))
    # Confirmation changes the review head; these two are binding metadata,
    # not approved generation settings. All other fields remain covered.
    del body["review_ref"]
    del body["confirmation_refs"]
    return digest(body)


def acceptance_digest(case):
    body = to_data(checked(case, PublicAcceptance))
    del body["ref"]
    return digest(body)


def validate_spec(spec):
    spec = checked(spec, LocalWebSpec)
    require(all(s.strip() for s in (spec.id, spec.version, spec.project_id)), "empty spec identity")
    refs = [spec.request_ref, spec.source_ref, spec.definition_ref, spec.candidate_ref, spec.review_ref,
            *spec.confirmation_refs, *(x.ref for x in spec.evidence), *(x.ref for x in spec.acceptance_cases)]
    if spec.initial_project_ref is not None:
        refs.append(spec.initial_project_ref)
    for ref in refs:
        validate_artifact_ref(ref)
        require(ref.project_id == spec.project_id, "cross-project spec reference", "conflict")
    require(len(spec.tasks) <= 32 and len(spec.views) <= 32 and len(spec.acceptance_cases) <= 16
            and len(spec.evidence) <= 64, "spec collection limit", "unsupported")
    require(len(str(to_data(spec)).encode("utf-8")) <= 2 * 1024 * 1024, "spec size limit", "unsupported")
    return spec


def assess_application(spec, verified_review_view, *, checker=None):
    """Pure contract assessment; host supplies a replay-verified view and checker.

    No filesystem or apps import. An absent checker cannot verify acceptance.
    """
    spec = validate_spec(spec)
    view = verified_review_view
    blockers = []
    def need(condition, code):
        if not condition and code not in blockers:
            blockers.append(code)
    for key in ("request_ref", "source_ref", "definition_ref", "candidate_ref", "review_ref"):
        need(to_data(getattr(spec, key)) == view[key], "binding:" + key)
    need(spec.project_id == view["project_id"], "binding:project_id")
    need(view["inspection"]["status"] == "valid", "candidate_rejected")
    need(not spec.required_unresolved, "required_unresolved")
    need(not spec.unsupported_requirements, "unsupported_requirements")
    need(not any(x["required"] for x in view["residuals"]), "required_domain_residual")
    need(not view["issues"], "unresolved_candidate_issues")
    initial_entry = None
    if spec.initial_project_ref is None:
        need(bool(spec.no_initial_data_reason and spec.no_initial_data_reason.strip()), "missing_initial_data_decision")
    else:
        need(spec.no_initial_data_reason is None, "ambiguous_initial_data_decision")
        initial_entry = next((p for p in view["projects"] if p["ref"] == to_data(spec.initial_project_ref)
                              and p["candidate_ref"] == view["candidate_ref"] and p["definition_ref"] == view["definition_ref"]), None)
        need(initial_entry is not None, "initial_project_binding")
    definition = None
    if view["inspection"]["status"] == "valid":
        definition = decode(DomainDefinition, view["inspection"]["checks"]["candidate"]["definition"])
        entities = {e.id for e in definition.entities}
        fields = {f.id for e in definition.entities for f in e.fields}
        relations = {r.id for r in definition.relations}
        scope = spec.edit_scope
        need(scope is not None and bool(scope.entities), "missing_edit_scope")
        if scope is not None:
            for name, known in (("entities", entities), ("fields", fields), ("relations", relations)):
                ids = getattr(scope, name)
                need(len(set(ids)) == len(ids) and set(ids) <= known, "invalid_edit_scope:" + name)
            need(all(f.id not in scope.fields or e.id in scope.entities for e in definition.entities for f in e.fields), "field_owner_scope")
            need(all(r.id not in scope.relations or {r.source, r.target} <= set(scope.entities) for r in definition.relations), "relation_endpoint_scope")
    def successful(report, project):
        return (project.population_complete and definition is not None
                and not any(r.required for r in definition.residuals)
                and all(o["status"] in ("satisfied", "not_applicable") for o in report["outcomes"]))
    if initial_entry is not None:
        if checker is None or definition is None:
            need(False, "initial_project_not_checked")
        else:
            try:
                initial = decode(ProjectModel, initial_entry["project"])
                initial_report = to_data(checker(definition, initial, project_id=view["project_id"]))
                need(successful(initial_report, initial), "initial_project_not_successful")
            except ValueError:
                need(False, "invalid_initial_project")
    need(bool(spec.views) and len({v.id for v in spec.views}) == len(spec.views), "missing_or_duplicate_views")
    need(bool(spec.tasks) and len({t.id for t in spec.tasks}) == len(spec.tasks), "missing_or_duplicate_tasks")
    need({t.action for t in spec.tasks} == ACTIONS, "missing_tasks")
    need(all(t.id.strip() and t.view_id in {v.id for v in spec.views} for t in spec.tasks), "task_view_binding")
    if spec.edit_scope is not None:
        for name in ("entities", "fields", "relations"):
            desired = set(getattr(spec.edit_scope, name))
            need(all(set(getattr(v, name)) <= desired and len(set(getattr(v, name))) == len(getattr(v, name)) for v in spec.views), "invalid_view_scope:" + name)
            need(set(x for v in spec.views for x in getattr(v, name)) == desired, "uncovered_view_scope:" + name)
    need(all(v.id.strip() and v.title.strip() for v in spec.views), "empty_view_identity")
    need(spec.storage is not None, "missing_storage")
    if spec.storage:
        path = spec.storage.relative_path
        parts = path.split("/")
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{x}" for x in range(1, 10)), *(f"LPT{x}" for x in range(1, 10))}
        need(bool(path) and len(path) <= 256 and not PurePosixPath(path).is_absolute() and "\\" not in path and ":" not in path
             and not any(ord(c) < 32 or c in '<>"|?*' for c in path)
             and all(p not in ("", ".", "..") and p.rstrip(" .") == p and p.split(".")[0].upper() not in reserved for p in parts)
             and path.endswith(".json"), "unsafe_storage_path")
    need(spec.access is not None, "missing_access")
    if spec.access:
        need(set(spec.access.allowed_actions) == ACTIONS and len(spec.access.allowed_actions) == 4, "access_actions")
    sources = [(view["source_ref"], view["source_text"])]
    for snapshot in (view, *(h["view"] for h in view["history"])):
        sources.extend((x["provenance"]["action_ref"], x["action"]["text"]) for x in snapshot["actions"])
    need({e.area for e in spec.evidence} == AREAS, "missing_config_evidence")
    for evidence in spec.evidence:
        need(bool(evidence.reason.strip()) and bool(evidence.quote.strip())
             and any(ref == to_data(evidence.ref) and text == evidence.quote for ref, text in sources), "config_evidence_binding:" + evidence.area)
    need(bool(spec.acceptance_cases), "missing_public_acceptance")
    need(len({(c.ref.artifact_id, c.ref.revision) for c in spec.acceptance_cases}) == len(spec.acceptance_cases),
         "duplicate_public_acceptance")
    successful_acceptance = False
    for case in spec.acceptance_cases:
        need(case.public and bool(case.description.strip()) and case.ref.content_hash == acceptance_digest(case), "public_acceptance_binding")
        need(case.steps == ("edit", "check", "save", "load") and bool(case.expected_outcomes), "acceptance_steps_or_expectations")
        need(to_data(case.project.definition) == view["definition_ref"], "acceptance_definition_binding")
        if checker is None or definition is None:
            need(False, "acceptance_not_checked")
        else:
            try:
                report = to_data(checker(definition, case.project, project_id=view["project_id"]))
                observed = [{k: outcome[k] for k in ("obligation", "target", "status")} for outcome in report["outcomes"]]
                need(observed == to_data(case.expected_outcomes), "acceptance_outcome_mismatch")
                if (case.public and case.ref.content_hash == acceptance_digest(case)
                        and observed == to_data(case.expected_outcomes) and case.expected_outcomes
                        and successful(report, case.project)):
                    successful_acceptance = True
            except ValueError:
                need(False, "invalid_acceptance_project")
    need(successful_acceptance, "missing_successful_public_acceptance")
    approval = "approve-local-web-spec:" + spec_content_hash(spec)
    confirmations = {digest(c["provenance"]["action_ref"]): c for c in view["confirmations"]}
    need(bool(spec.confirmation_refs), "missing_spec_confirmation")
    for ref in spec.confirmation_refs:
        confirmation = confirmations.get(digest(ref))
        need(confirmation is not None and confirmation["provenance"]["text"] == approval
             and confirmation["targets"] == [WHOLE_CANDIDATE], "spec_confirmation_binding")
    return {"status": "draft" if blockers else "generation_ready", "generation_ready": not blockers,
            "blockers": blockers, "spec_content_hash": spec_content_hash(spec)}
