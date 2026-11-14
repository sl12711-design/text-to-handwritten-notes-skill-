# Changelog

What changed in each version. Only the latest release is kept for download.

## v0.2.4 (13 Nov 2026)
[Code and examples at this version](../../tree/v0.2.4)
- Smoother iPad writing: letters are retraced at 3x size, the photo's jagged outline is rounded off before the centre line is found, and the stroke is redrawn with round ends and anti-aliased edges.
- The iPad version of each letter is computed once and kept in the handwriting folder (`pencil/`), so rendering stays under a second. It ships ready for the default handwriting.
- Notebook engine unchanged.

## v0.2.3 (13 Nov 2026)
- Renamed to **text-to-handwritten-notes-skill** (skill name `text-to-handwritten-notes`). The old GitHub address redirects here.

## v0.2.2 (13 Nov 2026)
- The iPad style now has its own engine, separate from the notebook one. Every learned letter is retraced once as an even Apple Pencil stroke: the faint gaps are closed, the stroke is thinned to its centre line, then redrawn with one solid width. No more faded or missing parts.
- Photo specks no longer turn into stray dots.
- The notebook engine is unchanged.

## v0.2.1 (13 Nov 2026)
- iPad style: solid, even Apple Pencil ink and straight, tidy lines. The ballpoint texture is now only used for the notebook photo.
- Lined paper has blue lines and a red margin, like a real notebook.
- Default handwriting: removed 4 badly cut samples (three P, one 9) that drew stray strokes.
- New example pages (notebook, iPad, lined) and new handwriting photos in the README.

## v0.2.0 (13 Nov 2026)
- The default output is a phone photo of a squared notebook page, in blue ink, with a bundled default handwriting. `--style ipad` gives a clean tablet page.
- A handwriting can be learned from photos of pages already written, with no template (`segment`, labels, then `build-hand`).
- Letters are distorted a little differently each time, lines drift, and the ballpoint ink varies. Maths looks less typeset.
- French accents are drawn on the writer's own letters.
- Fixes: wide formulas shrink to fit, `50,000` stays tight, `\$` gives a dollar sign, `[x]` ticks without crossing out.

## v0.1.0 (13 Nov 2026)
- First version: text to handwritten notes in 6 handwriting fonts, on iPad grid, dots, lines, college or Seyès paper.
- Highlights, arrows, checkboxes, and maths drawn by hand.
- A handwriting learned from a filled 2-page template.
