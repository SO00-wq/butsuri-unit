// tanbutsu.com 以外（workers.dev や www.）で開かれたら、同じページの tanbutsu.com へ 301 で転送する。
// あわせて、安全のためのヘッダーとキャッシュの設定をつける。
const CANONICAL_HOST = "tanbutsu.com";

const SECURITY_HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Frame-Options": "SAMEORIGIN",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Strict-Transport-Security": "max-age=31536000",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname !== CANONICAL_HOST) {
      url.protocol = "https:";
      url.hostname = CANONICAL_HOST;
      url.port = "";
      return Response.redirect(url.toString(), 301);
    }

    const res = await env.ASSETS.fetch(request);
    const out = new Response(res.body, res);
    for (const [k, v] of Object.entries(SECURITY_HEADERS)) out.headers.set(k, v);

    const p = url.pathname;
    if (p.startsWith("/assets/") && url.searchParams.has("v")) {
      // site.css?v=13 のように版番号つきのものは、中身が変わるたびに URL も変わるので長く保存してよい
      out.headers.set("Cache-Control", "public, max-age=31536000, immutable");
    } else if (/\.(png|svg|ico)$/.test(p)) {
      out.headers.set("Cache-Control", "public, max-age=604800");
    }
    return out;
  },
};
