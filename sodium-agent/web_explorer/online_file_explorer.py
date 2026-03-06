from pathlib import Path
from urllib.parse import urlparse
import requests

from utils.prompt import CHECK_IMAGE
from utils.lib import (
    parse_result_from_content,
    url_to_hash,
    image_to_data_url
)
from utils.log import document_func_call


def _guess_ext_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in (".pdf", ".png", ".jpg", ".jpeg", ".webp"):
        if path.endswith(ext):
            return ext
    return ""


def _download_to(url: str, out_path: Path, timeout: int = 60) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    r = requests.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True)
    r.raise_for_status()
    ct = (r.headers.get("content-type", "") or "").lower()
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 256):
            if chunk:
                f.write(chunk)
    return ct


def _render_pdf_page_to_png(pdf_path: Path, page_idx: int, png_path: Path, scale: float = 2.0) -> int:
    """
    Render one page of a PDF to PNG.
    Returns total page count.
    Requires `pymupdf` (fitz): pip install pymupdf
    """
    import fitz

    doc = fitz.open(pdf_path)
    n = doc.page_count
    if n == 0:
        doc.close()
        raise RuntimeError("Empty PDF")
    if page_idx < 0 or page_idx >= n:
        doc.close()
        raise IndexError(f"page_idx {page_idx} out of range (0..{n-1})")

    page = doc.load_page(page_idx)
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    pix.save(str(png_path))
    doc.close()
    return n


def inspect_file(
    url: str,
    query: str,
    primary_key: str,
    primary_key_val: str,
    col: str,
    client,
    given_info: dict,
    log_file,
    max_pdf_pages: int = 20, 
    pdf_scale: float = 2.0,
):

    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    base = url_to_hash(url)
    ext = _guess_ext_from_url(url)

    downloaded_path = None

    try:

        if ext in (".png", ".jpg", ".jpeg", ".webp"):
            downloaded_path = log_dir / f"{base}{ext}"
            ct = _download_to(url, downloaded_path)

            image_url = image_to_data_url(downloaded_path)

            prompt = CHECK_IMAGE.format(
                query=query,
                primary_key=primary_key,
                primary_key_val=primary_key_val,
                col=col,
                given_info=given_info,
            )

            response = client.responses.create(
                model="gpt-5",
                reasoning={"effort": "high"},
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {"type": "input_image", "image_url": image_url, "detail": "high"},
                        ],
                    }
                ],
            )

            result = parse_result_from_content(response.output_text, "res")

            if isinstance(result, dict):
                for key, val in result.items():
                    if key == col or key in given_info:
                        given_info[key] = val

            document_func_call(
                log_file,
                "inspect_file",
                response,
                prompt,
                {
                    "downloaded_path": str(downloaded_path),
                }
            )
            return given_info

        # -------------------- PDFs --------------------
        elif ext == ".pdf" :
            downloaded_path = log_dir / f"{base}.pdf"
            ct = _download_to(url, downloaded_path)

            prompt = CHECK_IMAGE.format(
                query=query,
                primary_key=primary_key,
                primary_key_val=primary_key_val,
                col=col,
                given_info=given_info,
            )

            # iterate pages
            total_pages = None
            for page_idx in range(max_pdf_pages):
                png_path = log_dir / f"{base}_p{page_idx+1}.png"  # 1-based in filename
                try:
                    total_pages = _render_pdf_page_to_png(downloaded_path, page_idx, png_path, scale=pdf_scale)
                except IndexError:
                    break  # ran out of pages

                image_url = image_to_data_url(png_path)

                response = client.responses.create(
                    model="gpt-5",
                    reasoning={"effort": "high"},
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": prompt + f"\n\n[PDF page {page_idx+1} of ?]"},
                                {"type": "input_image", "image_url": image_url, "detail": "high"},
                            ],
                        }
                    ],
                )

                result = parse_result_from_content(response.output_text, "res")

                document_func_call(
                    log_file,
                    "inspect_file",
                    response,
                    prompt,
                    {
                        "page_idx": page_idx,
                        "rendered_png": str(png_path),
                        "downloaded_path": str(downloaded_path),
                    },
                )

                if isinstance(result, dict):
                    for key, val in result.items():
                        if key == col or key in given_info:
                            given_info[key] = val
                    return given_info

                if result == -1:
                    return given_info
                continue
            return given_info
        else:
            return given_info

    except Exception as e:
        return given_info
