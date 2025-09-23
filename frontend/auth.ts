import NextAuth from "next-auth";
import GoogleProvider from "next-auth/providers/google";

export default NextAuth({
  session: {
    strategy: "jwt",
  },
  providers: [
    GoogleProvider({
      clientId: process.env.AUTH_GOOGLE_ID || "",
      clientSecret: process.env.AUTH_GOOGLE_SECRET || "",
    }),
  ],
  callbacks: {
    async jwt({ token, account, profile }) {
      const sub = (profile as any)?.sub ?? token.sub;
      if (sub) (token as any).uid = sub;
      if ((profile as any)?.email && !token.email) token.email = (profile as any).email;
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        (session.user as any).id = (token as any).uid ?? token.sub ?? null;
        session.user.email = (token.email as string | undefined) ?? session.user.email ?? null;
      }
      return session;
    },
  },
});
