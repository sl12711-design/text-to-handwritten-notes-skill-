---
name: handwritten-notes
description: Turn any content (a PDF, pasted text, a web page, a photo of a page or a whiteboard) into notes that look handwritten, like iPad Goodnotes/Notes pages or a school notebook (grid, lined, dotted, college-ruled or French Seyès paper), exported as PDF or PNG. Can also learn the user's own handwriting from a photo of a filled template sheet. Use when the user asks for handwritten notes, notes "à la main", iPad-style notes, notebook-style notes, or to write something in their own handwriting.
---

# Handwritten notes

You turn content into **real notes** (short, structured, with highlights) and render them so they look written by hand.
The renderer is `scripts/handnotes.py`. It only needs Python with Pillow and numpy (already present in ChatGPT and Claude code sandboxes). Fonts are in `fonts/`.

## Step 1: read the input

- **PDF**: extract the text (pypdf, pdftotext, or your own reader). For scanned PDFs, look at the page images.
- **Photo / screenshot / whiteboard**: read it yourself with vision. Do not run OCR libraries.
- **Text / web page**: use it as given.

## Step 2: write the notes (this is the important part)

Do **not** copy the source. Write what a good student would write in the margin of the lesson:

- One `# Title`, then `## Sections` that follow the source's structure.
- Short lines, keywords, no full sentences unless a definition needs one. Aim for 15-30 % of the source length.
- `==highlight==` the 1-3 key terms per section, not more. Each highlight is one key term or short phrase, so never put `==` around a whole line or bullet.
- `!! ` for the one or two things that truly matter (deadlines, warnings, exam traps).
- `->` for causes and consequences, `[ ]` for to-dos, `> ` for a side remark or an example.
- Keep the user's language. Keep numbers, names and formulas exact.
- If the source is long, keep each page to about 25 lines and group logically. The renderer adds pages by itself.

Markup reference:

```
# Title                     ## Heading                ### Sub-heading (underlined)
- bullet (2 spaces = one level deeper)                1. numbered
-> arrow line               !! IMPORTANT line (red)   > side note (accent ink)
[ ] to-do   [x] done        ---  separator            blank line = skip a line
inline: ==highlight==  =={pink}highlight==  **bold**  __underline__  ~~crossed~~
        {red}coloured ink{/}   ->  (drawn arrow)
inks: black blue red green purple pencil · highlights: yellow green pink blue orange
maths:  $...$ inline, $$...$$ alone on a line for a displayed formula (LaTeX subset)
```

**Maths.** Put every formula in `$...$`, even a short one like `$x^2$` or `$u_n$`. It is drawn by hand: powers and indices are raised or lowered, fractions get a bar, sums and integrals get their bounds, roots get a radical. Supported:
`\frac{a}{b}`, `\sum_{k=1}^{n}`, `\prod`, `\int_a^b`, `\lim_{n \to +\infty}`, `\sqrt{x}`, `\sqrt[3]{x}`, `x^{n+1}`, `x_i`, `\left( ... \right)` (also `[ ] \{ \} |`), `\binom{n}{k}`, `\vec{u}`, `\bar{x}`, `\hat{p}`, `\mathbb{R}`, `\text{...}`, `\sin \ln \exp \max ...`, Greek letters (`\alpha ... \Omega`), `\in \notin \subset \cup \cap \emptyset \forall \exists \leq \geq \neq \approx \equiv \pm \times \cdot \infty \to \Rightarrow \iff \mapsto \partial`, spaces `\, \; \quad`.
Intervals are written as they are read: `$[0, 1[$`, `$]-\infty ; 3]$`. Keep decimal commas if the source uses them. Unicode such as `x²`, `Aᶜ`, `x₁` also works outside `$`. Prefer `$$...$$` lines for big formulas (sums with bounds, integrals, stacked fractions) so they get their own space.

Save the notes to `notes.md`.

## Step 3: render

```bash
python scripts/handnotes.py render notes.md -o notes.pdf --paper grid --font caveat --seed 7
```

Choose the options from what the user asked for (defaults in bold):

| option | values |
|---|---|
| `--paper` | **grid** (iPad), dots, lines, blank, college (US notebook), seyes (French notebook) |
| `--page` | **a4**, letter, ipad, ipad-landscape |
| `--font` | **caveat** (fast, slanted), kalam (rounded), patrick (neat print), gochi (marker), indie (bubbly), playpen (school, clearest maths) |
| `--ink` / `--accent` / `--important` | **black** / **blue** / **red**, or green, purple, pencil |
| `--bullet` | **arrow** (↳), dot, dash |
| `--size` | small, **medium**, large |
| `--mess` | 0.5 neat … **1.0** … 1.5 rushed |

Use `-o notes.png` for an image instead of a PDF. A multi-page document then gives `notes-1.png`, `notes-2.png`, and so on.

## Step 4: check, then deliver

Look at the first page (render a PNG if you cannot view PDFs). Check that no line runs off the page, that highlights sit on the key words, and that the look matches the request. Then give the user the file.

## The user's own handwriting

1. Generate the template, and give it to the user:
   `python scripts/handnotes.py template -o handwriting-template.pdf`
   (2 pages, one box per character, lowercase twice for natural variation).
2. The user fills it in with the pen they normally use. They can print it, or import it into Goodnotes/Notes/Notability on an iPad and write on it. Then they send photos or screenshots of both pages. Photos can be tilted or sideways, but the 4 black corner squares must be visible.
3. Learn:
   `python scripts/handnotes.py learn page1.jpg page2.jpg -o my-hand`
   (prints which characters were learned, and which ones a font will stand in for).
4. Render with it: add `--hand my-hand` to the render command. Keep the `my-hand` folder, because it is what makes their handwriting reusable. Offer to zip it so they can re-upload it next time.

If the user sends photos of notes they already wrote, but no template, say honestly that exact copying needs the template. Meanwhile, pick the bundled font that looks closest to their writing and render with it.
