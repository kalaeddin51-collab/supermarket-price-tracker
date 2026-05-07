"""
Natural Language Search — agentic tool-use loop.

Claude interprets the user's query using their consumption profile as context,
decides what to search for (1-4 products), calls the scrapers as tools,
and returns a brief text summary + flat list of product results.
"""
import json
import anthropic

from app.ai.agent import search_stores
from app.config import get_anthropic_key


NL_TOOLS = [
    {
        "name": "search_products",
        "description": (
            "Search for a grocery product across supermarket stores and return "
            "matching products with current prices. Call once per distinct product "
            "you want to find. Keep queries specific."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Specific product name to search for. "
                        "Be precise — 'free range chicken thigh 1kg' beats 'chicken'."
                    ),
                },
                "stores": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Store slugs to search, e.g. ['coles', 'woolworths', 'aldi']",
                },
            },
            "required": ["query", "stores"],
        },
    }
]


def _format_profile(profile: list) -> str:
    if not profile:
        return "(no shopping profile set up — using general knowledge)"
    lines = []
    for item in profile:
        line = f"- {item.item_name}"
        if item.brand_preference:
            line += f" (brand: {item.brand_preference})"
        else:
            line += " (any brand)"
        if item.notes:
            line += f" — {item.notes}"
        lines.append(line)
    return "\n".join(lines)


def _build_system(profile: list, user_stores: list[str]) -> str:
    profile_text = _format_profile(profile)
    stores_text = ", ".join(user_stores) if user_stores else "woolworths, coles, aldi"
    return f"""You are a grocery shopping assistant for a Sydney supermarket price tracker.

The user regularly buys these groceries:
{profile_text}

Available stores: {stores_text}

Instructions:
- Call search_products once per distinct product you want to find (1–4 calls max)
- After all searches, write 2–3 sentences summarising the best value options found
- Cross-reference the user's profile: if they say "cheap protein", look at what they actually eat
- Keep queries specific: "Mainland tasty cheese block 500g" beats "cheese"
- If a profile item has a brand preference, include that brand in the search query
- After searching, highlight: best price, best value per unit, any specials
- Do not call search_products more than 4 times"""


async def run_nl_search(query: str, profile: list, user_stores: list[str]) -> dict:
    """
    Run a natural language grocery search using Claude with tool use.

    Returns:
        {
            "summary": str,          # Claude's 2-3 sentence recommendation
            "results": list[dict],   # flat list of all product results
            "error": str | None,     # friendly error message or None
        }
    """
    api_key = get_anthropic_key()
    if not api_key:
        return {
            "summary": "",
            "results": [],
            "error": (
                "Anthropic API key not configured. "
                "Add ANTHROPIC_API_KEY to your Railway environment variables to enable AI search."
            ),
        }

    if not user_stores:
        user_stores = ["woolworths", "coles", "aldi"]

    client = anthropic.AsyncAnthropic(api_key=api_key)
    messages: list[dict] = [{"role": "user", "content": query}]
    all_results: list[dict] = []
    summary = ""

    try:
        for _ in range(8):  # safety cap — prevents runaway loops
            response = await client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1024,
                system=_build_system(profile, user_stores),
                tools=NL_TOOLS,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                summary = next(
                    (b.text for b in response.content if hasattr(b, "text")), ""
                )
                break

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    if block.name == "search_products":
                        stores_to_use = block.input.get("stores") or user_stores
                        results = await search_stores(block.input["query"], stores_to_use, limit=5)
                        all_results.extend(results)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                # Truncate to keep context window manageable
                                "content": json.dumps(results[:8]),
                            }
                        )

                messages.append({"role": "user", "content": tool_results})
            else:
                break

        return {"summary": summary, "results": all_results, "error": None}

    except anthropic.AuthenticationError:
        return {
            "summary": "",
            "results": [],
            "error": "Invalid Anthropic API key. Check your ANTHROPIC_API_KEY environment variable.",
        }
    except Exception as exc:
        return {
            "summary": "",
            "results": [],
            "error": f"AI search encountered an error: {str(exc)[:200]}",
        }
