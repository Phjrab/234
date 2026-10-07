"""Generate fixture-only glyph probes from official font advances (optional FontTools).

Run with a disposable environment containing fonttools and brotli. No training,
network or application data. FixtureHandler serves only these two exact files.
"""
from pathlib import Path
import html
import json
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/ui-redesign/typography'
font_paths = {'ui': 'pretendard/PretendardVariable.woff2',
              'display': 'space-grotesk/SpaceGrotesk-Variable.woff2',
              'mono': 'jetbrains-mono/JetBrainsMono-Regular.woff2',
              'mono500': 'jetbrains-mono/JetBrainsMono-Medium.woff2'}
fonts = {role: TTFont(ROOT / 'static/fonts' / path) for role, path in font_paths.items()}
fonts['display'] = instantiateVariableFont(fonts['display'], {'wght': 600}, inplace=False)
samples = [('display',28,600,'FORGE'),('display',28,600,'Training Workbench'),
           ('ui',26,600,'학습 설정'),('ui',14,400,'체크포인트 저장 후 일시정지'),
           ('ui',12,400,'Train Loss / Eval Loss'),('mono500',22,500,'2.0e-4'),
           ('mono500',14,500,'120 / 800'),('mono',13,400,'checkpoint-000120'),
           ('mono',13,400,'Qwen/Qwen2.5-0.5B-Instruct'),('mono',14,400,'0 O 1 I l'),
           ('mono',13,400,'한글 로그: 체크포인트 저장 후 일시정지')]
rows = []
for index, (role,size,weight,text) in enumerate(samples):
    font = fonts[role]
    if role == 'ui' and weight != 400:
        font = instantiateVariableFont(font, {'wght': weight}, inplace=False)
    width = 0
    fallbacks = []
    for char in text:
        face = font
        if ord(char) not in face.getBestCmap():
            face = fonts['ui']; fallbacks.append(char)
        glyph = face.getBestCmap()[ord(char)]
        width += face['hmtx'][glyph][0] / face['head'].unitsPerEm * size
    rows.append({'id':f'probe-{index}', 'role':role,'size':size,'weight':weight,
                 'text':text,'expected_px':width,'pretendard_fallback':''.join(fallbacks)})
body = ''.join(f'<section><small>{r["role"]} · {r["size"]}px / {r["weight"]}</small><p><span id="{r["id"]}" data-expected="{r["expected_px"]}" style="font-family:var(--font-{r["role"].replace("500","")});font-size:{r["size"]}px;font-weight:{r["weight"]}">{html.escape(r["text"])}</span></p><p><span id="fallback-{i}" class="fallback" style="font-family:{"ui-monospace,monospace" if r["role"].startswith("mono") else "system-ui"};font-size:{r["size"]}px;font-weight:{r["weight"]}">{html.escape(r["text"])}</span> <small>system fallback comparison only</small></p></section>' for i,r in enumerate(rows))
OUT.mkdir(exist_ok=True)
(OUT/'proof.html').write_text('''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FORGE typography proof — fixture only</title><link rel="stylesheet" href="/fonts.css"><link rel="stylesheet" href="/style.css"><style>body{padding:24px}section{border-bottom:1px solid var(--border);margin-bottom:12px}section p{margin:4px 0}section span{white-space:pre;font-kerning:none;font-feature-settings:"kern" 0;font-variant-ligatures:none;letter-spacing:0}.fallback{color:var(--muted)}pre{font-size:13px}h1{font-size:26px}</style><script src="/__fixture__/typography-proof.js" defer></script></head><body><h1>Typography proof · UI 검증 전용</h1><p>All strings are glyph probes, not experiment metrics. System rows are diagnostic comparisons only. 한글 mono fallback은 Pretendard이며 고정폭을 가정하지 않습니다.</p>'''+body+'<h2>FontFaceSet / requests / rendered glyph advance comparison</h2><pre id="font-evidence">Loading fonts…</pre></body></html>')
(OUT/'expected-glyphs.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print('Built fixture-only typography proof and expected glyph advances')
