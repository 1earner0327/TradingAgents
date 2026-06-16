"""Sentiment analyst — domestic A-share sentiment analysis for a target ticker.

Previously named ``social_media_analyst``. Renamed and redesigned because
the old version had a prompt that demanded social-media analysis but the
only tool available was Yahoo Finance news — which led LLMs to fabricate
Reddit/X/StockTwits content under prompt pressure (verified live).

The redesigned agent pre-fetches complementary data sources before the LLM
is invoked and injects them into the prompt as structured blocks. This fork's
web console is A-share-only, so the analyst uses domestic sources: East Money
Guba desktop/mobile as the primary retail discussion source, an auxiliary
10jqka public-page snapshot, and optional Tushare Pro news when configured.

The agent does not use tool-calling; the data is in the prompt from
turn 0. Output uses the structured-output pattern (json_schema for
OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic), falling
back to free-text generation for providers that lack native support, so
the sentiment header (band + score + confidence) is deterministic across
runs and providers instead of free-form per-model prose.

See: https://github.com/TauricResearch/TradingAgents/issues/557
See: https://github.com/TauricResearch/TradingAgents/issues/796
"""

from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.schemas import SentimentReport, render_sentiment_report
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.dataflows.cn_sentiment import fetch_cn_sentiment_sources


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    Pre-fetches market-appropriate sentiment data, injects it into the prompt
    as structured blocks, and produces a deterministic sentiment report via
    structured output (with a free-text fallback for providers that do not
    support it).
    """
    structured_llm = bind_structured(llm, SentimentReport, "Sentiment Analyst")

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = get_instrument_context_from_state(state)

        # Pre-fetch source data before the model is invoked. Each fetcher
        # degrades gracefully and returns a string, so the LLM sees real data
        # or an explicit placeholder instead of being pressured to invent.
        domestic_block = fetch_cn_sentiment_sources(ticker, start_date, end_date)
        system_message = _build_china_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            domestic_block=domestic_block,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        # Format the template into a concrete message list so the structured
        # and free-text paths receive the same input. No bind_tools — the
        # data is already in the prompt.
        formatted_messages = prompt.format_messages(messages=state["messages"])

        report_text = invoke_structured_or_freetext(
            structured_llm,
            llm,
            formatted_messages,
            render_sentiment_report,
            "Sentiment Analyst",
        )

        return {
            "messages": [AIMessage(content=report_text)],
            "sentiment_report": report_text,
        }

    return sentiment_analyst_node


def _build_china_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    domestic_block: str,
) -> str:
    """Assemble the A-share sentiment prompt with domestic pre-fetched data."""
    return f"""You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}, drawing only on the domestic China data sources that have already been collected for you.

## Data sources (pre-fetched, in this prompt)

### China A-share sentiment packet — East Money Guba, East Money mobile Guba, 10jqka public page, plus optional Tushare Pro news
East Money Guba is the primary domestic retail-investor discussion source. East Money mobile Guba is a second public entry point that can expose additional live rows when the desktop page is sparse. 10jqka is treated only as an auxiliary public-page snapshot. Do not treat 10jqka as forum-post evidence unless the packet explicitly contains stable post rows. Tushare Pro news, when available, is a supplementary domestic news feed rather than a forum.

<start_of_china_sentiment>
{domestic_block}
<end_of_china_sentiment>

## How to analyze this data (best practices)

1. **Prioritize domestic evidence for A-shares.** Do not analyze Yahoo Finance, StockTwits, Reddit, or other overseas forums for A-share sentiment. For this A-share run, the relevant retail sentiment sources are East Money Guba desktop/mobile. 10jqka public-page text is supportive context only, not forum sentiment, unless stable post rows are explicitly present.

2. **Separate retail chatter from factual news.** East Money Guba user posts are opinion and momentum signals; posts from official information accounts or Tushare news are event/news inputs. Weight them differently.

3. **Use engagement as signal quality.** High comment/read posts deserve more attention than low-engagement noise. A one-line bullish title with little engagement should not dominate the report.

4. **Identify recurring domestic narratives.** Look for repeated themes such as order growth, sector rotation, financing flows, short-term price targets, valuation disputes, shareholder selling, policy expectations, and earnings catalysts.

5. **Be explicit about data limits.** If a source is blocked, permission-limited, or sparse, say so. If 10jqka does not expose stable post rows, state that it was not used as forum-post evidence. If Tushare returns a permission note, do not treat that as bearish; it is only a data-availability issue.

6. **Past sentiment is not predictive.** Frame your conclusions as signal for the trader to weigh alongside fundamentals and technicals, not as a price call.

## Output fields

Fill the following fields:

- **overall_band**: Exactly one of Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. Use Mixed when sources point in clearly different directions; Neutral only when all sources are genuinely silent.
- **overall_score**: A number from 0 (maximally bearish) to 10 (maximally bullish); 5 is neutral. Keep it consistent with overall_band.
- **confidence**: low / medium / high, based on data quality and sample size.
- **narrative**: Full source-by-source breakdown, divergences, dominant narrative themes, catalysts and risks, and a markdown summary table of key sentiment signals (direction, source, supporting evidence).

{get_language_instruction()}"""


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
def create_social_media_analyst(llm):
    """Deprecated alias for :func:`create_sentiment_analyst`.

    Kept so existing code that imports ``create_social_media_analyst``
    continues to work.

    .. deprecated::
        Import :func:`create_sentiment_analyst` directly instead.
    """
    import warnings
    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)
