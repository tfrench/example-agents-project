import os
from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_google_community import GmailToolkit
from langchain_google_community.gmail.utils import (
    build_resource_service,
)
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from functools import wraps

from .credentials import get_user_credentials
from .cache import acquire_lock, release_lock

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_URI = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

MODEL = "gpt-4o"


workflows: dict[str, StateGraph] = {}


def lock_required(func):
    @wraps(func)
    async def wrapper(user_id: str, *args, **kwargs):
        lock = await acquire_lock(user_id)
        if not lock:
            raise FailedToAcquireSessionLockException()
        try:
            return await func(user_id, *args, **kwargs)
        finally:
            await release_lock(user_id)

    return wrapper


class FailedToAcquireSessionLockException(Exception):
    pass


def should_continue(state: MessagesState) -> Literal["tools", END]:
    messages = state["messages"]
    last_message = messages[-1]
    # If the LLM makes a tool call, then we route to the "tools" node
    if last_message.tool_calls:
        return "tools"
    # Otherwise, we stop (reply to the user)
    return END


async def get_tools(user_id):
    credentials = await get_user_credentials(user_id)
    api_resource = build_resource_service(credentials=credentials)

    toolkit = GmailToolkit(api_resource=api_resource)
    tools = toolkit.get_tools()
    return tools


async def get_workflow(user_id: str):
    tools = await get_tools(user_id)
    tool_node = ToolNode(tools)

    model = ChatOpenAI(model=MODEL, temperature=0).bind_tools(tools)

    async def call_model(state: MessagesState):
        messages = state["messages"]
        response = await model.ainvoke(messages)
        # We return a list, because this will get added to the existing list
        return {"messages": [response]}

    workflow = StateGraph(MessagesState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
    )
    workflow.add_edge("tools", "agent")

    return workflow


@lock_required
async def process_message(user_id: str, message: str):
    if not user_id or not message:
        return {"error": "Missing required fields: user_id or message"}

    try:
        workflow = workflows[user_id]
    except KeyError:
        workflow = await get_workflow(user_id)
        workflows[user_id] = workflow

    connection_kwargs = {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }
    async with await AsyncConnection.connect(DB_URI, **connection_kwargs) as conn:
        checkpointer = AsyncPostgresSaver(conn)

        # Initialize the database (run this once)
        await checkpointer.setup()

        app = workflow.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": user_id}}
        inputs = {"messages": [HumanMessage(content=message)]}

        result = await app.ainvoke(inputs, config=config)

    return result["messages"][-1].content
