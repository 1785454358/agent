"""Render only schema branches applicable to this evaluation call."""


def evaluation_schema(schema, *, scientific: bool):
    document = schema.model_json_schema()
    definitions = document.get("$defs", {})
    if not scientific:
        finding = definitions.get("ReferenceFindingDraft", {})
        for field in ("research_result", "experiments"):
            finding.get("properties", {}).pop(field, None)
    reachable = set()

    def visit(value):
        if isinstance(value, dict):
            reference = value.get("$ref", "")
            if reference.startswith("#/$defs/"):
                name = reference.rsplit("/", 1)[1]
                if name not in reachable:
                    reachable.add(name)
                    visit(definitions.get(name, {}))
            for key, child in value.items():
                if key != "$defs":
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)
    document["$defs"] = {name: value for name, value in definitions.items() if name in reachable}
    return document
