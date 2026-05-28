# DragCalculator

[한국어 문서](README.ko.md)

DragCalculator is a Windows desktop calculator that reads numbers from a dragged screen region. Capture an area, review the detected numbers, correct OCR mistakes, reorder values, and calculate with regular or scientific formulas.

![DragCalculator workbench](docs/screenshots/01-workbench.png)

## Features

- Drag a screen region and run CPU OCR on only that capture.
- Preview the captured image with red boxes around detected numbers.
- Click a red box, or edit the number list, to correct OCR results.
- Reorder detected numbers with drag and drop.
- Apply uniform operations across all numbers: add, subtract, multiply, or divide.
- Build custom formulas with parentheses and number references such as `n1+(n2+n3)`.
- Use scientific helpers: `sqrt`, `sin`, `cos`, `tan`, `log`, `ln`, exponent, and `pi`.
- Automatically copy the latest result to the clipboard.
- Build a Windows executable with PyInstaller.

## Screenshots

### Formula Workbench

![Custom formula mode](docs/screenshots/02-custom-formula.png)

### Capture Overlay

![Capture overlay](docs/screenshots/03-capture-overlay.png)

## Example Workflows

Detected numbers:

```text
3, 4, 5
```

Uniform operations:

```text
3+4+5 = 12
3*4*5 = 60
```

Custom formula:

```text
n1+(n2+n3) -> 3+(4+5) = 12
```

Scientific formula:

```text
sqrt(n1^2+n2^2)
```

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

If your virtual environment is already activated:

```powershell
python run.py
```

## Build Windows EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The executable is created at:

```text
dist\DragCalculator\DragCalculator.exe
```

## Generate Screenshots

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe .\tools\generate_screenshots.py
```

Screenshots are saved in:

```text
docs\screenshots
```

## Notes

- GPU is not required.
- OCR quality depends on capture size, contrast, font clarity, and screen scaling.
- Press `Esc` on the capture overlay to cancel.
- The built `dist` folder is intentionally ignored by git.

