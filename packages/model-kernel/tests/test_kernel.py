"""Kernel units use a separate checker and model, with no assurance dependency."""
import unittest
from dataclasses import replace

from modelspine_kernel import ModelKernel, impact
from modelspine_protocols import (
    AddElement, ArtifactRef, ChangeProposal, CheckPlan, ContractError, Element, EvidenceRef,
    FieldSpec, KindSpec, Metamodel, MetamodelRef, Obligation, Outcome, Property,
    RemoveElement, ReportBinding, SetProperty, Snapshot,
    ValidationReport, digest, properties, ref,
)


def symbol_checker(snapshot, plan, scope=None):
    """Test consumer for identifier declarations; not an assurance implementation."""
    scope = tuple(sorted({o.target for o in plan.obligations})) if scope is None else scope
    values = {element.id: properties(element.properties) for element in snapshot.elements}
    outcomes = []
    for obligation in plan.obligations:
        if obligation.target not in scope:
            continue
        if obligation.kind != "ascii_identifier":
            status = "unknown"
        else:
            value = values[obligation.target][obligation.field]
            status = "satisfied" if value.isascii() and value.isidentifier() else "violated"
        outcomes.append(Outcome(obligation.id, obligation.version, status, ()))
    return ValidationReport(ReportBinding(digest(snapshot), digest(plan), scope, plan.assumptions,
                                         "test-symbol-checker", "1"), tuple(outcomes))


class KernelCheckerTests(unittest.TestCase):
    def setUp(self):
        self.meta = Metamodel(MetamodelRef("declarations", "1"), (
            KindSpec("declaration", (FieldSpec("symbol", "string"),)),))
        self.snapshot = Snapshot("test", "symbols", 0, self.meta.ref, digest(self.meta), tuple(
            Element(key, "declaration", key, None, (Property("symbol", key),), (), True,
                    "intent", True, ()) for key in ("alpha", "beta")))
        self.plan = CheckPlan("identifiers", "1", "1", (), tuple(
            Obligation(key, "1", "ascii_identifier", key, "symbol", ())
            for key in ("alpha", "beta")))
        self.proposal = ChangeProposal("0.1", "rename-symbol", ref(self.snapshot), (
            SetProperty("set_property", "alpha", "symbol", "gamma"),), ())

    def kernel(self, checker=symbol_checker):
        return ModelKernel(self.snapshot, self.meta, self.plan, checker, frozenset({"editor"}))

    def assert_uncommitted(self, kernel):
        self.assertEqual(kernel.snapshot(), self.snapshot)
        with self.assertRaises(ContractError) as raised:
            kernel.snapshot(1)
        self.assertEqual(raised.exception.code, "not_found")

    def test_alternative_checker_commits_and_preserves_unrelated_evidence(self):
        kernel = self.kernel()
        kernel.record_evidence(symbol_checker(self.snapshot, self.plan, ("beta",)))
        report = symbol_checker(kernel.preview(self.proposal).candidate, self.plan)
        decision = kernel.decide(self.proposal, report, "editor")
        commit = kernel.apply(self.proposal, decision, "editor")
        self.assertEqual(commit.snapshot.revision, 1)
        self.assertEqual(commit.report.binding.tool, "test-symbol-checker")
        self.assertEqual(commit.evidence_status[0].status, "current")

    def test_alternative_checker_failure_cannot_authorize_satisfied_save(self):
        kernel = self.kernel()
        proposal = replace(self.proposal, operations=(
            SetProperty("set_property", "alpha", "symbol", "invalid identifier"),))
        report = symbol_checker(kernel.preview(proposal).candidate, self.plan)
        self.assertEqual(report.residual, ("alpha",))
        with self.assertRaises(ContractError):
            kernel.decide(proposal, report, "editor")
        self.assert_uncommitted(kernel)

    def test_wrong_bindings_and_obligation_coverage_cannot_issue_decisions(self):
        candidate = self.kernel().preview(self.proposal).candidate
        good = symbol_checker(candidate, self.plan)
        malformed = {
            "old candidate": replace(good, binding=replace(good.binding, candidate_hash=digest(self.snapshot))),
            "other plan": replace(good, binding=replace(good.binding, plan_hash="wrong")),
            "other scope": replace(good, binding=replace(good.binding, scope=("alpha",))),
            "duplicate scope": replace(good, binding=replace(good.binding, scope=("alpha", "alpha", "beta"))),
            "other assumptions": replace(good, binding=replace(good.binding, assumptions=("different",))),
            "missing tool": replace(good, binding=replace(good.binding, tool="")),
            "missing version": replace(good, binding=replace(good.binding, tool_version="")),
            "missing obligation": replace(good, outcomes=good.outcomes[:-1]),
            "duplicate obligation": replace(good, outcomes=good.outcomes + good.outcomes[:1]),
            "other obligation": replace(good, outcomes=(replace(good.outcomes[0], obligation_id="other"), good.outcomes[1])),
            "other rule version": replace(good, outcomes=(replace(good.outcomes[0], obligation_version="2"), good.outcomes[1])),
        }
        for name, report in malformed.items():
            with self.subTest(name=name):
                kernel = self.kernel(lambda *args: report)
                with self.assertRaises(ContractError) as raised:
                    kernel.decide(self.proposal, report, "editor")
                self.assertEqual(raised.exception.code, "conflict")
                self.assert_uncommitted(kernel)

    def test_malformed_report_shape_is_rejected_at_checker_boundary(self):
        kernel = self.kernel(lambda *args: {"binding": "not a report"})
        report = symbol_checker(kernel.preview(self.proposal).candidate, self.plan)
        with self.assertRaises(ContractError) as raised:
            kernel.decide(self.proposal, report, "editor")
        self.assertEqual(raised.exception.code, "invalid")
        self.assert_uncommitted(kernel)

    def test_scoped_evidence_requires_exact_coverage(self):
        scoped = symbol_checker(self.snapshot, self.plan, ("alpha",))
        malformed = replace(scoped, outcomes=())
        corrupt = True

        def checker(snapshot, plan, scope=None):
            return malformed if corrupt else symbol_checker(snapshot, plan, scope)

        kernel = self.kernel(checker)
        with self.assertRaises(ContractError):
            kernel.record_evidence(malformed)
        corrupt = False
        self.assertEqual(kernel.evidence_status(), ())
        self.assertEqual(kernel.record_evidence(scoped).report, scoped)

    def test_backend_exception_aborts_decide_and_apply_without_partial_commit(self):
        failing = True

        def checker(snapshot, plan, scope=None):
            if failing:
                raise RuntimeError("selected checker unavailable")
            return symbol_checker(snapshot, plan, scope)

        kernel = self.kernel(checker)
        report = symbol_checker(kernel.preview(self.proposal).candidate, self.plan)
        with self.assertRaisesRegex(RuntimeError, "selected checker unavailable"):
            kernel.decide(self.proposal, report, "editor")
        self.assert_uncommitted(kernel)
        failing = False
        decision = kernel.decide(self.proposal, report, "editor")
        failing = True
        with self.assertRaisesRegex(RuntimeError, "selected checker unavailable"):
            kernel.apply(self.proposal, decision, "editor")
        self.assert_uncommitted(kernel)
        failing = False
        self.assertEqual(kernel.apply(self.proposal, decision, "editor").snapshot.revision, 1)

    def test_checker_result_change_between_decision_and_apply_is_conflict(self):
        changed = False

        def checker(snapshot, plan, scope=None):
            report = symbol_checker(snapshot, plan, scope)
            if changed:
                return replace(report, outcomes=tuple(replace(o, status="unknown") for o in report.outcomes))
            return report

        kernel = self.kernel(checker)
        report = checker(kernel.preview(self.proposal).candidate, self.plan)
        decision = kernel.decide(self.proposal, report, "editor")
        changed = True
        with self.assertRaises(ContractError) as raised:
            kernel.apply(self.proposal, decision, "editor")
        self.assertEqual(raised.exception.code, "conflict")
        self.assert_uncommitted(kernel)

    def test_proposal_intent_references_are_validated_before_checking(self):
        source = ArtifactRef('project', 'source', '1', digest('source content'))
        valid = EvidenceRef(source, 'line:1', 'user-input')
        malformed = [replace(valid, locator=''), replace(valid, origin=''),
                     replace(valid, source=replace(source, project_id='')),
                     replace(valid, source=replace(source, content_hash='not-a-hash'))]
        kernel = self.kernel()
        for reference in malformed:
            with self.subTest(reference=reference), self.assertRaises(ContractError) as raised:
                kernel.preview(replace(self.proposal, intent_refs=(reference,)))
            self.assertEqual(raised.exception.code, 'invalid')
            self.assert_uncommitted(kernel)
        proposal = replace(self.proposal, intent_refs=(valid,))
        report = symbol_checker(kernel.preview(proposal).candidate, self.plan)
        decision = kernel.decide(proposal, report, 'editor')
        self.assertEqual(kernel.apply(proposal, decision, 'editor').snapshot.revision, 1)

    def test_impact_rejects_different_model_or_metamodel_identity(self):
        changes = [dict(project_id='other'), dict(model_id='other'),
                   dict(metamodel=replace(self.snapshot.metamodel, id='other')),
                   dict(metamodel=replace(self.snapshot.metamodel, version='2')),
                   dict(metamodel_hash='0' * 64)]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ContractError) as raised:
                impact(self.snapshot, replace(self.snapshot, **change))
            self.assertEqual(raised.exception.code, 'conflict')
        self.assertEqual(impact(self.snapshot, replace(self.snapshot, revision=1)).changed, ())

    def test_removed_identity_cannot_be_recreated_in_the_same_batch(self):
        kernel = self.kernel()
        old = self.snapshot.elements[0]
        replacements = [old, replace(old, category='hypothesis'), replace(old, kind='another-kind')]
        for replacement in replacements:
            proposal = replace(self.proposal, operations=(
                RemoveElement('remove_element', old.id), AddElement('add_element', replacement)))
            with self.subTest(replacement=replacement), self.assertRaises(ContractError) as raised:
                kernel.preview(proposal)
            self.assertEqual(raised.exception.code, 'conflict')
            self.assert_uncommitted(kernel)
        fresh = replace(old, id='temporary')
        proposal = replace(self.proposal, operations=(AddElement('add_element', fresh),
            RemoveElement('remove_element', fresh.id), AddElement('add_element', fresh)))
        with self.assertRaises(ContractError) as raised:
            kernel.preview(proposal)
        self.assertEqual(raised.exception.code, 'conflict')
        self.assert_uncommitted(kernel)

    def test_committed_history_prevents_id_reuse_after_deletion(self):
        kernel = self.kernel()
        extra = replace(self.snapshot.elements[0], id='retired')

        def submit(proposal_id, operation):
            proposal = ChangeProposal('0.1', proposal_id, ref(kernel.snapshot()), (operation,), ())
            report = symbol_checker(kernel.preview(proposal).candidate, self.plan)
            decision = kernel.decide(proposal, report, 'editor')
            return kernel.apply(proposal, decision, 'editor')

        submit('add', AddElement('add_element', extra))
        submit('remove', RemoveElement('remove_element', extra.id))
        before = kernel.snapshot()
        with self.assertRaises(ContractError) as raised:
            submit('reuse', AddElement('add_element', extra))
        self.assertEqual(raised.exception.code, 'conflict')
        self.assertEqual(kernel.snapshot(), before)
        self.assertEqual(kernel.snapshot().revision, 2)
        self.assertIn(extra, kernel.snapshot(1).elements)
        self.assertEqual(submit('new-identity', AddElement('add_element',
            replace(extra, id='new-identity'))).snapshot.revision, 3)


if __name__ == "__main__":
    unittest.main()
