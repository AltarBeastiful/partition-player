"""Render a MusicXML file to PNG with verovio, for visual comparison."""
import sys, verovio, cairosvg
src, dst = sys.argv[1], sys.argv[2]
tk = verovio.toolkit()
tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 40, "adjustPageHeight": True})
tk.loadFile(src)
svg = tk.renderToSVG(1)
cairosvg.svg2png(bytestring=svg.encode(), write_to=dst, background_color="white")
print("rendered", dst, "pages:", tk.getPageCount())
