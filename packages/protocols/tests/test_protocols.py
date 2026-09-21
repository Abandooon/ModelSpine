import json
import unittest
from dataclasses import replace

from fixtures import load_fixture
from modelspine_protocols import (
    ChangeProposal, ContractError, Element, Property, Rename, Snapshot,
    digest, dumps, loads, ref, to_data, validate_model,
)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.meta, self.snapshot, self.plan = load_fixture()

    def test_json_roundtrip_preserves_identity_and_hash(self):
        restored = loads(Snapshot, dumps(self.snapshot))
        self.assertEqual(restored, self.snapshot)
        self.assertEqual(ref(restored), ref(self.snapshot))
        proposal = ChangeProposal('0.1', 'rename', ref(restored), (Rename('rename', 'order', 'Purchase'),), ())
        self.assertEqual(loads(ChangeProposal, dumps(proposal)), proposal)

    def test_unknown_missing_duplicate_and_noninteger_json_rejected(self):
        data = to_data(self.snapshot)
        wrong = [dict(data, metadata={}), {k:v for k,v in data.items() if k != 'model_id'},
                 dict(data, revision=True), dict(data, revision=1.0)]
        for value in wrong:
            with self.subTest(value=value), self.assertRaises(ContractError):
                loads(Snapshot, json.dumps(value))
        for text in ['{"revision":0,"revision":1}', 'NaN', 'Infinity']:
            with self.subTest(text=text), self.assertRaises(ContractError):
                loads(Snapshot, text)

    def test_duplicate_id_dangling_reference_and_containment_cycle(self):
        root, order, *rest = self.snapshot.elements
        variants = [self.snapshot.elements + (order,),
                    (root, replace(order, dependencies=('absent',)), *rest),
                    (replace(root, parent='order'), order, *rest)]
        for elements in variants:
            with self.subTest(elements=elements), self.assertRaises(ContractError):
                validate_model(replace(self.snapshot, elements=elements), self.meta)

    def test_metamodel_version_and_content_are_both_bound(self):
        for meta in [replace(self.meta, ref=replace(self.meta.ref, version='2')),
                     replace(self.meta, kinds=self.meta.kinds[:-1])]:
            with self.subTest(meta=meta), self.assertRaises(ContractError):
                validate_model(self.snapshot, meta)

    def test_unknown_operation_and_api_version_fail(self):
        proposal = ChangeProposal('0.1', 'bad', ref(self.snapshot), (Rename('rename','order','X'),), ())
        for field, value in [('api_version','9'), ('operations',[{'op':'metadata','model':{}}])]:
            data = to_data(proposal)
            data[field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                loads(ChangeProposal, json.dumps(data))

    def test_exact_field_types_and_no_float_or_bool_integer_coercion(self):
        policy = self.snapshot.elements[2]
        for bad in [True, '100', 1.5]:
            changed = replace(policy, properties=(Property('threshold_minor',bad), *policy.properties[1:]))
            with self.subTest(bad=bad), self.assertRaises(ContractError):
                validate_model(replace(self.snapshot, elements=(*self.snapshot.elements[:2],changed,*self.snapshot.elements[3:])), self.meta)

    def test_fact_requires_provenance_but_confirmation_does_not_relabel(self):
        order=replace(self.snapshot.elements[1],category='fact',sources=())
        with self.assertRaises(ContractError):
            validate_model(replace(self.snapshot,elements=(self.snapshot.elements[0],order,*self.snapshot.elements[2:])),self.meta)


if __name__ == '__main__':
    unittest.main()
