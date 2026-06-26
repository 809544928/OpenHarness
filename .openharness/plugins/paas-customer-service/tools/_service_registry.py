from __future__ import annotations

from pathlib import Path

import yaml

try:
    from ._config import get_registry_path
    from ._errors import RegistryError
    from ._models import ServiceCandidate, ServiceDefinition, ServiceRegistryConfig, ServiceResolution
except ImportError:
    from _config import get_registry_path
    from _errors import RegistryError
    from _models import ServiceCandidate, ServiceDefinition, ServiceRegistryConfig, ServiceResolution


class ServiceRegistry:
    def __init__(self, services: list[ServiceDefinition]) -> None:
        if not services:
            raise RegistryError("service registry must contain at least one service")
        self._services = services
        self._by_id = {service.id: service for service in services}
        if len(self._by_id) != len(services):
            raise RegistryError("service ids must be unique")

    def list_services(self) -> list[ServiceDefinition]:
        return list(self._services)

    def get(self, service_id: str) -> ServiceDefinition:
        service = self._by_id.get(service_id)
        if service is None:
            raise RegistryError(f"unknown serviceId: {service_id}")
        return service

    def resolve(self, message: str, candidate: str | None = None) -> ServiceResolution:
        haystacks = [candidate or "", message or ""]
        matched: list[ServiceDefinition] = []
        for service in self._services:
            aliases = [service.id, service.display_name, *service.aliases]
            if any(_contains_alias(haystack, aliases) for haystack in haystacks if haystack):
                matched.append(service)

        unique = _dedupe_services(matched)
        if len(unique) == 1:
            service = unique[0]
            return ServiceResolution.model_validate(
                {
                    "serviceId": service.id,
                    "confidence": 0.98,
                    "ambiguous": False,
                    "candidates": [_candidate(service)],
                }
            )
        if len(unique) > 1:
            return ServiceResolution.model_validate(
                {
                    "serviceId": None,
                    "confidence": 0.5,
                    "ambiguous": True,
                    "candidates": [_candidate(service) for service in unique],
                }
            )
        return ServiceResolution.model_validate(
            {
                "serviceId": None,
                "confidence": 0.0,
                "ambiguous": False,
                "candidates": [_candidate(service) for service in self._services],
            }
        )


def load_service_registry(path: str | Path | None = None) -> ServiceRegistry:
    registry_path = Path(path).expanduser().resolve() if path is not None else get_registry_path()
    if not registry_path.exists():
        raise RegistryError(f"service registry not found: {registry_path}")
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    config = ServiceRegistryConfig.model_validate(raw)
    return ServiceRegistry(config.services)


def _contains_alias(text: str, aliases: list[str]) -> bool:
    normalized_text = text.lower()
    return any(alias and alias.lower() in normalized_text for alias in aliases)


def _dedupe_services(services: list[ServiceDefinition]) -> list[ServiceDefinition]:
    seen: set[str] = set()
    unique: list[ServiceDefinition] = []
    for service in services:
        if service.id in seen:
            continue
        seen.add(service.id)
        unique.append(service)
    return unique


def _candidate(service: ServiceDefinition) -> ServiceCandidate:
    return ServiceCandidate.model_validate({"serviceId": service.id, "displayName": service.display_name})
