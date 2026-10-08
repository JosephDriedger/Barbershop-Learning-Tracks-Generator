"""Typed failures of the engine-neutral synthesis layer. ``code`` is stable, for scripts."""


class SynthesisPlanError(ValueError):
    """A synthesis plan cannot be built, or a plan object would be invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class PlanNotReadyError(RuntimeError):
    """A plan with unresolved review items was given to something that needs a ready plan."""

    def __init__(self, items: int, summary: str) -> None:
        super().__init__(f"PLAN_NOT_READY: {items} unresolved review item(s): {summary}")
        self.code = "PLAN_NOT_READY"
        self.items = items
