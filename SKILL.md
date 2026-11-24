---
name: text-to-handwritten-notes
description: Turn any content (a PDF, pasted text, a solution, a web page, a photo of a page or whiteboard) into pages that look written by hand, either as a phone photo of a real notebook page (squared, lined or Seyès paper) or as a clean iPad page, exported as PDF or PNG. Writes in a bundled default handwriting, or in the user's own handwriting learned from photos of notes they already wrote. Maths is drawn by hand (fractions, sums, integrals, roots, intervals, Greek). Use when the user asks for handwritten notes, notes "à la main", notebook or iPad-style notes, or something written in their own handwriting.
---

# Text to handwritten notes

You turn content into pages that look handwritten. The renderer is `scripts/handnotes.py`. It only needs Python with Pillow and numpy, which are already present in the ChatGPT and Claude code sandboxes.

**Default result:** a crisp 300 DPI lined A4 tablet page (`--style ipad --paper lines`, subtle light-gray horizontal ruled lines with a left margin line), in pure black ink (`--ink black --accent black --important black`), using `hands/my-hand` if present locally or falling back to `hands/default`, with natural per-character/symbol jitter (`--jitter`) and 1–2 subtle crossed-out false starts per page (`--scratch`) enabled by default.

**Always use horizontal lined tablet paper (`--style ipad --paper lines`) by default**, unless the user explicitly requests blank white paper (`--paper blank`), notebook photo mode (`--style notebook`), or another paper/ink option. If the user asks to turn off cross-outs or random jitter, pass `--no-scratch` and/or `--no-jitter`.

## Step 0: whose handwriting?

- **Local custom hand:** If `hands/my-hand/hand.json` exists locally, `scripts/handnotes.py` uses it automatically (`--hand default`). Otherwise it falls back cleanly to the bundled `hands/default`.
- **If the user sends photos of their handwriting:** learn them first (see *Learning a handwriting from photos* below) and save to `hands/my-hand` (or pass `--hand their-hand`). More pages give more samples per letter and a more natural result; 3 to 6 pages is good.
- **If no photos are provided and no `hands/my-hand` exists:** use the bundled default handwriting immediately—never ask for photos unless they want their own handwriting.

## Step 1: read the input

- **PDF:** extract the text with pypdf, pdftotext or your own reader. For a scanned PDF, look at the page images.
- **Photo, screenshot, whiteboard:** read it yourself with vision. Do not run OCR libraries.
- **Text, a solution, a web page:** use it as given.

## Step 2: write the page (Compact Layout, Concise Math & High-Clarity Rules)

### Rule 1: Compact Layout — Eliminate Excessive Whitespace
- **No unnecessary banner headers:** Do NOT add boilerplate title banners (`# Problem Set`, `# Solution Notes`), course headers (`MATH 101 - Statistics`), or redundant divider lines unless the user asks for a title block. Start directly with `## Exercise 1` (or `1.`).
- **No wasted blank lines:** Do NOT put blank lines between consecutive equations or steps within the same sub-problem `(a)`, `(b)`, `(c)`. Keep steps tight on consecutive ruled lines, with at most a compact break between major sections.
- **Prefer inline `$...$` and left-aligned stacked `=` lines over padded `$$...$$` blocks:** Write regular equations on normal lines (`$P(Y \leq y) = P(X^\alpha \leq y) = P(X \leq y^{1/\alpha})$`, then next line `$= 1 - e^{-\lambda^\alpha y}$`) instead of wrapping every single equation in `$$...$$`. Reserve `$$...$$` only for tall multi-story fractions, large integrals, or summations with limits.
- **High page utilization:** Aim for 32–38 compact lines per A4 page, matching real handwritten note density. Do not use giant `#` headings or `---` horizontal rules unless requested.

### Rule 2: Concise, Direct Step-by-Step Mathematical Style
When turning verbose explanations or typed solutions into handwritten notes, **distill prose into clean, direct step-by-step math** while keeping every required condition, reasoning step, and exact number intact:
- **Skip redundant problem restatements:** Omit filler openings like `Given: n = 500 observations...`, `We want to find...`, `Recall that...`, `From the problem statement...`. Jump straight into `(a)` and the formula/substitution.
- **Drop meta-commentary and parenthetical filler:** Omit boilerplate like `Notice that...`, `It is easy to verify...`, `In conclusion...`, `Tip: ...`.
- **Use crisp mathematical connectors:**
  - Use `$\because$` (since/because), `$\therefore$` (therefore), `$\implies$`, `Let`, `Then`, `So`, `Thus`, `When $n=2$:`.
  - Stack multi-step algebra vertically as `= ...` on consecutive lines with no filler words in between.
  - State conclusions concisely: `$\therefore T_1$ is unbiased`, `$\therefore Y \sim \text{Exp}(\lambda^\alpha)$`.
- **Clean formatting:** Avoid `**bold**` clutter, `==highlights==`, or `!!` red callouts unless requested.

**Example (Verbose vs. Concise Handwritten Style):**
- *Verbose (avoid):*
  ```
  # Homework Notes
  MATH 101 - Statistics
  ### Exercise 1
  Given: n = 500 observations, bin width |B_i| = 1.

  a) Since the total area under the density histogram is equal to 1, the height on each bin B_i is given by:
  $$h_i = \frac{\text{count}_i}{n |B_i|} = \frac{\text{count}_i}{500}$$
  (Note: this follows directly from the histogram definition.)
  ```
- *Concise (preferred):*
  ```
  ## Exercise 1
  (a) $\because \sum_i h_i |B_i| = 1$ and $|B_i| = 1, n = 500$,
  $h_i = \frac{\text{count}_i}{n |B_i|} = \frac{\text{count}_i}{500}$
  ```

Keep the user's language for genuine required verbal answers, and keep every mathematical condition, symbol, and numerical result exact.

### Rule 3: Crystal-Clear Legibility for Every Letter, Digit, and Formula
Every single character (`a-z`, `A-Z`, especially `l`/`L`, `i`, `x`, `z`), every digit (`0-9`), and every subscript/superscript MUST remain sharp, high-contrast, and unmistakably readable at normal viewing zoom:
- **300 DPI High-Contrast Output Only:** Always render at full **300 DPI** (`2480×3508` for A4) with solid dark ink and high-quality PDF encoding (`resolution=300, quality=95, subsampling=0`). Never downscale, blur, or re-compress the output PDF/PNG.
- **Never stack deeply nested micro-fractions inline:** Avoid 3-story inline compound fractions like `$\left(\frac{1}{\frac{1}{n}\sum_{i=1}^n x_i^\alpha}\right)^{1/\alpha}$` where inner symbols shrink twice. Either write them cleanly as `$\left(\frac{1}{n}\sum_{i=1}^n x_i^\alpha\right)^{-1/\alpha}$` or place tall multi-layer fractions in a `$$...$$` display block so every digit and subscript stays full-sized and clear.
- **Strict Glyph Quality Gate (when updating `my-hand`):** Never admit blurry low-resolution crops, flat-top `Z`-like `2`s (digit `2` must always have a clear rounded top arch distinct from `z`/`Z`), broken digits (`4`/`5`/`8` with fused loops, or `9` with an oversized descender tail), or isolated wide cursive-loop `l` (`ℓ`) that looks awkward inside print words (`sample`, `analogue`). Always render and visually audit a 62-character (`a-z`, `A-Z`, `0-9`) contact sheet before saving `hands/my-hand`.
- **Per-Character Subtle Jitter on Every Letter, Digit, Symbol & Delimiter:** When `--jitter` is ON (default), every letter (`a-z`, `A-Z`) and digit (`0-9`) in both text and math formulas receives subtle independent micro-variations in width/height ratio, slant/shear, rotation, baseline bounce, and smooth curve elasticity so adjacent repeated characters (such as `22`, `44`, `0.0121`, `ee`, `ss`, `ll`) never look like identical clones while remaining 100% sharp; likewise, every drawn symbol—arrows (`\implies`, `\to`), approx (`\approx`, `\sim`), inequalities (`\leq`, `\geq`, `<`, `>`), slashes (`/`), parentheses `()` & `\left(\right)`, square brackets `[]` & `\left[\right]`, `|...|`, because/therefore (`\because`, `\therefore`), radicals `\sqrt{}`, and fraction bars—varies naturally on every occurrence. Passing `--no-jitter` cleanly disables this variation.

Markup:

```
# Title (avoid unless asked)   ## Exercise N             ### Sub-heading (underlined)
- bullet (2 spaces = deeper)   1. numbered               blank line = small gap
$...$ inline maths             $$...$$ tall display formula (use sparingly)
```

**Maths.** Put every formula in `$...$`, even short ones like `$x^2$`, `$n=16$`, or `$E_2$`. Supported:
`\frac{a}{b}`, `\sum_{k=1}^{n}`, `\prod`, `\int_a^b`, `\lim_{n \to +\infty}`, `\sqrt{x}`, `\sqrt[3]{x}`, `x^{n+1}`, `x_i`, `\left( ... \right)`, `\binom{n}{k}`, `\vec{u}`, `\bar{x}`, `\hat{\lambda}`, `\mathbb{R}`, `\text{...}`, `\mid`, Greek letters, `\therefore` (`∴`), `\because` (`∵`), `\in \subset \cup \cap \emptyset \forall \exists \leq \geq \neq \approx \pm \times \cdot \infty \to \implies \iff`, and spaces `\, \; \quad`.

Write decimals as the source does (`0.81` or `0,81`). Split long derivations across consecutive `$= ...$` lines rather than one wide shrinking line.

Save the page as `notes.md` (UTF-8 without BOM).

## Step 3: render

```bash
python scripts/handnotes.py render notes.md -o notes.pdf
```

Running with no extra flags outputs: 300 DPI A4 lined tablet paper (`--style ipad --paper lines`), pure black ink (`--ink black --accent black --important black`), `hands/my-hand` if present (or `hands/default`), natural per-character/symbol jitter (`--jitter`), and 1–2 subtle crossed-out false starts per page (`--scratch`). Change only what the user explicitly asked for:

| option | values |
|---|---|
| `--style` | **ipad** (default: solid Apple Pencil strokes on a clean lined tablet page) · notebook (phone photo of a real page: uneven light, lines drifting down, tilted sheet, ballpoint ink) |
| `--paper` | **lines** (default for ipad: subtle horizontal ruled lines) · blank (plain white) · **squared** (default for notebook) · college · seyes · grid · dots |
| `--hand` | **default** (`hands/my-hand`), `hands/default`, or a folder made by `build-hand` or `learn` |
| `--font` | use a handwriting font instead: caveat, kalam, patrick, gochi, indie, playpen |
| `--ink` | **black** (default for ipad) or **blue** (default for notebook), red, green, purple, pencil |
| `--jitter` / `--no-jitter` | **--jitter** (default ON: natural random glyph/baseline jitter) · `--no-jitter` (turn off jitter for neat alignment) |
| `--scratch` / `--no-scratch` | **--scratch** (default ON: 1–2 subtle crossed-out mistakes per page) · `--no-scratch` (turn off all cross-outs) |
| `--scratch-rate N` | max crossed-out mistakes per page when `--scratch` is ON (default: `2`) |
| `--page` | **a4**, letter, ipad, ipad-landscape |
| `--seed N` | the same page every time; change N for another take |

Use `-o notes.png` to get images (`notes-1.png`, `notes-2.png`, and so on) instead of a PDF.

## Step 4: check, then deliver

Render or inspect the output at full resolution (check PNG pages directly if you cannot view PDFs). Zoom-check that:
1. **Every letter (`a-z`, `A-Z`, including `l`/`L`) and every digit (`0-9`) is sharp, dark, and 100% legible**, including inside fractions, exponents, and summation limits (`i=1`, `n`).
2. **No line runs off the page or overlaps vertically** with the line above/below on horizontal ruled paper.
3. **Every number and symbol matches the source** with zero AI filler prose or excessive whitespace.
Then deliver the file.

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
