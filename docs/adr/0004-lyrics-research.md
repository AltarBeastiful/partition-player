# Lyrics recognition: research notes on OMR lyrics, OCR engines and alignment

Date: 2026-09-18. Appendix A of [ADR 0004](0004-lyrics.md). Compiled by a research agent from primary
sources (docs, papers, repositories); every claim carries its URL. Items marked "unverified" could not
be confirmed from a primary source. The companion survey of datasets and tools is
[0004-lyrics-survey.md](0004-lyrics-survey.md).

## 1. State of the art: lyrics in OMR

**Audiveris (the only open-source OMR with a real lyrics pipeline).** Text is delegated to Tesseract in
the TEXTS step; since 5.5 no language data ships with the installer and you pick languages as
`fra+eng` codes (docs warn that adding languages slows recognition and raises false positives)
([OCR languages](https://audiveris.github.io/audiveris/_pages/guides/main/languages/)). Lyrics must be
enabled in Book Parameters; each syllable is linked to a chord above/below, and a wrong link is fixed
by dragging the syllable to the right chord in the editor
([Text UI page](https://audiveris.github.io/audiveris/_pages/guides/ui/ui_tools/text/)). The source
shows the actual algorithm
([LyricItemInter.java](https://raw.githubusercontent.com/Audiveris/audiveris/master/app/src/main/java/org/audiveris/omr/sig/inter/LyricItemInter.java)):

- OCR words are split into items of kind Syllable / Hyphen / Extension / Elision / Number /
  Punctuation. Separators: hyphen `-`, elision `‿` (U+203F), extension = `_`, en dash or em dash
  ([StringUtil.java](https://raw.githubusercontent.com/Audiveris/audiveris/master/app/src/main/java/org/audiveris/omr/util/StringUtil.java)).
  A one-character dash item is a Hyphen, longer runs are an Extension.
- Syllabic type (SINGLE/BEGIN/MIDDLE/END) is inferred from whether the neighbouring items are hyphens.
- `mapToChord()`: candidate head-chords in the measure whose |dx| to the syllable's reference x is at
  most `maxItemDx` = **3 interlines** (a `Scale.Fraction` constant); the nearest by squared Euclidean
  distance wins; if two syllables claim the same chord, the one with the smaller |dx| keeps it and the
  other looks for a second choice. It searches chords below or above the staff depending on the
  syllable's y.
- Leading `[0-9]+\.?` is split off as a verse number (5.10, March 2026), and isolated punctuation "as
  in French" (`, ; : ! ?` set off by a space) is appended to the previous syllable
  ([Updates page](https://audiveris.github.io/audiveris/_pages/reference/updates/)).
- Known weaknesses: lyric lines of a close-below system get assigned to the wrong staff, and non-lyric
  text under the lyrics is taken as a verse (open since 2019,
  [issue #334](https://github.com/Audiveris/audiveris/issues/334)); accented characters get OCR'd as
  digits and the word is then classified as a Number
  ([Text UI page](https://audiveris.github.io/audiveris/_pages/guides/ui/ui_tools/text/)).

**MuseScore 4 PDF import** is Audiveris (server-side, one pass), so lyrics quality is Tesseract's and
the forum has repeated "lyrics missing after PDF import" threads
([musescore.org 342965](https://musescore.org/en/node/342965),
[318831](https://musescore.org/en/node/318831),
[audiveris.com](https://audiveris.com/how-does-audiveris-musescore-connection-work/)).

**Research (2023-2026).** The task has a name, AMNLT (Aligned Music Notation and Lyrics
Transcription). Martinez-Sevilla et al., ICDAR 2023, is end-to-end: the staff image is rotated 90
degrees and sliced at note positions so one sequence alternates notes and lyric characters
([Springer](https://link.springer.com/chapter/10.1007/978-3-031-41676-7_11),
[code](https://github.com/antoniorv6/icdar-2023-amnlt), outputs **kern). The journal follow-up
(Pattern Recognition 2026, [arXiv 2412.04217](https://arxiv.org/abs/2412.04217)) formalises alignment
as a partition of the note sequence into groups, one per syllable, compares divide-and-conquer vs
end-to-end, and finds end-to-end plus language modelling with the Sheet Music Transformer best (2.93 %
aligned error on GregoSynth, 7.32 % on Salzinnes). **Everything in that line is Gregorian chant on
4-line staves**; nothing is trained on modern lead sheets. SMT/SMT++
([2402.07596](https://arxiv.org/abs/2402.07596v2), [2405.12105](https://arxiv.org/html/2405.12105v2))
transcribe pianoform **kern without lyrics; LEGATO ([2506.19065](https://arxiv.org/abs/2506.19065))
outputs ABC from 214K full pages, lyrics not mentioned in the abstract (unverified whether its ABC
includes `w:` lines); OLiMPiC/Zeus ([ufal/olimpic-icdar24](https://github.com/ufal/olimpic-icdar24))
is Linearized MusicXML of the Lieder corpus and the repo does not state that lyrics are encoded. The
ISMIR 2025 jazz lead sheet OMR paper does melody + chords, no lyrics
([2509.05329](https://arxiv.org/abs/2509.05329)). Commercial PhotoScore/SmartScore do lyrics but
reviewers call the results unreliable
([Scoring Notes](https://www.scoringnotes.com/reviews/a-review-of-optical-music-recognition-software/)).
No GitHub project was found that does lyric OCR + syllable-to-note alignment on printed modern scores
other than Audiveris; oemer, Mozart, SheetVision, ScanScore have no lyrics
([oemer](https://github.com/BreezeWhite/oemer)). "The Lyrics of the Music Score" and "TrOMR with
lyrics" turned up nothing; treat those names as unverified.

## 2. OCR engines

**RapidOCR / PaddleOCR (already in the project).** The PP-OCR `en` recognizer's dictionary is pure
ASCII: no é è ê à ç ù; it does contain `-` and `_`
([en_dict.txt](https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/en_dict.txt)).
The PP-OCRv5 `latin` model covers French among 32+ Latin-script languages and its dictionary has all
French accents, œ/Œ, `-`, `_`, ASCII and typographic apostrophes and en dash
([ppocrv5_latin_dict.txt](https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/dict/ppocrv5_latin_dict.txt));
the v3 latin dict lacks Œ and ’
([latin_dict.txt](https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/dict/latin_dict.txt)).
Paddle reports latin v5 mobile at 84.7 % line accuracy vs 76.9 % for v3, **14 MB**, about 21 ms/line
CPU; en_v5 mobile 7.5 MB
([text_recognition module](http://www.paddleocr.ai/main/en/version3.x/module_usage/text_recognition.html),
[multilingual page](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md)).
In rapidocr v3 select it with `params={"Rec.lang_type": LangRec.LATIN, "Rec.ocr_version":
OCRVersion.PPOCRV5, "Rec.model_type": ModelType.MOBILE}`; `LangRec` has CH, EN, LATIN, CYRILLIC,
ESLAV, etc. and there is no separate `FRENCH` value in v3
([typings.py](https://raw.githubusercontent.com/RapidAI/RapidOCR/main/python/rapidocr/utils/typings.py),
[model list](https://rapidai.github.io/RapidOCRDocs/main/model_list/): latin is mobile-only, models
auto-download from ModelScope). Flag: the older "french"/"german" v3 models listed in the docs are a
legacy path; not verified that they still download in v3.

*Local check (this project, 2026-09-18):* the rapidocr version installed with homr defaults to the
**PP-OCRv6 small** recognizer, whose embedded dictionary has 18 708 characters including é è ê à ç œ,
so the default model already reads French. The latin v5 mobile model downloaded (7.5 MB) and gave
equivalent text on the benchmark photo. See the ADR's probe findings.

**Tesseract 5 `fra`.** best = 3.97 MB, fast = 1.13 MB
([tessdata_best](https://api.github.com/repos/tesseract-ocr/tessdata_best/contents/fra.traineddata),
[tessdata_fast](https://api.github.com/repos/tesseract-ocr/tessdata_fast/contents/fra.traineddata));
fast is "best value", best trades "a lot of speed for slightly better accuracy"
([Data-Files](https://tesseract-ocr.github.io/tessdoc/Data-Files.html)). Geometry: TSV gives word
boxes + confidence, hOCR gives word boxes and line baseline, `-c hocr_char_boxes=1` adds character
boxes ([CLI docs](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html),
[issue 2580](https://github.com/tesseract-ocr/tesseract/issues/2580)). Weaknesses: designed for 300
dpi scans, degrades on skewed, unevenly lit phone photos
([ImproveQuality](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html));
`tessedit_char_whitelist` breaks whitespace with the LSTM engine
([issue 2923](https://github.com/tesseract-ocr/tesseract/issues/2923)); end-of-line hyphens can be
turned into soft hyphens U+00AD ([issue 2161](https://github.com/tesseract-ocr/tesseract/issues/2161)).
Audiveris's Tesseract-on-lyrics experience above is the best proxy for "typical accuracy".

**Others, briefly.** docTR/OnnxTR: `crnn_mobilenet_v3_small` uses the French vocab, 0.12-0.17 s/page
CPU with 8-bit quantised ONNX ([OnnxTR](https://github.com/felixdittrich92/OnnxTR),
[doctr models](https://mindee.github.io/doctr/latest/using_doctr/using_models.html)); a credible
alternative but line-level boxes only. EasyOCR: ~500 MB footprint, roughly 3x slower on CPU
([issue 645](https://github.com/JaidedAI/EasyOCR/issues/645)). Surya: 4-8 GB RAM, 2-5 s/page on CPU,
over the 3 GB budget ([surya](https://github.com/datalab-to/surya)). TrOCR: printed models are
English-only; the French checkpoints are handwriting fine-tunes
([trocr-large-handwritten-fr](https://huggingface.co/agomberto/trocr-large-handwritten-fr)). None is
clearly better than PP-OCRv5 latin for this job.

**Vision LLM.** Claude charges ⌈w/28⌉×⌈h/28⌉ visual tokens: a 1000×1000 crop is 1296 tokens, so
about $0.0013 on Haiku 4.5 ($1/MTok) or $0.0065 on Opus 5, plus output; latency is seconds per call
([vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)). Accuracy on clean
printed French lyric strips is very likely near-perfect for text, but VLMs hallucinate ("BASE" read as
"Baseline") and their coordinates are approximate, so they cannot give per-syllable x-positions
([VLM OCR benchmark 2502.06445](https://arxiv.org/html/2502.06445v1), vision docs "Spatial
reasoning"). Best used as a text corrector/syllabifier over OCR output, not as the positioner.

## 3. Word and syllable positions

- RapidOCR: line polygons by default; `return_word_box=True` adds per-word (Latin) / per-char (CJK)
  boxes derived from the CTC column index (`center_x = (col+0.5)·avg_col_width`), so they are
  approximate, ~20-35 % slower, and words are split on spaces or column gaps > 5
  ([DeepWiki word-level](https://deepwiki.com/RapidAI/RapidOCR/6.3-word-level-information),
  [issue 400](https://github.com/RapidAI/RapidOCR/issues/400)). Hyphens and underscores are in the
  latin dictionary but a detached ` - ` between syllables is a one-glyph token that DBNet may drop or
  merge; expect to recover hyphens and extenders **from pixels** (thin horizontal runs on the lyric
  baseline between word boxes) as a fallback. Audiveris does the equivalent: it treats `_`, en/em
  dash runs as extensions and a lone `-` as a hyphen, then reclassifies.
- Tesseract: word boxes (TSV/hOCR) and optional char boxes; hyphens survive better inside words
  ("cho-") than as isolated glyphs; soft-hyphen substitution at line ends.
- Practical rule seen in Audiveris: a syllable's anchor is its box centre x; candidate notes within 3
  interlines; ties resolved by smallest |dx|. For lead sheets one can additionally enforce
  left-to-right monotonicity (dynamic programming over syllables × noteheads), which Audiveris does not
  do and which issue #334 proposes.

## 4. Syllabification and conventions

- MusicXML: `<lyric number="1">` with `<syllabic>` single/begin/middle/end, `<text>`, `<elision>`
  between two syllables on one note, `<extend>` for melisma
  ([lyric](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/lyric/),
  [syllabic](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/syllabic),
  [elision example](https://www.w3.org/2021/06/musicxml40/musicxml-reference/examples/elision-element/)).
- MuseScore entry conventions (the de-facto engraving rules): `-` between syllables of a word, `_`
  extender for a melisma at word end, repeated `-` for a mid-word melisma, elision slur for two
  syllables on one note, verse numbers typed as "1." before the first syllable; literal hyphen/space
  inside a syllable via Ctrl+- / Ctrl+Space
  ([MuseScore handbook](https://handbook.musescore.org/text/lyrics),
  [melisma thread](https://musescore.org/en/node/359617)).
- Pyphen ships LibreOffice hunspell hyphenation for fr and en_US/en_GB (`inserted`, `positions`)
  ([pyphen.org](https://pyphen.org/)); these are typographic line-break rules, and one user measured
  ~15 % error when used as syllabification
  ([ResearchGate thread](https://www.researchgate.net/post/How-to-automatically-cut-words-into-syllables)).
  Rule-based French syllabifiers exist
  ([LuisAVasquez/french_syllabification](https://github.com/LuisAVasquez/french_syllabification),
  [ian-nai/french-syllabification](https://github.com/ian-nai/french-syllabification)). The real
  French problem is the e muet: in songs it is sung or not depending on the composer, and a final -e
  before a vowel is elided ([Mélodie Treasury](https://www.melodietreasury.com/singinginfrench.html),
  [Spoken vs sung French](http://www.newworldchorale.org/wp-content/uploads/2014/07/Spoken_vs_sung_French_RS.pdf)),
  so syllable count must come from the engraved hyphens/note count, not from a dictionary; use pyphen
  only to propose split points when the user types a plain-text verse.

## 5. Test data

- OpenScore Lieder: 1,300+ songs, CC0, `.mscx` with lyrics plus per-song lyric `.txt`; convertible to
  MusicXML/PDF with MuseScore ([repo](https://github.com/OpenScore/Lieder/blob/main/README.md)).
  Mostly German, some French; single vocal staff + piano, so only the voice part would be rendered to
  mimic a lead sheet.
- PDMX: 250K MuseScore MusicXML files with MXL + PDF, lyrics parsed by MusicRender; use the
  `no_license_conflict` subset (222,856) ([arXiv 2409.10831](https://arxiv.org/abs/2409.10831),
  [GitHub](https://github.com/pnlong/PDMX/)). Filter by genre tags for hymns/folk/chanson to get real
  lead sheets with verses.
- CPDL: 51K choral works, many with MusicXML uploads, multi-verse hymns
  ([CPDL forum](https://forums.cpdl.org/phpBB3/viewtopic.php?t=7061)); no bulk corpus, scraping needed.
- Rendering: Verovio keeps MEI/MusicXML ids and element names as SVG `id`/`class`, so the rendered
  `syl` positions give exact syllable-to-note ground truth
  ([Verovio CSS/SVG](https://book.verovio.org/interactive-notation/css-and-svg.html)); OLiMPiC did the
  same with MuseScore for its synthetic split ([olimpic-icdar24](https://github.com/ufal/olimpic-icdar24)).
- No public **photo** dataset with lyric ground truth was found; Camera-PrIMuS/MUSCIMA++ have no lyrics
  ([OMR-Datasets](https://apacha.github.io/OMR-Datasets/)). Photos of rendered pages (or
  Camera-PrIMuS-style distortions) have to be made in-house.

## Recommendation from the evidence

- **OCR**: RapidOCR with a French-capable recognizer (the installed PP-OCRv6 default, or
  `LangRec.LATIN` + PP-OCRv5, 14 MB, same runtime already loaded); `return_word_box` for word
  x-ranges. Tesseract `fra` is a reasonable second opinion on hyphens/char boxes but not worth adding
  as a dependency unless PP-OCR word boxes prove too coarse.
- **Alignment**: do what Audiveris does but better: (1) find lyric lines as text rows below the staff
  (y bands ordered by verse), strip leading "1." numbers; (2) detect hyphens/underscores on the
  baseline when OCR drops them; (3) assign syllables to homr noteheads with monotone DP on x-distance
  (tolerance ~3 interlines) so a dropped or spurious syllable cannot shift the rest of the line;
  (4) derive syllabic begin/middle/end from the hyphen graph; extender pixels give `<extend>`;
  (5) optionally send the OCR text with note count per phrase to a small LLM to fix accents and
  confirm syllable count, at ~$0.001/strip.
- **Biggest risks**: word boxes from CTC columns are approximate on tilted photos (rectify with homr's
  staff-line geometry first); isolated hyphens and underscores are the glyphs OCR drops most;
  multi-verse lines under one staff are easy to swap when interline spacing is tight (Audiveris #334);
  e muet means note count and text syllable count legitimately disagree, so never "fix" text to match
  pyphen; and there is no off-the-shelf model or dataset for modern lead sheets, so the benchmark has
  to be self-made from Lieder/PDMX renders.
