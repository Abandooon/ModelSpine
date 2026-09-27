"""Handwritten candidate contract fixtures, not extraction or semantic evidence."""
import copy
import json
import unittest
from dataclasses import replace
from hashlib import sha256

from modelspine_protocols import ArtifactRef, ContractError, digest, to_data
from modelspine_requirements.domain_modeling import (
    MAX_ITEMS, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, MAX_SOURCE_BYTES,
    inspect_candidate, modeling_prompt, prepare_request, validate_request,
)


class DomainModelingTests(unittest.TestCase):
    def setUp(self):
        self.lines = [
            "每位读者可借任意本书；每本书同时最多借给一位读者。",
            "读者编号的类型和借阅期限尚未确定。",
            "仅在借阅开放时允许续借，未结清罚款者除外。",
            "外部信用评分算法不在当前表达范围。",
        ]
        self.raw = ("\r\n".join(self.lines) + "\r\n").encode("utf-8")
        self.source = ArtifactRef("contract-tests", "raw-source", "1",
                                  sha256(self.raw).hexdigest())
        self.request = prepare_request(self.raw, self.source, request_id="request-1",
                                       scope="Describe the stated library domain.")

    def span(self, first=1, last=None):
        last = first if last is None else last
        return {"start_line": first, "end_line": last,
                "quote": "\n".join(self.lines[first - 1:last])}

    def candidate(self):
        return {
            "schema_version": "domain-modeling-candidate/0.1",
            "id": "manual-contract-candidate", "version": "1",
            "request_hash": digest(self.request), "status": "unconfirmed",
            "concepts": [
                {"id": "reader", "name": "读者", "description": "借书的人",
                 "evidence": [self.span()]},
                {"id": "book", "name": "书", "description": "可供借阅的书",
                 "evidence": [self.span()]},
            ],
            "attributes": [],
            "relations": [{
                "id": "borrows", "name": "借阅", "source_concept": "reader",
                "target_concept": "book",
                "targets_per_source": {"minimum": 0, "maximum": "unbounded"},
                "sources_per_target": {"minimum": 0, "maximum": 1},
                "evidence": [self.span()],
            }],
            "rules": [], "issues": [],
        }

    def issue(self, identity="unknown", kind="missing_information", related=()):
        return {"id": identity, "kind": kind, "text": "原文未确定，需要保留。",
                "related_ids": list(related), "question": "应如何解释？",
                "evidence": [self.span(2)]}

    def encoded(self, value, **kwargs):
        return json.dumps(value, ensure_ascii=False, **kwargs).encode("utf-8")

    def inspect(self, value):
        return inspect_candidate(self.request, self.encoded(value))

    def rejected(self, value, code=None):
        raw = value if type(value) is bytes else self.encoded(value)
        with self.assertRaises(ContractError) as error:
            inspect_candidate(self.request, raw)
        if code is not None:
            self.assertEqual(error.exception.code, code)

    def test_request_starts_from_original_utf8_without_model(self):
        self.assertEqual(self.request.text.encode("utf-8"), self.raw)
        self.assertEqual(self.request.source, self.source)
        self.assertEqual(validate_request(self.request), self.request)
        prompt = modeling_prompt(self.request)
        self.assertIn("\nREQUEST_HASH=" + digest(self.request), prompt)
        payload = json.loads(prompt.split("\nINPUT_JSON=", 1)[1])
        self.assertEqual(payload, to_data(self.request))
        self.assertEqual(set(payload), {"schema_version", "id", "source", "text", "scope"})

    def test_source_identity_and_bytes_are_checked(self):
        cases = [
            (self.raw.decode("utf-8"), self.source, "request-1", "scope"),
            (b"\xff", self.source, "request-1", "scope"),
            (self.raw.replace(b"\r\n", b"\n"), self.source, "request-1", "scope"),
            (self.raw, replace(self.source, content_hash="0" * 64), "request-1", "scope"),
            (self.raw, self.source, " ", "scope"),
            (self.raw, self.source, "request-1", " "),
            (b" ", replace(self.source, content_hash=sha256(b" ").hexdigest()),
             "request-1", "scope"),
        ]
        for raw, source, identity, scope in cases:
            with self.subTest(raw=raw, source=source, identity=identity, scope=scope):
                with self.assertRaises(ContractError):
                    prepare_request(raw, source, request_id=identity, scope=scope)

    def test_response_is_bound_to_complete_request(self):
        response = self.encoded(self.candidate())
        updated_raw = self.raw + "增加一条原文。".encode("utf-8")
        changed = [
            replace(self.request, id="request-2"),
            replace(self.request, scope="Another scope"),
            replace(self.request, source=replace(self.source, revision="2")),
            replace(self.request, source=replace(self.source, artifact_id="other-source")),
            prepare_request(updated_raw,
                            replace(self.source, content_hash=sha256(updated_raw).hexdigest()),
                            request_id=self.request.id, scope=self.request.scope),
        ]
        for request in changed:
            with self.subTest(request=request):
                validate_request(request)
                with self.assertRaises(ContractError) as error:
                    inspect_candidate(request, response)
                self.assertEqual(error.exception.code, "conflict")

    def test_response_hash_preserves_original_serialization(self):
        compact = self.encoded(self.candidate(), separators=(",", ":"))
        spaced = self.encoded(self.candidate(), indent=2) + b"\n"
        first = inspect_candidate(self.request, compact)
        second = inspect_candidate(self.request, spaced)
        self.assertEqual(first.candidate, second.candidate)
        self.assertEqual(first.response_hash, sha256(compact).hexdigest())
        self.assertEqual(second.response_hash, sha256(spaced).hexdigest())
        self.assertNotEqual(first.response_hash, second.response_hash)

    def test_isolated_unicode_surrogates_are_contract_errors(self):
        for codepoint in (0xD800, 0xDFFF):
            invalid_text = "invalid-" + chr(codepoint)
            with self.subTest(codepoint=codepoint, field="candidate.description"):
                candidate = self.candidate()
                candidate["concepts"][0]["description"] = invalid_text
                # The wire bytes are valid ASCII; the escaped JSON value is not valid Unicode.
                raw = json.dumps(candidate, ensure_ascii=True).encode("ascii")
                self.rejected(raw, "invalid")
            for field in ("scope", "text"):
                with self.subTest(codepoint=codepoint, field="request." + field):
                    with self.assertRaises(ContractError) as error:
                        validate_request(replace(self.request, **{field: invalid_text}))
                    self.assertEqual(error.exception.code, "invalid")
            with self.subTest(codepoint=codepoint, field="prepare_request.scope"):
                with self.assertRaises(ContractError) as error:
                    prepare_request(self.raw, self.source, request_id="request-1", scope=invalid_text)
                self.assertEqual(error.exception.code, "invalid")

    def test_evidence_uses_exact_inclusive_source_lines(self):
        candidate = self.candidate()
        candidate["concepts"][0]["evidence"] = [self.span(1, 2)]
        evidence = self.inspect(candidate).candidate.concepts[0].evidence[0]
        self.assertEqual((evidence.start_line, evidence.end_line), (1, 2))
        self.assertEqual(evidence.quote, "\n".join(self.lines[:2]))
        self.assertIn("\r\n", self.request.text)

    def test_evidence_rejects_missing_shifted_and_out_of_bounds_citations(self):
        spans = [
            [], [self.span(), self.span()],
            [{**self.span(), "quote": self.lines[0] + " invented"}],
            [{**self.span(), "start_line": 2, "end_line": 2}],
            [{**self.span(), "start_line": 0}],
            [{**self.span(), "end_line": len(self.lines) + 1}],
            [{**self.span(), "start_line": 2, "end_line": 1}],
        ]
        for evidence in spans:
            with self.subTest(evidence=evidence):
                candidate = self.candidate()
                candidate["concepts"][0]["evidence"] = evidence
                self.rejected(candidate)

    def test_directional_cardinality_keeps_unknown_distinct_from_unbounded(self):
        candidate = self.candidate()
        candidate["relations"][0]["sources_per_target"] = {"minimum": None, "maximum": None}
        candidate["issues"] = [self.issue(related=("borrows",))]
        result = self.inspect(candidate)
        relation = result.candidate.relations[0]
        self.assertEqual((relation.source_concept, relation.target_concept), ("reader", "book"))
        self.assertEqual((relation.targets_per_source.minimum, relation.targets_per_source.maximum),
                         (0, "unbounded"))
        self.assertEqual((relation.sources_per_target.minimum, relation.sources_per_target.maximum),
                         (None, None))
        self.assertEqual(result.unresolved_ids, ("unknown",))
        self.assertEqual(self.inspect(self.candidate()).unresolved_ids, ())

    def test_unknown_attribute_or_cardinality_requires_related_issue(self):
        candidate = self.candidate()
        candidate["attributes"] = [{"id": "reader-code", "concept_id": "reader",
                                    "name": "编号", "value_type": None,
                                    "evidence": [self.span(2)]}]
        candidate["relations"][0]["targets_per_source"]["minimum"] = None
        for related in [(), ("reader",), ("reader-code",), ("borrows",)]:
            with self.subTest(related=related):
                candidate["issues"] = [self.issue(related=related)]
                self.rejected(candidate)
        candidate["issues"] = [self.issue(related=("reader-code", "borrows"))]
        result = self.inspect(candidate)
        self.assertIsNone(result.candidate.attributes[0].value_type)
        self.assertIsNone(result.candidate.relations[0].targets_per_source.minimum)

    def test_strict_wire_rejects_bool_numbers_duplicate_keys_and_extra_fields(self):
        good = self.candidate()
        variants = []
        for field, value in [("minimum", True), ("maximum", False), ("minimum", -1),
                             ("maximum", -1), ("minimum", 2)]:
            candidate = copy.deepcopy(good)
            candidate["relations"][0]["sources_per_target"][field] = value
            variants.append(candidate)
        candidate = copy.deepcopy(good)
        candidate["concepts"][0]["evidence"][0]["start_line"] = True
        variants.append(candidate)
        for owner, field, value in [("root", "accepted", True), ("root", "status", "confirmed"),
                                    ("relation", "inferred", True)]:
            candidate = copy.deepcopy(good)
            target = candidate if owner == "root" else candidate["relations"][0]
            target[field] = value
            variants.append(candidate)
        raw = self.encoded(good)
        variants += [b"{", b"\xff", b"[]",
                     raw.replace(b'"status": "unconfirmed"',
                                 b'"status": "unconfirmed", "status": "unconfirmed"'),
                     raw.replace(b'"minimum": 0', b'"minimum": 0, "minimum": 0', 1),
                     raw.replace(b'"minimum": 0', b'"minimum": 0.0', 1)]
        for candidate in variants:
            with self.subTest(candidate=candidate):
                self.rejected(candidate)

    def test_item_ids_owners_endpoints_and_references_are_checked(self):
        good = self.candidate()
        good["attributes"] = [{"id": "reader-code", "concept_id": "reader", "name": "编号",
                               "value_type": "string", "evidence": [self.span(2)]}]
        good["rules"] = [{"id": "renewal", "text": self.lines[2], "related_ids": ["borrows"],
                          "formalization": "not_formalized", "evidence": [self.span(3)]}]
        good["issues"] = [self.issue(related=("renewal",))]
        self.inspect(good)
        mutations = [
            ("attributes", "concept_id", "missing"),
            ("attributes", "concept_id", "borrows"),
            ("relations", "source_concept", "missing"),
            ("relations", "target_concept", "reader-code"),
            ("attributes", "id", "reader"),
            ("concepts", "id", " "),
            ("rules", "related_ids", ["missing"]),
            ("rules", "related_ids", ["renewal"]),
            ("rules", "related_ids", ["borrows", "borrows"]),
            ("issues", "related_ids", ["missing"]),
            ("issues", "related_ids", ["reader", "reader"]),
        ]
        for group, field, value in mutations:
            with self.subTest(group=group, field=field, value=value):
                candidate = copy.deepcopy(good)
                candidate[group][0][field] = value
                self.rejected(candidate)

    def test_issues_and_unformalized_rules_are_preserved_without_resolution(self):
        candidate = self.candidate()
        candidate["rules"] = [{"id": "renewal", "text": self.lines[2], "related_ids": ["borrows"],
                               "formalization": "not_formalized", "evidence": [self.span(3)]}]
        kinds = ("ambiguity", "conflict", "missing_information", "unsupported")
        candidate["issues"] = [self.issue(kind, kind, ("renewal",)) for kind in kinds]
        candidate["issues"][-1].update(question=None, text=self.lines[3], evidence=[self.span(4)])
        result = self.inspect(candidate)
        self.assertEqual(result.unresolved_ids, kinds)
        self.assertEqual(to_data(result.candidate.issues), candidate["issues"])
        self.assertEqual(to_data(result.candidate.rules), candidate["rules"])
        self.assertEqual(result.candidate.status, "unconfirmed")
        self.assertEqual(result.rule_execution, "not_implemented")

    def test_empty_output_is_rejected_but_unsupported_issue_is_preserved(self):
        candidate = self.candidate()
        candidate.update(concepts=[], relations=[])
        self.rejected(candidate)
        candidate["issues"] = [self.issue("outside-scope", "unsupported")]
        candidate["issues"][0].update(question=None, text=self.lines[3], evidence=[self.span(4)])
        result = self.inspect(candidate)
        self.assertEqual(result.candidate.concepts, ())
        self.assertEqual(result.unresolved_ids, ("outside-scope",))
        self.assertEqual(result.semantics, "not_checked")
        self.assertEqual(result.candidate.status, "unconfirmed")

    def test_structural_validity_does_not_claim_semantic_fidelity(self):
        candidate = self.candidate()
        # A deliberately reversed interpretation has real citations but no semantic verdict.
        candidate["relations"][0].update(source_concept="book", target_concept="reader")
        candidate["concepts"][0]["description"] = "This description is not established by the source."
        result = self.inspect(candidate)
        self.assertEqual(result.structure, "valid")
        self.assertEqual(result.semantics, "not_checked")
        self.assertEqual(result.rule_execution, "not_implemented")
        self.assertEqual(result.candidate.status, "unconfirmed")

    def test_payload_and_item_limits_fail_explicitly(self):
        raw = b"x" * MAX_SOURCE_BYTES
        source = replace(self.source, content_hash=sha256(raw).hexdigest())
        self.assertEqual(len(prepare_request(raw, source, request_id="limit", scope="scope").text),
                         MAX_SOURCE_BYTES)
        with self.assertRaises(ContractError) as error:
            prepare_request(raw + b"x", source, request_id="limit", scope="scope")
        self.assertEqual(error.exception.code, "unsupported")
        with self.assertRaises(ContractError) as error:
            prepare_request(self.raw, self.source, request_id="limit", scope="x" * MAX_REQUEST_BYTES)
        self.assertEqual(error.exception.code, "unsupported")
        self.rejected(b" " * (MAX_RESPONSE_BYTES + 1), "unsupported")
        candidate = self.candidate()
        candidate.update(relations=[], concepts=[
            {**candidate["concepts"][0], "id": f"concept-{index}"}
            for index in range(MAX_ITEMS + 1)
        ])
        self.rejected(candidate)


if __name__ == "__main__":
    unittest.main()
