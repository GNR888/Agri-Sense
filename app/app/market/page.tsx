'use client';

import { Suspense, useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import {
  ComposedChart, Line, Area, XAxis, YAxis, Tooltip,
  CartesianGrid, ReferenceLine, ResponsiveContainer, Legend,
  BarChart, Bar, Cell, LabelList,
} from 'recharts';
import { fetchMarketPrices } from '@/lib/api';
import type { MarketPricesResponse } from '@/lib/api';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CROPS = ['rice_paddy', 'coffee_green', 'cashew_raw', 'pepper_black', 'maize'] as const;
type Crop = (typeof CROPS)[number];

const CROP_LABELS: Record<Crop, string> = {
  rice_paddy:   'Rice (Lúa)',
  coffee_green: 'Coffee (Cà phê)',
  cashew_raw:   'Cashew (Hạt điều)',
  pepper_black: 'Pepper (Hồ tiêu)',
  maize:        'Maize (Ngô)',
};

const CROP_COLORS: Record<Crop, string> = {
  rice_paddy:   '#10b981',
  coffee_green: '#8b5cf6',
  cashew_raw:   '#f59e0b',
  pepper_black: '#ef4444',
  maize:        '#3b82f6',
};

// Mirrors price_forecast.py — kept in sync manually for client-side comparison chart
const SEASONAL_MULTIPLIERS: Record<Crop, Record<number, number>> = {
  rice_paddy:   { 1:1.08, 2:1.10, 3:1.05, 4:1.00, 5:0.97, 6:0.94, 7:0.93, 8:0.95, 9:0.98, 10:1.02, 11:1.05, 12:1.06 },
  coffee_green: { 1:0.98, 2:0.96, 3:0.97, 4:1.00, 5:1.02, 6:1.04, 7:1.05, 8:1.06, 9:1.05, 10:1.02, 11:0.99, 12:0.98 },
  pepper_black: { 1:1.05, 2:1.06, 3:1.04, 4:1.00, 5:0.98, 6:0.96, 7:0.95, 8:0.97, 9:1.00, 10:1.02, 11:1.03, 12:1.05 },
  maize:        { 1:1.04, 2:1.05, 3:1.03, 4:1.00, 5:0.97, 6:0.95, 7:0.94, 8:0.96, 9:0.99, 10:1.01, 11:1.02, 12:1.03 },
  cashew_raw:   { 1:0.97, 2:0.95, 3:0.98, 4:1.03, 5:1.06, 6:1.05, 7:1.03, 8:1.00, 9:0.99, 10:0.98, 11:0.97, 12:0.97 },
};

const BASE_PRICES_VND_PER_TONNE: Record<Crop, number> = {
  rice_paddy:   7_200_000,
  coffee_green: 63_000_000,
  cashew_raw:   31_500_000,
  pepper_black: 75_000_000,
  maize:        7_300_000,
};

const TYPICAL_YIELDS_T_HA: Record<Crop, number> = {
  rice_paddy:   5.5,
  coffee_green: 2.8,
  cashew_raw:   1.2,
  pepper_black: 1.5,
  maize:        4.8,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatMonth(iso: string): string {
  const parts = iso.split('-');
  const names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${names[parseInt(parts[1], 10) - 1]} '${parts[0].slice(2)}`;
}

function fmtVnd(n: number): string {
  return '₫' + Math.round(n).toLocaleString('en-US');
}

function fmtVndShort(n: number): string {
  if (n >= 1_000_000_000) return `₫${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000)     return `₫${(n / 1_000_000).toFixed(0)}M`;
  return fmtVnd(n);
}

function driverIcon(text: string): string {
  const t = text.toLowerCase();
  if (/export|import|demand|buyer|philippine|india|eu\b/.test(t)) return '🌍';
  if (/harvest|supply|surplus|output|process|bottleneck|glut/.test(t)) return '📦';
  if (/rain|flood|drought|salinity|el ni|tidal|weather|sea-level/.test(t)) return '🌧';
  return '🌡';
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

interface TooltipEntry { name: string; value: number; color?: string }

function PriceTooltip({
  active, payload, label,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const hist = payload.find(p => p.name === 'historical');
  const fore = payload.find(p => p.name === 'forecast');
  const upper = payload.find(p => p.name === 'upper');
  const lower = payload.find(p => p.name === 'lower');
  return (
    <div className="bg-white border border-stone-200 rounded-lg shadow-sm px-3 py-2 text-xs space-y-1 min-w-[180px]">
      <p className="font-semibold text-stone-700">{label}</p>
      {hist  && <p className="text-emerald-700">Historical: {fmtVnd(hist.value)}/tonne</p>}
      {fore  && <p className="text-emerald-500">Forecast: {fmtVnd(fore.value)}/tonne</p>}
      {upper && lower && (
        <p className="text-stone-400">Range: {fmtVnd(lower.value)}–{fmtVnd(upper.value)}/tonne</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Comparison bar tooltip
// ---------------------------------------------------------------------------

function BarTooltip({
  active, payload, label,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-stone-200 rounded-lg shadow-sm px-3 py-2 text-xs space-y-1">
      <p className="font-semibold text-stone-700">{label}</p>
      <p className="text-stone-600">Revenue: {fmtVnd(payload[0].value)}/ha</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main content (uses useSearchParams — must be inside Suspense)
// ---------------------------------------------------------------------------

function MarketPageContent() {
  const searchParams = useSearchParams();
  const paramCrop = searchParams.get('crop');
  const [selectedCrop, setSelectedCrop] = useState<Crop>(
    CROPS.includes(paramCrop as Crop) ? (paramCrop as Crop) : 'rice_paddy',
  );

  // Keep selected crop in sync when navigating from dashboard cards
  useEffect(() => {
    const c = searchParams.get('crop');
    if (c && CROPS.includes(c as Crop)) setSelectedCrop(c as Crop);
  }, [searchParams]);

  const { data, isLoading, error } = useQuery<MarketPricesResponse>({
    queryKey: ['market-prices', selectedCrop],
    queryFn: () => fetchMarketPrices(selectedCrop),
  });

  // Chart data: historical + forecast merged into one flat array
  const chartData = useMemo(() => {
    if (!data) return [];
    return [
      ...data.historical.map(h => ({ month: formatMonth(h.month), historical: h.price })),
      ...data.forecast.map(f => ({
        month: formatMonth(f.month),
        forecast: f.price,
        upper: f.upper_bound,
        lower: f.lower_bound,
      })),
    ];
  }, [data]);

  // Label for the "today" reference line (last historical month)
  const todayLabel = data ? formatMonth(data.historical[data.historical.length - 1].month) : '';

  // Comparison bar chart: month_3 price × typical yield for all 5 crops
  const comparisonData = useMemo(() => {
    const today = new Date();
    const m3 = ((today.getMonth() + 3) % 12) + 1; // calendar month 3 months from now
    return CROPS.map(crop => ({
      name: CROP_LABELS[crop].split(' ')[0], // short name
      fullName: CROP_LABELS[crop],
      revenue: Math.round(
        BASE_PRICES_VND_PER_TONNE[crop] * (SEASONAL_MULTIPLIERS[crop][m3] ?? 1.0) * TYPICAL_YIELDS_T_HA[crop],
      ),
      color: CROP_COLORS[crop],
    }));
  }, []);

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

      <main className="flex-1 px-4 py-6 w-full max-w-6xl mx-auto flex flex-col gap-6">
        <div>
          <h2 className="text-base font-semibold text-stone-800 mb-1">Market Intelligence</h2>
          <p className="text-sm text-stone-500">Historical and 6-month price forecasts for major Vietnamese crops. Source: hardcoded GSO farmgate data with seasonal patterns.</p>
        </div>

        {/* Crop selector */}
        <div className="flex gap-2 flex-wrap">
          {CROPS.map(crop => (
            <button
              key={crop}
              onClick={() => setSelectedCrop(crop)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors border ${
                selectedCrop === crop
                  ? 'bg-emerald-700 text-white border-emerald-700'
                  : 'bg-white text-stone-600 border-stone-200 hover:border-emerald-400 hover:text-emerald-700'
              }`}
            >
              {CROP_LABELS[crop]}
            </button>
          ))}
        </div>

        {/* Summary chips */}
        {data && (
          <div className="flex gap-3 flex-wrap">
            <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white border border-stone-200 text-xs font-medium text-stone-700 shadow-sm">
              📊 Volatility: <span className={`font-semibold ${data.volatility_label === 'High' ? 'text-red-600' : data.volatility_label === 'Moderate' ? 'text-amber-600' : 'text-emerald-600'}`}>{data.volatility_label}</span>
            </span>
            <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white border border-stone-200 text-xs font-medium text-stone-700 shadow-sm">
              📈 Best month to sell: <span className="font-semibold text-emerald-700">{data.best_selling_months[0]}</span>
            </span>
            <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white border border-stone-200 text-xs font-medium text-stone-700 shadow-sm">
              📉 Avoid selling: <span className="font-semibold text-red-600">{data.avoid_selling_months[0]}</span>
            </span>
          </div>
        )}

        {/* Price chart */}
        <div className="bg-white rounded-xl border border-stone-200 shadow-sm p-5">
          <h3 className="text-sm font-semibold text-stone-800 mb-4">
            {CROP_LABELS[selectedCrop]} — Price Forecast (VND/tonne)
          </h3>

          {isLoading && (
            <div className="h-64 flex items-center justify-center text-stone-400 text-sm">Loading…</div>
          )}
          {error && (
            <div className="h-64 flex items-center justify-center text-red-500 text-sm">
              Failed to load market data.
            </div>
          )}
          {data && chartData.length > 0 && (
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis
                  dataKey="month"
                  tick={{ fontSize: 10, fill: '#6b7280' }}
                  angle={-40}
                  textAnchor="end"
                  interval={1}
                  height={50}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: '#6b7280' }}
                  tickFormatter={fmtVndShort}
                  width={70}
                />
                <Tooltip content={(props) => <PriceTooltip {...(props as unknown as { active?: boolean; payload?: TooltipEntry[]; label?: string })} />} />
                <Legend
                  formatter={(value: string) => value === 'historical' ? 'Historical' : value === 'forecast' ? 'Forecast' : ''}
                  wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                />

                {/* Confidence band — erase technique */}
                <Area type="monotone" dataKey="upper" stroke="none" fill={CROP_COLORS[selectedCrop]} fillOpacity={0.15} legendType="none" name="upper" />
                <Area type="monotone" dataKey="lower" stroke="none" fill="white" fillOpacity={1} legendType="none" name="lower" />

                {/* Historical line */}
                <Line
                  type="monotone"
                  dataKey="historical"
                  name="historical"
                  stroke="#047857"
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                />

                {/* Forecast line (dashed) */}
                <Line
                  type="monotone"
                  dataKey="forecast"
                  name="forecast"
                  stroke={CROP_COLORS[selectedCrop]}
                  strokeWidth={2}
                  strokeDasharray="6 3"
                  dot={false}
                  connectNulls={false}
                />

                {/* Today divider */}
                {todayLabel && (
                  <ReferenceLine
                    x={todayLabel}
                    stroke="#9ca3af"
                    strokeDasharray="4 2"
                    label={{ value: 'Today', position: 'insideTopRight', fontSize: 9, fill: '#9ca3af' }}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Bottom section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Key drivers */}
          <div className="bg-white rounded-xl border border-stone-200 shadow-sm p-5">
            <h3 className="text-sm font-semibold text-stone-800 mb-3">What&apos;s moving this price</h3>
            {isLoading && <p className="text-stone-400 text-sm">Loading…</p>}
            {data && (
              <ul className="space-y-2.5">
                {data.key_drivers.map((driver, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-stone-600">
                    <span className="text-base leading-tight shrink-0">{driverIcon(driver)}</span>
                    <span>{driver}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-stone-400 mt-4">Source: hardcoded_gso · Seasonal patterns 2018–2024 avg.</p>
          </div>

          {/* Comparison bar chart */}
          <div className="bg-white rounded-xl border border-stone-200 shadow-sm p-5">
            <h3 className="text-sm font-semibold text-stone-800 mb-1">Expected revenue per hectare (3-month forecast)</h3>
            <p className="text-xs text-stone-400 mb-4">Price × typical yield — illustrative, not location-specific</p>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart
                data={comparisonData}
                layout="vertical"
                margin={{ top: 0, right: 70, left: 8, bottom: 0 }}
              >
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 11, fill: '#374151' }}
                  width={52}
                />
                <Tooltip content={(props) => <BarTooltip {...(props as unknown as { active?: boolean; payload?: TooltipEntry[]; label?: string })} />} />
                <Bar dataKey="revenue" radius={[0, 4, 4, 0]}>
                  {comparisonData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                  <LabelList
                    dataKey="revenue"
                    position="right"
                    formatter={(v: unknown) => fmtVndShort(v as number)}
                    style={{ fontSize: 10, fill: '#6b7280' }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </main>

      <footer className="text-center text-xs text-stone-400 px-4 py-4 border-t border-stone-200 bg-white">
        MVP demo — price forecasts are rule-based seasonal estimates. Not financial advice.
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export — wraps content in Suspense (required for useSearchParams)
// ---------------------------------------------------------------------------

export default function MarketPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-stone-50 flex items-center justify-center">
          <p className="text-stone-400 text-sm">Loading market data…</p>
        </div>
      }
    >
      <MarketPageContent />
    </Suspense>
  );
}
