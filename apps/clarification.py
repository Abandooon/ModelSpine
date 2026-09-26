"""Sourced finite clarification and explicit successor-task acceptance."""
import argparse
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
bootstrap.activate(("requirements", "model-kernel", "assurance"))
sys.path.insert(0, str(bootstrap.PLATFORM / "adapters"))

from clarification_checks import goal, observe
from fixtures import load_case
from task_acceptance import SourcePath, TaskRunResult, _inside, run_task
from task_checks import check_tasks
from modelspine_assurance.tasks import PreparedTask, assess_task, prepare_task
from modelspine_kernel import ModelKernel
from modelspine_protocols import (
    ArtifactRef, ContractError, EvidenceRef, TaskBinding, TaskContract, TaskStatement,
    digest, dumps, loads, ref, require, to_data,
)
from modelspine_requirements import (
    AnswerRecord, AnsweredQuestion, ClarificationCase, Session, answer, artifact, prepare, propose,
)


@dataclass(frozen=True)
class ClarificationCard:
    schema_version: Literal["clarification-card/0.1"]
    parent: SourcePath
    case: SourcePath
    sources: tuple[SourcePath, ...]
    answers: tuple[SourcePath, ...]
    successor_version: str


@dataclass(frozen=True)
class RecordedArtifact:
    reference: ArtifactRef
    text: str


@dataclass(frozen=True)
class Derivation:
    parent: ArtifactRef
    case: ArtifactRef
    mapping: str
    answers: tuple[ArtifactRef, ...]
    successor: ArtifactRef


@dataclass(frozen=True)
class ClarificationRun:
    session: Session
    derivation: Derivation | None
    successor: TaskContract | None
    artifacts: tuple[RecordedArtifact, ...]
    run: TaskRunResult | None


def _evidence(reference, raw, origin):
    return EvidenceRef(reference, f"lines:1-{len(raw.decode('utf-8').splitlines())}", origin)


def derive_task(parent: PreparedTask, case: ClarificationCase, case_ref: ArtifactRef,
                answers: tuple[AnsweredQuestion, ...], version: str, sources):
    """Append answered goals only. Candidate state/selected operations are not inputs."""
    require(case_ref in sources and parent.task_ref in sources, "missing derivation inputs", "not_found")
    require(sha256(sources[case_ref]).hexdigest() == case_ref.content_hash
            and dumps(loads(ClarificationCase, sources[case_ref].decode("utf-8"))) == dumps(case)
            and (case.id, case.version) == (case_ref.artifact_id, case_ref.revision),
            "case bytes/identity mismatch", "conflict")
    require(prepare_task(sources[parent.task_ref], parent.task_ref, sources) == parent,
            "parent bytes changed", "conflict")
    require(case.task_ref == parent.task_ref and case.base == parent.contract.base,
            "clarification parent changed", "conflict")
    require(bool(version.strip()) and version != parent.contract.version, "successor needs a new version")
    require(parent.contract.plan is not None and bool(answers), "cannot derive without parent plan and answers")
    require(version != parent.contract.plan.version, "successor needs a new plan version")
    source_contents = dict(sources)
    statements, obligations, bindings, recorded = [], [], [], []
    existing_statements = {s.id for s in parent.contract.statements}
    existing_obligations = {o.id for o in parent.contract.plan.obligations}
    probe_table = {probe.id: probe for probe in case.probes}
    used = set()
    for item in answers:
        question, record = item.question, item.answer
        require(record.status == "answered" and record.value is not None, "unresolved answer")
        require(question.case_ref == case_ref and question.task_ref == parent.task_ref
                and question.base == parent.contract.base, "question context mismatch", "conflict")
        require(probe_table.get(question.probe.id) == question.probe, "question template changed", "conflict")
        require(question.probe.id not in used, "duplicate answered probe")
        used.add(question.probe.id)
        question_ref, question_raw = artifact(question, case_ref.project_id, question.id, question.version)
        source_contents[question_ref] = question_raw
        require(item.answer_ref in source_contents, "answer bytes unavailable", "not_found")
        answer_raw = source_contents[item.answer_ref]
        require(record.question_hash == digest(question)
                and dumps(loads(AnswerRecord, answer_raw.decode("utf-8"))) == dumps(record),
                "answer record/bytes or question mismatch", "conflict")
        require((record.id, record.version) == (item.answer_ref.artifact_id, item.answer_ref.revision),
                "answer identity mismatch", "conflict")
        # Original answer bytes and identity were checked by requirements.answer.
        # prepare_task below checks every source again at the successor-task boundary.
        requirement_id = f"clarification/{case.id}/{question.probe.id}"
        obligation = goal(question.probe, record.value)
        require(requirement_id not in existing_statements and obligation.id not in existing_obligations,
                "successor identifier collision", "conflict")
        existing_statements.add(requirement_id)
        existing_obligations.add(obligation.id)
        evidence = (*question.probe.source_refs,
                    _evidence(parent.task_ref, source_contents[parent.task_ref], "parent-task"),
                    _evidence(case_ref, source_contents[case_ref], "fixed-interpretations-and-probes"),
                    _evidence(question_ref, question_raw, "issued-behavior-question"),
                    _evidence(item.answer_ref, answer_raw, "scripted-answer:" + record.actor))
        statements.append(TaskStatement(requirement_id, f"{question.probe.text} Answer: {record.value}.",
                                        "intent", "confirmed", True, evidence, None))
        obligations.append(obligation)
        bindings.append(TaskBinding(obligation.id, obligation.version, (requirement_id,)))
        recorded.extend((RecordedArtifact(question_ref, question_raw.decode("utf-8")),
                         RecordedArtifact(item.answer_ref, answer_raw.decode("utf-8"))))
    plan = replace(parent.contract.plan, version=version,
                   obligations=parent.contract.plan.obligations + tuple(obligations))
    successor = replace(parent.contract, version=version, plan=plan,
                        statements=parent.contract.statements + tuple(statements),
                        bindings=parent.contract.bindings + tuple(bindings))
    successor_ref, raw = artifact(successor, case_ref.project_id, successor.id, successor.version)
    prepared = prepare_task(raw, successor_ref, source_contents)
    recorded.append(RecordedArtifact(successor_ref, raw.decode("utf-8")))
    derivation = Derivation(parent.task_ref, case_ref, "finite-probe-goal/0.1",
                            tuple(a.answer_ref for a in answers), successor_ref)
    return prepared, derivation, tuple(recorded)


def run_clarification(parent_raw, parent_ref, case_raw, case_ref, sources, replies,
                      successor_version, metamodel, snapshot, actor="clarification-host"):
    """Trusted local host: inputs are pinned before exploration; no evaluator feedback."""
    source_contents = dict(sources)
    source_contents[parent_ref] = parent_raw
    source_contents[case_ref] = case_raw
    parent = prepare_task(parent_raw, parent_ref, source_contents)
    require(parent.contract.base == ref(snapshot), "parent initial snapshot mismatch", "conflict")
    require(parent.contract.plan is not None, "clarification requires explicit baseline obligations", "unsupported")
    kernel = ModelKernel(snapshot, metamodel, parent.contract.plan, check_tasks, frozenset({actor}))
    session = prepare(case_raw, case_ref, parent_ref, metamodel, snapshot, source_contents, kernel.preview, observe)
    recorded = []
    for answer_ref, raw in replies:
        require(session.question is not None, "extra answer after clarification stopped", "conflict")
        question = session.question
        question_ref, question_raw = artifact(question, case_ref.project_id, question.id, question.version)
        recorded.append(RecordedArtifact(question_ref, question_raw.decode("utf-8")))
        session = answer(session, question, raw, answer_ref)
        source_contents[answer_ref] = raw
        recorded.append(RecordedArtifact(answer_ref, raw.decode("utf-8")))
    if session.status not in ("ready", "no_change"):
        return ClarificationRun(session, None, None, tuple(recorded), None)
    prepared, derivation, artifacts = derive_task(parent, session.case, case_ref,
                                                  session.answers, successor_version, source_contents)
    proposal = propose(session, prepared.task_ref)
    if proposal is None:
        assessment = assess_task(prepared, snapshot, check_tasks)
        result = TaskRunResult(assessment, None, snapshot, snapshot, "clarified; no model change or commit")
    else:
        result = run_task(prepared, metamodel, snapshot, proposal, check_tasks, actor)
    return ClarificationRun(session, derivation, prepared.contract, artifacts, result)


def load_example(profile):
    require(profile in ("structural-graph", "finite-automaton"), "unsupported clarification profile")
    folder = bootstrap.PLATFORM / "domain-packs" / profile
    card = loads(ClarificationCard, (folder / "clarification" / "card.json").read_text(encoding="utf-8"))
    def read(item):
        return _inside(folder, item.path).read_bytes()
    sources = {}
    for source in card.sources:
        require(source.ref not in sources, "duplicate source in clarification card")
        sources[source.ref] = read(source)
    metamodel, snapshot, _ = load_case(folder)
    return (read(card.parent), card.parent.ref, read(card.case), card.case.ref, sources,
            tuple((a.ref, read(a)) for a in card.answers), card.successor_version, metamodel, snapshot)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=("structural-graph", "finite-automaton"))
    args = parser.parse_args()
    try:
        result = run_clarification(*load_example(args.profile))
    except (ContractError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(to_data(result), ensure_ascii=False, indent=2))
    return 0 if result.run and result.run.assessment.intent_status == "ready" and result.run.assessment.goal_status == "satisfied" else 1


if __name__ == "__main__":
    sys.exit(main())
