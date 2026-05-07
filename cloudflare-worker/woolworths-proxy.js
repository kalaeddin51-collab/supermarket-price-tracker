/**
 * Cloudflare Worker — Woolworths Search Proxy
 *
 * The JSON API is blocked from Cloudflare IPs but the HTML search page
 * is accessible. We fetch the HTML page and extract the __NEXT_DATA__
 * embedded JSON which contains full product data.
 *
 * Usage: GET /?q=eggs&limit=20&token=<secret>
 */

const WOW_HOME = "https://www.woolworths.com.au";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Auth
    const token  = url.searchParams.get("token") || "";
    const secret = env.SECRET_TOKEN || "";
    if (secret && token !== secret) return json({ error: "Unauthorized" }, 401);

    const query = (url.searchParams.get("q") || "").trim();
    if (!query) return json({ error: "q param required" }, 400);

    const limit = Math.min(parseInt(url.searchParams.get("limit") || "20", 10), 36);

    const searchUrl = `${WOW_HOME}/shop/search/products?searchTerm=${encodeURIComponent(query)}&hideUnavailable=true&pageNumber=1`;

    const headers = {
      "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
      "Accept-Language": "en-AU,en;q=0.9",
      "Accept-Encoding": "gzip, deflate, br",
      "sec-ch-ua":          '"Chromium";v="124", "Google Chrome";v="124"',
      "sec-ch-ua-mobile":   "?0",
      "sec-ch-ua-platform": '"Windows"',
      "sec-fetch-dest":  "document",
      "sec-fetch-mode":  "navigate",
      "sec-fetch-site":  "none",
      "sec-fetch-user":  "?1",
      "Upgrade-Insecure-Requests": "1",
    };

    // Fetch HTML search page
    let resp;
    try {
      resp = await fetch(searchUrl, {
        headers,
        redirect: "follow",
        cf: { cacheEverything: false },
      });
    } catch (err) {
      return json({ error: "fetch_failed", detail: String(err) }, 502);
    }

    if (!resp.ok) {
      const snippet = await resp.text().catch(() => "").then(t => t.slice(0, 300));
      return json({ error: `woolworths_${resp.status}`, snippet }, 502);
    }

    const html = await resp.text();

    // Extract __NEXT_DATA__ embedded JSON
    const match = html.match(/<script id="__NEXT_DATA__" type="application\/json">([\s\S]*?)<\/script>/);
    if (!match) {
      // Return diagnostic snippet to help debug
      return json({
        error: "no_next_data",
        html_len: html.length,
        snippet: html.slice(0, 500),
      }, 502);
    }

    let nextData;
    try {
      nextData = JSON.parse(match[1]);
    } catch (e) {
      return json({ error: "json_parse_failed", detail: String(e) }, 502);
    }

    // Navigate to product list — path varies by Next.js version
    const products = extractProducts(nextData, limit);

    // Return in same format as the JSON API so Railway app needs no changes
    return json({ Products: [{ Products: products }] });
  },
};

function extractProducts(nextData, limit) {
  // Try common paths where Woolworths embeds product search results
  const candidates = [
    nextData?.props?.pageProps?.searchResults?.Products,
    nextData?.props?.pageProps?.initialState?.search?.products?.items,
    nextData?.props?.pageProps?.products,
  ].filter(Boolean);

  for (const list of candidates) {
    const flat = Array.isArray(list) ? list : Object.values(list);
    const mapped = flat.slice(0, limit).map(mapProduct).filter(Boolean);
    if (mapped.length > 0) return mapped;
  }

  // Deep search: walk the object tree looking for arrays of product-shaped items
  const found = [];
  deepSearch(nextData, found, limit);
  return found.slice(0, limit);
}

function mapProduct(p) {
  // Handle both flat products and bundled {Products:[...]} shape
  const item = p?.Products?.[0] ?? p;
  if (!item || !item.Name) return null;
  return {
    Stockcode: String(item.Stockcode ?? item.stockcode ?? ""),
    Name:  item.Name  ?? item.name  ?? "",
    Price: item.Price ?? item.price ?? item.InstorePrice ?? null,
    CupString: item.CupString ?? item.cupString ?? null,
    IsOnSpecial: item.IsOnSpecial ?? item.isOnSpecial ?? false,
    WasPrice: item.WasPrice ?? item.wasPrice ?? null,
    ImageUrl: item.MediumImageFile ?? item.mediumImageFile ?? null,
  };
}

function deepSearch(obj, found, limit, depth = 0) {
  if (depth > 8 || found.length >= limit) return;
  if (Array.isArray(obj)) {
    // Check if this looks like a product array
    if (obj.length > 0 && obj[0]?.Name && obj[0]?.Price !== undefined) {
      for (const item of obj) {
        const mapped = mapProduct(item);
        if (mapped && mapped.Name) found.push(mapped);
        if (found.length >= limit) return;
      }
    } else {
      for (const item of obj) deepSearch(item, found, limit, depth + 1);
    }
  } else if (obj && typeof obj === "object") {
    for (const v of Object.values(obj)) deepSearch(v, found, limit, depth + 1);
  }
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
  });
}
