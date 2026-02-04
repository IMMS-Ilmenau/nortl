class VerilogFormatter:
    def __init__(self, code: str) -> None:
        self.code_lst = code.split('\n')
        self.indent_level = 0

    def format(self) -> str:
        self.code_lst = [self._indent(line) for line in self.code_lst]
        self.code_lst = [self._newlines(line) for line in self.code_lst]
        return '\n'.join(self.code_lst)

    def _indent(self, line: str) -> str:
        reasons_for_indent = ['begin', 'case']
        reasons_for_dedent = ['end', 'endcase']

        if any([x in line.split() for x in reasons_for_dedent]):
            self.indent_level -= 1

        ret = '   ' * self.indent_level + line

        if any([x in line.split() for x in reasons_for_indent]):
            self.indent_level += 1

        return ret

    def _newlines(self, line: str) -> str:
        reasons_for_newline = ['module', 'always']
        if any(line.strip().startswith(reason) for reason in reasons_for_newline):
            return f'\n{line}'
        return line
