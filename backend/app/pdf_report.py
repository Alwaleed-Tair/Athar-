"""
Small PDF layout engine on top of reportlab's canvas, built for Arabic (RTL)
and English (LTR) legal reports.

Why custom instead of platypus Paragraph: Arabic needs letter shaping
(arabic-reshaper) and bidirectional reordering (python-bidi). Both must run
on each already-WRAPPED line -- reordering a whole paragraph first and then
letting a layout engine wrap it scrambles line order. So text is wrapped in
logical order here, and each line is shaped/reordered individually.
"""
import io
import re
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

_FONT_DIR = Path(__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("Athar", str(_FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("Athar-Bold", str(_FONT_DIR / "DejaVuSans-Bold.ttf")))

_reshaper = arabic_reshaper.ArabicReshaper(configuration={"support_ligatures": True, "delete_harakat": False})
_HAS_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")

NAVY = (0.07, 0.15, 0.30)
BLUE = (0.0, 0.40, 0.93)
GREY = (0.40, 0.45, 0.53)
LIGHT = (0.94, 0.96, 0.99)
LINE = (0.80, 0.85, 0.92)
GREEN = (0.06, 0.55, 0.38)
RED = (0.80, 0.15, 0.15)
AMBER = (0.80, 0.52, 0.0)
AMBER_BG = (1.0, 0.97, 0.88)
GREEN_BG = (0.90, 0.98, 0.94)
RED_BG = (1.0, 0.92, 0.92)


class Pdf:
    def __init__(self, rtl: bool, footer_text: str, total_pages: int | None = None):
        self.rtl = rtl
        self.footer_text = footer_text
        self.total = total_pages
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4)
        self.c.setTitle("ATHAR - Digital Evidence Report")
        self.c.setAuthor("ATHAR")
        self.c.setSubject("Digital evidence report")
        self.W, self.H = A4
        self.M = 18 * mm
        self.top = self.H - 20 * mm
        self.bottom = 20 * mm
        self.y = self.top
        self.page = 1
        self.base = "R" if rtl else "L"

    # ---- text primitives ---------------------------------------------------
    def shape(self, text: str) -> str:
        if _HAS_ARABIC.search(text):
            text = _reshaper.reshape(text)
        return get_display(text, base_dir=self.base)

    def width(self, text: str, font: str, size: float) -> float:
        return pdfmetrics.stringWidth(self.shape(text), font, size)

    def wrap(self, text: str, font: str, size: float, maxw: float) -> list[str]:
        lines: list[str] = []
        for para in str(text).split("\n"):
            cur = ""
            for word in para.split(" "):
                trial = f"{cur} {word}".strip() if cur else word
                if self.width(trial, font, size) <= maxw:
                    cur = trial
                    continue
                if cur:
                    lines.append(cur)
                cur = ""
                while word and self.width(word, font, size) > maxw:   # very long token (hash, URL)
                    cut = len(word)
                    while cut > 1 and self.width(word[:cut], font, size) > maxw:
                        cut -= 1
                    lines.append(word[:cut])
                    word = word[cut:]
                cur = word
            lines.append(cur)
        return lines or [""]

    def _draw(self, text: str, x_left: float, x_right: float, y: float, font: str, size: float, color=(0, 0, 0)):
        self.c.setFont(font, size)
        self.c.setFillColorRGB(*color)
        shaped = self.shape(text)
        if self.rtl:
            self.c.drawRightString(x_right, y, shaped)
        else:
            self.c.drawString(x_left, y, shaped)

    # ---- page handling -----------------------------------------------------------
    def _footer(self):
        c = self.c
        c.setStrokeColorRGB(*LINE)
        c.setLineWidth(0.6)
        c.line(self.M, 15 * mm, self.W - self.M, 15 * mm)
        label = self.footer_text
        pg = f"{self.page}" + (f" / {self.total}" if self.total else "")
        self._draw(label, self.M, self.W - self.M, 10.5 * mm, "Athar", 7.5, GREY)
        c.setFont("Athar", 7.5)
        c.setFillColorRGB(*GREY)
        if self.rtl:
            c.drawString(self.M, 10.5 * mm, pg)
        else:
            c.drawRightString(self.W - self.M, 10.5 * mm, pg)

    def new_page(self):
        self._footer()
        self.c.showPage()
        self.page += 1
        self.y = self.top

    def need(self, h: float):
        if self.y - h < self.bottom:
            self.new_page()

    def finish(self) -> bytes:
        self._footer()
        self.c.showPage()
        self.c.save()
        return self.buf.getvalue()

    # ---- blocks ---------------------------------------------------------------------
    @property
    def content_w(self) -> float:
        return self.W - 2 * self.M

    def title_block(self, title: str, subtitle: str):
        c = self.c
        c.setFillColorRGB(*NAVY)
        c.rect(0, self.H - 38 * mm, self.W, 38 * mm, stroke=0, fill=1)
        self._draw(title, self.M, self.W - self.M, self.H - 20 * mm, "Athar-Bold", 20, (1, 1, 1))
        self._draw(subtitle, self.M, self.W - self.M, self.H - 29 * mm, "Athar", 10, (0.78, 0.86, 1.0))
        self.y = self.H - 38 * mm - 10 * mm

    def h1(self, text: str, tag: tuple[str, tuple, tuple] | None = None):
        self.need(75)  # keep a heading together with the start of its content
        self.y -= 4
        self._draw(text, self.M, self.W - self.M, self.y, "Athar-Bold", 13, NAVY)
        if tag:
            label, fg, bg = tag
            tw = self.width(label, "Athar-Bold", 7.5) + 10
            x = (self.M if self.rtl else self.W - self.M - tw)
            self.c.setFillColorRGB(*bg)
            self.c.roundRect(x, self.y - 3, tw, 12, 3, stroke=0, fill=1)
            self._draw(label, x + 5, x + tw - 5, self.y, "Athar-Bold", 7.5, fg)
        self.y -= 5
        self.c.setStrokeColorRGB(*BLUE)
        self.c.setLineWidth(1.2)
        self.c.line(self.M, self.y, self.W - self.M, self.y)
        self.y -= 14

    def h2(self, text: str):
        self.need(48)
        self._draw(text, self.M, self.W - self.M, self.y, "Athar-Bold", 10.5, NAVY)
        self.y -= 15

    def para(self, text: str, size: float = 9.5, color=(0.1, 0.1, 0.12), bold=False, indent: float = 0, gap: float = 4):
        font = "Athar-Bold" if bold else "Athar"
        lead = size * 1.55
        for ln in self.wrap(text, font, size, self.content_w - indent):
            self.need(lead)
            self._draw(ln, self.M, self.W - self.M - indent if self.rtl else self.M + indent, self.y, font, size, color)
            if self.rtl:
                pass
            self.y -= lead
        self.y -= gap

    def bullet(self, text: str, size: float = 9.5):
        lead = size * 1.55
        lines = self.wrap(text, "Athar", size, self.content_w - 14)
        for i, ln in enumerate(lines):
            self.need(lead)
            if i == 0:
                bx = (self.W - self.M - 4) if self.rtl else (self.M + 4)
                self.c.setFillColorRGB(*BLUE)
                self.c.circle(bx, self.y + 3, 1.5, stroke=0, fill=1)
            xr = self.W - self.M - 14
            xl = self.M + 14
            self._draw(ln, xl, xr, self.y, "Athar", size, (0.1, 0.1, 0.12))
            self.y -= lead
        self.y -= 2

    def callout(self, text: str, fg, bg, bold_label: str | None = None, size: float = 8.8):
        lead = size * 1.5
        pad = 7
        inner = self.content_w - 2 * pad
        lines = self.wrap(text, "Athar", size, inner)
        if bold_label:
            lines = self.wrap(bold_label, "Athar-Bold", size, inner) + lines
        h = len(lines) * lead + 2 * pad
        self.need(h + 6)
        top = self.y + 4
        self.c.setFillColorRGB(*bg)
        self.c.setStrokeColorRGB(*fg)
        self.c.setLineWidth(0.8)
        self.c.roundRect(self.M, top - h, self.content_w, h, 4, stroke=1, fill=1)
        yy = top - pad - size
        nlabel = len(self.wrap(bold_label, "Athar-Bold", size, inner)) if bold_label else 0
        for i, ln in enumerate(lines):
            font = "Athar-Bold" if i < nlabel else "Athar"
            self._draw(ln, self.M + pad, self.W - self.M - pad, yy, font, size, fg if i < nlabel else (0.1, 0.1, 0.12))
            yy -= lead
        self.y = top - h - 8

    def kv(self, label: str, value: str, label_w: float = 42 * mm, size: float = 9):
        lead = size * 1.55
        vlines = self.wrap(value or "—", "Athar", size, self.content_w - label_w - 4)
        need = max(len(vlines), 1) * lead
        self.need(need)
        if self.rtl:
            self._draw(label, 0, self.W - self.M, self.y, "Athar-Bold", size, GREY)
            for i, ln in enumerate(vlines):
                self._draw(ln, 0, self.W - self.M - label_w, self.y - i * lead, "Athar", size)
        else:
            self._draw(label, self.M, 0, self.y, "Athar-Bold", size, GREY)
            for i, ln in enumerate(vlines):
                self._draw(ln, self.M + label_w, 0, self.y - i * lead, "Athar", size)
        self.y -= need + 2

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float], size: float = 8.2):
        """widths are fractions of content width (sum ~1). In RTL the first
        column is drawn at the right edge."""
        lead = size * 1.45
        pad = 3.5
        cw = [w * self.content_w for w in widths]

        def col_x(i):
            if self.rtl:
                right = self.W - self.M - sum(cw[:i])
                return right - cw[i], right
            left = self.M + sum(cw[:i])
            return left, left + cw[i]

        def draw_header():
            h = lead + 2 * pad
            self.need(h + 4)
            self.c.setFillColorRGB(*NAVY)
            self.c.rect(self.M, self.y - h + 4, self.content_w, h, stroke=0, fill=1)
            for i, t in enumerate(headers):
                xl, xr = col_x(i)
                self._draw(t, xl + pad, xr - pad, self.y - pad - size + 4, "Athar-Bold", size, (1, 1, 1))
            self.y -= h

        draw_header()
        for ri, row in enumerate(rows):
            wrapped = [self.wrap(cell, "Athar", size, cw[i] - 2 * pad) for i, cell in enumerate(row)]
            nlines = max(len(w) for w in wrapped)
            h = nlines * lead + 2 * pad
            if self.y - h < self.bottom:
                self.new_page()
                draw_header()
            if ri % 2 == 0:
                self.c.setFillColorRGB(*LIGHT)
                self.c.rect(self.M, self.y - h + 4, self.content_w, h, stroke=0, fill=1)
            for i, lines in enumerate(wrapped):
                xl, xr = col_x(i)
                for k, ln in enumerate(lines):
                    self._draw(ln, xl + pad, xr - pad, self.y - pad - size + 4 - k * lead, "Athar", size)
            self.y -= h
        self.c.setStrokeColorRGB(*LINE)
        self.c.line(self.M, self.y + 4, self.W - self.M, self.y + 4)
        self.y -= 10

    def spacer(self, h: float = 6):
        self.y -= h
