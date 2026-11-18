#!/usr/bin/env python3
"""
Parts Label Generator
Creates a 3" × 2" PDF parts label with Code 128 barcode.

Usage:
  Interactive (loops until you quit):
    python make_parts_label.py

  Command-line (single label):
    python make_parts_label.py "BRZ CT 450 L SS" "CLAMP WITH LINER"
    python make_parts_label.py "BRZ CT 450 L SS" "CLAMP WITH LINER" --header "PARTS LABEL"
    python make_parts_label.py "BRZ CT 450 L SS" "CLAMP WITH LINER" -H "SHOP STOCK" -o my_label.pdf
"""

import argparse
import csv
import json
import os
import re
import sys
import tempfile

try:
    from barcode import get_barcode_class
    from barcode.writer import ImageWriter
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    from reportlab.lib.colors import black, white
    from reportlab.lib.utils import ImageReader
except ImportError:
    print("Missing dependency. Install with:")
    print("  pip install python-barcode pillow reportlab")
    sys.exit(1)



def _enable_windows_color() -> None:
    """Turn on ANSI colors in Windows console."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL
    except Exception:
        pass


_enable_windows_color()

# Colors
RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GRN = "\033[92m"
YEL = "\033[93m"
BLU = "\033[94m"
MAG = "\033[95m"
CYN = "\033[96m"
WHT = "\033[97m"

APP_SETTINGS_NAME = "settings.json"


def _is_frozen() -> bool:
    """True when running from a PyInstaller build rather than the scripts."""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> str:
    """Folder the scripts or the installed program live in.

    PARTS_LABEL_SEARCH_DIR overrides this for tests. Running the scripts from
    the LABEL MAKER folder still looks for parts_list_clean.csv here.
    """
    override = os.environ.get("PARTS_LABEL_SEARCH_DIR")
    if override:
        return os.path.abspath(override)
    if _is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def user_data_dir() -> str:
    """Printer setting and saved paths. This folder survives uninstall.

    Windows: %APPDATA%\\PartsLabel
    Linux:   $XDG_DATA_HOME/parts-label-maker or ~/.local/share/parts-label-maker
    macOS:   ~/Library/Application Support/PartsLabel
    Override with PARTS_LABEL_DATA_DIR.
    """
    override = os.environ.get("PARTS_LABEL_DATA_DIR")
    if override:
        path = os.path.abspath(override)
    elif sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "PartsLabel")
    elif sys.platform == "darwin":
        path = os.path.join(
            os.path.expanduser("~"), "Library", "Application Support", "PartsLabel"
        )
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share"
        )
        path = os.path.join(base, "parts-label-maker")
    os.makedirs(path, exist_ok=True)
    return path


def settings_path() -> str:
    return os.path.join(user_data_dir(), APP_SETTINGS_NAME)


def load_settings() -> dict:
    path = settings_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    path = settings_path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except Exception:
            pass


def app_version() -> str:
    try:
        from version import __version__
        return __version__
    except Exception:
        return "0.0.0"


def updates_on_startup() -> bool:
    return bool(load_settings().get("check_updates_on_startup", True))


def set_updates_on_startup(enabled: bool) -> None:
    data = load_settings()
    data["check_updates_on_startup"] = bool(enabled)
    save_settings(data)


def skipped_version() -> str:
    return str(load_settings().get("skipped_version") or "")


def set_skipped_version(tag: str) -> None:
    data = load_settings()
    data["skipped_version"] = (tag or "").strip()
    save_settings(data)


def set_parts_csv(path: str) -> None:
    """Remember which parts list to use, including an existing LABEL MAKER file."""
    data = load_settings()
    data["parts_csv"] = os.path.abspath(path)
    save_settings(data)


def configured_parts_csv() -> str:
    """Saved parts-list path, even when the file is missing. Empty if unset."""
    return str(load_settings().get("parts_csv") or "").strip()


def _legacy_csv_candidates() -> list[str]:
    root = bundle_dir()
    names = [
        "parts_list_clean.csv",
        os.path.join("Parts List", "parts_list_clean.csv"),
        "FULL PARTS LIST",
        os.path.join("Parts List", "FULL PARTS LIST"),
    ]
    return [os.path.join(root, name) for name in names]


def _remember_clean_csv(path: str) -> None:
    """Stick to a parts_list_clean.csv found beside the scripts.

    Remembering it is what keeps the installed app on the shop file after an
    upgrade. The older FULL PARTS LIST export is not remembered, so updates
    still go to parts_list_clean.csv the way they always have.
    """
    if os.path.basename(path) != "parts_list_clean.csv":
        return
    abs_path = os.path.abspath(path)
    data = load_settings()
    if data.get("parts_csv") == abs_path:
        return
    data["parts_csv"] = abs_path
    save_settings(data)


def read_saved_printer() -> str:
    data = load_settings()
    name = str(data.get("printer_name") or "").strip().strip('"')
    if name:
        return name
    for path in (
        os.path.join(user_data_dir(), "printer_name.txt"),
        os.path.join(bundle_dir(), "printer_name.txt"),
    ):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                name = handle.read().strip().strip('"')
            if name:
                return name
        except Exception:
            continue
    return ""


def cprint(msg: str = "", color: str = RST) -> None:
    print(f"{color}{msg}{RST}")


def ask(prompt: str, color: str = CYN) -> str:
    return input(f"{color}{prompt}{RST}")


def normalize_part_number(text: str) -> str:
    """Keep part numbers as typed, including dashes and spaces.

    - Converts fancy dashes (en/em) to a normal hyphen
    - Strips invisible/format characters that break barcodes
      (e.g. left-to-right marks pasted from Excel/web)
    """
    if not text:
        return ""
    # Fancy dashes -> ASCII hyphen
    for ch in ("‐", "‑", "‒", "–", "—", "−"):
        text = text.replace(ch, "-")
    # Remove invisible / formatting chars (LRM, RLM, ZW*, BOM, etc.)
    cleaned = []
    for ch in text:
        o = ord(ch)
        # skip format chars, zero-width, BOM, soft hyphen
        if o in (0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF, 0x00AD):
            continue
        if 0x202A <= o <= 0x202E:  # bidi controls
            continue
        if 0x2060 <= o <= 0x206F:  # word joiners etc.
            continue
        cleaned.append(ch)
    return "".join(cleaned).strip().upper()


def sanitize_filename(text: str) -> str:
    """Turn part number into a safe filename fragment (keeps dashes)."""
    text = normalize_part_number(text)
    cleaned = re.sub(r"[^\w\-]+", "_", text)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_") or "label"



def wrap_text_lines(text: str, max_chars: int) -> list[str]:
    """Word-wrap text into centered-friendly lines (max characters per line)."""
    text = (text or "").strip()
    if not text:
        return []
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) <= max_chars:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            # hard-break very long single words
            while len(w) > max_chars:
                lines.append(w[:max_chars])
                w = w[max_chars:]
            cur = w
    if cur:
        lines.append(cur)
    return lines


def parse_header_or_price(text: str) -> tuple[str, str]:
    """Split input into (header, price).

    Examples:
      "$12.99"          -> header="", price="$12.99"
      "12.99"           -> header="", price="$12.99"
      "Amazon $12"      -> header="Amazon", price="$12.00"
      "Shop Stock $4.5" -> header="Shop Stock", price="$4.50"
      "PARTS LABEL"     -> header="PARTS LABEL", price=""
    """
    import re
    raw = (text or "").strip()
    if not raw:
        return "", ""

    def fmt_price(num: str) -> str:
        try:
            return f"${float(num):.2f}"
        except ValueError:
            return f"${num}"

    # Price only: $12.99 / 12.99 / 12
    only = raw.strip("$").strip()
    if re.match(r"^\d+(\.\d{1,2})?$", only):
        return "", fmt_price(only)

    # Header + trailing price: "Amazon $12" or "Amazon 12.99"
    m = re.match(r"^(.*?)\s+\$?(\d+(?:\.\d{1,2})?)\s*$", raw)
    if m:
        header = m.group(1).strip().strip("$").strip()
        price = fmt_price(m.group(2))
        # If header became empty, treat whole thing as price-only
        if not header:
            return "", price
        return header, price

    # Plain header text
    return raw, ""


def generate_barcode(part_number: str, output_path: str) -> str:
    """Generate a wide, scannable Code 128 barcode.

    Encodes the exact part number — dashes, spaces, everything kept.
    """
    part_number = normalize_part_number(part_number)
    # Code 128 allows letters, digits, space, and common punctuation including -
    code128 = get_barcode_class("code128")
    try:
        barcode = code128(part_number, writer=ImageWriter())
    except Exception as e:
        raise ValueError(
            f"Cannot barcode part number {part_number!r}. "
            f"Remove any special/invisible characters. ({e})"
        ) from e

    # Keep bars as thick as possible while fitting the full string
    length = len(part_number)
    if length <= 10:
        module_width = 0.48
    elif length <= 13:
        module_width = 0.40
    elif length <= 16:
        module_width = 0.34
    elif length <= 20:
        module_width = 0.28
    else:
        module_width = 0.24

    path = barcode.save(
        output_path,
        options={
            "module_width": module_width,
            "module_height": 14,
            "font_size": 1,
            "text_distance": 1.0,
            "quiet_zone": 2.5,
            "write_text": False,
            "dpi": 600,
        },
    )
    return path


def create_label(
    part_number: str,
    description: str,
    output_pdf: str,
    header_text: str = "",
    price_text: str = "",
) -> None:
    """Build the 3" × 2" parts label PDF.

    header_text -> black header bar
    price_text  -> shown under description (not a header)
    """
    label_width = 3 * inch
    label_height = 2 * inch
    has_header = bool(header_text and header_text.strip())
    has_price = bool(price_text and price_text.strip())

    with tempfile.TemporaryDirectory() as tmpdir:
        barcode_base = os.path.join(tmpdir, "barcode")
        barcode_path = generate_barcode(part_number, barcode_base)

        c = canvas.Canvas(output_pdf, pagesize=(label_width, label_height))

        # Background
        c.setFillColor(white)
        c.rect(0, 0, label_width, label_height, fill=1, stroke=0)

        # Outer border
        c.setStrokeColor(black)
        c.setLineWidth(2)
        c.rect(3, 3, label_width - 6, label_height - 6, fill=0, stroke=1)

        # Inner border
        c.setLineWidth(0.6)
        c.rect(6, 6, label_width - 12, label_height - 12, fill=0, stroke=1)

        # Optional black header bar
        if has_header:
            header_height = 0.24 * inch
            c.setFillColor(black)
            c.rect(
                6,
                label_height - 6 - header_height,
                label_width - 12,
                header_height,
                fill=1,
                stroke=0,
            )
            c.setFillColor(white)
            h_font = 9
            while h_font > 6 and c.stringWidth(header_text, "Helvetica-Bold", h_font) > label_width - 28:
                h_font -= 0.5
            c.setFont("Helvetica-Bold", h_font)
            c.drawCentredString(
                label_width / 2,
                label_height - 6 - header_height + 5,
                header_text.strip(),
            )
            # Positions when header is present (tighter)
            pn_label_y = label_height - 0.42 * inch
            pn_y = label_height - 0.58 * inch
            div1_y = label_height - 0.70 * inch
            desc_label_y = label_height - 0.84 * inch
            desc_y = label_height - 0.98 * inch
            div2_y = label_height - 1.08 * inch
            barcode_h = 0.50 * inch
            barcode_y = 0.12 * inch
        else:
            # Positions when no header (more room)
            pn_label_y = label_height - 0.26 * inch
            pn_y = label_height - 0.46 * inch
            div1_y = label_height - 0.60 * inch
            desc_label_y = label_height - 0.76 * inch
            desc_y = label_height - 0.96 * inch
            div2_y = label_height - 1.10 * inch
            barcode_h = 0.55 * inch
            barcode_y = 0.12 * inch

        # Part number
        c.setFillColor(black)
        c.setFont("Helvetica", 6)
        c.drawString(12, pn_label_y, "PART NUMBER")

        font_size = 13
        while font_size > 8 and c.stringWidth(part_number, "Helvetica-Bold", font_size) > label_width - 30:
            font_size -= 0.5
        c.setFont("Helvetica-Bold", font_size)
        c.drawCentredString(label_width / 2, pn_y, part_number)

        # Divider
        c.setStrokeColor(black)
        c.setLineWidth(0.7)
        c.line(12, div1_y, label_width - 12, div1_y)

        # Description (wrap long text, centered)
        c.setFont("Helvetica", 6)
        c.drawString(12, desc_label_y, "DESCRIPTION")

        max_desc_width = label_width - 30
        font_size = 11
        # Prefer wrapping over tiny font
        while font_size > 8:
            # estimate chars that fit
            avg = c.stringWidth("M", "Helvetica-Bold", font_size) or 1
            max_chars = max(12, int(max_desc_width / avg))
            desc_lines = wrap_text_lines(description, max_chars)
            if len(desc_lines) <= 3:
                break
            font_size -= 0.5
        else:
            avg = c.stringWidth("M", "Helvetica-Bold", font_size) or 1
            max_chars = max(12, int(max_desc_width / avg))
            desc_lines = wrap_text_lines(description, max_chars)[:3]

        c.setFont("Helvetica-Bold", font_size)
        line_h = font_size + 2
        # Start at desc_y and go downward for extra lines
        for i, line in enumerate(desc_lines):
            c.drawCentredString(label_width / 2, desc_y - i * line_h * 0.9, line)

        last_desc_y = desc_y - (len(desc_lines) - 1) * line_h * 0.9 if desc_lines else desc_y

        # Optional price under description
        if has_price:
            price_y = last_desc_y - 0.18 * inch
            c.setFont("Helvetica", 6)
            c.drawString(12, price_y + 0.12 * inch, "PRICE")
            p_size = 11
            while p_size > 7 and c.stringWidth(price_text, "Helvetica-Bold", p_size) > label_width - 30:
                p_size -= 0.5
            c.setFont("Helvetica-Bold", p_size)
            c.drawCentredString(label_width / 2, price_y, price_text.strip())
            div2_y = price_y - 0.10 * inch
        else:
            div2_y = last_desc_y - 0.12 * inch

        # Divider before barcode
        c.setLineWidth(0.7)
        c.line(12, div2_y, label_width - 12, div2_y)

        # Barcode — use nearly full label width for better scan reliability
        img = ImageReader(barcode_path)
        barcode_w = 2.90 * inch
        barcode_x = (label_width - barcode_w) / 2
        c.drawImage(
            img,
            barcode_x,
            barcode_y,
            width=barcode_w,
            height=barcode_h,
            preserveAspectRatio=True,
            mask="auto",
        )

        c.save()


def open_file(path: str) -> None:
    """Open a file with the default system application (PDF viewer on Windows)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", path])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"  (Could not auto-open file: {e})")



def find_zebra_printer() -> str | None:
    """Find a Zebra GC420d (or the saved printer) on Windows or CUPS."""
    saved = read_saved_printer()
    # On Windows the saved name wins even if the spooler list is empty,
    # matching the old printer_name.txt override.
    if sys.platform.startswith("win") and saved:
        return saved
    names = list_printers()
    if saved and (not names or saved in names):
        return saved
    for n in names:
        u = n.upper()
        if "GC420" in u or "GC 420" in u:
            return n
    for n in names:
        if "ZEBRA" in n.upper() or "ZDESIGNER" in n.upper():
            return n
    if saved:
        return saved
    return None


def build_zpl(part_number: str, description: str, header_text: str = "", price_text: str = "", copies: int = 1) -> str:
    """Build ZPL for a 3" x 2" label at 203 DPI — matches PDF layout."""
    def esc(s: str) -> str:
        return s.replace("^", " ").replace("~", " ").replace("\\", " ")

    pn = esc(part_number)
    desc = esc(description)
    hdr = esc(header_text.strip()) if header_text else ""
    price = esc(price_text.strip()) if price_text else ""

    # 203 dpi: 3" x 2"
    W, H = 609, 406
    M = 22  # content margin inside inner border

    def center_text(y: int, size: int, data: str) -> str:
        return f"^FO0,{y}^FB{W},1,0,C^A0N,{size},{size}^FD{data}\\&^FS"

    lines = [
        "^XA",
        f"^PW{W}",
        f"^LL{H}",
        "^LH2,9",  # +0.3mm right, +1.1mm down
        "^LT0",
        "^LS0",
        "^CI28",
        "^FWN",
        # Double border like the PDF
        f"^FO6,6^GB{W-12},{H-12},4^FS",
        f"^FO12,12^GB{W-24},{H-24},2^FS",
    ]

    y = 24
    if hdr:
        lines.append(f"^FO16,16^GB{W-32},36,36^FS")
        h_size = 28 if len(hdr) <= 16 else 22
        lines.append(f"^FO0,22^FB{W},1,0,C^A0N,{h_size},{h_size}^FR^FD{hdr}\\&^FS")
        y = 60
    else:
        y = 24

    # PART NUMBER caption
    lines.append(f"^FO{M},{y}^A0N,20,20^FDPART NUMBER^FS")
    y += 24

    if len(pn) <= 12:
        pn_size = 48
    elif len(pn) <= 16:
        pn_size = 40
    elif len(pn) <= 20:
        pn_size = 34
    else:
        pn_size = 28
    lines.append(center_text(y, pn_size, pn))
    y += pn_size + 8

    # divider under part number
    lines.append(f"^FO{M},{y}^GB{W-2*M},2,2^FS")
    y += 10

    # DESCRIPTION caption
    lines.append(f"^FO{M},{y}^A0N,20,20^FDDESCRIPTION^FS")
    y += 22

    # Wrap long descriptions onto centered lines
    if len(desc) <= 18:
        desc_size = 36
        max_chars = 22
    elif len(desc) <= 28:
        desc_size = 30
        max_chars = 26
    elif len(desc) <= 40:
        desc_size = 26
        max_chars = 30
    else:
        desc_size = 22
        max_chars = 34

    desc_lines = wrap_text_lines(desc, max_chars)
    # Cap at 3 lines so barcode still fits
    if len(desc_lines) > 3:
        desc_size = max(18, desc_size - 4)
        max_chars = min(40, max_chars + 4)
        desc_lines = wrap_text_lines(desc, max_chars)[:3]

    for line in desc_lines:
        lines.append(center_text(y, desc_size, line))
        y += desc_size + 4
    y += 4

    # Price under description (normal text, not header)
    if price:
        lines.append(f"^FO{M},{y}^A0N,16,16^FDPRICE^FS")
        y += 18
        p_size = 28 if len(price) <= 10 else 24
        lines.append(center_text(y, p_size, price))
        y += p_size + 6

    # divider under description (or price)
    lines.append(f"^FO{M},{y}^GB{W-2*M},2,2^FS")

    # Wide barcode near bottom, centered
    modules = 11 + 11 * len(pn) + 11 + 13
    max_bar_w = int((W - 2 * M) * 0.88)
    by = max(2, min(4, max_bar_w // modules))
    bar_w = modules * by
    bar_h = 100 if price else 110
    bottom_pad = 20
    bar_y = H - bottom_pad - bar_h
    if bar_y < y + 8:
        bar_h = max(70, H - bottom_pad - (y + 8))
        bar_y = H - bottom_pad - bar_h

    bx = max(M, (W - bar_w) // 2)
    lines.append(f"^FO{bx},{bar_y}^BY{by},3,{bar_h}^BCN,{bar_h},N,N,N^FD{pn}^FS")

    copies = max(1, int(copies))
    if copies > 1:
        lines.append(f"^PQ{copies}")
    lines.append("^XZ")
    return "\n".join(lines)


def _send_raw_windows(data: bytes, printer_name: str) -> bool:
    try:
        import win32print  # type: ignore
        handle = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(handle, 1, ("Parts Label", None, "RAW"))
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, data)
            win32print.EndPagePrinter(handle)
            win32print.EndDocPrinter(handle)
            return True
        finally:
            win32print.ClosePrinter(handle)
    except Exception as e:
        print(f"  (Raw print failed: {e})")
        return False


def _send_raw_cups(data: bytes, printer_name: str) -> bool:
    """Send raw ZPL with `lp -o raw`. Falls back to `lpr -l` only when lp is missing."""
    import subprocess

    def _run(cmd: list[str]) -> subprocess.CompletedProcess | None:
        try:
            return subprocess.run(cmd, input=data, capture_output=True, timeout=30)
        except FileNotFoundError:
            return None

    try:
        result = _run(["lp", "-d", printer_name, "-o", "raw", "-t", "Parts Label"])
        if result is None:
            result = _run(["lpr", "-P", printer_name, "-l", "-T", "Parts Label"])
        if result is None:
            print("  (Raw print failed: lp and lpr are not installed)")
            return False
    except Exception as e:
        print(f"  (Raw print failed: {e})")
        return False
    if result.returncode == 0:
        return True
    err = (result.stderr or b"").decode("utf-8", "replace").strip()
    print(f"  (Raw print failed: {err or 'printer command failed'})")
    return False


def send_raw_to_printer(data: bytes, printer_name: str) -> bool:
    """Send raw ZPL. Windows uses win32print; Linux uses CUPS. Never raises."""
    if not printer_name:
        return False
    if sys.platform.startswith("win"):
        return _send_raw_windows(data, printer_name)
    return _send_raw_cups(data, printer_name)


DEFAULT_PRINTER = "ZDesigner GC420d (EPL)"


def pick_default_printer(names: list[str]) -> str:
    """Choose the startup printer: saved default, else ZDesigner GC420d."""
    saved = read_saved_printer()
    if saved and (not names or saved in names):
        return saved
    preferred = [
        "ZDesigner GC420d (EPL)",
        "ZDesigner GC420d",
        "ZDesigner GC420d (ZPL)",
    ]
    upper_map = {n.upper(): n for n in names}
    for want in preferred:
        if want.upper() in upper_map:
            return upper_map[want.upper()]
    for n in names:
        u = n.upper()
        if "GC420" in u or "GC 420" in u:
            return n
    for n in names:
        if "ZEBRA" in n.upper() or "ZDESIGNER" in n.upper():
            return n
    # Windows keeps the historical default name when nothing is installed yet.
    # Linux uses a real CUPS queue when the user has not saved one.
    if names and not saved and not sys.platform.startswith("win"):
        return names[0]
    return saved or DEFAULT_PRINTER


def _parse_lpstat_printers(text: str) -> list[str]:
    """Pull queue names out of `lpstat -p` output."""
    names: list[str] = []
    for line in (text or "").splitlines():
        match = re.match(r"^printer\s+(\S+)\s+", line.strip())
        if match:
            names.append(match.group(1))
    return names


def _list_windows_printers() -> list[str]:
    try:
        import win32print  # type: ignore
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        return [p[2] for p in win32print.EnumPrinters(flags) if p[2]]
    except Exception:
        pass
    try:
        import subprocess
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Printer | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=15,
        )
        return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def _list_cups_printers() -> list[str]:
    """CUPS queues. Empty when lpstat is missing or the spooler is down."""
    try:
        import subprocess
        result = subprocess.run(
            ["lpstat", "-p"],
            capture_output=True, text=True, timeout=8,
        )
    except Exception:
        return []
    return _parse_lpstat_printers(result.stdout)


def list_printers() -> list[str]:
    """Installed printer names. Windows uses the spooler; Linux uses CUPS."""
    if sys.platform.startswith("win"):
        return _list_windows_printers()
    return _list_cups_printers()


def save_printer_choice(name: str) -> None:
    """Remember the selected printer outside the install folder.

    Running from the scripts also refreshes printer_name.txt beside them,
    which is where the original app stored it.
    """
    name = (name or "").strip()
    if not name:
        return
    data = load_settings()
    data["printer_name"] = name
    save_settings(data)
    try:
        with open(os.path.join(user_data_dir(), "printer_name.txt"), "w", encoding="utf-8") as handle:
            handle.write(name)
    except Exception:
        pass
    if _is_frozen():
        return
    try:
        with open(os.path.join(bundle_dir(), "printer_name.txt"), "w", encoding="utf-8") as handle:
            handle.write(name)
    except Exception:
        pass


def print_label(part_number: str, description: str, header: str = "", pdf_path: str = "", price: str = "", copies: int = 1, printer_name: str = "") -> None:
    """Auto-print to Zebra GC420d. Tries raw ZPL, then a PDF on Windows.

    Linux sends the same ZPL to a CUPS queue (`lp -o raw`). A missing printer
    or a missing lp/lpr command is reported and then skipped.
    """
    printer = (printer_name or "").strip() or find_zebra_printer()
    if not printer:
        print("  (No GC420d/Zebra printer found — skipped auto-print)")
        if sys.platform.startswith("win"):
            try:
                import win32print  # type: ignore
                flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                names = [p[2] for p in win32print.EnumPrinters(flags)]
                if names:
                    print("  Printers Windows sees:")
                    for n in names:
                        print(f"    - {n}")
                    print("  Tip: pick the printer in the window, or set it with Set Default.")
            except Exception as e:
                print(f"  (Could not list printers: {e})")
                print("  Tip: run  python -m pip install pywin32")
        else:
            print("  Linux printing uses CUPS. Add the GC420d, then pick it in the window.")
            print("  A raw queue is the right kind for ZPL:  lp -d NAME -o raw")
        return

    # 1) Raw ZPL — most reliable for GC420d
    try:
        zpl = build_zpl(part_number, description, header, price, copies)
        if send_raw_to_printer(zpl.encode("utf-8"), printer):
            cprint(f"  Printed {copies}x to: {printer}", GRN)
            return
        if sys.platform.startswith("win"):
            print("  ZPL print did not succeed, trying PDF...")
        else:
            print("  ZPL print did not succeed.")
    except Exception as e:
        print(f"  ZPL error: {e}")

    if not sys.platform.startswith("win"):
        return

    # 2) PDF via PrintTo (repeat for copies)
    copies = max(1, int(copies))
    if pdf_path and os.path.isfile(pdf_path):
        try:
            import subprocess
            for i in range(copies):
                ps = (
                    f'Start-Process -FilePath "{pdf_path}" '
                    f'-Verb PrintTo -ArgumentList \'"{printer}"\' '
                    f'-WindowStyle Hidden'
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps],
                    capture_output=True, text=True, timeout=60,
                )
            print(f"  Sent PDF {copies}x to: {printer}")
            return
        except Exception as e:
            print(f"  PDF PrintTo error: {e}")

        # 3) Default print verb
        try:
            for i in range(copies):
                os.startfile(pdf_path, "print")  # type: ignore[attr-defined]
            print(f"  Sent PDF {copies}x to default printer")
            return
        except Exception as e:
            print(f"  Print failed: {e}")



def make_one_label(part_number: str, description: str, header: str = "", output: str = "", auto_open: bool = False, auto_print: bool = True, copies: int = 1, printer_name: str = "") -> str:
    """Create a single label and return the output path.

    Default save location: a "Parts List" folder next to this script.
    The folder is created automatically if it does not exist.
    header input may be a price ($12.99) or a black-bar header.
    """
    header_text, price_text = parse_header_or_price(header)

    if not output:
        safe = sanitize_filename(part_number)
        if _is_frozen():
            # Keep generated PDFs out of the install folder so uninstall
            # and upgrades do not take them with them.
            parts_dir = os.path.join(user_data_dir(), "Parts List")
        else:
            parts_dir = os.path.join(bundle_dir(), "Parts List")
        os.makedirs(parts_dir, exist_ok=True)
        output = os.path.join(parts_dir, f"{safe}.pdf")
    else:
        if not os.path.isabs(output):
            output = os.path.abspath(output)
        parent = os.path.dirname(output)
        if parent:
            os.makedirs(parent, exist_ok=True)

    create_label(part_number, description, output, header_text, price_text)

    if auto_open:
        open_file(output)

    if auto_print:
        print_label(part_number, description, header_text, output, price_text, copies, printer_name)

    return output



def find_parts_csv() -> str | None:
    """Locate the parts list.

    A path saved in settings wins, including the existing LABEL MAKER file.
    If that path is set but the file is missing, this does not switch to a
    different list. With nothing saved yet, look beside the scripts the way
    the original app did.
    """
    remembered = configured_parts_csv()
    if remembered:
        return remembered if os.path.isfile(remembered) else None

    found_clean = None
    found_any = None
    for candidate in _legacy_csv_candidates():
        if not os.path.isfile(candidate):
            continue
        if os.path.basename(candidate) == "parts_list_clean.csv" and found_clean is None:
            found_clean = candidate
        if found_any is None:
            found_any = candidate
    chosen = found_clean or found_any
    if chosen and os.path.basename(chosen) == "parts_list_clean.csv":
        _remember_clean_csv(chosen)
    return chosen


def load_parts_lookup() -> dict[str, dict]:
    """Load PartNo -> {description, price, header} (keys uppercased)."""
    path = find_parts_csv()
    if not path:
        return {}

    lookup: dict[str, dict] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            if "PAR:PartNo" in sample:
                reader = csv.DictReader(f)
                for row in reader:
                    part = (row.get("PAR:PartNo") or "").strip().strip('"')
                    desc = (row.get("PAR:Description") or "").strip().strip('"')
                    if part:
                        lookup[part.upper()] = {
                            "description": desc, "price": "", "header": ""
                        }
            else:
                reader = csv.DictReader(f)
                fields = reader.fieldnames or []
                part_key = "PartNo" if "PartNo" in fields else fields[0]
                desc_key = "Description" if "Description" in fields else (
                    fields[1] if len(fields) > 1 else fields[0]
                )
                price_key = "Price" if "Price" in fields else None
                header_key = "Header" if "Header" in fields else None
                for row in reader:
                    part = (row.get(part_key) or "").strip()
                    desc = (row.get(desc_key) or "").strip()
                    price = (row.get(price_key) or "").strip() if price_key else ""
                    header = (row.get(header_key) or "").strip() if header_key else ""
                    if part:
                        lookup[part.upper()] = {
                            "description": desc,
                            "price": price,
                            "header": header,
                        }
    except Exception as e:
        print(f"  (Could not load parts list: {e})")
        return {}

    return lookup


def get_clean_csv_path() -> str:
    """Path updates are written to.

    A path already chosen always wins, so an upgrade cannot start a new empty
    file. Otherwise keep the old rule: parts_list_clean.csv beside the scripts.
    The installed app writes a brand-new list into the user data folder, and
    only after someone asks for one.
    """
    remembered = configured_parts_csv()
    if remembered:
        return remembered
    for candidate in _legacy_csv_candidates():
        if os.path.isfile(candidate) and os.path.basename(candidate) == "parts_list_clean.csv":
            return candidate
    if _is_frozen():
        return os.path.join(user_data_dir(), "parts_list_clean.csv")
    return os.path.join(bundle_dir(), "parts_list_clean.csv")


def update_parts_list(
    part_number: str,
    description: str,
    lookup: dict,
    price: str = "",
    header: str = "",
) -> None:
    """Add or update a part (description + price + header) in parts_list_clean.csv."""
    key = part_number.upper()
    old = lookup.get(key) or {"description": "", "price": "", "header": ""}
    if not isinstance(old, dict):
        old = {"description": str(old), "price": "", "header": ""}
    old_desc = old.get("description", "")
    old_price = old.get("price", "")
    old_header = old.get("header", "")

    # Normalize price
    _, price_norm = parse_header_or_price(price) if price else ("", "")
    if not price_norm and price:
        price_norm = price.strip()
    header_norm = (header or "").strip()

    if (
        old_desc == description
        and old_price == price_norm
        and old_header == header_norm
        and key in lookup
    ):
        return  # nothing changed

    csv_path = get_clean_csv_path()
    parent = os.path.dirname(csv_path)
    if parent:
        try:
            os.makedirs(parent, exist_ok=True)
        except Exception:
            pass
    is_new = key not in lookup
    fields = ["PartNo", "Description", "Price", "Header"]

    try:
        rows: list[dict] = []
        if os.path.isfile(csv_path):
            with open(csv_path, "r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    part = (row.get("PartNo") or "").strip()
                    desc = (row.get("Description") or "").strip()
                    pr = (row.get("Price") or "").strip()
                    hd = (row.get("Header") or "").strip()
                    if not part:
                        continue
                    if part.upper() == key:
                        rows.append({
                            "PartNo": part_number,
                            "Description": description,
                            "Price": price_norm,
                            "Header": header_norm,
                        })
                    else:
                        rows.append({
                            "PartNo": part,
                            "Description": desc,
                            "Price": pr,
                            "Header": hd,
                        })
        if is_new:
            rows.append({
                "PartNo": part_number,
                "Description": description,
                "Price": price_norm,
                "Header": header_norm,
            })

        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        lookup[key] = {
            "description": description,
            "price": price_norm,
            "header": header_norm,
        }
        if is_new:
            print(f"  Added to parts list: {part_number}")
        else:
            print(f"  Updated parts list: {part_number}")
    except Exception as e:
        print(f"  (Could not update parts list: {e})")


def interactive_loop() -> None:
    """Keep prompting for labels until the user quits.

    Type X on a prompt to go back to the previous step.
    Enter keeps the original saved values (even after you started changing them).
    """
    cprint("=== Parts Label Generator ===", BOLD + GRN)
    cprint("  Type q at Part Number to quit", DIM)
    cprint("  Type r or again to reprint the last label", DIM)
    cprint("  Type X on any prompt to go back one step", DIM)
    cprint("  Type N at Quantity for no print (update label only)", DIM)
    print()

    parts = load_parts_lookup()
    if parts:
        cprint(f"  Parts list loaded: {len(parts)} parts", GRN)
        cprint("  Description, price, and header auto-fill when found (Enter to keep).", DIM)
    else:
        cprint("  No parts list found (parts_list_clean.csv).", YEL)
        cprint("  Descriptions must be entered manually.", YEL)
    print()

    count = 0
    last = None

    while True:
        # State machine: 0=part, 1=desc, 2=header, 3=qty
        step = 0
        part_number = ""
        description = ""
        header = ""
        header_text = ""
        price_text = ""
        entry = None
        copies = 1
        # Baseline = original saved values when part was first looked up
        base_desc = ""
        base_header = ""
        base_price = ""
        draft_header = ""
        draft_price = ""

        while step >= 0:
            if step == 0:
                part_number = normalize_part_number(ask("Part Number  : ", BOLD + CYN))
                if part_number.lower() in ("q", "quit", "exit"):
                    step = -2
                    break
                if part_number.lower() in ("r", "again", "reprint"):
                    if not last:
                        cprint("  No previous label to reprint.\n", YEL)
                        break
                    qty_raw = ask(
                        f"  Reprint {last['part_number']} — Quantity [Enter=1, X=back]: ", MAG
                    ).strip()
                    if qty_raw.upper() == "X":
                        cprint("  (back)\n", DIM)
                        break
                    try:
                        copies = int(qty_raw) if qty_raw else 1
                        if copies < 1:
                            copies = 1
                    except ValueError:
                        copies = 1
                    try:
                        out = make_one_label(
                            last["part_number"], last["description"],
                            last["header"], copies=copies,
                        )
                        count += 1
                        last["copies"] = copies
                        cprint(f"  Reprinted: {out}\n", GRN)
                    except Exception as e:
                        cprint(f"  [ERROR] {e}\n", RED)
                    break
                if not part_number:
                    cprint("  Part number is required. (or type q to quit)\n", RED)
                    break

                entry = parts.get(part_number.upper())
                if not entry:
                    key = re.sub(r"\s*-\s*", "-", part_number.upper())
                    for k, v in parts.items():
                        if re.sub(r"\s*-\s*", "-", k) == key:
                            entry = v
                            break
                if not isinstance(entry, dict):
                    entry = {"description": entry or "", "price": "", "header": ""} if entry else None
                elif entry is not None:
                    entry.setdefault("price", "")
                    entry.setdefault("header", "")
                    entry.setdefault("description", "")

                # Snapshot originals for this part (Enter always restores these)
                base_desc = (entry or {}).get("description", "") if entry else ""
                base_header = (entry or {}).get("header", "") if entry else ""
                base_price = (entry or {}).get("price", "") if entry else ""
                draft_header = base_header
                draft_price = base_price
                description = base_desc
                header_text = base_header
                price_text = base_price
                if base_header and base_price:
                    header = f"{base_header} {base_price}"
                else:
                    header = base_header or base_price
                step = 1

            elif step == 1:
                if base_desc:
                    cprint(f"  Found Description: {base_desc}", YEL)
                    override = ask("  Description [Enter to accept, X=back]: ", CYN).strip()
                    if override.upper() == "X":
                        cprint("  (back)\n", DIM)
                        step = 0
                        continue
                    if not override:
                        description = base_desc
                        cprint(f"  Keeping Description: {description}", GRN)
                    else:
                        description = override
                else:
                    description = ask("Description [X=back]: ", CYN).strip()
                    if description.upper() == "X":
                        cprint("  (back)\n", DIM)
                        step = 0
                        continue
                    if not description:
                        cprint("  Description is required.\n", RED)
                        continue
                step = 2

            elif step == 2:
                # Always show original saved values when entering this step
                # (including after X from quantity — discard a mistaken entry)
                if not base_header and not base_price:
                    cprint("  Current Header/Price: [BLANK]", MAG)
                    raw_hp = ask(
                        "Header/price e.g. Amazon $12\n(blank=none)\n(CLEAR)\n(X=back): ", MAG
                    ).strip()
                else:
                    h_show = base_header if base_header else "[BLANK]"
                    p_show = base_price if base_price else "[BLANK]"
                    if base_header and base_price:
                        suggestion = f"{base_header} {base_price}"
                    elif base_price:
                        suggestion = base_price
                    else:
                        suggestion = base_header
                    raw_hp = ask(
                        f" Current Header/Price:\n"
                        f" HEADER= {h_show}\n"
                        f" PRICE= {p_show}\n"
                        f"(CLEAR)\n"
                        f"(X=back)\n"
                        f"[Enter keeps {suggestion}]: ",
                        MAG,
                    ).strip()

                if raw_hp.upper() == "X":
                    cprint("  (back)\n", DIM)
                    step = 1
                    continue

                if raw_hp.upper() == "CLEAR":
                    cprint("  Cleared header and price.", YEL)
                    raw_hp = ask(
                        "  New header/price e.g. Amazon $12\n(blank=none)\n(X=back): ", MAG
                    ).strip()
                    if raw_hp.upper() == "X":
                        cprint("  (back)\n", DIM)
                        step = 1
                        continue
                    h, p = parse_header_or_price(raw_hp) if raw_hp else ("", "")
                    header_text, price_text = h, p
                    header = f"{h} {p}".strip() if (h or p) else ""
                elif not raw_hp:
                    header_text, price_text = base_header, base_price
                    if base_header and base_price:
                        header = f"{base_header} {base_price}"
                    else:
                        header = base_header or base_price
                    if header:
                        cprint(f"  Keeping Header/Price: {header}", GRN)
                    else:
                        cprint("  Keeping Header/Price: (none)", DIM)
                else:
                    h, p = parse_header_or_price(raw_hp)
                    if p and not h:
                        h = base_header
                    elif h and not p:
                        p = base_price
                    header_text, price_text = h, p
                    header = f"{h} {p}".strip() if (h or p) else (h or p)
                step = 3

            elif step == 3:
                qty_raw = ask(
                    "Quantity to print; \n(X=Back)\n(N=No print update only)\nPress Enter for [1] Copy: ",
                    BLU,
                ).strip()
                if qty_raw.upper() == "X":
                    cprint("  (back)\n", DIM)
                    step = 2
                    continue
                do_print = True
                if qty_raw.upper() == "N":
                    do_print = False
                    copies = 1
                else:
                    try:
                        copies = int(qty_raw) if qty_raw else 1
                        if copies < 1:
                            copies = 1
                    except ValueError:
                        copies = 1

                try:
                    out = make_one_label(
                        part_number, description, header,
                        copies=copies, auto_print=do_print,
                    )
                    count += 1
                    update_parts_list(
                        part_number, description, parts,
                        price=price_text, header=header_text,
                    )
                    # Refresh baselines from what we just saved
                    base_desc = description
                    base_header = header_text
                    base_price = price_text
                    if part_number.upper() in parts:
                        parts[part_number.upper()] = {
                            "description": description,
                            "price": price_text,
                            "header": header_text,
                        }
                    last = {
                        "part_number": part_number,
                        "description": description,
                        "header": header,
                        "copies": copies,
                    }
                    if do_print:
                        cprint(f"  Saved: {out}\n", GRN)
                    else:
                        cprint(f"  Updated (no print): {out}\n", YEL)
                except Exception as e:
                    cprint(f"  [ERROR] {e}\n", RED)
                break

        if step == -2:
            break

    if count:
        cprint(f"Done. Created {count} label(s).", BOLD + GRN)
    else:
        cprint("No labels created.", YEL)



def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a 3x2 inch parts label PDF with Code 128 barcode."
    )
    parser.add_argument("part_number", nargs="?", help="Part number (spaces preserved)")
    parser.add_argument("description", nargs="?", help="Part description")
    parser.add_argument(
        "-H", "--header",
        default="",
        help="Optional header text (black bar). Leave empty for no header.",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output PDF path (default: auto-named from part number)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"parts-label-maker {app_version()}",
    )
    args = parser.parse_args()

    # No args → interactive continuous mode
    if not args.part_number:
        interactive_loop()
        return

    # Single-shot command-line mode
    if not args.description:
        print("Error: Description is required when using command-line mode.")
        sys.exit(1)

    path = make_one_label(args.part_number, args.description, args.header, args.output or "")
    print(f"Label created: {path}")
    print(f"  Part Number : {args.part_number}")
    print(f"  Description : {args.description}")
    if args.header and args.header.strip():
        print(f"  Header      : {args.header.strip()}")
    else:
        print(f"  Header      : (none)")


if __name__ == "__main__":
    main()
