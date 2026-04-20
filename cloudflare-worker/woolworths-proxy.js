/**
 * Cloudflare Worker — Woolworths Search Proxy
 * Uses Cloudflare's edge network to bypass Akamai's datacenter IP block.
 *
 * Set SECRET_TOKEN env var in Worker settings.
 * Usage: GET /?q=eggs&limit=20&token=<secret>
 */

const WOW_HOME   = "https://www.woolworths.com.au";
const SEARCH_API = `${WOW_HOME}/apis/ui/Search/products`;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Auth
    const token  = url.searchParams.get("token") || "";
    const secret = env.SECRET_TOKEN || "";
    if (secret && token !== secret) {
      return json({ error: "Unauthorized" }, 401);
    }

    const query = (url.searchParams.get("q") || "").trim();
    if (!query) return json({ error: "q param required" }, 400);

    const limit = Math.min(parseInt(url.searchParams.get("limit") || "20", 10), 36);

    // Build realistic browser headers
    const headers = {
      "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Accept":          "application/json, text/plain, */*",
      "Accept-Language": "en-AU,en;q=0.9",
      "Accept-Encoding": "gzip, deflate, br",
      "Content-Type":    "application/json",
      "Origin":          WOW_HOME,
      "Referer":         `${WOW_HOME}/shop/search/products?searchTerm=${encodeURIComponent(query)}`,
      "sec-ch-ua":       '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
      "sec-ch-ua-mobile":   "?0",
      "sec-ch-ua-platform": '"Windows"',
      "sec-fetch-dest":  "empty",
      "sec-fetch-mode":  "cors",
      "sec-fetch-site":  "same-origin",
    };

    // Step 1 — warm up session (get cookies)
    let cookieStr = "";
    try {
      const home = await fetch(WOW_HOME + "/", {
        headers: { ...headers, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Content-Type": undefined },
        redirect: "follow",
        cf: { cacheEverything: false },
      });
      const raw = home.headers.get("set-cookie") || "";
      if (raw) {
        cookieStr = raw.split(/,(?=[^ ].*?=)/)
          .map(c => c.split(";")[0].trim())
          .filter(Boolean)
          .join("; ");
      }
    } catch (_) {}

    if (cookieStr) headers["Cookie"] = cookieStr;

    // Step 2 — search
    const payload = {
      Filters: [], IsSpecial: false,
      Location: `/shop/search/products?searchTerm=${query}`,
      PageNumber: 1, PageSize: limit,
      SearchTerm: query, SortType: "TraderRelevance",
      token: "", gpBoost: 0, CategoryVersion: "v2",
    };

    let resp;
    try {
      resp = await fetch(SEARCH_API, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        cf: { cacheEverything: false },
      });
    } catch (err) {
      return json({ error: "fetch_failed", detail: String(err) }, 502);
    }

    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      return json({
        error:      `woolworths_${resp.status}`,
        statusText: resp.statusText,
        snippet:    body.slice(0, 400),
        cookies_got: cookieStr.length > 0,
      }, 502);
    }

    const data = await resp.text();
    return new Response(data, {
      status: 200,
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
    });
  },
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
