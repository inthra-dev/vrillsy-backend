import './globals.css';

export const metadata = {
  title: 'Reels Generator',
  description: 'Next.js ↔ FastAPI ↔ Celery demo',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pl">
      <body style={{ margin: 0, minHeight: '100vh', background: '#0b0b0b', color: '#eaeaea' }}>
        {children}
      </body>
    </html>
  );
}
