import { SignJWT } from "jose";
const enc = new TextEncoder();
export async function signBackendJwt(payload: Record<string, any>) {
  const secret = process.env.NEXTAUTH_SECRET || process.env.AUTH_SECRET || "";
  const key = enc.encode(secret);
  const now = Math.floor(Date.now()/1000);
  return await new SignJWT(payload)
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setIssuedAt(now)
    .setExpirationTime(now + 300)
    .sign(key);
}
