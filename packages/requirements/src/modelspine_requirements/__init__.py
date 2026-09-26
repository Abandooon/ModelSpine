"""Finite, sourced clarification. No domain semantics, model writes, or LLM calls."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from hashlib import sha256
import re
from typing import Literal

from modelspine_protocols import (
    ArtifactRef, ChangeProposal, EvidenceRef, Metamodel, Obligation, Operation,
    Preview, Snapshot, SnapshotRef, checked, digest, dumps, loads, ref, require,
    validate_artifact_ref, validate_evidence_refs, validate_model, validate_snapshot_ref,
)


@dataclass(frozen=True)
class EvidenceNeed:
    id: str
    text: str
    source_refs: tuple[EvidenceRef, ...]
    pending_reason: str | None


@dataclass(frozen=True)
class Interpretation:
    id: str
    text: str
    operations: tuple[Operation, ...]
    source_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True)
class Probe:
    id: str
    text: str
    obligation: Obligation
    source_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True)
class Budget:
    max_candidates: int
    max_observations: int
    max_questions: int


@dataclass(frozen=True)
class ClarificationCase:
    schema_version: Literal["clarification-case/0.1"]
    id: str
    version: str
    task_ref: ArtifactRef
    base: SnapshotRef
    needs: tuple[EvidenceNeed, ...]
    interpretations: tuple[Interpretation, ...]
    probes: tuple[Probe, ...]
    budget: Budget


@dataclass(frozen=True)
class Observation:
    candidate: SnapshotRef
    probe_hash: str
    status: Literal["observed", "unknown", "error"]
    value: bool | None
    reason: str


@dataclass(frozen=True)
class Prediction:
    interpretation_id: str
    observation: Observation


@dataclass(frozen=True)
class ProbeObservations:
    probe_id: str
    predictions: tuple[Prediction, ...]


@dataclass(frozen=True)
class Question:
    id: str
    version: str
    case_ref: ArtifactRef
    task_ref: ArtifactRef
    base: SnapshotRef
    remaining: tuple[str, ...]
    sequence: int
    probe: Probe
    predictions: tuple[Prediction, ...]


@dataclass(frozen=True)
class AnswerRecord:
    schema_version: Literal["clarification-answer/0.1"]
    id: str
    version: str
    question_hash: str
    status: Literal["answered", "refused", "conflicted"]
    value: bool | None
    actor: str


@dataclass(frozen=True)
class AnsweredQuestion:
    question: Question
    answer: AnswerRecord
    answer_ref: ArtifactRef


@dataclass(frozen=True)
class Candidate:
    interpretation_id: str
    snapshot: Snapshot


@dataclass(frozen=True)
class Session:
    """Trusted immutable in-process state; not a cross-process authorization token."""
    case: ClarificationCase
    case_ref: ArtifactRef
    base: Snapshot
    candidates: tuple[Candidate, ...]
    observations: tuple[ProbeObservations, ...]
    remaining: tuple[str, ...]
    answers: tuple[AnsweredQuestion, ...]
    question: Question | None
    observations_used: int
    questions_used: int
    status: Literal["awaiting_answer", "ready", "no_change", "unresolved"]
    reason: str


def artifact(value, project_id: str, artifact_id: str, version: str):
    """Canonical UTF-8 bytes are also the exact raw bytes pinned by this helper."""
    raw = dumps(value).encode("utf-8")
    reference = ArtifactRef(project_id, artifact_id, version, sha256(raw).hexdigest())
    return validate_artifact_ref(reference), raw


def _load(cls, raw: bytes, expected: ArtifactRef):
    expected = validate_artifact_ref(expected)
    require(type(raw) is bytes, "expected original bytes")
    require(sha256(raw).hexdigest() == expected.content_hash, "artifact hash mismatch", "conflict")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        require(False, "artifact must be UTF-8")
    value = loads(cls, text)
    require((value.id, value.version) == (expected.artifact_id, expected.revision),
            "artifact identity/version mismatch", "conflict")
    return value


def _sources(refs: tuple[EvidenceRef, ...], sources: Mapping[ArtifactRef, bytes]):
    validate_evidence_refs(refs)
    for evidence in refs:
        require(evidence.source in sources, "declared clarification source missing", "not_found")
        raw = sources[evidence.source]
        require(type(raw) is bytes, "source must be raw bytes")
        require(sha256(raw).hexdigest() == evidence.source.content_hash, "source hash mismatch", "conflict")
        try:
            lines = raw.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            require(False, "source must be UTF-8")
        locator = re.fullmatch(r"lines:([1-9][0-9]*)-([1-9][0-9]*)", evidence.locator)
        require(locator is not None, "unsupported source locator")
        start, end = map(int, locator.groups())
        require(start <= end <= len(lines), "source locator out of bounds")


def _advance(session: Session) -> Session:
    if len(session.remaining) == 1 and session.answers:
        selected = next(c for c in session.candidates if c.interpretation_id == session.remaining[0])
        same = selected.snapshot.elements == session.base.elements
        return replace(session, question=None, status="no_change" if same else "ready",
                       reason="answer_resolved_no_change" if same else "finite_interpretation_resolved")
    if session.questions_used >= session.case.budget.max_questions:
        return replace(session, question=None, status="unresolved", reason="question_budget_exhausted")
    active = set(session.remaining)
    ranked = []
    for row in session.observations:
        predictions = tuple(p for p in row.predictions if p.interpretation_id in active)
        if len(predictions) != len(active) or any(p.observation.status != "observed" for p in predictions):
            continue
        positive = sum(p.observation.value is True for p in predictions)
        negative = len(predictions) - positive
        if positive and negative:
            # Maximise the smaller partition: no priors or calibrated probabilities.
            ranked.append((-min(positive, negative), row.probe_id, predictions))
    if not ranked:
        return replace(session, question=None, status="unresolved", reason="no_distinguishing_probe")
    _, probe_id, predictions = sorted(ranked, key=lambda row: row[:2])[0]
    probe = next(p for p in session.case.probes if p.id == probe_id)
    number = session.questions_used + 1
    question = Question(f"{session.case.id}/question-{number}", "1", session.case_ref,
                        session.case.task_ref, session.case.base, session.remaining, number, probe, predictions)
    return replace(session, question=question, questions_used=number, status="awaiting_answer", reason="")


def prepare(raw: bytes, expected_ref: ArtifactRef, task_ref: ArtifactRef,
            metamodel: Metamodel, snapshot: Snapshot, sources: Mapping[ArtifactRef, bytes],
            preview: Callable[[ChangeProposal], Preview],
            observe: Callable[[Snapshot, Probe], Observation]) -> Session:
    """Enumerate explicitly supplied candidates and bounded observations, never infer source meaning."""
    case = _load(ClarificationCase, raw, expected_ref)
    validate_artifact_ref(task_ref)
    validate_snapshot_ref(case.base)
    snapshot, metamodel = checked(snapshot, Snapshot), checked(metamodel, Metamodel)
    validate_model(snapshot, metamodel)
    require(case.task_ref == task_ref and case.base == ref(snapshot), "case task/base mismatch", "conflict")
    require(expected_ref.project_id == task_ref.project_id == snapshot.project_id,
            "case project mismatch", "conflict")
    require(isinstance(sources, Mapping) and callable(preview) and callable(observe), "invalid dependencies")
    require(all(x >= 0 for x in (case.budget.max_candidates, case.budget.max_observations,
                                case.budget.max_questions)), "negative budget")
    require(len(case.interpretations) >= 2, "clarification needs at least two explicit interpretations")
    require(bool(case.needs), "missing declared evidence needs")
    for items in (case.needs, case.interpretations, case.probes):
        require(len({x.id for x in items}) == len(items), "duplicate clarification ID")
        for item in items:
            require(bool(item.id.strip() and item.text.strip()), "empty clarification ID/text")
            _sources(item.source_refs, sources)
    for interpretation in case.interpretations:
        require(bool(interpretation.source_refs), "interpretation must have a declared source")
    for probe in case.probes:
        require(bool(probe.source_refs), "probe must have a declared source")
    pending = []
    for need in case.needs:
        require(need.pending_reason is None or bool(need.pending_reason.strip()), "empty pending reason")
        require(bool(need.source_refs) or need.pending_reason is not None, "missing source without reason")
        if need.pending_reason is not None:
            pending.append(need.id)
    session = Session(case, expected_ref, snapshot, (), (),
                      tuple(sorted(i.id for i in case.interpretations)), (), None, 0, 0, "unresolved", "")
    if pending:
        return replace(session, reason="evidence_pending:" + ",".join(pending))
    if len(case.interpretations) > case.budget.max_candidates:
        return replace(session, reason="candidate_budget_exhausted")
    candidates = []
    for interpretation in sorted(case.interpretations, key=lambda i: i.id):
        candidate = snapshot
        if interpretation.operations:
            proposal = ChangeProposal("0.1", f"{case.id}/preview/{interpretation.id}", case.base,
                                      interpretation.operations, interpretation.source_refs)
            result = checked(preview(proposal), Preview)
            require(result.proposal_hash == digest(proposal) and result.candidate_hash == digest(result.candidate),
                    "preview binding mismatch", "conflict")
            candidate = result.candidate
            require(ref(candidate) == replace(case.base, revision=case.base.revision + 1,
                                              content_hash=digest(candidate)), "preview identity mismatch", "conflict")
            validate_model(candidate, metamodel)
        candidates.append(Candidate(interpretation.id, candidate))
    session = replace(session, candidates=tuple(candidates))
    rows, calls = [], 0
    for probe in sorted(case.probes, key=lambda p: p.id):
        predictions = []
        for candidate in candidates:
            if calls >= case.budget.max_observations:
                if predictions:
                    rows.append(ProbeObservations(probe.id, tuple(predictions)))
                return replace(session, observations=tuple(rows), observations_used=calls,
                               reason="observation_budget_exhausted")
            observation = checked(observe(candidate.snapshot, probe), Observation)
            calls += 1
            require(observation.candidate == ref(candidate.snapshot) and observation.probe_hash == digest(probe),
                    "observation binding mismatch", "conflict")
            require((observation.status == "observed") == (observation.value is not None),
                    "observation status/value mismatch")
            require(observation.status == "observed" or bool(observation.reason.strip()), "missing observation reason")
            predictions.append(Prediction(candidate.interpretation_id, observation))
        rows.append(ProbeObservations(probe.id, tuple(predictions)))
    return _advance(replace(session, observations=tuple(rows), observations_used=calls))


def answer(session: Session, question: Question, raw: bytes, expected_ref: ArtifactRef) -> Session:
    """Return new state; rejected or repeated answers do not overwrite earlier state."""
    require(type(session) is Session and session.status == "awaiting_answer", "session is not awaiting answer", "conflict")
    question = checked(question, Question)
    require(digest(question) == digest(session.question), "stale or altered question", "conflict")
    record = _load(AnswerRecord, raw, expected_ref)
    require(expected_ref.project_id == session.case.base.project_id and record.question_hash == digest(question),
            "answer question/project mismatch", "conflict")
    require(bool(record.actor.strip()), "missing answer actor")
    require((record.status == "answered") == (record.value is not None), "answer status/value mismatch")
    require(not any(a.answer_ref.artifact_id == expected_ref.artifact_id for a in session.answers),
            "answer identity already used", "conflict")
    recorded = AnsweredQuestion(question, record, expected_ref)
    updated = replace(session, answers=session.answers + (recorded,), question=None)
    if record.status != "answered":
        return replace(updated, status="unresolved", reason="answer_" + record.status)
    remaining = tuple(p.interpretation_id for p in question.predictions if p.observation.value == record.value)
    if not remaining:
        return replace(updated, remaining=(), status="unresolved", reason="answer_excludes_all")
    return _advance(replace(updated, remaining=remaining))


def propose(session: Session, successor_ref: ArtifactRef) -> ChangeProposal | None:
    """The host fixes a distinct successor task before requesting the final proposal."""
    require(type(session) is Session and session.status in ("ready", "no_change"), "clarification unresolved")
    successor_ref = validate_artifact_ref(successor_ref)
    require(successor_ref.project_id == session.case.task_ref.project_id
            and successor_ref.artifact_id == session.case.task_ref.artifact_id
            and successor_ref.revision != session.case.task_ref.revision,
            "expected explicit successor task version", "conflict")
    if session.status == "no_change":
        return None
    selected = next(i for i in session.case.interpretations if i.id == session.remaining[0])
    evidence = [*selected.source_refs, EvidenceRef(session.case_ref, "lines:1-1", "finite-clarification-case"),
                EvidenceRef(successor_ref, "lines:1-1", "pinned-successor-task")]
    for item in session.answers:
        question_ref, _ = artifact(item.question, session.case.base.project_id,
                                   item.question.id, item.question.version)
        evidence.extend((EvidenceRef(question_ref, "lines:1-1", "issued-behavior-question"),
                         EvidenceRef(item.answer_ref, "lines:1-1", "scripted-answer:" + item.answer.actor)))
    return ChangeProposal("0.1", f"{session.case.id}/resolved/{digest(session.answers)[:16]}",
                          session.case.base, selected.operations, tuple(dict.fromkeys(evidence)))
