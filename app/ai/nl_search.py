"""
Natural Language Search — agentic function-calling loop.

Gemini interprets the user's query using their consumption profile as context,
decides what to search for (1-4 products), calls the scrapers as tools,
and returns a brief text summary + flat list of product results.
"""
import json
from google import genai
from google.genai import types

from app.ai.agent import search_stores
from app.config import get_google_key


_SEARCH_DECLARATION = types.FunctionDeclaration(
    name="search_products",
    description=(
        "Search for a grocery product across supermarket stores and return "
        "matching products with current prices. Call once per distinct product "
        "you want to find. Keep queries specific."
    ),
    parameters={
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
)


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
    Run a natural language grocery search using Gemini with function calling.

    Returns:
        {
            "summary": str,          # Gemini's 2-3 sentence recommendation
            "results": list[dict],   # flat list of all product results
            "error": str | None,     # friendly error message or None
        }
    """
    api_key = get_google_key()
    if not api_key:
        return {
            "summary": "",
            "results": [],
            "error": (
                "Google API key not configured. "
                "Add GOOGLE_API_KEY to your .env or Railway environment variables to enable AI search."
            ),
        }

    if not user_stores:
        user_stores = ["woolworths", "coles", "aldi"]

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=[_SEARCH_DECLARATION])],
        system_instruction=_build_system(profile, user_stores),
    )

    chat = client.aio.chats.create(model="gemini-2.0-flash", config=config)
    all_results: list[dict] = []
    summary = ""

    try:
        response = await chat.send_message(query)

        for _ in range(8):  # safety cap — prevents runaway loops
            fn_calls = [
                p.function_call
                for p in response.candidates[0].content.parts
                if p.function_call
            ]

            if not fn_calls:
                # Extract text from response
                for part in response.candidates[0].content.parts:
                    if part.text:
                        summary += part.text
                break

            fn_response_parts = []
            for fc in fn_calls:
                if fc.name == "search_products":
                    stores_to_use = list(fc.args.get("stores") or user_stores)
                    results = await search_stores(fc.args["query"], stores_to_use, limit=5)
                    all_results.extend(results)
                    fn_response_parts.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=fc.name,
                                response={"result": json.dumps(results[:8])},
                            )
                        )
                    )

            if not fn_response_parts:
                break

            response = await chat.send_message(fn_response_parts)

        return {"summary": summary, "results": all_results, "error": None}

    except Exception as exc:
        return {
            "summary": "",
            "results": [],
            "error": f"AI search encountered an error: {str(exc)[:200]}",
        }
