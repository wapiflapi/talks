import ast
import inspect
import textwrap


def explore_ast_paths(node):

    # ast.walk does not specify order, DIY:
    node_chains_to_explore = [[node]]

    while node_chains_to_explore:
        node_chain = node_chains_to_explore.pop(0)
        yield node_chain

        node_chains_to_explore.extend([
            node_chain + [child_node]
            for child_node in ast.iter_child_nodes(node_chain[-1])
        ]
        )


def iter_node_paths_matching_kwargs(node, **kwargs) -> list:
    for node_path in explore_ast_paths(node):
        try:
            if all(
                getattr(node_path[-1], attr) == value
                for attr, value in kwargs.items()
            ):
                yield node_path
        except AttributeError:
            continue


def find_parent_instance_path(node_chain, cls) -> list:
    for i, node in enumerate(reversed(node_chain)):
        if i > 0 and isinstance(node, cls):
            return node_chain[:-i]
    return []



def dwim():
    caller_frame_info = inspect.stack()[1]

    caller_source = inspect.getsource(caller_frame_info.frame.f_code)

    alligned_caller_source = textwrap.dedent(caller_source)
    caller_node = ast.parse(alligned_caller_source)

    line_offset = caller_frame_info.frame.f_code.co_firstlineno - 1
    dedent_count = (len(caller_source) - len(alligned_caller_source)) / caller_source.count("\n")

    for node_path in iter_node_paths_matching_kwargs(
        caller_node,
        lineno=caller_frame_info.positions.lineno - line_offset,
        end_lineno=caller_frame_info.positions.end_lineno - line_offset,
        col_offset=caller_frame_info.positions.col_offset - dedent_count,
        end_col_offset=caller_frame_info.positions.end_col_offset - dedent_count,
    ):
        parent_keyword_path = find_parent_instance_path(node_path, ast.keyword)
        parent_call_path = find_parent_instance_path(parent_keyword_path, ast.Call)
        if parent_call_path:
            break

    else:
        raise ValueError("Could not locate parent call for dwim.")

    function_call = parent_call_path[-1]
    assert isinstance(function_call, ast.Call), "not sure where to find function"
    assert isinstance(function_call.func, ast.Name), "not sure where to find function"
    assert isinstance(function_call.func.ctx, ast.Load), "not sure where to find function"

    function_call_target = caller_frame_info.frame.f_locals.get(
        function_call.func.id, caller_frame_info.frame.f_globals.get(
            function_call.func.id, None
        )
    )

    assert function_call_target is not None, "didn't find function target"

    signature = inspect.signature(function_call_target)

    candidate_arg_names = [
        arg_name
        for i, arg_name in enumerate(signature.parameters)
        if i >= len(function_call.args) and not any(
            # The kwarg is not passed explicitely.
            arg_name == keyword.arg for keyword in function_call.keywords
        )
    ]

    keywords = {
        k: v for k, v in caller_frame_info.frame.f_locals.items()
        if k in candidate_arg_names
    }

    return keywords