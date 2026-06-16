from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_macro_indicators,
    get_news,
)


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_news,
            get_macro_indicators,
        ]

        system_message = (
            "You are a domestic China A-share news researcher. Produce a "
            "comprehensive report for the target A-share using only China-local "
            "company news and domestic macro context. Use get_news(query, "
            "start_date, end_date) for company-specific A-share news. If macro "
            "context is necessary, use get_macro_indicators with "
            "`china_yield_curve` to retrieve the ChinaBond RMB government-bond "
            "yield curve. Do not request or discuss Yahoo Finance, Reddit, "
            "StockTwits, FRED, Polymarket, Fed-rate probabilities, U.S. CPI, "
            "U.S. Treasury yields, or other overseas forum/global-news sources "
            "unless the domestic source packet itself explicitly mentions them. "
            "If a domestic source is sparse or unavailable, report it as a data "
            "gap and continue instead of inventing evidence. Provide specific, "
            "actionable insights with supporting evidence for A-share traders."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
