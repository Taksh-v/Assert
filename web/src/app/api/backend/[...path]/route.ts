import { NextRequest } from "next/server";
import { getServerBackendUrl } from "@/lib/config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type BackendRouteContext = {
  params: Promise<{ path?: string[] }>;
};

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-encoding",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function buildBackendUrl(pathSegments: string[] = [], search: string) {
  const backendBase = getServerBackendUrl();
  const backendPath = pathSegments.map(encodeURIComponent).join("/");
  return `${backendBase}/api/${backendPath}${search}`;
}

function buildForwardHeaders(request: NextRequest) {
  const headers = new Headers(request.headers);

  const incomingAuth = request.headers.get("authorization");
  console.log(`[Proxy] Authorization header present: ${!!incomingAuth} (len: ${incomingAuth?.length || 0})`);
  
  if (incomingAuth) {
    headers.set("x-user-authorization", incomingAuth);
    console.log("[Proxy] Set x-user-authorization from incoming authorization");
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
    headers.set("authorization", `Bearer ${hfToken}`);
  }

  return headers;
}

function buildResponseHeaders(upstreamHeaders: Headers) {
  const headers = new Headers(upstreamHeaders);

  for (const header of HOP_BY_HOP_HEADERS) {
    headers.delete(header);
  }

  headers.set("cache-control", "no-store");
  return headers;
}

async function proxyBackend(request: NextRequest, context: BackendRouteContext) {
  try {
    const { path = [] } = await context.params;
    const targetUrl = buildBackendUrl(path, request.nextUrl.search);
    const method = request.method.toUpperCase();
    const hasBody = method !== "GET" && method !== "HEAD";

    console.log(`[Proxy] Request ${method} ${targetUrl} (hasBody: ${hasBody})`);

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

      console.log(`[Proxy] Response status from backend: ${upstream.status} ${upstream.statusText}`);

      return new Response(upstream.body, {
        status: upstream.status,
        statusText: upstream.statusText,
        headers: buildResponseHeaders(upstream.headers),
      });
    } catch (innerError) {
      console.error(`[Proxy] Inner fetch error for ${targetUrl}:`, innerError);
      const message = innerError instanceof Error ? innerError.message : "Unknown backend proxy error";
      return Response.json(
        {
          detail: "Unable to reach Assest backend.",
          message,
        },
        { status: 502, headers: { "cache-control": "no-store" } },
      );
    }
  } catch (outerError) {
    console.error("[Proxy] Outer parameter/setup error:", outerError);
    return Response.json(
      {
        detail: "Proxy setup error.",
        message: outerError instanceof Error ? outerError.message : String(outerError),
      },
      { status: 500, headers: { "cache-control": "no-store" } },
    );
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

