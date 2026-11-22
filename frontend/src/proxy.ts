import { NextResponse, type NextRequest } from "next/server";

// Cheap gate: without a session cookie, send page requests to /login.
// The API itself validates the cookie (or Bearer token) on every request.
export function proxy(req: NextRequest) {
  if (!req.cookies.has("th_session")) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(req.nextUrl.pathname + req.nextUrl.search)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Everything except the login page, API/docs proxies, runs' reports (a signed link) and static assets.
  matcher: ["/((?!login|invite/|api|docs|openapi.json|r/|_next|favicon.ico|.*\\.[a-z0-9]+$).*)"],
};
