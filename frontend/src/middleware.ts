import { NextResponse, type NextRequest } from "next/server";

// First-line redirect for signed-out visitors. This is navigation only;
// authorization is decided by the backend on every API call.
const SESSION_COOKIE = "agriflow_session";
const PUBLIC = ["/login", "/register"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const hasSession = req.cookies.has(SESSION_COOKIE);
  const isPublic = PUBLIC.some((p) => pathname.startsWith(p));

  if (!hasSession && !isPublic) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname)}`;
    return NextResponse.redirect(url);
  }
  if (pathname === "/") {
    return NextResponse.redirect(new URL("/dashboard", req.url));
  }
  return NextResponse.next();
}

export const config = {
  // Skip API calls, Next internals and static assets (artwork must load on the sign-in page).
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|art/|.*\\.(?:svg|png|jpg|jpeg|webp|ico|woff2?)$).*)"],
};
