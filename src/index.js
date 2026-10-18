// タンブツ：正式な住所 tanbutsu.com 以外（古い workers.dev や www つき）へのアクセスを、
// 同じページの tanbutsu.com へ 301 で転送する。tanbutsu.com へのアクセスはそのままページを返す。
const CANONICAL_HOST = "tanbutsu.com";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname !== CANONICAL_HOST) {
      url.protocol = "https:";
      url.hostname = CANONICAL_HOST;
      url.port = "";
      return Response.redirect(url.toString(), 301);
    }
    return env.ASSETS.fetch(request);
  },
};
