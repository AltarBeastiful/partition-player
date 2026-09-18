# Lyrics recognition: survey of datasets, tools and papers

Date: 2026-09-18

Scope: what exists to add lyric recognition (text, syllable-to-note assignment, hyphenation, extenders, verses) to the homr + RapidOCR pipeline, on CPU ARM64 with ~3 GB RAM. Every "verdict" is relative to that constraint. Items marked *(unverified)* were not confirmed against a primary source.

## Summary

- No public OMR model outputs lyrics for modern printed notation. SMT/SMT++/Zeus/Legato/LEGATO 2/Transcoda all strip or replace lyrics; homr's only lyrics PR (#65) was closed unmerged. We will have to build the lyric stage ourselves.
- The only research that solves aligned music+lyrics end to end (AMNLT, ICDAR 2023 and Pattern Recognition 2026, MIT code) is on Gregorian chant only; its *encoding idea* (music tokens with a prefix interleaved with syllable text, plus syllable-level post-alignment metrics AMLER/AlER) is reusable for a benchmark, its models are not.
- The strongest open reference implementation of the whole lyric stack is Audiveris (Java, AGPL): Tesseract words -> `TextRole` guess (position below staff, not italic, not chord) -> `LyricLineInter` -> `LyricItemInter` kinds (syllable/hyphen/extension/elision/number) -> `mapToChord` by nearest x with tolerance `maxItemDx = 3` staff spaces and conflict resolution -> `SyllabicType` from neighbouring hyphens. Copy the algorithm, not the code.
- RapidOCR with `Rec.lang_type=LangDet.LATIN`, `Rec.ocr_version=OCRVersion.PPOCRV5` (rapidocr >= 3.3.0, mobile model only) and `return_word_box=True` gives per-word quads via CTC alignment on CPU: this is the natural text front end and already in the stack.
- Best ground-truth sources with lyrics: OpenScore Lieder (1,300+ MuseScore songs, CC0, lyrics in mscx and as .txt) and PDMX (250K MusicXML from MuseScore, lyrics present but "uncommon"); render them with MuseScore or verovio to get pixel-exact syllable positions for synthetic training/benchmark pages. CPDL and Mutopia add choral/hymn material with lyrics but no bulk dump.
- Only one public *scanned* set has lyrics ground truth aligned to notes in modern notation: Sheet Music Benchmark (685 KernScores pages, `**kern` with lyric syllables scored by OMR-NED). License conflict: paper says CC BY 4.0, HF card says CC BY-NC 4.0.
- Every classic OMR dataset on apacha/OMR-Datasets (DoReMi, DeepScores V1/V2, MUSCIMA++, CVC-MUSCIMA, PrIMuS/Camera-PrIMuS, MSMD, GrandStaff, OLiMPiC, AudioLabs) has no lyric annotation; OLiMPiC and GrandStaff explicitly remove lyrics and the vocal staff.
- Hyphenation dictionaries (pyphen `hyph_fr.dic`, `hyph_en_US.dic`, LibreOffice, LGPL/MPL) are typographic; ~15% disagreement with sung syllabification is reported for French. Acceptable for a first pass because the OCR'd hyphens on the page already carry the true split; dictionaries are only needed when the user retypes a word in the editor.
- MusicXML 4.0 `<lyric>` carries everything we need: `<syllabic>` single/begin/middle/end, `<extend type="start|continue|stop">`, `<elision>`, `number` per verse. music21's `Lyric` maps 1:1 (text, syllabic, number, identifier, components for elision) but has no syllabifier.
- Rendering benchmark pages with known positions is easy with verovio (SVG `<g class="syl" id=...>` nested under the note's `<g class="note">`, `svgAdditionalAttribute` for extra data) or MuseScore CLI `-o page.svg/.png`.

## 1. Datasets

Legend: GT = ground truth; syl-note = syllable-to-note alignment; boxes = text bounding boxes.

| Dataset | URL | Licence | Activity | Lyrics? | Type | Verdict |
|---|---|---|---|---|---|---|
| OpenScore Lieder | https://github.com/OpenScore/Lieder | CC0 | active (239 commits) | Yes: lyrics in .mscx/.mxl, plus extracted .txt per part; syl-note implicit in MusicXML | symbolic (render to get images) | Best source for synthetic lyric pages; German/French 19th c. songs, vocal staff + piano |
| PDMX | https://github.com/pnlong/PDMX, https://zenodo.org/records/13763756 | CC (per-score; use `no_license_conflict` subset) | 2024-2025 | Some; lyrics parsed by MusicRender; "uncommon" per LEGATO 2 authors | symbolic + PDF | Filter for `lyrics` present; large pool of lead-sheet-like user scores |
| Sheet Music Benchmark (SMB) | https://huggingface.co/datasets/PRAIG/SMB, https://arxiv.org/abs/2506.10488 | CC BY 4.0 (paper) vs CC BY-NC 4.0 (HF card) - conflict | 2025 | Yes: `**kern` incl. lyric syllables and verse ids; OMR-NED has a lyric category | scanned PD pages from KernScores, 685 pages / 4,039 regions with region boxes | Only scanned modern-notation set with lyric GT; use for evaluation, mind the licence |
| AMNLT datasets (GregoSynth, Solesmes, Einsiedeln, Salzinnes) | https://huggingface.co/datasets/PRAIG/AMNLT | CC BY-NC 4.0 | 2024-2026 | Yes, syl-note aligned in gabc/pseudo-gabc | Gregorian chant, staff-level | Wrong notation for us; useful only for metric/encoding ideas |
| ICDAR 2023 AMNLT data | https://grfia.dlsi.ua.es/musicdocs/ICDAR2023_AMNLT.tgz | unstated | 2023 | Yes (kern with text spines) | Gregorian/early | Same as above |
| OLiMPiC (synthetic + scanned) | https://github.com/ufal/olimpic-icdar24 | CC BY-SA | 2024 | No: piano part only, lyrics discarded; scanned split = IMSLP page scans of Lieder with system boxes | synthetic + scanned | Page scans could be re-annotated for lyrics since the Lieder MusicXML is known *(check whether vocal staff is in the crops)* |
| No lyrics at all: GrandStaff (lyrics removed), DoReMi (only `dynamicText`), DeepScores V1/V2 (no lyric class among 135 *(unverified)*), MUSCIMA++/CVC-MUSCIMA, PrIMuS/Camera-PrIMuS, MSMD, AudioLabs v1/v2, PRAIG/polish-scores, FLSS, ABC/Nottingham | see apacha list | various | - | No | - | Irrelevant |
| SEILS | https://github.com/SEILSdataset/SEILSdataset | CC BY-NC-SA | 2017 | Yes (madrigal texts, LilyPond/MEI) | historical prints | Marginal |
| CPDL / ChoralWiki | https://www.cpdl.org/ | CPDL licence (GPL-like) | active | Yes, per-score MusicXML/PDF | symbolic, no bulk dump | Hymn/choir material; scrape a few hundred MusicXML for rendering |
| Mutopia | https://www.mutopiaproject.org/ | PD / CC | active | Yes in vocal works (LilyPond `\lyricmode`) | symbolic | Small vocal subset; LilyPond gives exact glyph positions |
| Open Hymnal | http://openhymnal.org/ | PD | 2014 | Yes | PDF, sources *(unverified)* | Marginal |
| IMSLP | https://imslp.org | PD scans | active | Scans with lyrics, no GT | scans | Realistic test pages once we have an annotator |
| Cantus / DIAMM / CantusCorpus | https://arxiv.org/abs/2603.11933 | mixed | 2026 | Chant text only | manuscripts | Irrelevant |

Nothing found contains photos of printed *lead sheets* with lyric GT. We must make our own: render Lieder/PDMX/CPDL with lyrics (verovio or MuseScore), keep syllable boxes from the SVG, apply photo augmentation, and add a small hand-labelled photo set for the final benchmark.

## 2. Tools, code and papers

| Item | URL | Licence / runtime | Activity | Lyrics? | Verdict |
|---|---|---|---|---|---|
| Audiveris 5.x | https://github.com/Audiveris/audiveris | AGPL-3, Java, Tesseract 5 (`fra+eng` tessdata via Tools > Languages) | active 2026 | Full stack: `TextRole.guess()` (lyrics only below the part's staves unless `lyricsAboveStaff`, not italic, not all-chords, min length 2.5 interlines, max staff distance 7), `LyricLineInter` (verse number per part), `LyricItemInter` (kinds syllable/hyphen/extension/elision/punctuation/number; `SyllabicType` from neighbours; `mapToChord`: nearest chord by x within `maxItemDx = 3` interlines, closer syllable wins, loser retries with that chord blacklisted), `ChordSyllableRelation` | Reference design. Weaknesses (issues #334, #633, #55): wrong staff when systems are close, trailing non-lyric text taken as lyrics, chord symbols treated as lyrics; verse numbers filtered, isolated French punctuation merged with previous syllable |
| MuseScore 4 PDF import | https://musescore.org/en/node/363395 | server-side Audiveris | - | via Audiveris/Tesseract; users report lyrics missing | Nothing new |
| homr | https://github.com/liebharc/homr | AGPL-3, Python, ONNX/CPU | active 2026 | No. PR #65 "Marko/lyrics detection" (Jan-Mar 2026, closed unmerged: lyrics detection + slurs + extra XML attrs, trained model not published); no open issue on lyrics | Confirms we add lyrics as a separate stage on top of homr's geometry |
| oemer | https://github.com/BreezeWhite/oemer | MIT, ONNX/CPU | maintained | No | Nothing for lyrics |
| SMT / SMT++ | https://github.com/antoniorv6/SMT, https://github.com/antoniorv6/SMT-plusplus | MIT, PyTorch, GPU-oriented, weights on HF `antoniorv6/sheet-music-transformer` | 2024-2025 (SMT++ archived into SMT) | No; bekern without text | Not usable for lyrics |
| Zeus / OLiMPiC (ufal) | https://github.com/ufal/olimpic-icdar24 | MIT code, CC BY-SA model | 2024 | No (LMX drops lyrics) | Not usable |
| Legato | https://github.com/guang-yng/legato, https://huggingface.co/guangyangmusic/legato | weights public; Llama-3.2-11B-Vision encoder (836M frozen) + 101M decoder, ABC output | 2025 | No: all text incl. lyrics replaced by `<|text|>` tokens | Too large for CPU/3 GB; no lyrics anyway |
| LEGATO 2 | https://arxiv.org/abs/2607.05769 | code/data "upon publication", not yet released | July 2026 | Titles/annotations yes, lyrics explicitly excluded | Watch, not usable |
| Transcoda | https://arxiv.org/abs/2605.10835 | not released | May 2026 | No | Not usable |
| AMNLT (Fuentes-Martinez et al., Pattern Recognition 2026) | https://github.com/efm18/AMNLT, https://arxiv.org/abs/2412.04217 | MIT, PyTorch Lightning, GPU; "under major refactoring" | 2025-2026 | Yes: joint transcription+alignment; `<m>`-prefixed music tokens interleaved with lyric chars; CTC "divide & conquer", "unfolding" CRNN on rotated images, ConvNeXt+Transformer LM; metrics AMLER/AlER | Chant only; borrow the sequence encoding and metrics for our benchmark |
| ICDAR 2023 AMNLT | https://github.com/antoniorv6/icdar-2023-amnlt | MIT, PyTorch 2.0/CUDA | 2023-2024 | Yes (kern + text spines) | Same |
| Jazz lead sheet OMR (ISMIR 2025) | https://arxiv.org/abs/2509.05329 | CC BY 4.0, code+data+models released | 2025 | Chords yes, lyrics no; 293 handwritten lead sheets in kern/MusicXML | Relevant to the chord stage, not lyrics |
| Sheet Music Benchmark | see datasets | - | 2025 | OMR-NED lyric category (one symbol per syllable character + verse id) | Use its lyric metric definition |
| PhotoScore & NotateMe Ultimate | https://www.soundonsound.com/reviews/neuratron-photoscore-notateme-ultimate-2020 | commercial, Windows/macOS | last update 2020 | Claims printed lyrics in several languages | Reference for what users expect; no API |
| SmartScore 64 / ScanScore / PlayScore 2 | https://www.scoringnotes.com/reviews/scanning-the-current-omr-landscape/ (Dec 2024) | commercial | active | ScanScore and PhotoScore "attempt" lyrics; PlayScore text recognition off by default; SmartScore reads lyrics *(unverified)* | No public evaluation of lyric accuracy exists |
| Verovio | https://github.com/rism-digital/verovio | LGPL-3, C++/Python/JS | active | Rendering only, see section 5 | Benchmark rendering |
| music21 | https://www.music21.org/music21docs/moduleReference/moduleNote.html | BSD | active | `Lyric(text, number, identifier, syllabic, components/elision)`, `rawText` keeps hyphens; MusicXML round-trip; no syllabifier | Use for MusicXML lyric I/O in tests |
| hymn-ocr | https://github.com/nitaibezerra/hymn-ocr | MIT, Python, Tesseract | 2026 | Text only, PDF hymnals to YAML, no note alignment | Not useful |
| Audio-to-Lead-Sheet-Transcription | https://github.com/Multimodal-Music-Research-Lab/Audio-to-Lead-Sheet-Transcription | ? | 2024 | Aligns ASR syllables to kern notes (audio side) | Alignment idea only |

GitHub searches for "OMR lyrics", "sheet music lyrics OCR", "lyrics syllable note alignment musicxml", "hymn OCR" found nothing else usable (results are chord-sheet editors and songbook apps).

## 3. Text OCR building blocks (CPU ARM64, accented French, word boxes)

| Engine | French accents | Boxes | CPU cost / size | Note |
|---|---|---|---|---|
| RapidOCR (PP-OCRv5 latin mobile rec + PP-OCRv4/v5 det) | Yes, `latin` dictionary covers fr/de/es/it | Line quads from DBNet; `return_word_box=True` yields `word_results` = (text, conf, quad) per word via CTC alignment | det ~5 MB, rec ~10 MB ONNX; sub-second per page on CPU | Already in the stack; needs `rapidocr>=3.3.0`, `Rec.lang_type=LangDet.LATIN`, `Rec.ocr_version=OCRVersion.PPOCRV5`. Server variant not available for latin v5. Issue #400 reports word boxes failing in some configurations |
| Tesseract 5 `fra` | Yes | Word boxes + confidences (hOCR/TSV/ALTO) | ~15 MB traineddata, a few seconds per page, ARM64 packages available | What Audiveris uses; weaker than PP-OCR on photos, fine on scans |
| docTR (Mindee) | Yes, `french` vocab, CRNN/PARSeq heads | Word boxes | ~60-100 MB per model, ONNX export available, CPU ok | Solid fallback; heavier than RapidOCR *(sizes approximate)* |
| EasyOCR | Yes (`fr`, latin_g2) | Word/line boxes | ~90 MB rec + ~80 MB CRAFT det, PyTorch, slow on CPU | No advantage |
| Surya | Yes (90+ languages) | Char/word/line boxes | ~650M params total, GPU-oriented | Too heavy for 3 GB |
| PARSeq (pretrained) | English charset only; French needs retraining | Recognizer only, no det | 23M params | Use only via docTR's French-trained variant |
| TrOCR | Printed English; multilingual by fine-tune | Recognizer only | 330M-560M params | Too heavy, no French |
| Florence-2 | Limited, `<OCR_WITH_REGION>` returns boxes | Yes | 230M/770M, ~1.5 GB weights, ~1 s on T4 | Too heavy on CPU |
| Vision LLM APIs | Excellent on accents and on reading verse structure | Boxes unreliable | per-call cost, latency, privacy | Good for a "fix the words" pass in the editor, not for placement |

## 4. Syllabification and lyric-entry conventions

- pyphen: https://github.com/Kozea/Pyphen, pure Python, GPL/LGPL/MPL tri-licence; ships `hyph_fr.dic`, `hyph_en_US.dic`, `hyph_en_GB.dic` from LibreOffice. `Pyphen(lang='fr').inserted('chanter')` returns `chan-ter`. Reported ~15% error when used as a syllabifier.
- PyHyphen: https://github.com/dr-leo/PyHyphen, C libhyphen binding, `syllables()` helper, same dictionaries.
- `syllables` (PyPI): English syllable *counter* only, GPLv3. Not useful.
- French phonetic syllabifiers: https://github.com/LuisAVasquez/french_syllabification, https://github.com/ian-nai/french-syllabification, https://github.com/psawa/syllable_splitter (WIP), https://github.com/UrielCh/syllabify-fr (JS). Small rule-based projects, no licence/maintenance guarantees.
- Typographic vs sung: hyphenation dictionaries are typographic (line-break points), not phonetic. For singing the differences matter in French for schwa/mute e (`ta-ble` sung as two syllables vs one), for liaison/elision across words (`l'a-mour`, `que je` sung as one note: MusicXML `<elision>`), and for diaeresis (`li-on` vs `lion`). English hyphenation (`-ing`, `-tion`) is closer to sung practice but still splits on morphology. Consequence: use the hyphens printed on the page as truth; call pyphen only as a suggestion when the user retypes a word in the editor, and let the user override.
- Notation conventions to mirror in the editor: MuseScore (https://handbook.musescore.org/text/lyrics): `-` moves to the next note and inserts a hyphen; `_` adds a melisma extender; Space ends a word; `Ctrl+-`/`Ctrl+_`/`Ctrl+Space` insert literal characters; elision slur via Special Characters. LilyPond (https://lilypond.org/doc/v2.24/Documentation/notation/common-notation-for-vocal-music): `" -- "` hyphen, `" __ "` extender, `_` skip one note, `~` lyric tie (elision), `\lyricsto` auto-aligns syllables to notes and treats slurs/ties as melismata (`melismaBusyProperties`). MusicXML 4.0 `<lyric number="1">` with `<syllabic>`, `<text>`, `<elision>`, `<extend type="start|continue|stop">`, `<end-line>`, `<end-paragraph>` (https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/lyric/).
- The MuseScore-community online hyphenator (hyphenator.glitch.me) is gone (HTTP 410).

## 5. Benchmark rendering

Verovio (Python wheel `verovio`, LGPL) renders MusicXML/MEI to SVG where each MEI element becomes a `<g>` with `class` = element name and `id` = xml:id, so a note is `<g class="note" id="...">` and its lyric syllable is a `<g class="syl" id="..."><text>` nested under `<g class="verse">` inside that note; hyphens and extender lines are separate groups, and `svgAdditionalAttribute` can expose extra MEI attributes (e.g. `verse@n`). Parsing the SVG gives syllable boxes plus the owning note id for free; there is no PNG output in verovio, so rasterise the SVG with cairosvg/resvg before augmenting. MuseScore 4 CLI (`mscore score.mxl -o page.svg` or `page.png`, `--trim-image`) renders with MuseScore's own engraving (closer to typical lead sheets) but the SVG carries no element ids, so positions must be recovered by matching text runs. Recommendation: verovio for GT positions, MuseScore for visual variety.

## Gaps and risks

- No dataset of photographed lead sheets with lyric GT; building one (synthetic + a few dozen hand-checked photos) is on the critical path.
- No CPU-runnable neural model does syllable-to-note assignment for modern notation; the realistic v1 is RapidOCR words + a small alignment model or DP over homr note x-positions, Audiveris-style, with hyphen/extender tokens from OCR.
- OCR failure modes specific to lyrics: single-vowel syllables, isolated hyphens and underscores (DBNet often drops them), verse numbers, French apostrophes and elisions, chord symbols on the line above being read as words.
- Verse count and chorus/refrain lines vary; text under the last system is often not lyrics (Audiveris issue #334).
- Licences: SMB may be CC BY-NC; AMNLT data is CC BY-NC; homr and Audiveris are AGPL; pyphen dictionaries are LGPL/MPL (fine to vendor).
- Word-box support in RapidOCR has had regressions (issue #400); pin a version and test.

## Sources

- https://github.com/apacha/OMR-Datasets
- https://github.com/OpenScore/Lieder
- https://github.com/pnlong/PDMX, https://zenodo.org/records/13763756, https://arxiv.org/abs/2409.10831
- https://huggingface.co/datasets/PRAIG/SMB, https://arxiv.org/abs/2506.10488
- https://huggingface.co/datasets/PRAIG/AMNLT, https://github.com/efm18/AMNLT, https://arxiv.org/abs/2412.04217
- https://github.com/antoniorv6/icdar-2023-amnlt
- https://github.com/ufal/olimpic-icdar24, https://arxiv.org/abs/2403.13763
- https://github.com/steinbergmedia/DoReMi
- https://zenodo.org/records/4012193
- https://huggingface.co/datasets/PRAIG/polish-scores
- https://zenodo.org/records/19068882
- https://github.com/SEILSdataset/SEILSdataset
- https://www.cpdl.org/, https://www.mutopiaproject.org/, http://openhymnal.org/
- https://arxiv.org/abs/2603.11933
- https://github.com/Audiveris/audiveris (files `app/src/main/java/org/audiveris/omr/text/TextRole.java`, `sig/inter/LyricItemInter.java`, `sig/inter/LyricLineInter.java`, `sig/relation/ChordSyllableRelation.java`)
- https://github.com/Audiveris/audiveris/issues/334, /issues/633, /issues/55, /issues/751
- https://audiveris.github.io/audiveris/_pages/guides/main/languages/
- https://musescore.org/en/node/363395
- https://github.com/liebharc/homr, https://github.com/liebharc/homr/pull/65
- https://github.com/BreezeWhite/oemer
- https://github.com/antoniorv6/SMT, https://github.com/antoniorv6/SMT-plusplus, https://arxiv.org/abs/2405.12105
- https://github.com/guang-yng/legato, https://huggingface.co/guangyangmusic/legato, https://arxiv.org/abs/2506.19065
- https://arxiv.org/abs/2607.05769 (LEGATO 2)
- https://arxiv.org/abs/2605.10835 (Transcoda)
- https://arxiv.org/abs/2509.05329 (Jazz lead sheets)
- https://arxiv.org/abs/2606.09479
- https://www.scoringnotes.com/reviews/scanning-the-current-omr-landscape/
- https://www.soundonsound.com/reviews/neuratron-photoscore-notateme-ultimate-2020
- https://github.com/nitaibezerra/hymn-ocr
- https://github.com/Multimodal-Music-Research-Lab/Audio-to-Lead-Sheet-Transcription
- https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/, https://github.com/RapidAI/RapidOCRDocs/blob/main/docs/model_list.md, https://github.com/RapidAI/RapidOCR/issues/400
- https://huggingface.co/PaddlePaddle/latin_PP-OCRv5_mobile_rec
- https://github.com/tesseract-ocr/tessdata/blob/main/fra.traineddata
- https://blog.roboflow.com/florence-2-ocr/
- https://www.music21.org/music21docs/moduleReference/moduleNote.html
- https://github.com/Kozea/Pyphen, https://pyphen.org/, https://github.com/dr-leo/PyHyphen, https://pypi.org/project/syllables/
- https://github.com/LuisAVasquez/french_syllabification, https://github.com/ian-nai/french-syllabification, https://github.com/psawa/syllable_splitter, https://github.com/UrielCh/syllabify-fr
- https://handbook.musescore.org/text/lyrics, https://handbook.musescore.org/appendix/command-line-usage
- https://lilypond.org/doc/v2.24/Documentation/notation/common-notation-for-vocal-music
- https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/lyric/
- https://book.verovio.org/advanced-topics/internal-structure.html, https://book.verovio.org/interactive-notation/css-and-svg.html, https://archives.ismir.net/ismir2014/paper/000221.pdf
