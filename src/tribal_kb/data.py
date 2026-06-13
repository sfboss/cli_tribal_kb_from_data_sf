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
        self._object_names = {name.casefold(): name for name in objects}
        self._indexes: dict[tuple[str, str], dict[str, list[dict[str, str]]]] = {}

    @classmethod
    def load(cls, object_config_path: Path, data_dir: Path) -> "DataCatalog":
        config = load_json(object_config_path)
        object_specs = config.get("objects")
        if not isinstance(object_specs, dict) or not object_specs:
            raise ConfigurationError("Object config must contain a non-empty 'objects' mapping.")
        if not data_dir.is_dir():
            raise ConfigurationError(f"Data directory was not found: {data_dir}")

        csv_files: dict[str, Path] = {}
        for path in data_dir.iterdir():
            if path.is_file() and path.suffix.casefold() == ".csv":
                key = path.name.casefold()
                if key in csv_files:
                    raise ConfigurationError(
                        f"Multiple CSV files differ only by case: {csv_files[key].name}, {path.name}"
                    )
                csv_files[key] = path

        objects: dict[str, ObjectConfig] = {}
        rows: dict[str, list[dict[str, str]]] = {}
        for name, spec in object_specs.items():
            if not isinstance(spec, dict):
                raise ConfigurationError(f"Object '{name}' must be an object mapping.")
            expected_file = f"{name}.csv"
            declared_file = str(spec.get("file", expected_file))
            if Path(declared_file).name != declared_file or declared_file.casefold() != expected_file.casefold():
                raise ConfigurationError(
                    f"Object '{name}' must use the direct filename '{expected_file}' "
                    "(matching is case-insensitive)."
                )
            path = csv_files.get(expected_file.casefold())
            if not path:
                raise ConfigurationError(
                    f"CSV for object '{name}' was not found. Expected a case-insensitive "
                    f"match for {data_dir / expected_file}"
                )
            obj = ObjectConfig(
                name=name,
                file=path.name,
                primary_key=str(spec.get("primary_key", "Id")),
            )
            objects[name] = obj
            rows[name] = read_csv(path)
        return cls(objects=objects, rows=rows)

    def get_rows(self, object_name: str) -> list[dict[str, str]]:
        resolved_name = self.resolve_object_name(object_name)
        if not resolved_name:
            raise ConfigurationError(f"Unknown object '{object_name}'.")
        return self.rows[resolved_name]

    def has_object(self, object_name: str) -> bool:
        return object_name.casefold() in self._object_names

    def resolve_object_name(self, object_name: str) -> str | None:
        return self._object_names.get(object_name.casefold())

    def index(self, object_name: str, field: str) -> dict[str, list[dict[str, str]]]:
        resolved_name = self.resolve_object_name(object_name)
        if not resolved_name:
            raise ConfigurationError(f"Unknown object '{object_name}'.")
        key = (resolved_name, field)
        if key not in self._indexes:
            index: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in self.get_rows(resolved_name):
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
