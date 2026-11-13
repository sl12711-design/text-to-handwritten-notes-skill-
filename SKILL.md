---
name: handwritten-notes
description: Turn any content (a PDF, pasted text, a solution, a web page, a photo of a page or whiteboard) into pages that look written by hand, either as a phone photo of a real notebook page (squared, lined or Seyès paper) or as a clean iPad page, exported as PDF or PNG. Writes in a bundled default handwriting, or in the user's own handwriting learned from photos of notes they already wrote. Maths is drawn by hand (fractions, sums, integrals, roots, intervals, Greek). Use when the user asks for handwritten notes, notes "à la main", notebook or iPad-style notes, or something written in their own handwriting.
---

# Handwritten notes

You turn content into pages that look handwritten. The renderer is `scripts/handnotes.py`. It only needs Python with Pillow and numpy, which are already present in the ChatGPT and Claude code sandboxes.

**Default result:** a phone photo of a notebook page on squared paper, in blue ink, written in the bundled default handwriting. If the user asks for nothing special, give them that.

## Step 0: whose handwriting?

Ask once, briefly: *"Send me as many photos of your own handwriting as you can (any pages you already wrote: notes, homework). Otherwise I'll use the default handwriting."*

- **No photos:** use the default handwriting. Do not ask again.
- **Photos:** learn them first (see *Learning a handwriting from photos* below), then render with `--hand their-hand`. More pages give more samples per letter and a more natural result. 3 to 6 pages is good.

## Step 1: read the input

- **PDF:** extract the text with pypdf, pdftotext or your own reader. For a scanned PDF, look at the page images.
- **Photo, screenshot, whiteboard:** read it yourself with vision. Do not run OCR libraries.
- **Text, a solution, a web page:** use it as given.

## Step 2: write the page

There are two cases.

- **Notes from a lesson:** write what a good student writes. Short lines, keywords, the source's structure, 15 to 30 % of its length.
- **A solution or homework the user gives:** keep every step and every number. Write it the way a student writes on paper: `1/`, `a)` and `b)` labels, one equation per line, `=>` between steps. Do not add AI-looking decoration: no "Tip:", no highlighting everywhere, no bold. Underline or `!!` a final result only if the user would.

Keep the user's language. Keep numbers, names and formulas exact.

Markup:

```
# Title                     ## Heading                ### Sub-heading (underlined)
- bullet (2 spaces = one level deeper)                1. numbered
-> arrow line               !! IMPORTANT line (red)   > side note (accent ink)
[ ] to-do   [x] done (ticked)   ---  separator        blank line = skip a line
inline: ==highlight==  **bold**  __underline__  ~~crossed~~  {red}coloured ink{/}  ->  (drawn arrow)
\$  = a dollar sign      $...$ inline maths      $$...$$ alone on a line = displayed formula
```

**Maths.** Put every formula in `$...$`, even a short one like `$x^2$` or `$E_2$`. Supported:
`\frac{a}{b}`, `\sum_{k=1}^{n}`, `\prod`, `\int_a^b`, `\lim_{n \to +\infty}`, `\sqrt{x}`, `\sqrt[3]{x}`, `x^{n+1}`, `x_i`, `\left( ... \right)`, `\binom{n}{k}`, `\vec{u}`, `\bar{x}`, `\mathbb{R}`, `\text{...}`, `\mid`, Greek letters, `\in \subset \cup \cap \emptyset \forall \exists \leq \geq \neq \approx \pm \times \cdot \infty \to \implies \iff`, and spaces `\, \; \quad`.

Write decimals as the source does (`0,81` or `0.81`), and large numbers as `50\,000` inside maths. Write intervals as they are read: `$[0, 1[$`. Put big formulas on their own `$$...$$` line. A formula too wide for the page is shrunk to fit, but splitting a long one at `=` onto two lines looks more natural.

Save the page as `notes.md`.

## Step 3: render

```bash
python scripts/handnotes.py render notes.md -o notes.pdf
```

That gives the default: a notebook photo, squared paper, blue ink, default handwriting. Change only what the user asked for:

| option | values |
|---|---|
| `--style` | **notebook** (phone photo of a real page: uneven light, lines drifting down, tilted sheet) · ipad (clean tablet page) |
| `--paper` | **squared** (notebook) or **grid** (ipad), lines, college, seyes, dots, blank |
| `--hand` | **default**, or a folder made by `build-hand` or `learn` |
| `--font` | use a handwriting font instead: caveat, kalam, patrick, gochi, indie, playpen |
| `--ink` | **blue** (notebook) or **black** (ipad), red, green, purple, pencil |
| `--page` | **a4**, letter, ipad, ipad-landscape |
| `--seed N` | the same page every time; change N for another take |

Use `-o notes.png` to get images (`notes-1.png`, `notes-2.png`, and so on) instead of a PDF.

## Step 4: check, then deliver

Look at page 1 (render a PNG if you cannot view PDFs). Check that no line runs off the page or overlaps another, and that every number matches the source. Then give the file.

## Learning a handwriting from photos

This works from any pages the person already wrote. They do not need to fill anything in.

1. **Cut:** `python scripts/handnotes.py segment p1.jpg p2.jpg p3.jpg -o hand-work`
   This removes the printed lines of the notebook, cuts every piece of ink, and writes numbered sheets `hand-work/sheet-pageN-K.png`.

2. **Label:** look at every sheet. You know what the pages say, because you can read the original photos. Write `hand-work/labels.json` (page numbers follow the order of the photos):
   ```json
   {"1": {"12": "a", "13": "(", "40": "the", "41": "7"}, "2": {"5": "é", "9": "dy"}}
   ```
   - Label only pieces you are sure of. Skip anything unclear, cut in half, glued to a neighbour, crossed out, or just a line fragment.
   - A piece holding several joined letters can be labelled as that word or pair ("the", "le", "qu"). It is reused whenever that sequence appears, which looks very natural.
   - Aim for at least 2 or 3 samples of each lowercase letter and each digit.

3. **Build:** `python scripts/handnotes.py build-hand hand-work hand-work/labels.json -o their-hand`
   This normalises sizes and ink strength, drops badly cut samples, and builds missing letters from the writer's own strokes (u from n, m from two n, w from two v, r, q). Accents (é è à ê ç ë) are drawn on their own plain letter. It prints the letters a font still stands in for.

4. **Check one render.** Look at a page and zoom on any letter that looks broken or too faint. Find its samples in the `their-hand/glyphs` files listed in `their-hand/hand.json`, remove the bad label, and build again.

Keep the `their-hand` folder: it is their handwriting. Offer to zip it so they can reuse it next time.

There is also a template route (`template`, then `learn`): the person fills a 2-page grid of boxes. It is cleaner but more work for them, so only offer it if they prefer it.
