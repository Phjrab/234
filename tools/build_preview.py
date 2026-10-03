"""Build a read-only, synthetic offline rendering preview. No network calls."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
html = (ROOT / 'static/index.html').read_text()
css = (ROOT / 'static/style.css').read_text()
js = (ROOT / 'static/app.js').read_text()
fixture = json.loads((ROOT / 'docs/sample-snapshot.json').read_text())
start = js.index('async function api(')
end = js.index('function setConnection(', start)
js = js[:start] + '''async function api(path, body) {
  if (body !== undefined) throw new Error('Offline preview is read-only. Run python server.py for working demo controls.');
  return structuredClone(OFFLINE_FIXTURE);
}
''' + js[end:]
js = 'const OFFLINE_FIXTURE=' + json.dumps(fixture,ensure_ascii=False).replace('<','\\u003c') + ';\n' + js
js = js.replace("'Demo API online'", "'Offline preview'")
html = html.replace('<link rel="stylesheet" href="/style.css">', '<style>' + css + '</style>')
html = html.replace('<script src="/app.js" defer></script>', '')
html = html.replace('All runs, charts and GPU readings are synthetic. No GPU is connected and no model is downloaded.', 'READ-ONLY OFFLINE PREVIEW. Synthetic data; no API, GPU, training or downloads. Run python server.py for working controls.')
html = html.replace('</body>', '<script>' + js + '</script></body>')
(ROOT / 'docs/offline-preview.html').write_text(html)
print('Built docs/offline-preview.html (read-only synthetic rendering preview)')
