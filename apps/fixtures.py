"""Load the historical JSON fixture without importing application composition."""
from pathlib import Path

from modelspine_protocols import CheckPlan, Metamodel, Snapshot, loads


def load_fixture():
    folder = Path(__file__).resolve().parents[1] / "domain-packs" / "order-approval"

    def read(cls, name):
        return loads(cls, (folder / name).read_text(encoding="utf-8"))

    return read(Metamodel, "metamodel.json"), read(Snapshot, "model.json"), read(CheckPlan, "obligations.json")
