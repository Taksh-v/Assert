import { NextRequest } from "next/server";
import { getServerBackendUrl } from "@/lib/config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const IS_DEV = process.env.NODE_ENV !== "production";

type BackendRouteContext = {
  params: Promise<{ path?: string[] }>;
};

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-encoding",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "upgrade",
]);

function buildBackendUrl(pathSegments: string[] = [], search: string, request: NextRequest) {
  const backendBase = getServerBackendUrl();
  const backendPath = pathSegments.map(encodeURIComponent).join("/");
  
  // EXTRACTION: Get user token from ANY incoming header
  const auth = request.headers.get("authorization") || 
               request.headers.get("x-supabase-token") || 
               request.headers.get("x-access-token") ||
               request.headers.get("token");

  let tokenParam = "";
  if (auth) {
    const token = auth.startsWith("Bearer ") ? auth.slice(7) : auth;
    if (IS_DEV) console.log(`[Proxy] Forwarding token (start: ${token.slice(0, 10)}...) as query params`);
    const separator = search ? "&" : (search.includes("?") ? "&" : "?");
    tokenParam = `${separator}supabase_token=${encodeURIComponent(token)}&access_token=${encodeURIComponent(token)}`;
  }

  return `${backendBase}/api/${backendPath}${search}${tokenParam}`;
}

function buildForwardHeaders(request: NextRequest) {
  const headers = new Headers(request.headers);

  // Redundantly forward all auth headers
  const auth = request.headers.get("authorization");
  if (auth) {
    headers.set("x-user-authorization", auth);
    const clean = auth.startsWith("Bearer ") ? auth.slice(7) : auth;
    if (IS_DEV) console.log(`[Proxy] Incoming User Token (start: ${clean.slice(0, 10)}...)`);
  }
  
  const supToken = request.headers.get("x-supabase-token");
  if (supToken) {
      headers.set("x-supabase-token", supToken);
      if (IS_DEV) console.log(`[Proxy] Incoming Custom Header Token (start: ${supToken.slice(0, 10)}...)`);
  }

  for (const header of HOP_BY_HOP_HEADERS) {
    headers.delete(header);
  }

  headers.set("x-forwarded-host", request.headers.get("host") || "");
  headers.set("x-forwarded-proto", request.nextUrl.protocol.replace(":", ""));

  const internalApiKey = process.env.ASSEST_BACKEND_API_KEY;
  if (internalApiKey && !headers.has("x-api-key")) {
    headers.set("x-api-key", internalApiKey);
  }

  const hfToken = process.env.HF_TOKEN;
  if (hfToken) {
    if (IS_DEV) console.log(`[Proxy] Injecting HF_TOKEN (start: ${hfToken.slice(0, 10)}...)`);
    headers.set("authorization", `Bearer ${hfToken}`);
  }

  return headers;
}

function buildResponseHeaders(upstreamHeaders: Headers) {
  const headers = new Headers(upstreamHeaders);
  for (const header of HOP_BY_HOP_HEADERS) {
    headers.delete(header);
  }
  headers.delete("content-length");
  headers.delete("transfer-encoding");
  headers.set("cache-control", "no-store");
  return headers;
}

async function proxyBackend(request: NextRequest, context: BackendRouteContext) {
  try {
    const { path = [] } = await context.params;
    const targetUrl = buildBackendUrl(path, request.nextUrl.search, request);
    const method = request.method.toUpperCase();
    const hasBody = method !== "GET" && method !== "HEAD";

    if (IS_DEV) console.log(`[Proxy] ${method} -> ${targetUrl}`);

    let bodyBuffer: ArrayBuffer | undefined = undefined;
    if (hasBody) {
      bodyBuffer = await request.arrayBuffer();
    }

    try {
      const upstream = await fetch(targetUrl, {
        method,
        headers: buildForwardHeaders(request),
        body: bodyBuffer,
        cache: "no-store",
      });

      if (IS_DEV) console.log(`[Proxy] Backend Response: ${upstream.status}`);

      return new Response(upstream.body, {
        status: upstream.status,
        statusText: upstream.statusText,
        headers: buildResponseHeaders(upstream.headers),
      });
    } catch (innerError) {
      console.error(`[Proxy] Fetch error:`, innerError);
      return Response.json({ detail: "Backend unreachable." }, { status: 502 });
    }
  } catch (outerError) {
    console.error("[Proxy] Setup error:", outerError);
    return Response.json({ detail: "Proxy error." }, { status: 500 });
  }
}

export function OPTIONS() {
  return new Response(null, {
    status: 204,
    headers: {
      allow: "GET,POST,PUT,PATCH,DELETE,OPTIONS",
      "cache-control": "no-store",
    },
  });
}

export const GET = proxyBackend;
export const POST = proxyBackend;
export const PUT = proxyBackend;
export const PATCH = proxyBackend;
export const DELETE = proxyBackend;
