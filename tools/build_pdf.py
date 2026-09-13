"""Convierte ESTRATEGIA.md a ESTRATEGIA.pdf usando python-markdown + Google Chrome en modo headless.
Uso: .venv/bin/python tools/build_pdf.py"""
import base64, os, re, shutil, signal, subprocess, sys, tempfile, time
from pathlib import Path
import markdown

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "ESTRATEGIA.md"
PDF = ROOT / "ESTRATEGIA.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 18mm 17mm 20mm 17mm; }
html { font-size: 10.5pt; }
body { font-family: "Helvetica Neue", system-ui, -apple-system, sans-serif; color: #0b0b0b; background: #fff; line-height: 1.45; margin: 0; }
.cover { height: 88vh; display: flex; flex-direction: column; justify-content: center; break-after: page; }
.cover h1 { font-size: 30pt; margin: 0 0 12pt; line-height: 1.15; }
.cover .meta { color: #52514e; font-size: 11pt; margin: 3pt 0; }
.cover .warn { margin-top: 28pt; padding: 10pt 12pt; border-left: 3px solid #eda100; background: #fff8e6; font-size: 10pt; color: #52514e; }
.toc { break-after: page; }
.toctitle { display: block; font-size: 16pt; font-weight: 600; margin-bottom: 10pt; }
h2.flow { break-before: auto; margin-top: 22pt; }
.toc ul { list-style: none; padding-left: 0; margin: 0; }
.toc > ul > li { margin: 5pt 0; font-weight: 500; }
.toc ul ul { padding-left: 14pt; font-weight: 400; color: #52514e; font-size: 9.5pt; }
.toc ul ul li { margin: 2pt 0; }
.toc a { color: inherit; text-decoration: none; }
h1 { font-size: 22pt; margin: 0 0 10pt; }
h2 { break-before: page; font-size: 16pt; margin: 0 0 10pt; padding-bottom: 4pt; border-bottom: 1px solid #e1e0d9; break-after: avoid; }
h3 { font-size: 12.5pt; margin: 16pt 0 6pt; break-after: avoid; }
h2 + h3 { margin-top: 8pt; }
p { margin: 5pt 0 8pt; orphans: 3; widows: 3; }
ul, ol { margin: 4pt 0 8pt; padding-left: 18pt; }
li { margin: 2pt 0; }
li > ul, li > ol { margin: 2pt 0; }
hr { border: 0; border-top: 1px solid #e1e0d9; margin: 14pt 0; }
strong { font-weight: 600; }
a { color: #1c5cab; text-decoration: none; word-break: break-all; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0 12pt; font-size: 9pt; break-inside: auto; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { text-align: left; font-weight: 600; color: #0b0b0b; border-bottom: 1.5px solid #c3c2b7; padding: 4pt 6pt; background: #f4f4f1; vertical-align: bottom; }
td { border-bottom: 1px solid #e1e0d9; padding: 4pt 6pt; vertical-align: top; }
td:first-child { font-weight: 500; }
code { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 8.6pt; background: #f4f4f1; padding: 0 3pt; border-radius: 3px; }
pre { background: #f4f4f1; border: 1px solid #e1e0d9; border-radius: 4px; padding: 8pt 10pt; font-size: 8.2pt; line-height: 1.4; white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: inherit; }
figure { margin: 12pt 0 14pt; break-inside: avoid; text-align: center; }
figure img { max-width: 100%; height: auto; }
figcaption { font-size: 8.8pt; color: #52514e; text-align: left; margin-top: 4pt; line-height: 1.35; }
blockquote { margin: 8pt 0; padding: 6pt 12pt; border-left: 3px solid #c3c2b7; color: #52514e; }
.sources li { font-size: 9pt; margin: 3pt 0; }
"""


LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+")

def normalize_lists(text: str) -> str:
    """Python-Markdown (a diferencia de GFM) necesita una línea en blanco antes de una lista que sigue a un párrafo,
    y 4 espacios de sangría para anidar. Normaliza sin alterar el contenido."""
    out, in_fence, prev = [], False, ""
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence; out.append(line); prev = line; continue
        if not in_fence:
            m = LIST_RE.match(line)
            if m:
                indent = m.group(1)
                if indent and len(indent) < 4:
                    line = "    " + line[len(indent):]
                elif not indent and prev.strip() and not LIST_RE.match(prev) and not prev.startswith("    "):
                    out.append("")
        out.append(line); prev = line
    return "\n".join(out)

def embed_figures(html: str) -> str:
    """Sustituye <p><img ...></p> por <figure> con la imagen en base64 y el alt como pie."""
    def rep(m):
        src, alt = m.group(1), m.group(2)
        p = ROOT / src
        data = base64.b64encode(p.read_bytes()).decode()
        return f'<figure><img src="data:image/png;base64,{data}" alt="{alt}"><figcaption>{alt}</figcaption></figure>'
    return re.sub(r'<p><img alt="([^"]*)" src="([^"]+)"\s*/?></p>', lambda m: rep(type("M", (), {"group": lambda self, i: (m.group(2), m.group(1))[i - 1]})()), html)

def main():
    text = MD.read_text(encoding="utf-8")
    # Separa cabecera (título + metadatos hasta la primera regla horizontal) del cuerpo
    head, _, body = text.partition("\n---\n")
    title = re.search(r"^# (.+)$", head, re.M).group(1)
    meta = re.findall(r"^\*\*(.+?):\*\* (.+)$", head, re.M)
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
                           extension_configs={"toc": {"toc_depth": "2-3", "title": "Índice"}})
    body_html = md.convert(normalize_lists(body))
    body_html = embed_figures(body_html)
    for anchor in ('id="0-resumen-ejecutivo"', 'id="apendice-b-', 'id="apendice-c-'):
        body_html = re.sub(r'<h2 ' + re.escape(anchor), '<h2 class="flow" ' + anchor, body_html)
    # Apéndice de fuentes con letra menor
    body_html = body_html.replace('<h2 id="apendice-d-fuentes-principales">', '<h2 class="sources-h" id="apendice-d-fuentes-principales">')
    body_html = re.sub(r'(<h2 class="sources-h".*?</h2>)(.*)$', lambda m: m.group(1) + '<div class="sources">' + m.group(2) + '</div>', body_html, flags=re.S)
    meta_html = "".join(f'<div class="meta"><strong>{k}:</strong> {markdown.markdown(v)[3:-4]}</div>' for k, v in meta)
    warn = ("Documento de trabajo. Nada de lo que contiene es asesoramiento financiero ni una promesa de rentabilidad. "
            "Los gráficos ilustran cifras de las fuentes citadas; ninguno es resultado de un backtest propio.")
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{title}</title><style>{CSS}</style></head>
<body>
<div class="cover"><h1>{title}</h1>{meta_html}<div class="warn">{warn}</div></div>
<div class="toc">{md.toc}</div>
{body_html}
</body></html>"""
    out_html = ROOT / "tools" / "_build.html"
    out_html.write_text(html, encoding="utf-8")
    PDF.unlink(missing_ok=True)
    tmp = tempfile.mkdtemp(prefix="chrome-pdf-")
    if True:
        cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run", "--no-default-browser-check",
               "--disable-background-networking", "--disable-component-update", "--no-pdf-header-footer",
               f"--user-data-dir={tmp}", f"--print-to-pdf={PDF}", out_html.as_uri()]
        # Chrome deja procesos auxiliares vivos y no termina solo: esperamos a que el PDF exista y su tamaño se estabilice.
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        last, stable, t0 = -1, 0, time.time()
        while time.time() - t0 < 150:
            time.sleep(1)
            size = PDF.stat().st_size if PDF.exists() else -1
            stable = stable + 1 if (size > 0 and size == last) else 0
            last = size
            if stable >= 3 or proc.poll() is not None: break
        try: os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        time.sleep(1); shutil.rmtree(tmp, ignore_errors=True)
    if not PDF.exists():
        sys.exit("Chrome no generó el PDF")
    print("PDF:", PDF, f"{PDF.stat().st_size/1024:.0f} KB")

if __name__ == "__main__":
    main()
