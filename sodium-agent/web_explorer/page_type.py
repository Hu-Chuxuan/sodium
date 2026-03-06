from .static_explorer import get_static_content
from utils.dynamic_explorer_tools import _get_visible_text
from utils.lib import parse_result_from_content
from utils.prompt import CHECK_SD
from utils.log import document_func_call
from utils.dynamic_explorer_tools import load_page

def decide_sd(url, query, primary_key, primary_key_val, col, given_info, client, log_file):
    base_url = None
    webpage_content = get_static_content(url)
    sess = load_page(url)
    page = sess.page
    base_url = page.url
    try:
        observation = _get_visible_text(page)
        sess.close()
    except:
        sess.close()
        return True, base_url
        
    prompt = CHECK_SD.format(
        webpage_content=webpage_content,
        observation=observation,
        query=query,
        primary_key=primary_key, 
        primary_key_val=primary_key_val, 
        given_info=given_info,
        col=col
    )
    response = client.responses.create(
        model="gpt-5",
        reasoning={"effort": "high"},
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt}
                ],
            }
        ],
    )

    print(response.output_text)
    document_func_call(log_file, "decide_sd", response, prompt, {"base_url": base_url})

    if parse_result_from_content(response.output_text, 'res') == 1:
        return True, base_url
    else:
        return False, base_url


def is_document_url(url: str) -> bool:
    url = url.lower()
    return (
        "/document/" in url
        or url.endswith(".pdf")
        or url.endswith(".doc")
        or url.endswith(".docx")
        or url.endswith(".xls")
        or url.endswith(".xlsx")
        or url.endswith(".zip")
        or url.endswith(".csv")
        or url.endswith("/download/")
        or url.endswith("/download")
    )