import type { Metadata } from 'next';
import { Geist } from 'next/font/google';
import './globals.css';
import QueryProvider from '@/components/QueryProvider';

const geist = Geist({ subsets: ['latin'], variable: '--font-geist-sans' });

export const metadata: Metadata = {
  title: 'Agri-Sense Vietnam',
  description: 'Crop recommendations for Vietnamese farmers powered by satellite, soil, and climate data.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={`${geist.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
