from __future__ import annotations

from typing import Any

from .base import BaseCommissionModule, ModuleResult


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, BaseCommissionModule] = {}

    def register(self, module: BaseCommissionModule) -> None:
        self._modules[module.name] = module

    def run_all(self, context: dict[str, Any]) -> list[ModuleResult]:
        results: list[ModuleResult] = []
        for name in sorted(self._modules):
            result = self._modules[name].run(context)
            results.append(result)
        return results

    @property
    def modules(self) -> list[BaseCommissionModule]:
        return list(self._modules.values())
