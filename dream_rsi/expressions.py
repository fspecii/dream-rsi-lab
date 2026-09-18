"""A deliberately small, bounded expression language for executable policies.

No attributes, imports, indexing, loops, file access, or hidden trace objects.
Policy code is interpreted, never exec'd. Numeric expression strings are also
exported as readable Python for inspection; this is not an OS security sandbox.
"""
import ast
import math
import operator

FUNCTIONS = {"min": min, "max": max, "abs": abs, "int": int, "round": round}
BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
          ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
COMPARE = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}


class Expression:
    def __init__(self, source: str, names: set[str]):
        if not isinstance(source, str) or len(source) > 1000:
            raise ValueError("expression must be a string of at most 1000 characters")
        self.source = source
        self.tree = ast.parse(source, mode="eval").body
        if len(list(ast.walk(self.tree))) > 150:
            raise ValueError("expression exceeds AST size limit")
        self._validate(self.tree, names)

    def _validate(self, node, names):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, bool):
            if not math.isfinite(node.value) or abs(node.value) > 10000:
                raise ValueError("numeric literal out of bounds")
        elif isinstance(node, ast.Name) and node.id in names:
            pass
        elif isinstance(node, ast.BinOp) and type(node.op) in BINARY:
            self._validate(node.left, names)
            self._validate(node.right, names)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
            self._validate(node.operand, names)
        elif isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            for value in node.values:
                self._validate(value, names)
        elif isinstance(node, ast.Compare) and all(type(op) in COMPARE for op in node.ops):
            for child in [node.left, *node.comparators]:
                self._validate(child, names)
        elif isinstance(node, ast.IfExp):
            for child in (node.test, node.body, node.orelse):
                self._validate(child, names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and not node.keywords and 1 <= len(node.args) <= 5:
            for arg in node.args:
                self._validate(arg, names)
        else:
            raise ValueError(f"unsupported policy syntax: {ast.dump(node)[:180]}")

    def __call__(self, values: dict) -> float | bool:
        def visit(n):
            if isinstance(n, ast.Constant):
                result = n.value
            elif isinstance(n, ast.Name):
                result = values[n.id]
            elif isinstance(n, ast.BinOp):
                result = BINARY[type(n.op)](visit(n.left), visit(n.right))
            elif isinstance(n, ast.UnaryOp):
                v = visit(n.operand)
                result = -v if isinstance(n.op, ast.USub) else (+v if isinstance(n.op, ast.UAdd) else not v)
            elif isinstance(n, ast.BoolOp):
                # Short-circuit, matching the exported Python semantics.
                result = visit(n.values[0])
                for child in n.values[1:]:
                    if isinstance(n.op, ast.And) and not result or isinstance(n.op, ast.Or) and result:
                        break
                    result = visit(child)
            elif isinstance(n, ast.Compare):
                left, result = visit(n.left), True
                for op, child in zip(n.ops, n.comparators):
                    right = visit(child)
                    if not COMPARE[type(op)](left, right):
                        result = False
                        break
                    left = right
            elif isinstance(n, ast.IfExp):
                result = visit(n.body if visit(n.test) else n.orelse)
            else:
                result = FUNCTIONS[n.func.id](*[visit(a) for a in n.args])
            if type(result) not in (int, float, bool) or not math.isfinite(result) or abs(result) > 1e12:
                raise ValueError("policy expression produced a non-finite or unbounded result")
            return result
        try:
            return visit(self.tree)
        except (ArithmeticError, TypeError, KeyError) as exc:
            raise ValueError(f"policy expression failed: {self.source}: {exc}") from exc
