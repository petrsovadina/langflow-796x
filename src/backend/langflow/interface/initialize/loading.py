import json
from typing import Any, Callable, Dict, Sequence

from langchain.agents import ZeroShotAgent
from langchain.agents import agent as agent_module
from langchain.agents.agent import AgentExecutor
from langchain.agents.agent_toolkits.base import BaseToolkit
from langchain.agents.tools import BaseTool
from langflow.interface.initialize.vector_store import vecstore_initializer

from pydantic import ValidationError

from langflow.interface.custom_lists import CUSTOM_NODES
from langflow.interface.importing.utils import get_function, import_by_type
from langflow.interface.toolkits.base import toolkits_creator
from langflow.interface.chains.base import chain_creator
from langflow.interface.utils import load_file_into_dict
from langflow.utils import validate


def instantiate_class(node_type: str, base_type: str, params: Dict) -> Any:
    """Instantiate class from module type and key, and params"""
    params = convert_params_to_sets(params)
    params = convert_kwargs(params)
    if node_type in CUSTOM_NODES:
        if custom_node := CUSTOM_NODES.get(node_type):
            if hasattr(custom_node, "initialize"):
                return custom_node.initialize(**params)
            return custom_node(**params)

    class_object = import_by_type(_type=base_type, name=node_type)
    return instantiate_based_on_type(class_object, base_type, node_type, params)


def convert_params_to_sets(params):
    """Convert certain params to sets"""
    if "allowed_special" in params:
        params["allowed_special"] = set(params["allowed_special"])
    if "disallowed_special" in params:
        params["disallowed_special"] = set(params["disallowed_special"])
    return params


def convert_kwargs(params):
    # if *kwargs are passed as a string, convert to dict
    # first find any key that has kwargs in it
    kwargs_keys = [key for key in params.keys() if "kwargs" in key]
    for key in kwargs_keys:
        if isinstance(params[key], str):
            params[key] = json.loads(params[key])
    return params


def instantiate_based_on_type(class_object, base_type, node_type, params):
    if base_type == "agents":
        return instantiate_agent(class_object, params)
    elif base_type == "prompts":
        return instantiate_prompt(node_type, class_object, params)
    elif base_type == "tools":
        return instantiate_tool(node_type, class_object, params)
    elif base_type == "toolkits":
        return instantiate_toolkit(node_type, class_object, params)
    elif base_type == "embeddings":
        return instantiate_embedding(class_object, params)
    elif base_type == "vectorstores":
        return instantiate_vectorstore(class_object, params)
    elif base_type == "documentloaders":
        return instantiate_documentloader(class_object, params)
    elif base_type == "textsplitters":
        return instantiate_textsplitter(class_object, params)
    elif base_type == "utilities":
        return instantiate_utility(node_type, class_object, params)
    elif base_type == "chains":
        return instantiate_chains(node_type, class_object, params)
    else:
        return class_object(**params)


def instantiate_chains(node_type, class_object, params):
    if "retriever" in params and hasattr(params["retriever"], "as_retriever"):
        params["retriever"] = params["retriever"].as_retriever()
    if node_type in chain_creator.from_method_nodes:
        method = chain_creator.from_method_nodes[node_type]
        if class_method := getattr(class_object, method, None):
            return class_method(**params)
        raise ValueError(f"Method {method} not found in {class_object}")

    return class_object(**params)


def instantiate_agent(class_object, params):
    return load_agent_executor(class_object, params)


def instantiate_prompt(node_type, class_object, params):
    if node_type == "ZeroShotPrompt":
        if "tools" not in params:
            params["tools"] = []
        return ZeroShotAgent.create_prompt(**params)
    return class_object(**params)


def instantiate_tool(node_type, class_object, params):
    if node_type == "JsonSpec":
        params["dict_"] = load_file_into_dict(params.pop("path"))
        return class_object(**params)
    elif node_type == "PythonFunctionTool":
        params["func"] = get_function(params.get("code"))
        return class_object(**params)
    # For backward compatibility
    elif node_type == "PythonFunction":
        function_string = params["code"]
        if isinstance(function_string, str):
            return validate.eval_function(function_string)
        raise ValueError("Function should be a string")
    elif node_type.lower() == "tool":
        return class_object(**params)
    return class_object(**params)


def instantiate_toolkit(node_type, class_object, params):
    loaded_toolkit = class_object(**params)
    # Commenting this out for now to use toolkits as normal tools
    # if toolkits_creator.has_create_function(node_type):
    #     return load_toolkits_executor(node_type, loaded_toolkit, params)
    if isinstance(loaded_toolkit, BaseToolkit):
        return loaded_toolkit.get_tools()
    return loaded_toolkit


def instantiate_embedding(class_object, params):
    params.pop("model", None)
    params.pop("headers", None)
    try:
        return class_object(**params)
    except ValidationError:
        params = {
            key: value
            for key, value in params.items()
            if key in class_object.__fields__
        }
        return class_object(**params)


def instantiate_vectorstore(class_object, params):
    search_kwargs = params.pop("search_kwargs", {})
    if initializer := vecstore_initializer.get(class_object.__name__):
        vecstore = initializer(class_object, params)
    else:
        if "texts" in params:
            params["documents"] = params.pop("texts")
        vecstore = class_object.from_documents(**params)

    # ! This might not work. Need to test
    if search_kwargs and hasattr(vecstore, "as_retriever"):
        vecstore = vecstore.as_retriever(search_kwargs=search_kwargs)

    return vecstore


def instantiate_documentloader(class_object, params):
    if "file_filter" in params:
        # file_filter will be a string but we need a function
        # that will be used to filter the files using file_filter
        # like lambda x: x.endswith(".txt") but as we don't know
        # anything besides the string, we will simply check if the string is
        # in x and if it is, we will return True
        file_filter = params.pop("file_filter", None)
        extensions = file_filter.split(",")
        params["file_filter"] = lambda x: any(
            extension.strip() in x for extension in extensions
        )
    metadata = params.pop("metadata", None)
    docs = class_object(**params).load()
    if metadata:
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "The metadata you provided is not a valid JSON string."
                ) from exc

        for doc in docs:
            doc.metadata = metadata

    return docs


def instantiate_textsplitter(class_object, params):
    try:
        documents = params.pop("documents")
    except KeyError as e:
        raise ValueError(
            "The source you provided did not load correctly or was empty."
            "Try changing the chunk_size of the Text Splitter."
        ) from e
    text_splitter = class_object(**params)
    return text_splitter.split_documents(documents)


def instantiate_utility(node_type, class_object, params):
    if node_type == "SQLDatabase":
        return class_object.from_uri(params.pop("uri"))
    return class_object(**params)


def replace_zero_shot_prompt_with_prompt_template(nodes):
    """Replace ZeroShotPrompt with PromptTemplate"""
    for node in nodes:
        if node["data"]["type"] == "ZeroShotPrompt":
            # Build Prompt Template
            tools = [
                tool
                for tool in nodes
                if tool["type"] != "chatOutputNode"
                and "Tool" in tool["data"]["node"]["base_classes"]
            ]
            node["data"] = build_prompt_template(prompt=node["data"], tools=tools)
            break
    return nodes


def load_agent_executor(agent_class: type[agent_module.Agent], params, **kwargs):
    """Load agent executor from agent class, tools and chain"""
    allowed_tools: Sequence[BaseTool] = params.get("allowed_tools", [])
    llm_chain = params["llm_chain"]
    # if allowed_tools is not a list or set, make it a list
    if not isinstance(allowed_tools, (list, set)) and isinstance(
        allowed_tools, BaseTool
    ):
        allowed_tools = [allowed_tools]
    tool_names = [tool.name for tool in allowed_tools]
    # Agent class requires an output_parser but Agent classes
    # have a default output_parser.
    agent = agent_class(allowed_tools=tool_names, llm_chain=llm_chain)  # type: ignore
    return AgentExecutor.from_agent_and_tools(
        agent=agent,
        tools=allowed_tools,
        **kwargs,
    )


def load_toolkits_executor(node_type: str, toolkit: BaseToolkit, params: dict):
    create_function: Callable = toolkits_creator.get_create_function(node_type)
    if llm := params.get("llm"):
        return create_function(llm=llm, toolkit=toolkit)


def build_prompt_template(prompt, tools):
    """Build PromptTemplate from ZeroShotPrompt"""
    prefix = prompt["node"]["template"]["prefix"]["value"]
    suffix = prompt["node"]["template"]["suffix"]["value"]
    format_instructions = prompt["node"]["template"]["format_instructions"]["value"]

    tool_strings = "\n".join(
        [
            f"{tool['data']['node']['name']}: {tool['data']['node']['description']}"
            for tool in tools
        ]
    )
    tool_names = ", ".join([tool["data"]["node"]["name"] for tool in tools])
    format_instructions = format_instructions.format(tool_names=tool_names)
    value = "\n\n".join([prefix, tool_strings, format_instructions, suffix])

    prompt["type"] = "PromptTemplate"

    prompt["node"] = {
        "template": {
            "_type": "prompt",
            "input_variables": {
                "type": "str",
                "required": True,
                "placeholder": "",
                "list": True,
                "show": False,
                "multiline": False,
            },
            "output_parser": {
                "type": "BaseOutputParser",
                "required": False,
                "placeholder": "",
                "list": False,
                "show": False,
                "multline": False,
                "value": None,
            },
            "template": {
                "type": "str",
                "required": True,
                "placeholder": "",
                "list": False,
                "show": True,
                "multiline": True,
                "value": value,
            },
            "template_format": {
                "type": "str",
                "required": False,
                "placeholder": "",
                "list": False,
                "show": False,
                "multline": False,
                "value": "f-string",
            },
            "validate_template": {
                "type": "bool",
                "required": False,
                "placeholder": "",
                "list": False,
                "show": False,
                "multline": False,
                "value": True,
            },
        },
        "description": "Schema to represent a prompt for an LLM.",
        "base_classes": ["BasePromptTemplate"],
    }

    return prompt
