"""Native LangSmith examples, with stable identities for repeatable uploads."""
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


def load_examples(path: Path):
    records, seen = [], set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        identity = record.get("metadata", {}).get("id")
        question = record.get("inputs", {}).get("question")
        answer = record.get("outputs", {}).get("answer")
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError(f"line {line_number}: metadata.id is required")
        if identity in seen:
            raise ValueError(f"duplicate example id: {identity}")
        if not isinstance(question, str) or not question.strip() or not isinstance(answer, str):
            raise ValueError(f"line {line_number}: question and reference answer are required")
        seen.add(identity)
        records.append(record)
    if not records:
        raise ValueError("dataset is empty")
    return records


def sync_dataset(client, name, records):
    dataset = (client.read_dataset(dataset_name=name) if client.has_dataset(dataset_name=name)
               else client.create_dataset(name, description="DeepTrace reference questions; see per-example provenance and scope."))
    existing = {str(example.id) for example in client.list_examples(dataset_id=dataset.id)}
    pending = []
    seen = set()
    for record in records:
        identity = uuid5(NAMESPACE_URL, f"deeptrace/{name}/{record['metadata']['id']}")
        if identity in seen:
            raise ValueError("duplicate example id")
        seen.add(identity)
        values = {key: record[key] for key in ("inputs", "outputs", "metadata")}
        split = record["metadata"].get("split")
        if split:
            values["split"] = split
        if str(identity) in existing:
            client.update_example(identity, **values)
        else:
            pending.append({"id": identity, **values})
    if pending:
        client.create_examples(dataset_id=dataset.id, examples=pending)
    return dataset
