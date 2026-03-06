from utils.prompt import PATH_SEARCH
from utils.log import document_func_call
from utils.lib import parse_result_from_content_list

def discover_path(query, primary_key, primary_key_val, col, upper_primary_key_val, upper_col, search_path_up, left_primary_key_val, left_col, search_path_left, given_info, client, log_file, k=5):
    prompt = PATH_SEARCH.format(
        query=query,
        primary_key=primary_key, 
        primary_key_val=primary_key_val, 
        col=col, 
        k=k,
        upper_primary_key_val=upper_primary_key_val,
        upper_col=upper_col,
        search_path_up=search_path_up,
        left_primary_key_val=left_primary_key_val,
        left_col=left_col,
        search_path_left=search_path_left,
        given_info=given_info
    )

    response = client.responses.create(
        model="gpt-5",
        reasoning={"effort": "high"},
        input=prompt,
    )

    document_func_call(log_file, "discover_path", response, prompt)
    content = response.output_text
    rank_list = parse_result_from_content_list(content, "res")

    return rank_list
