# Bundled official webfonts

Downloaded 2026-10-07. All binaries are unmodified official files. Runtime requests are same-origin only; no CDN and no font preloads. Each family retains its upstream SIL Open Font License 1.1 file in this directory. No fourth body font is bundled.

| Family / release | Official source path | File / registration |
| --- | --- | --- |
| Pretendard v1.3.9 | https://github.com/orioncactus/pretendard/blob/v1.3.9/packages/pretendard/dist/web/variable/woff2/PretendardVariable.woff2 | pretendard/PretendardVariable.woff2; UI CSS range 100–900 |
| Space Grotesk 2.0.0 | https://github.com/floriankarsten/space-grotesk/blob/2.0.0/fonts/woff2/SpaceGrotesk%5Bwght%5D.woff2 | space-grotesk/SpaceGrotesk-Variable.woff2; 300–700 |
| JetBrains Mono v2.304 | https://github.com/JetBrains/JetBrainsMono/tree/v2.304/fonts/webfonts | jetbrains-mono/JetBrainsMono-Regular.woff2 (400), JetBrainsMono-Medium.woff2 (500) |

Pinned release tree commits: Pretendard `5c41199ea0024a9e0b2cb31735265056e5472d76`, Space Grotesk `7220f5d04813fe83babe76d4fd23e02275021280`, JetBrains Mono `cd5227bd1f61dff3bbd6c814ceaf7ffd95e947d9`.

FontTools decoded the actual WOFF2 files. Pretendard name-table version is **1.309** (release v1.3.9), physical `wght` axis **45–930**, default 400; the CSS deliberately exposes the standard UI 100–900 range within that supported axis. Space Grotesk is version 2.000, `wght` 300–700, default 300. JetBrains Mono is version 2.304, static 400/500. UI uses 400/500/600; 650/750 declarations were normalized to 600. Pretendard's full variable WOFF2 is 2,057,688 bytes; this avoids changing official Korean subset mappings and makes one local request. There are no unicode-range rewrites or generated subsets. Total font binary size: 2,292,932 bytes.

`../fonts.css` defines normal faces with `font-display: swap`. `../style.css` defines `--font-ui`, `--font-display`, `--font-mono`. The last token falls back to Pretendard for Hangul before a fixed-pitch system fallback; Korean logs are not assumed to be monospaced.

See `../../docs/ui-redesign/typography/font-metadata.json` for byte sizes, SHA-256 and decoded axes, and `../../docs/ui-redesign/typography/README.md` for usage and verification. The offline builder embeds these same bytes and the license texts in its standalone HTML. Do not replace these files with CDN links, broaden CSP, or serve anything outside the existing public static root.
