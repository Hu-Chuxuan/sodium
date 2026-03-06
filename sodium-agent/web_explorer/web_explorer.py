from utils.prompt import URL_FINDER_SORT
from utils.lib import parse_result_from_content_list
from utils.log import cell_summary, document_func_call

from .page_explorer import inspect_page

def atp_bfs(client, log_file, base_domain, query, primary_key, primary_key_val, col, given_info, k=10, max_depth=5):
    if not base_domain.startswith(("http://", "https://")):
        base_domain = "https://" + base_domain
    visited = set()
    results_by_depth = {}
    path_record = {}

    # queue holds only URLs of the *current* depth
    current_level = [base_domain]

    for depth in range(max_depth + 1):
        if not current_level:
            break

        print(f"\n=== Starting depth {depth} ===")
        next_level = []
        results_by_depth[depth] = []

        if depth != 0:
            current_level = augment_select_rank(current_level, query, primary_key, primary_key_val, col, k, given_info, client, log_file)

        for url in current_level:

            if url in visited:
                continue
            visited.add(url) 
            given_info, next_level_links, proceed, source_url, path_record_level, static = inspect_page(url, log_file, query, primary_key, primary_key_val, col, given_info, client)
            path_record.update(path_record_level)

            if col in given_info:
                path = backtrace(path_record, source_url)
                return given_info, source_url, static, path
            elif not proceed and url != base_domain:
                continue

            for link_info in next_level_links:
                results_by_depth[depth].append(link_info)
                if 'localhost' not in link_info["url"] and link_info["url"] not in visited:
                    path_record[link_info["url"]] = source_url
                    next_level.append(link_info)

        current_level = next_level

    total = sum(len(v) for v in results_by_depth.values())
    return given_info, base_domain, None, [base_domain]

def augment_select_rank(candidate_urls, query, primary_key, primary_key_val, col, k, given_info, client, log_file):
    prompt = URL_FINDER_SORT.format(
        candidate_urls=candidate_urls,
        query=query,
        primary_key=primary_key, 
        primary_key_val=primary_key_val, 
        col=col, 
        k=k,
        given_info=given_info
    )

    response = client.responses.create(
        model="gpt-5",
        reasoning={"effort": "high"},
        input=prompt,
    )

    document_func_call(log_file, "augment_select_rank", response, prompt)
    content = response.output_text
    current_level = parse_result_from_content_list(content, "res")

    return current_level

def backtrace(path_record, url):
    res = []
    visited = set()

    while url in path_record:
        if url in visited:
            # cycle detected
            print(f"[WARN] Cycle detected in backtrace at {url}")
            break
        visited.add(url)

        res = [url] + res
        url = path_record[url]

    return [url] + res