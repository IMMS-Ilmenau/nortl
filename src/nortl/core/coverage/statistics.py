"""Coverage statistics."""

__all__ = [
    'CoverageStatistics',
]


class CoverageStatistics:
    """Coverage statistics."""

    def __init__(self, name: str, covered: int, total: int) -> None:
        self.name = name
        self.covered = covered
        self.total = total
        self.uncovered = total - covered
        self.percentage = covered / total if total > 0 else 1

    def __str__(self) -> str:
        return f'{self}'

    def __format__(self, format_spec: str) -> str:
        return f'{self.name}: {self.covered} / {self.total} covered ({self.percentage:.1%})'
