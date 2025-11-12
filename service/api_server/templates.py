from __future__ import annotations

"""SPARQL template registry utilities."""

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_REGISTRY_PATH = _TEMPLATE_DIR / "registry.json"


@dataclass(slots=True)
class ParameterSpec:
    name: str
    type: str
    default: Any | None = None


@dataclass(slots=True)
class Template:
    name: str
    file: Path
    params: Mapping[str, ParameterSpec]
    allow_in: Iterable[str]

    def render(self, values: Mapping[str, Any]) -> str:
        data = self.file.read_text(encoding="utf-8")
        merged: Dict[str, Any] = {}
        for key, spec in self.params.items():
            if key in values:
                merged[key] = _sanitize(values[key], spec.type)
            elif spec.default is not None:
                merged[key] = _sanitize(spec.default, spec.type)
            else:
                raise KeyError(
                    f"Missing required template parameter '{key}' for {self.name}"
                )
        # Ensure no unexpected params sneak in
        for unexpected in set(values) - set(self.params):
            raise KeyError(f"Unknown template parameter '{unexpected}' for {self.name}")
        rendered = data
        for key, value in merged.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", value)
        return rendered


class TemplateRegistry:
    """Lazy loader for SPARQL query templates."""

    def __init__(self, templates: Mapping[str, Template]):
        self._templates = dict(templates)

    @classmethod
    def load_default(cls) -> "TemplateRegistry":
        raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        templates: Dict[str, Template] = {}
        for name, entry in raw.items():
            file_path = _TEMPLATE_DIR / entry["file"]
            params = {
                p_name: ParameterSpec(
                    name=p_name,
                    type=p_details["type"],
                    default=p_details.get("default"),
                )
                for p_name, p_details in entry.get("params", {}).items()
            }
            allow_in = entry.get("allow_in", [])
            templates[name] = Template(
                name=name,
                file=file_path,
                params=params,
                allow_in=allow_in,
            )
        return cls(templates)

    def get(self, name: str) -> Template:
        try:
            return self._templates[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"Unknown template '{name}'") from exc

    def filter_by_allow_in(self, scope: str) -> Dict[str, Template]:
        return {
            name: template
            for name, template in self._templates.items()
            if scope in template.allow_in
        }

    @property
    def names(self) -> Iterable[str]:
        return self._templates.keys()


def _sanitize(value: Any, kind: str) -> str:
    if kind == "iri":
        if not isinstance(value, str):
            raise TypeError("IRI values must be strings")
        if not _IRI_RE.match(value):
            raise ValueError(f"Invalid IRI value: {value}")
        return f"<{value}>"
    if kind == "string":
        if not isinstance(value, str):
            raise TypeError("String parameters must be str")
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if kind == "int":
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        if not isinstance(value, int):
            raise TypeError("Integer parameters must be integers")
        return str(value)
    if kind == "float":
        if isinstance(value, (int, float)):
            return str(value)
        raise TypeError("Float parameters must be numbers")
    raise ValueError(f"Unsupported parameter type '{kind}'")


_IRI_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:.+")
