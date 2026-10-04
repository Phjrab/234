# Hugging Face API

All routes require dashboard authentication. Reads require viewing permission; mutations require control permission, a same-origin Origin and CSRF token. No arbitrary URLs, paths or commands are accepted.

| Route | Function |
|---|---|
| `GET /api/huggingface/account` | Connected flag and username; never the token |
| `POST /api/huggingface/connect` | Validate `{token}` with official `whoami-v2`; store a private server copy |
| `POST /api/huggingface/disconnect` | Empty body; remove the copy when no download is active |
| `GET /api/huggingface/models` | Paginated Hub catalog: search, author, kind ALL/LLM/VLM, family, sort and cursor |
| `GET /api/huggingface/model?id=publisher/model` | Revision, task/type, architecture family, size, license, access, installed status and training limitations |
| `GET /api/huggingface/avatar?author=publisher` | Official bounded raster publisher icon, proxied without token |
| `POST /api/huggingface/download` | `{model, revision}`; explicit background safe-asset download at the displayed commit |
| `GET /api/huggingface/download` | Current/last status, byte progress and sanitized outcome |
| `POST /api/huggingface/download/cancel` | Empty body; terminate the owned downloader |

The list uses the official task/config metadata, not repository name guesses. Non-generative and unclassified models remain selectable and display their limitations. The VLM filter uses the Hub `image-text-to-text` task; older image-to-text/VQA repositories can also be found with All or an exact repository ID. Family filtering uses the corresponding Hub tag. Publisher grouping is based on the repository owner, who may be a community publisher rather than the original model company.

Hub search is paginated with 30 results per request. The next cursor is extracted only from official Hub response links; the browser never supplies a remote URL. Selecting a repository does not download or start training. Installing requires compatible LLM/VLM metadata, safetensors and sufficient disk space for the listed assets plus 2 GiB. Downloaded bytes include incomplete Hub files and may temporarily include cache metadata. One download runs at a time; cancellation retains partial files for a retry. A service interruption marks the download failed and requires an explicit retry.

The catalog describes potential compatibility. GPU training checks the downloaded model, tokenizer, image processor, dataset and actual memory. Remote Python code, pickle weights, arbitrary commands and arbitrary filesystem paths are not supported. Newly installed models are discovered from private revision-pinned manifests without expanding a hardcoded repository allowlist.

Account connection is a personal access token flow, with an official sign-in/token page link in Settings. It does not use an OAuth callback. Gated models also require the publisher's access approval. Disconnect removes the local token copy; actual token revocation is performed at Hugging Face.
