"""Contant value."""

from typing import Optional

from nortl.core.renderers.operations.base import SliceRenderer

__all__ = [
    'Slice',
]


class Slice(SliceRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        if self.value.is_primitive:
            if isinstance(self.index, int):
                return f'{self.value}[{self.index}]'
            else:
                return f'{self.value}[{self.index.start}:{self.index.stop}]'
        else:
            if isinstance(self.index, int):
                mask = 1
                offset = self.index
            else:
                mask = 2 ** (max(self.index.start, self.index.stop) - min(self.index.start, self.index.stop) + 1) - 1
                offset = self.index.stop

            if offset != 0:
                return f'(({self.value} >> {offset}) & {mask})'
            else:
                return f'({self.value} & {mask})'
