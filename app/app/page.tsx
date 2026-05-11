'use client';

import dynamic from 'next/dynamic';
import { useState } from 'react';
import Link from 'next/link';
import RecommendPanel from '@/components/RecommendPanel';

const VietnamMap = dynamic(() => import('@/components/VietnamMap'), { ssr: false });

export default function Page() {
  const [selectedLat, setSelectedLat] = useState<number | null>(null);
  const [selectedLon, setSelectedLon] = useState<number | null>(null);

  return (
    <div className="min-h-screen bg-stone-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-stone-200 px-6 py-4 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-emerald-800">Agri-Sense Vietnam</h1>
            <p className="text-sm text-stone-500 mt-0.5">
              Crop recommendations for Vietnamese farmers, powered by satellite, soil, and climate data.
            </p>
          </div>
          <nav className="flex gap-3 shrink-0 pt-0.5">
            <Link href="/" className="text-sm font-medium text-emerald-700 hover:text-emerald-900 underline-offset-2 hover:underline">
              Dashboard
            </Link>
            <Link href="/market" className="text-sm font-medium text-emerald-700 hover:text-emerald-900 underline-offset-2 hover:underline">
              Market Prices
            </Link>
          </nav>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 px-4 py-6 w-full max-w-7xl mx-auto">
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Map — 60% */}
          <div
            className="lg:w-[60%] rounded-xl overflow-hidden border border-stone-200 shadow-sm"
            style={{ minHeight: 480 }}
          >
            <VietnamMap
              onLocationSelect={(lat, lon) => {
                setSelectedLat(lat);
                setSelectedLon(lon);
              }}
              selectedLat={selectedLat}
              selectedLon={selectedLon}
            />
          </div>

          {/* Recommendation panel — 40% */}
          <div className="lg:w-[40%] bg-white rounded-xl border border-stone-200 shadow-sm p-5 overflow-y-auto max-h-[80vh]">
            <h2 className="text-base font-semibold text-stone-800 mb-4">Crop Recommendations</h2>
            <RecommendPanel lat={selectedLat} lon={selectedLon} />
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="text-center text-xs text-stone-400 px-4 py-4 border-t border-stone-200 bg-white">
        MVP demo — predictions are illustrative. Not a substitute for local agronomic advice.
      </footer>
    </div>
  );
}
