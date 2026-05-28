from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps


class OcrError(RuntimeError):
    pass


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    box: tuple[tuple[float, float], ...]
    rect: tuple[int, int, int, int]


@dataclass(frozen=True)
class OcrNumber:
    index: int
    text: str
    confidence: float
    rect: tuple[int, int, int, int]
    line_text: str


@dataclass(frozen=True)
class OcrResult:
    text: str
    lines: list[OcrLine]
    numbers: list[OcrNumber]


_NUMBER_TOKEN_RE = re.compile(r"[-+]?(?:\d[\d,]*(?:\.\d*)?|\.\d+)")


class RapidOcrReader:
    def __init__(self, min_confidence: float = 0.25) -> None:
        self.min_confidence = min_confidence
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise OcrError(
                "rapidocr-onnxruntime is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        self._engine = RapidOCR()

    def read(self, image: Image.Image) -> str:
        return self.read_result(image).text

    def read_result(self, image: Image.Image) -> OcrResult:
        prepared, scale = _prepare_image(image)
        result, _elapsed = self._engine(np.array(prepared))
        lines = self._parse_lines(result or [], scale)
        numbers = _extract_numbers(lines)
        return OcrResult(
            text="\n".join(line.text for line in lines),
            lines=lines,
            numbers=numbers,
        )

    def _parse_lines(self, result: list[Any], scale: float) -> list[OcrLine]:
        lines: list[OcrLine] = []
        for item in result:
            if len(item) < 3:
                continue

            box = _scale_box(item[0], scale)
            text = str(item[1]).strip()
            confidence = float(item[2])
            if text and confidence >= self.min_confidence:
                lines.append(
                    OcrLine(
                        text=text,
                        confidence=confidence,
                        box=box,
                        rect=_box_to_rect(box),
                    )
                )

        return sorted(lines, key=_line_sort_key)


def _prepare_image(image: Image.Image) -> tuple[Image.Image, float]:
    image = image.convert("RGB")

    width, height = image.size
    scale = 1.0
    if width < 900 or height < 260:
        scale = float(max(2, min(4, int(900 / max(width, 1)))))
        image = image.resize(
            (int(width * scale), int(height * scale)),
            Image.Resampling.LANCZOS,
        )

    grayscale = ImageOps.grayscale(image)
    grayscale = ImageOps.autocontrast(grayscale)
    grayscale = grayscale.filter(ImageFilter.SHARPEN)
    return grayscale.convert("RGB"), scale


def _extract_numbers(lines: list[OcrLine]) -> list[OcrNumber]:
    numbers: list[OcrNumber] = []

    for line in lines:
        text = unicodedata.normalize("NFKC", line.text)
        matches = list(_NUMBER_TOKEN_RE.finditer(text))
        if not matches:
            continue

        for match in matches:
            numbers.append(
                OcrNumber(
                    index=len(numbers),
                    text=_clean_number(match.group(0)),
                    confidence=line.confidence,
                    rect=_number_rect(line.rect, text, match.start(), match.end()),
                    line_text=line.text,
                )
            )

    return numbers


def _number_rect(
    line_rect: tuple[int, int, int, int],
    line_text: str,
    start: int,
    end: int,
) -> tuple[int, int, int, int]:
    x, y, width, height = line_rect
    text_length = max(len(line_text), 1)
    left = x + int(width * start / text_length)
    right = x + int(width * end / text_length)
    token_width = max(right - left, 14)
    pad_x = 4
    pad_y = max(3, int(height * 0.08))
    return (
        max(0, left - pad_x),
        max(0, y - pad_y),
        token_width + pad_x * 2,
        height + pad_y * 2,
    )


def _clean_number(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace(",", "")


def _scale_box(box: Any, scale: float) -> tuple[tuple[float, float], ...]:
    scaled = []
    for point in box:
        x, y = point[0], point[1]
        scaled.append((float(x) / scale, float(y) / scale))
    return tuple(scaled)


def _box_to_rect(box: tuple[tuple[float, float], ...]) -> tuple[int, int, int, int]:
    xs = [point[0] for point in box]
    ys = [point[1] for point in box]
    left = int(min(xs))
    top = int(min(ys))
    right = int(max(xs))
    bottom = int(max(ys))
    return (left, top, max(1, right - left), max(1, bottom - top))


def _line_sort_key(line: OcrLine) -> tuple[int, float]:
    try:
        xs = [point[0] for point in line.box]
        ys = [point[1] for point in line.box]
        return (round(sum(ys) / len(ys) / 12), sum(xs) / len(xs))
    except Exception:
        return (0, 0.0)

