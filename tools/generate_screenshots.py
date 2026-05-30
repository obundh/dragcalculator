from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import QApplication

from dragcalculator.app import AppController, SelectionOverlay
from dragcalculator.calculator import calculate_from_text
from dragcalculator.ocr import OcrNumber, OcrResult


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = ROOT / "docs" / "screenshots"


def main() -> int:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication([])
    controller = AppController()
    controller.start()
    app.processEvents()

    sample_image, ocr_result = make_sample_capture()
    controller.window.set_capture_result(
        sample_image,
        ocr_result,
        calculate_from_text(ocr_result.text),
    )
    controller.window.resize(1200, 960)
    controller.window.show()
    controller.window.fit_preview_to_width()
    app.processEvents()
    controller.window.grab().save(str(SCREENSHOT_DIR / "01-workbench.png"))

    controller.window.formula_input.setText("n1+(n2+n3)")
    controller.window.apply_custom_expression()
    app.processEvents()
    controller.window.grab().save(str(SCREENSHOT_DIR / "02-custom-formula.png"))

    overlay = SelectionOverlay(lambda _rect: None, lambda: None)
    overlay.setGeometry(120, 120, 940, 520)
    overlay._selection = QRect(180, 130, 520, 230)
    overlay.show()
    app.processEvents()
    overlay.grab().save(str(SCREENSHOT_DIR / "03-capture-overlay.png"))
    overlay.close()
    controller.window.close()

    return 0


def make_sample_capture() -> tuple[Image.Image, OcrResult]:
    image = Image.new("RGB", (920, 540), "#ffffff")
    draw = ImageDraw.Draw(image)
    title_font = load_font(38, bold=True)
    label_font = load_font(28)
    number_font = load_font(32, bold=True)

    draw.rounded_rectangle((24, 24, 896, 516), radius=18, outline="#d7dee7", width=3)
    draw.text((54, 48), "Q2 Utility Cost", fill="#111827", font=title_font)
    draw.text((54, 112), "Electricity", fill="#475569", font=label_font)
    draw.text((680, 112), "320.50", fill="#111827", font=number_font)
    draw.text((54, 178), "Water", fill="#475569", font=label_font)
    draw.text((716, 178), "84.25", fill="#111827", font=number_font)
    draw.text((54, 244), "Maintenance", fill="#475569", font=label_font)
    draw.text((716, 244), "54.75", fill="#111827", font=number_font)
    draw.text((54, 332), "Formula example", fill="#64748b", font=label_font)
    draw.text((604, 332), "n1+(n2+n3)", fill="#0f766e", font=number_font)

    numbers = [
        OcrNumber(0, "320.50", 0.98, (668, 102, 136, 48), "Electricity 320.50"),
        OcrNumber(1, "84.25", 0.96, (704, 168, 112, 48), "Water 84.25"),
        OcrNumber(2, "54.75", 0.96, (704, 234, 112, 48), "Maintenance 54.75"),
    ]
    return image, OcrResult(text="320.50 84.25 54.75", lines=[], numbers=numbers)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            pass
    return ImageFont.load_default()


if __name__ == "__main__":
    raise SystemExit(main())
