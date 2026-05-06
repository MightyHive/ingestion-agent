import { withAuth } from "next-auth/middleware"

export default withAuth(
  function middleware(req) {
    const token = req.nextauth.token
    if (token && req.nextUrl.pathname.startsWith("/login")) {
      return Response.redirect(new URL("/", req.url))
    }
  },
  {
    callbacks: {
      authorized: ({ token, req }) => {
        if (req.nextUrl.pathname.startsWith("/login")) return true
        return !!token
      },
    },
    pages: {
      signIn: "/login",
    },
  }
)

export const config = {
  matcher: [
    "/((?!api/auth|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
}
