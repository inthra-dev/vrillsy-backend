import { NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "../../../auth-options";
import { signBackendJwt } from "../../../lib/jwt";

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user && process.env.FEATURE_GUEST_UPLOAD !== "true") {
    return NextResponse.json({ error: "Auth required" }, { status: 401 });
  }
  const userId = (session?.user as any)?.id ?? "guest";
  const email = session?.user?.email ?? "";
  const token = await signBackendJwt({ sub: userId, email });
  const r = await fetch(`${process.env.BACKEND_INTERNAL_URL}/health`, {
    headers: {
      "X-User-Id": userId,
      "X-User-Email": email,
      "Authorization": `Bearer ${token}`
    },
  });
  return NextResponse.json({ ok: r.ok });
}
