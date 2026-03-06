from .dynamic_explorer import inspect_dynamic
from .static_explorer import inspect_static
from .online_file_explorer import inspect_file
from .page_type import decide_sd, is_document_url


def inspect_page(url, log_file, query, primary_key, primary_key_val, col, given_info, client):
    if is_document_url(url):
        return inspect_file(url, query, primary_key, primary_key_val, col, client, given_info, log_file), [], True, None, {}, True
    url_type = decide_sd(url, query, primary_key, primary_key_val, col, given_info, client, log_file)
    if url_type:
        given_info, next_level_links, proceed, source_url, path_record_level = inspect_static(url, query, primary_key, primary_key_val, col, client, given_info, log_file)
    else:
        given_info, next_level_links, proceed, source_url, path_record_level = inspect_dynamic(url, query, primary_key, primary_key_val, col, given_info, client, log_file)
    
    return given_info, next_level_links, proceed, source_url, path_record_level, url_type