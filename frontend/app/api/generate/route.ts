import { NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "../../../auth-options";
import { signBackendJwt } from "../../../lib/jwt";

export async function POST(req: Request) {
  const session = await getServerSession(authOptions);
  const guestAllowed = process.env.FEATURE_GUEST_UPLOAD === "true";
  if (!session?.user && !guestAllowed) {
    return NextResponse.json({ error: "Auth required" }, { status: 401 });
  }
  const userId = (session?.user as any)?.id ?? "guest";
  const email = session?.user?.email ?? "";
  const token = await signBackendJwt({ sub: userId, email });

  const url = `${process.env.BACKEND_INTERNAL_URL}/generate`;
  const body = await req.arrayBuffer();
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": req.headers.get("content-type") ?? "application/json",
      "X-User-Id": userId,
      "X-User-Email": email,
      "Authorization": `Bearer ${token}`
    },
    body,
  });

  const buf = await res.arrayBuffer();
  return new NextResponse(buf, { status: res.status, headers: res.headers });
}
