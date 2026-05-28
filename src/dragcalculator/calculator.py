from __future__ import annotations

import ast
import math
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation, getcontext
from typing import Sequence

getcontext().prec = 28


class CalculationError(ValueError):
    pass


@dataclass(frozen=True)
class Calculation:
    raw_text: str
    expression: str
    mode: str
    value: Decimal
    display: str


_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
_EXPRESSION_NUMBER_RE = re.compile(r"(?<![\d.])(?:\d+(?:\.\d*)?|\.\d+)")
_UNSAFE_EXPR_CHARS_RE = re.compile(r"[^0-9+\-*/().\s]")

_OPERATOR_LABELS = {
    "+": "add",
    "-": "subtract",
    "*": "multiply",
    "/": "divide",
}


def calculate_from_text(text: str) -> Calculation:
    normalized = normalize_ocr_text(text)
    if not normalized:
        raise CalculationError("OCR did not return any text.")

    if _looks_like_expression(normalized):
        expression = _extract_expression(normalized)
        if expression and not _has_suspicious_operator_sequence(expression):
            try:
                return calculate_expression(expression, raw_text=text, mode="expression")
            except CalculationError:
                pass

    numbers = [Decimal(match.group(0)) for match in _NUMBER_RE.finditer(normalized)]
    if not numbers:
        raise CalculationError("No numbers were found in the OCR text.")

    value = sum(numbers, Decimal("0"))
    expression = " + ".join(_format_decimal(number) for number in numbers)
    return Calculation(
        raw_text=text,
        expression=expression,
        mode="sum",
        value=value,
        display=_format_decimal(value),
    )


def calculate_expression(
    expression: str,
    raw_text: str | None = None,
    mode: str = "custom",
) -> Calculation:
    prepared = normalize_expression(expression)
    if not prepared:
        raise CalculationError("Expression is empty.")

    value = _SafeDecimalEvaluator.evaluate(prepared)
    return Calculation(
        raw_text=raw_text if raw_text is not None else expression,
        expression=prepared,
        mode=mode,
        value=value,
        display=_format_decimal(value),
    )


def calculate_with_operator(numbers: Sequence[str], operator: str) -> Calculation:
    if operator not in _OPERATOR_LABELS:
        raise CalculationError(f"Unsupported operation: {operator}")

    cleaned_numbers = [clean_number_text(number) for number in numbers]
    if not cleaned_numbers:
        raise CalculationError("No editable numbers are available.")

    expression = f" {operator} ".join(cleaned_numbers)
    return calculate_expression(
        expression,
        raw_text=" ".join(cleaned_numbers),
        mode=_OPERATOR_LABELS[operator],
    )


def calculate_from_edited_numbers(
    base_calculation: Calculation,
    numbers: Sequence[str],
) -> Calculation:
    cleaned_numbers = [clean_number_text(number) for number in numbers]
    if not cleaned_numbers:
        raise CalculationError("No editable numbers are available.")

    if base_calculation.mode == "expression":
        expression = replace_numbers_in_expression(base_calculation.expression, cleaned_numbers)
        return calculate_expression(expression, raw_text=expression, mode="expression")

    return calculate_with_operator(cleaned_numbers, "+")


def clean_number_text(text: str) -> str:
    normalized = normalize_ocr_text(text).replace(",", "")
    match = _NUMBER_RE.fullmatch(normalized)
    if match is None:
        raise CalculationError(f"Invalid number: {text}")
    return _format_decimal(Decimal(normalized))


def replace_numbers_in_expression(expression: str, numbers: Sequence[str]) -> str:
    iterator = iter(numbers)
    replacements = 0

    def replace(_match: re.Match[str]) -> str:
        nonlocal replacements
        try:
            value = next(iterator)
        except StopIteration:
            return _match.group(0)
        replacements += 1
        return value

    edited_expression = _EXPRESSION_NUMBER_RE.sub(replace, expression)
    if replacements == 0:
        return " + ".join(numbers)
    return edited_expression


def normalize_expression(expression: str) -> str:
    expression = normalize_ocr_text(expression)
    expression = expression.replace("^", "**")
    expression = re.sub(r"\s+", "", expression)
    return expression


def normalize_ocr_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    replacements = {
        "−": "-",
        "–": "-",
        "—": "-",
        "×": "*",
        "x": "*",
        "X": "*",
        "÷": "/",
        "=": "=",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _looks_like_expression(text: str) -> bool:
    left_side = text.split("=", 1)[0]
    if any(operator in left_side for operator in ("+", "*", "/", "(", ")")):
        return True
    return bool(re.search(r"\d\s*-\s*\d", left_side))


def _extract_expression(text: str) -> str:
    left_side = text.split("=", 1)[0]
    expression = _UNSAFE_EXPR_CHARS_RE.sub("", left_side)
    expression = re.sub(r"\s+", "", expression)
    expression = expression.strip()

    while expression and expression[-1] in "+-*/.":
        expression = expression[:-1]

    return expression


def _has_suspicious_operator_sequence(expression: str) -> bool:
    # OCR often reads a plus as a dangling minus followed by a signed number.
    return "-+" in expression


def _format_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(value.quantize(Decimal("1")))

    formatted = format(value.normalize(), "f")
    return formatted.rstrip("0").rstrip(".")


class _SafeDecimalEvaluator(ast.NodeVisitor):
    _BIN_OPS = {
        ast.Add: lambda left, right: left + right,
        ast.Sub: lambda left, right: left - right,
        ast.Mult: lambda left, right: left * right,
        ast.Div: lambda left, right: left / right,
        ast.Pow: lambda left, right: left**right,
    }

    _UNARY_OPS = {
        ast.UAdd: lambda value: value,
        ast.USub: lambda value: -value,
    }

    _CONSTANTS = {
        "pi": lambda: _from_float(math.pi),
        "e": lambda: _from_float(math.e),
        "tau": lambda: _from_float(math.tau),
    }

    _FUNCTIONS = {
        "abs": lambda value: abs(value),
        "sqrt": lambda value: _from_float(math.sqrt(float(value))),
        "sin": lambda value: _from_float(math.sin(float(value))),
        "cos": lambda value: _from_float(math.cos(float(value))),
        "tan": lambda value: _from_float(math.tan(float(value))),
        "asin": lambda value: _from_float(math.asin(float(value))),
        "acos": lambda value: _from_float(math.acos(float(value))),
        "atan": lambda value: _from_float(math.atan(float(value))),
        "ln": lambda value: _from_float(math.log(float(value))),
        "log": lambda value: _from_float(math.log10(float(value))),
        "log10": lambda value: _from_float(math.log10(float(value))),
        "floor": lambda value: Decimal(math.floor(value)),
        "ceil": lambda value: Decimal(math.ceil(value)),
        "round": lambda value: value.to_integral_value(),
        "pow": lambda left, right: left**right,
    }

    @classmethod
    def evaluate(cls, expression: str) -> Decimal:
        try:
            tree = ast.parse(expression, mode="eval")
            return cls().visit(tree)
        except (
            SyntaxError,
            DivisionByZero,
            InvalidOperation,
            OverflowError,
            ValueError,
            ZeroDivisionError,
        ) as exc:
            raise CalculationError(f"Could not calculate expression: {expression}") from exc

    def visit_Expression(self, node: ast.Expression) -> Decimal:
        return self.visit(node.body)

    def visit_BinOp(self, node: ast.BinOp) -> Decimal:
        operator = self._BIN_OPS.get(type(node.op))
        if operator is None:
            raise CalculationError("Unsupported operator.")
        return operator(self.visit(node.left), self.visit(node.right))

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Decimal:
        operator = self._UNARY_OPS.get(type(node.op))
        if operator is None:
            raise CalculationError("Unsupported unary operator.")
        return operator(self.visit(node.operand))

    def visit_Constant(self, node: ast.Constant) -> Decimal:
        if not isinstance(node.value, (int, float)):
            raise CalculationError("Only numeric values are supported.")
        return Decimal(str(node.value))

    def visit_Name(self, node: ast.Name) -> Decimal:
        constant = self._CONSTANTS.get(node.id)
        if constant is None:
            raise CalculationError(f"Unknown value: {node.id}")
        return constant()

    def visit_Call(self, node: ast.Call) -> Decimal:
        if not isinstance(node.func, ast.Name):
            raise CalculationError("Unsupported function call.")

        function = self._FUNCTIONS.get(node.func.id)
        if function is None:
            raise CalculationError(f"Unsupported function: {node.func.id}")

        args = [self.visit(arg) for arg in node.args]
        if node.keywords:
            raise CalculationError("Keyword arguments are not supported.")

        try:
            return function(*args)
        except TypeError as exc:
            raise CalculationError(f"Wrong number of arguments for {node.func.id}.") from exc

    def generic_visit(self, node: ast.AST) -> Decimal:
        raise CalculationError(f"Unsupported expression node: {type(node).__name__}")


def _from_float(value: float) -> Decimal:
    if not math.isfinite(value):
        raise CalculationError("Result is not finite.")
    return Decimal(str(value))
