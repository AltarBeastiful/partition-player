"""The offline case: a tiny synthetic page and a scripted route, so the harness runs without keys or bench data.

Four 4/4 measures of quarter notes. The engine reads measure 1 with one wrong pitch; the scripted model answers with
the fix and with one operation that would break a measure (the validator must reject it).
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from harness import Case

TRUTH = [["C4", "D4", "E4", "F4"], ["G4", "A4", "B4", "C5"], ["C5", "B4", "A4", "G4"], ["F4", "E4", "D4", "C4"]]
ENGINE = [row[:] for row in TRUTH]
ENGINE[1][2] = "A4"   # a B read as an A


def build(measures: list[list[str]]) -> ET.Element:
    out = ['<score-partwise><part-list><score-part id="P1"/></part-list><part id="P1">']
    for i, m in enumerate(measures):
        attrs = "<attributes><divisions>1</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>" if i == 0 else ""
        out.append(f'<measure number="{i + 1}">{attrs}')
        for n in m:
            out.append(f"<note><pitch><step>{n[0]}</step><octave>{n[1]}</octave></pitch><duration>1</duration><type>quarter</type></note>")
        out.append("</measure>")
    out.append("</part></score-partwise>")
    return ET.fromstring("".join(out))


def case() -> Case:
    return Case("synthetic", build(ENGINE), build(TRUTH), [{"staff": 0, "from": 0, "to": 3}])


def script(model: str, prompt: str) -> str:
    return json.dumps([
        {"op": "stepPitch", "measure": 1, "event": 2, "delta": 1},   # A -> B: right
        {"op": "deleteEvent", "measure": 2, "event": 0},             # measure 2 stops adding up: rejected
    ])
