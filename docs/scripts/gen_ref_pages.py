"""Generate the code reference pages."""

from pathlib import Path
from typing import Sequence

import mkdocs_gen_files

INIT_TEMPLATE = """
::: {identifier}
    options:
        members: [{members}]
        members_order: alphabetical
"""


def find_submodules(dir: Path) -> Sequence[str]:
    """Find submodules within a directory."""
    submodules = []
    for path in dir.iterdir():
        if path.is_dir():
            if (path / '__init__.py').exists():
                submodules.append(path.name)
        elif path.suffix == '.py' and path.stem != '__init__':
            submodules.append(path.stem)
    return sorted(submodules)


def gen_ref_pages():
    nav = mkdocs_gen_files.Nav()
    mod_symbol = '<code class="doc-symbol doc-symbol-nav doc-symbol-module"></code>'

    root = Path(__file__).parent.parent.parent
    src = root / 'src'

    for path in sorted(src.rglob('*.py')):
        # Skip Python files that are not in a module
        if not (path.parent / '__init__.py').exists():
            continue

        module_path = path.relative_to(src).with_suffix('')
        doc_path = path.relative_to(src).with_suffix('.md')
        full_doc_path = Path('reference', doc_path)

        parts = tuple(module_path.parts)

        if is_init := parts[-1] == '__init__':
            parts = parts[:-1]
            doc_path = doc_path.with_name('index.md')
            full_doc_path = full_doc_path.with_name('index.md')
        elif parts[-1] == '__main__':
            continue

        nav_parts = [f'{mod_symbol} {part}' for part in parts]
        nav[tuple(nav_parts)] = doc_path.as_posix()

        with mkdocs_gen_files.open(full_doc_path, 'w') as fd:
            identifier = '.'.join(parts)
            if is_init:
                text = INIT_TEMPLATE.format(identifier=identifier, members=','.join(find_submodules(path.parent)))
            else:
                text = f'::: {identifier}\n'
            print(text, file=fd)

        mkdocs_gen_files.set_edit_path(full_doc_path, Path('../../') / path.relative_to(root))

    with mkdocs_gen_files.open('reference/summary.nav', 'w') as nav_file:
        nav_file.writelines(nav.build_literate_nav())


gen_ref_pages()
