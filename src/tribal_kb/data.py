from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from tribal_kb.models import ConfigurationError, ObjectConfig


class DataCatalog:
    """In-memory Salesforce object rows and lazily-built field indexes."""

    def __init__(self, objects: dict[str, ObjectConfig], rows: dict[str, list[dict[str, str]]]):
        self.objects = objects
        self.rows = rows
        self._indexes: dict[tuple[str, str], dict[str, list[dict[str, str]]]] = {}

    @classmethod
    def load(cls, object_config_path: Path, data_dir: Path) -> "DataCatalog":
        config = load_json(object_config_path)
        object_specs = config.get("objects")
        if not isinstance(object_specs, dict) or not object_specs:
            raise ConfigurationError("Object config must contain a non-empty 'objects' mapping.")

        objects: dict[str, ObjectConfig] = {}
        rows: dict[str, list[dict[str, str]]] = {}
        for name, spec in object_specs.items():
            if not isinstance(spec, dict) or not spec.get("file"):
                raise ConfigurationError(f"Object '{name}' must define a CSV 'file'.")
            obj = ObjectConfig(
                name=name,
                file=str(spec["file"]),
                primary_key=str(spec.get("primary_key", "Id")),
            )
            path = data_dir / obj.file
            if not path.exists():
                raise ConfigurationError(f"CSV for object '{name}' was not found: {path}")
            objects[name] = obj
            rows[name] = read_csv(path)
        return cls(objects=objects, rows=rows)

    def get_rows(self, object_name: str) -> list[dict[str, str]]:
        if object_name not in self.rows:
            raise ConfigurationError(f"Unknown object '{object_name}'.")
        return self.rows[object_name]

    def index(self, object_name: str, field: str) -> dict[str, list[dict[str, str]]]:
        key = (object_name, field)
        if key not in self._indexes:
            index: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in self.get_rows(object_name):
                index[row.get(field, "")].append(row)
            self._indexes[key] = dict(index)
        return self._indexes[key]

    def related_rows(
        self,
        source_row: dict[str, str],
        related_object: str,
        local_field: str,
        remote_field: str,
    ) -> list[dict[str, str]]:
        return self.index(related_object, remote_field).get(source_row.get(local_field, ""), [])

    def summary(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.rows.items()}

    def validate_fields(self, object_name: str, fields: Iterable[str]) -> list[str]:
        rows = self.get_rows(object_name)
        known_fields = set().union(*(row.keys() for row in rows)) if rows else set()
        return [field for field in fields if field not in known_fields]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ConfigurationError(f"CSV has no header row: {path}")
        return [{key: value or "" for key, value in row.items()} for row in reader]


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Configuration file was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"Top-level JSON value must be an object: {path}")
    return data

