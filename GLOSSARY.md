# Partition Player

Turns a photo, PDF or MusicXML of a song sheet into a score that can be reviewed, corrected and played.

## Language

**Doubt**:
A place on the recognized score where the engine's reading is not trusted, rated at one of two levels.
_Avoid_: error, warning

**Reading**:
One possible way a part of the score could be; the engine's own is the first, the others are proposed beside it and chosen by the user.
_Avoid_: alternative, suggestion, candidate

**Span**:
One staff over a range of measures, with its photo crop and the score slice read from it; the unit of work of a model pass.
_Avoid_: region, section, zone

**Model pass**:
An optional step after recognition and review in which a language model re-reads chosen spans; it never runs on the whole score unasked.
_Avoid_: LLM correction, AI fix, repair

**Lyrics source**:
A picture or typed text of the lyrics alone, supplied by the user for a span; its words are taken as correct and only their placement under the notes is decided.
_Avoid_: better image, replacement text

**Repair bundle**:
Everything one model pass needs about one span: the crops, the score slice, the task and the shape of the expected answer.
_Avoid_: prompt, payload

**Model route**:
The way a model pass reaches a model: the user's own Claude Code session, an Anthropic-compatible API with the visitor's key, or one with the operator's key.
_Avoid_: backend, provider
