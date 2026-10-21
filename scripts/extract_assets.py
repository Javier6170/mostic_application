#!/usr/bin/env python3
"""Extract base64 payloads from Mostic HTML into external files and rewrite references."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "Mostic_COMPLETA_CONOCENOS.html"
OUT = ROOT / "index.html"
IMG_DIR = ROOT / "assets" / "img"
PDF_DIR = ROOT / "assets" / "pdf"
GAMES_DIR = ROOT / "games"

EXT_MAP = {
    "image/webp": "webp",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/svg+xml": "svg",
    "application/pdf": "pdf",
}

GAME_FILES = {
    "mstConjuntosGameB64": "conjuntos.html",
    "mstSupermercadoGameB64": "supermercado.html",
    "mstRestauranteGameB64": "restaurante.html",
    "mstJugueteriaGameB64": "jugueteria.html",
    "mstSelvaGameB64": "selva.html",
}


def decode_b64(s: str) -> bytes:
    # JSON often escapes / as \/ inside string payloads.
    s = s.replace("\\/", "/")
    s = re.sub(r"\s+", "", s)
    pad = (-len(s)) % 4
    if pad == 3:
        raise ValueError(f"invalid base64 length {len(s)}")
    if pad:
        s += "=" * pad
    return base64.b64decode(s, validate=False)


def replace_function(src: str, header: str, new_body: str) -> str:
    start = src.find(header)
    if start < 0:
        raise SystemExit(f"Function header not found: {header}")
    brace = src.find("{", start)
    if brace < 0:
        raise SystemExit(f"No opening brace for: {header}")
    depth = 0
    i = brace
    in_str = None
    escape = False
    while i < len(src):
        ch = src[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
        else:
            if ch in ("'", '"', "`"):
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return src[:start] + new_body + src[i + 1 :]
        i += 1
    raise SystemExit(f"Unbalanced braces for: {header}")


def extract_assign(text: str, name: str):
    for q in ('"', "'"):
        m = re.search(
            rf"(?:const|let|var)\s+{name}\s*=\s*{q}([^{q}]*){q}",
            text,
            re.DOTALL,
        )
        if m:
            return m
    return None


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Missing source: {SRC}")

    for d in (IMG_DIR, PDF_DIR, GAMES_DIR):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    text = SRC.read_text(encoding="utf-8", errors="ignore")
    print(f"loaded {len(text) / 1e6:.2f} MB")

    hash_to_rel: dict[str, str] = {}

    def store(data: bytes, ext: str, preferred: str | None = None) -> str:
        digest = hashlib.sha1(data).hexdigest()
        if digest in hash_to_rel:
            return hash_to_rel[digest]
        out_dir = PDF_DIR if ext == "pdf" else IMG_DIR
        rel_prefix = "assets/pdf" if ext == "pdf" else "assets/img"
        name = preferred or f"asset_{digest[:12]}.{ext}"
        candidate = name
        n = 1
        while (out_dir / candidate).exists():
            existing = (out_dir / candidate).read_bytes()
            if existing == data:
                rel = f"{rel_prefix}/{candidate}"
                hash_to_rel[digest] = rel
                return rel
            stem, e = Path(name).stem, Path(name).suffix
            candidate = f"{stem}_{n}{e}"
            n += 1
        (out_dir / candidate).write_bytes(data)
        rel = f"{rel_prefix}/{candidate}"
        hash_to_rel[digest] = rel
        return rel

    # --- 1) Pull out huge base64 consts FIRST (avoids false URI matches inside them) ---
    for var, fname in GAME_FILES.items():
        m = extract_assign(text, var)
        if not m:
            raise SystemExit(f"Missing game var {var}")
        raw = decode_b64(m.group(1)).decode("utf-8", errors="replace")
        (GAMES_DIR / fname).write_text(raw, encoding="utf-8")
        text = text[: m.start()] + text[m.end() :]
        print(f"game {var} -> games/{fname} ({len(raw)} bytes)")

    text = text.replace(
        "get htmlB64(){return mstSelvaGameB64}",
        'path:"games/selva.html"',
    )
    text = text.replace("htmlB64:mstConjuntosGameB64", 'path:"games/conjuntos.html"')
    text = text.replace(
        "htmlB64:mstSupermercadoGameB64", 'path:"games/supermercado.html"'
    )
    text = text.replace(
        "htmlB64:mstRestauranteGameB64", 'path:"games/restaurante.html"'
    )
    text = text.replace(
        "htmlB64:mstJugueteriaGameB64", 'path:"games/jugueteria.html"'
    )

    m = extract_assign(text, "circusCardsPdfBase64")
    if not m:
        raise SystemExit("Missing circusCardsPdfBase64")
    rel = store(decode_b64(m.group(1)), "pdf", "circus-cards.pdf")
    text = text[: m.start()] + f'const circusCardsPdfPath="{rel}"' + text[m.end() :]
    print("circus", rel)

    m = extract_assign(text, "mstSequencePdfBase64")
    if not m:
        raise SystemExit("Missing mstSequencePdfBase64")
    rel = store(decode_b64(m.group(1)), "pdf", "secuencias-selva.pdf")
    text = text[: m.start()] + f'const mstSequencePdfPath="{rel}"' + text[m.end() :]
    print("sequence", rel)

    m = re.search(
        r"(?:const|let|var)\s+mstRestaurantPdfBase64\s*=\s*(\{.*?\})\s*;",
        text,
        re.DOTALL,
    )
    if not m:
        raise SystemExit("Missing mstRestaurantPdfBase64")
    restaurant = {}
    for key, b64 in re.findall(r'"([^"]+)":"([A-Za-z0-9+/=]+)"', m.group(1)):
        restaurant[key] = store(decode_b64(b64), "pdf", f"restaurante-{key}.pdf")
        print("restaurant", key, restaurant[key])
    text = (
        text[: m.start()]
        + "const mstRestaurantPdfPaths="
        + json.dumps(restaurant, ensure_ascii=False)
        + text[m.end() :]
    )

    m = re.search(
        r"(?:const|let|var)\s+mstToyAssetBase64\s*=\s*(\{.*?\})\s*;",
        text,
        re.DOTALL,
    )
    if not m:
        raise SystemExit("Missing mstToyAssetBase64")
    toys = {}
    for key, b64 in re.findall(r'"([^"]+)":"([A-Za-z0-9+/=]+)"', m.group(1)):
        data = decode_b64(b64)
        ext = "png" if data.startswith(b"\x89PNG\r\n\x1a\n") else "bin"
        toys[key] = store(data, ext, f"toy-{key}.{ext}")
        print("toy", key, toys[key])
    text = (
        text[: m.start()]
        + "const mstToyAssetPaths="
        + json.dumps(toys, ensure_ascii=False)
        + text[m.end() :]
    )

    # --- 2) data: URIs (plain, then JSON-escaped with \/ inside payload) ---
    def repl_uri(m: re.Match[str]) -> str:
        mime = m.group(1).replace("\\/", "/")
        b64 = m.group(2)
        ext = EXT_MAP.get(mime, "bin")
        data = decode_b64(b64)
        preferred = None
        if mime == "application/pdf":
            preferred = f"embedded_{hashlib.sha1(data).hexdigest()[:8]}.pdf"
        return store(data, ext, preferred)

    plain_re = re.compile(
        r"data:(image/[\w.+-]+|application/pdf);base64,([A-Za-z0-9+/=]+)"
    )
    text, n_plain = plain_re.subn(repl_uri, text)

    # In JSON.parse("..."), slashes may appear as \/ even inside base64.
    esc_re = re.compile(
        r"data:(image\\/[\w.+-]+|application\\/pdf);base64,((?:[A-Za-z0-9+/=]|\\/)+)"
    )
    text, n_esc = esc_re.subn(repl_uri, text)
    print(
        f"replaced data URIs: plain={n_plain} escaped={n_esc}; "
        f"unique files={len(hash_to_rel)}"
    )

    # --- 3) Helpers + download / game open rewrites ---
    helpers = """
async function mstFetchBlob(path, mime){
  const res = await fetch(path);
  if(!res.ok) throw new Error('No se pudo cargar '+path);
  const buf = await res.arrayBuffer();
  return new Blob([buf], {type: mime || res.headers.get('content-type') || 'application/octet-stream'});
}
function mstTriggerDownload(blob, filename){
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.rel = 'noopener';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(url), 3000);
}
"""
    anchor = "function mstDownloadCircusCards()"
    idx = text.find(anchor)
    if idx < 0:
        raise SystemExit("mstDownloadCircusCards not found")
    text = text[:idx] + helpers + text[idx:]

    text = replace_function(
        text,
        "function mstDownloadCircusCards()",
        """function mstDownloadCircusCards() {
  mstFetchBlob(circusCardsPdfPath, 'application/pdf')
    .then(blob => mstTriggerDownload(blob, 'Mostic_tarjetas_caja_magica_letra_T.pdf'))
    .catch(error => {
      console.error('No fue posible descargar las tarjetas', error);
      alert('No se pudo iniciar la descarga. Abre el sitio con un servidor local (no file://).');
    });
}""",
    )
    text = replace_function(
        text,
        "function mstDownloadSequencePdf()",
        """async function mstDownloadSequencePdf(){
 try{
  const blob = await mstFetchBlob(mstSequencePdfPath, 'application/pdf');
  mstTriggerDownload(blob, 'Mostic_exploradores_secuencias_tarjetas.pdf');
 }catch(error){console.error('No fue posible descargar el PDF',error);alert('No se pudo descargar este PDF. Abre el sitio con un servidor local.');}
}""",
    )
    text = replace_function(
        text,
        "function mstDownloadRestaurantPdf(type)",
        """async function mstDownloadRestaurantPdf(type){
 const path=mstRestaurantPdfPaths[type];if(!path)return;
 try{
  const blob=await mstFetchBlob(path,'application/pdf');
  mstTriggerDownload(blob, type==='menu'?'Mostic_menu_letra_R_para_imprimir.pdf':'Mostic_ultima_mision_restaurante_R.pdf');
 }catch(error){console.error(error);alert('No se pudo descargar este PDF.');}
}""",
    )
    text = replace_function(
        text,
        "function mstDownloadToyAsset(type)",
        """async function mstDownloadToyAsset(type){
 const path=mstToyAssetPaths[type]; if(!path) return;
 try{
  const mime=type==='toyPrintablePng'?'image/png':'application/octet-stream';
  const name=type==='toyPrintablePng'?'Mostic_imprimible_jugueteria_tamanos.png':'Mostic_recurso';
  const blob=await mstFetchBlob(path, mime);
  mstTriggerDownload(blob, name);
 }catch(error){console.error(error);alert('No se pudo descargar el archivo.');}
}""",
    )

    text = text.replace(
        "function mstDecodeB64Html(b64){const bytes=Uint8Array.from(atob(b64),ch=>ch.charCodeAt(0));return new TextDecoder('utf-8').decode(bytes);}\n",
        "",
    )
    text = text.replace(
        "frame.srcdoc=mstDecodeB64Html(game.htmlB64);",
        "frame.src=game.path;",
    )
    text = text.replace(
        "const frame=overlay.querySelector('iframe');if(frame)frame.srcdoc='';",
        "const frame=overlay.querySelector('iframe');if(frame)frame.src='about:blank';",
    )

    text = re.sub(r"\n{3,}", "\n\n", text)

    leftovers = {
        "data:image": text.count("data:image"),
        "GameB64": len(re.findall(r"GameB64", text)),
        "PdfBase64": len(re.findall(r"PdfBase64", text)),
        "ToyAssetBase64": text.count("ToyAssetBase64"),
        "htmlB64": text.count("htmlB64"),
        "atob(": text.count("atob("),
        "mstDecodeB64Html": text.count("mstDecodeB64Html"),
    }
    print("leftovers:", leftovers)

    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")
    print(
        f"files: img={len(list(IMG_DIR.iterdir()))} "
        f"pdf={len(list(PDF_DIR.iterdir()))} "
        f"games={len(list(GAMES_DIR.iterdir()))}"
    )

    if leftovers["data:image"] == 0 and leftovers["GameB64"] == 0:
        SRC.unlink(missing_ok=True)
        print(f"removed bulky source {SRC.name}")
    else:
        print("kept source HTML because some payloads remain; inspect leftovers")


if __name__ == "__main__":
    main()
