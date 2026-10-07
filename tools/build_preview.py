"""Build a read-only synthetic offline rendering preview; no network or training."""
from pathlib import Path
import json
import base64
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from workspace import Workspace

html = (ROOT / 'static/index.html').read_text()
css = (ROOT / 'static/style.css').read_text()
font_css = (ROOT / 'static/fonts.css').read_text()
# Embed the same official files: the single-file offline artifact makes no requests.
font_css = re.sub(r'url\("(/fonts/[^"]+)"\)', lambda m: 'url("data:font/woff2;base64,' + base64.b64encode((ROOT / 'static' / m[1].lstrip('/')).read_bytes()).decode('ascii') + '")', font_css)
font_licenses = '\n\n'.join('\n'.join(line.rstrip() for line in p.read_text().splitlines()) for p in sorted((ROOT / 'static/fonts').rglob('*.txt')))
theme_js = (ROOT / 'static/theme.js').read_text()
js = (ROOT / 'static/app.js').read_text()
hf_js = (ROOT / 'static/huggingface.js').read_text()
training_js = (ROOT / 'static/training.js').read_text()
builder_js = (ROOT / 'static/builder.js').read_text()
i18n_js = (ROOT / 'static/i18n.js').read_text()
workspace_js = (ROOT / 'static/workspace.js').read_text()
fixture = json.loads((ROOT / 'docs/sample-snapshot.json').read_text())
fixture['ui_fixture'] = {'id':'offline-demo', 'label':'UI DEMO / SYNTHETIC FIXTURE / 성능·임상·실장비 검증 아님'}
workspace = Workspace(':memory:', clock=lambda: 1767225600)
text = '\n'.join(json.dumps({'instruction': f'Synthetic example {i}', 'output': f'Synthetic response {i}'}) for i in range(3))
dataset = workspace.import_dataset({'name': 'Synthetic preview data', 'kind': 'LLM', 'text': text, 'synthetic': True})['dataset']
workspace.split_dataset(dataset['id'], {'seed': 42, 'val_ratio': 0.2})
settings = {'configured': {'lan_access': True, 'remote_view': True, 'remote_control': True},
            'effective': {'lan_access': False, 'remote_view': False, 'remote_control': False},
            'bootstrap_required': False, 'listener_lan': False, 'tls': False}
routes = {'/api/status': fixture, '/api/workspace': workspace.summary(), '/api/presets': workspace.presets(),
          '/api/huggingface/account': {'connected':False,'username':None},
          '/api/huggingface/models': {'models':[], 'next_cursor':None},
          '/api/huggingface/download': {'status':'idle'},
          '/api/training': {'available': False, 'models': [], 'message': 'Offline preview: no real GPU worker'},
          '/api/auth/status': {'authenticated': True, 'username': 'offline-preview', 'must_change_password': False,
                               'csrf_token': None, 'local_peer': True, 'settings': settings},
          '/api/diagnostics': {'python': {'version': 'Offline snapshot'}, 'os': {'name': 'Read-only preview'},
                               'disk': {'available': False}, 'gpu': {'detected': False, 'message': 'No live probe in this preview'},
                               'warnings': ['Offline rendering preview, not live environment diagnostics.']},
          f"/api/datasets/{dataset['id']}": {'dataset': workspace.get_dataset(dataset['id'])}}
workspace.close()
start = js.index('async function api(')
end = js.index('function setConnection(', start)
js = js[:start] + '''async function api(path, body) {
  if (body !== undefined) throw new Error('Offline preview is read-only. Run python server.py for working demo/preparation controls.');
  return structuredClone(OFFLINE_ROUTES[path] || {});
}
''' + js[end:]
js = 'const OFFLINE_ROUTES=' + json.dumps(routes, ensure_ascii=False).replace('<', '\\u003c') + ';\n' + js
js = js.replace("'Demo API online'", "'Offline preview'").replace('t("Demo API online")', 't("Offline preview")')
html = html.replace('<script src="/theme.js"></script>', '<script>' + theme_js + '</script>')
html = html.replace('<link rel="stylesheet" href="/fonts.css">', '<!-- Bundled font licenses\n' + font_licenses + '\n--><style>' + font_css + '</style>')
html = html.replace('<link rel="stylesheet" href="/style.css">', '<style>' + css + '</style>')
html = html.replace('<script src="/i18n.js" defer></script>', '').replace('<script src="/app.js" defer></script>', '').replace('<script src="/workspace.js" defer></script>', '').replace('<script src="/training.js" defer></script>', '').replace('<script src="/huggingface.js" defer></script>', '').replace('<script src="/builder.js" defer></script>', '')
html = html.replace('All runs, charts and GPU readings are synthetic. No training GPU is connected and no model is downloaded.',
                    'READ-ONLY OFFLINE PREVIEW. Synthetic fixture data; no live API, GPU, training or downloads. Controls require the local server.')
html = html.replace('<body>', '<body><div class="fixture-watermark" role="note">UI DEMO / SYNTHETIC FIXTURE / 성능·임상·실장비 검증 아님 · read-only offline preview</div>')
html = html.replace('</body>', '<script>' + i18n_js + '\n' + js + '\n' + workspace_js + '\n' + hf_js + '\n' + training_js + '\n' + builder_js + '''
document.addEventListener('click', event => {
 const link = event.target.closest('a[href^="/api/"]');
 if(link) { event.preventDefault(); toast('Downloads require the running local server'); }
});
</script></body>''')
(ROOT / 'docs/offline-preview.html').write_text(html)
print('Built docs/offline-preview.html (read-only synthetic rendering preview)')
