/**
 * Cloudflare Worker — Woolworths Search Proxy
 *
 * Woolworths blocks all cloud-datacenter IPs (Railway, AWS, GCP) via Akamai.
 * Cloudflare's edge IPs are not on that blocklist, so this Worker can reach
 * Woolworths while Railway cannot.
 *
 * Deploy (free):
 *   1. Go to https://workers.cloudflare.com  (free account, no credit card)
 *   2. Create a new Worker → paste this file → Save & Deploy
 *   3. Set env variable SECRET_TOKEN to any random string you choose
 *   4. Copy the Worker URL (e.g. https://woolworths-proxy.YOUR-NAME.workers.dev)
 *   5. In Railway → Variables, add:
 *        WOOLWORTHS_PROXY_URL = https://woolworths-proxy.YOUR-NAME.workers.dev
 *        WOOLWORTHS_PROXY_TOKEN = <same token you set in step 3>
 *
 * Usage:
 *   GET <worker-url>?q=eggs&limit=20&token=<secret>
 */

const WOW_HOME = "https://www.woolworths.com.au";
const SEARCH_API = `${WOW_HOME}/apis/ui/Search/products`;

const BASE_HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
    "AppleWebKit/537.36 (KHTML, like Gecko) " +
    "Chrome/124.0.0.0 Safari/537.36",
  Accept: "application/json, text/plain, */*",
  "Accept-Language": "en-AU,en;q=0.9",
  "Content-Type": "application/json",
  Origin: WOW_HOME,
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // ── Auth ──────────────────────────────────────────────────────────────────
    const token = url.searchParams.get("token") || "";
    const secret = env.SECRET_TOKEN || "";
    if (secret && token !== secret) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }

    // ── Params ────────────────────────────────────────────────────────────────
    const query = (url.searchParams.get("q") || "").trim();
    if (!query) {
      return new Response(JSON.stringify({ error: "q param required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }
    const limit = Math.min(parseInt(url.searchParams.get("limit") || "20", 10), 36);

    // ── Step 1: warm up — get session cookies from homepage ───────────────────
    const referer = `${WOW_HOME}/shop/search/products?searchTerm=${encodeURIComponent(query)}`;
    let cookieHeader = "";
    try {
      const homeResp = await fetch(WOW_HOME + "/", {
        headers: { ...BASE_HEADERS, Referer: WOW_HOME + "/" },
        redirect: "follow",
      });
      // Collect all Set-Cookie values into one Cookie header
      const raw = homeResp.headers.get("set-cookie") || "";
      if (raw) {
        cookieHeader = raw
          .split(/,(?=[^ ].*?=)/)          // split multi-cookie header
          .map((c) => c.split(";")[0].trim())
          .join("; ");
      }
    } catch (_) {
      // Continue without cookies — may still work
    }

    // ── Step 2: search API ────────────────────────────────────────────────────
    const payload = {
      Filters: [],
      IsSpecial: false,
      Location: `/shop/search/products?searchTerm=${query}`,
      PageNumber: 1,
      PageSize: limit,
      SearchTerm: query,
      SortType: "TraderRelevance",
      token: "",
      gpBoost: 0,
      CategoryVersion: "v2",
    };

    const searchHeaders = {
      ...BASE_HEADERS,
      Referer: referer,
      "request-id": `|${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}.${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`,
    };
    if (cookieHeader) searchHeaders["Cookie"] = cookieHeader;

    let searchResp;
    try {
      searchResp = await fetch(SEARCH_API, {
        method: "POST",
        headers: searchHeaders,
        body: JSON.stringify(payload),
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ error: "Woolworths fetch failed", detail: String(err) }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }

    if (!searchResp.ok) {
      return new Response(
        JSON.stringify({ error: `Woolworths returned ${searchResp.status}` }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }

    const body = await searchResp.text();
    return new Response(body, {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      },
    });
  },
};
