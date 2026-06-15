from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_capital_flow(
    symbol: Annotated[str, "mainland China A-share six-digit ticker symbol"],
    curr_date: Annotated[str, "the current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "number of recent trading rows to include"] = 20,
) -> str:
    """Retrieve A-share capital-flow data such as main-force net inflow."""
    return route_to_vendor("get_capital_flow", symbol, curr_date, look_back_days)
