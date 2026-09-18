"""Hand-encoded ground truth for bench/samples/anton_yvan_boris_photo.jpg, written as MusicXML.

Read from the photo by hand, then checked note by note on zoomed crops (bench/RESULTS.md).
Notes worth a comment: m8 note 4 ("ra") is printed with a natural sign and sits on the C4 ledger line,
so it is C4. m9 note 2 ("Sous") has a natural and sits just below the ledger line: B3, the leading tone
before the G chord. The low notes in systems 3 and 4 are engraved without ledger lines; the ones about
0.7 interline below the staff are C4 (under Cm), the shallower ones are D4 (under G).
"""
from music21 import stream, note, meter, key, clef, harmony, metadata, bar

# (pitch or 'r', quarterLength, lyric)
MEASURES = [
    ("Cm", [("E-4",.75,"Lors"),("F4",.25,"que"),("G4",.5,"nous"),("G4",.5,"é")]),
    (None, [("G4",.5,"tions"),("A-4",.5,"en"),("A-4",.5,"core"),("G4",.5,"en")]),
    (None, [("G4",1,"fants"),("E-4",.75,"sur"),("F4",.25,"le")]),
    (None, [("G4",.5,"che"),("G4",.5,"min"),("G4",.5,"de"),("E-4",.5,"bru")]),
    ("Fm", [("F4",1,"yère,"),("D4",.75,"tout"),("E-4",.25,"le")]),
    (None, [("F4",.5,"long"),("G4",.5,"de"),("F4",.5,"la"),("D4",.5,"ri")]),
    ("Cm", [("E-4",1,"vière"),("C4",.75,"on"),("D4",.25,"cueil")]),
    ("Fm", [("E-4",.5,"lait"),("F4",.5,"la"),("E-4",.5,"mi"),("C4",.5,"ra")]),  # "ra" is printed with a natural sign on the C4 ledger line
    ("G",  [("D4",1,"belle."),("B3",.75,"Sous"),("C4",.25,"le")]),
    (None, [("D4",.5,"nez"),("E-4",.5,"des"),("D4",.5,"tour"),("B3",.5,"te")]),
    ("Cm", [("C4",1,"relles."),("G4",.5,"An"),("r",.5,None)]),
    (None, [("C4",.5,"ton,"),("r",.5,None),("G4",.5,"Y"),("r",.5,None)]),
    ("G",  [("D4",.5,"van,"),("r",.5,None),("G4",.5,"Bo"),("r",.5,None)]),
    (None, [("D4",.5,"ris"),("r",.5,None),("G4",.5,"et"),("r",.5,None)]),  # no ledger line, harmony still G
    ("Cm", [("C4",.5,"moi."),("r",.5,None),("G4",.5,"Re"),("G4",.5,"bec")]),
    (None, [("C4",.5,"ca,"),("r",.5,None),("G4",.5,"Pau"),("r",.5,None)]),
    ("G",  [("D4",.5,"la,"),("r",.5,None),("G4",.5,"Jo"),("G4",.5,"han")]),
    (None, [("D4",.5,"na"),("r",.5,None),("G4",.5,"et"),("r",.5,None)]),
    ("Cm", [("C4",.5,"moi."),("r",.5,None),("r",1,None)]),
]

s = stream.Score()
s.metadata = metadata.Metadata(title="Anton, Yvan, Boris et moi", composer="Marie Laforêt")
p = stream.Part(); p.partName = "Voice"
for i,(chord, events) in enumerate(MEASURES, start=1):
    m = stream.Measure(number=i)
    if i == 1:
        m.append(clef.TrebleClef()); m.append(key.KeySignature(-3)); m.append(meter.TimeSignature('2/4'))
    if chord:
        m.insert(0, harmony.ChordSymbol(chord))
    for pitch, ql, lyr in events:
        e = note.Rest(quarterLength=ql) if pitch == 'r' else note.Note(pitch, quarterLength=ql)
        if lyr: e.lyric = lyr
        m.append(e)
    if i == len(MEASURES): m.rightBarline = bar.Barline('final')
    p.append(m)
s.append(p)
s.write('musicxml', fp='bench/samples/anton_yvan_boris_ground_truth.musicxml')
print("measures", len(MEASURES), "notes", sum(1 for _,ev in MEASURES for e in ev if e[0]!='r'), "rests", sum(1 for _,ev in MEASURES for e in ev if e[0]=='r'))
