'use client';

import { useState, useCallback, useMemo } from 'react';
import Link from 'next/link';
import {
  LineChart, Line, ResponsiveContainer,
  PieChart, Pie, Cell, Tooltip,
} from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { fetchProvinces, fetchRecommendations, fetchSoilData } from '@/lib/api';
import type {
  PlanningMode, CropRecommendation, FertiliserRecommendation, FertiliserSchedule,
  PriceForecast, PriceTrend, FarmPlan, RecommendResponse, SeasonInfo,
  TransitionInfo, Province, SoilData, SoilOverrides, NutrientStatus,
  FarmingMethods, IrrigationStage, HarvestTiming, DataFreshness,
} from '@/lib/api';

// ---------------------------------------------------------------------------
// Season calendar constants (mirrors src/agri_sense/utils/seasons.py)
// Each array entry is the season for months Jan–Dec (index 0–11),
// probed at the 15th of each month.
// ---------------------------------------------------------------------------

const MONTH_TO_SEASON: Record<string, string[]> = {
  mekong_delta: [
    'Đông Xuân', 'Đông Xuân', 'Đông Xuân',                     // Jan Feb Mar
    'Hè Thu',    'Hè Thu',    'Hè Thu',    'Hè Thu',            // Apr May Jun Jul
    'Mùa',       'Mùa',       'Mùa',                            // Aug Sep Oct
    'Đông Xuân', 'Đông Xuân',                                   // Nov Dec
  ],
  red_river_delta: [
    'Đông Xuân', 'Đông Xuân', 'Đông Xuân', 'Đông Xuân', 'Đông Xuân', // Jan–May
    'Mùa',       'Mùa',       'Mùa',       'Mùa',       'Mùa',       // Jun–Oct
    'Đông Xuân', 'Đông Xuân',                                          // Nov Dec
  ],
  central_highlands: Array(12).fill('annual') as string[],
};

type Suitability = 'optimal' | 'acceptable' | 'none';

const CROP_SUITABILITY: Record<string, Record<string, Suitability>> = {
  rice_paddy:   { 'Đông Xuân': 'optimal',    'Hè Thu': 'acceptable', 'Mùa': 'acceptable', annual: 'none' },
  coffee_green: { 'Đông Xuân': 'none',        'Hè Thu': 'none',       'Mùa': 'none',       annual: 'optimal' },
  cashew_raw:   { 'Đông Xuân': 'none',        'Hè Thu': 'none',       'Mùa': 'none',       annual: 'optimal' },
  pepper_black: { 'Đông Xuân': 'acceptable',  'Hè Thu': 'none',       'Mùa': 'none',       annual: 'optimal' },
  maize:        { 'Đông Xuân': 'acceptable',  'Hè Thu': 'optimal',    'Mùa': 'none',       annual: 'none' },
};

// ---------------------------------------------------------------------------
// Display constants
// ---------------------------------------------------------------------------

const CROP_LABELS: Record<string, string> = {
  rice_paddy:   'Rice (Lúa)',
  coffee_green: 'Coffee (Cà phê)',
  cashew_raw:   'Cashew (Hạt điều)',
  pepper_black: 'Pepper (Hồ tiêu)',
  maize:        'Maize (Ngô)',
};

const CROP_COLORS: Record<string, string> = {
  rice_paddy:   '#10b981',
  coffee_green: '#8b5cf6',
  cashew_raw:   '#f59e0b',
  pepper_black: '#ef4444',
  maize:        '#3b82f6',
};

const CONFIDENCE_BADGE: Record<string, string> = {
  high:   'bg-emerald-100 text-emerald-800',
  medium: 'bg-amber-100 text-amber-800',
  low:    'bg-red-100 text-red-800',
};

const CONFIDENCE_BAR: Record<string, string> = {
  high:   'bg-emerald-500',
  medium: 'bg-amber-500',
  low:    'bg-red-500',
};

const TREND_COLOR: Record<PriceTrend, string> = {
  rising:  '#10b981',
  stable:  '#6b7280',
  falling: '#ef4444',
};

const TREND_ARROW: Record<PriceTrend, string> = {
  rising:  '↑ Rising',
  stable:  '→ Stable',
  falling: '↓ Falling',
};

const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const MONTHS_FULL  = ['January','February','March','April','May','June','July','August','September','October','November','December'];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtVnd(n: number): string {
  return new Intl.NumberFormat('vi-VN').format(n);
}

function fmtMillions(n: number): string {
  return (n / 1_000_000).toFixed(1) + 'M';
}

function nearestProvince(lat: number, lon: number, provinces: Province[]): Province | null {
  if (!provinces.length) return null;
  return provinces.reduce((best, p) => {
    const d = Math.hypot(p.lat - lat, p.lon - lon);
    const bestD = Math.hypot(best.lat - lat, best.lon - lon);
    return d < bestD ? p : best;
  });
}

function regionTypeFromProvince(p: Province | null): string {
  if (!p) return 'mekong_delta';
  const r = p.region.toLowerCase();
  if (r.includes('mekong'))      return 'mekong_delta';
  if (r.includes('red river'))   return 'red_river_delta';
  if (r.includes('highland'))    return 'central_highlands';
  if (r.includes('south-east'))  return 'central_highlands';
  return 'mekong_delta';
}

const TEXTURE_CLASSES = [
  'sand', 'loamy sand', 'sandy loam', 'loam', 'silt loam', 'silt',
  'sandy clay loam', 'clay loam', 'silty clay loam', 'sandy clay', 'silty clay', 'clay',
];

const STATUS_COLORS: Record<NutrientStatus, string> = {
  adequate:  'bg-emerald-100 text-emerald-800',
  deficient: 'bg-red-100 text-red-800',
  excess:    'bg-amber-100 text-amber-800',
};

const DATA_SOURCE_LABELS: Record<string, string> = {
  soilgrids:        'Source: SoilGrids 2.0',
  farmer_measured:  'Source: Farmer measurements',
  mixed:            'Source: SoilGrids + farmer measurements',
};

// ---------------------------------------------------------------------------
// YourLandPanel
// ---------------------------------------------------------------------------

interface SoilRowProps {
  label: string;
  value: string | number | null;
  unit?: string;
  hint?: string;
  editKey: keyof SoilOverrides;
  editType: 'number' | 'select';
  isOverridden: boolean;
  editingField: string | null;
  editValue: string;
  onEditStart: (key: string, currentVal: string) => void;
  onEditChange: (val: string) => void;
  onEditCommit: () => void;
  onReset: (key: keyof SoilOverrides) => void;
}

function SoilRow({
  label, value, unit, hint, editKey, editType, isOverridden,
  editingField, editValue, onEditStart, onEditChange, onEditCommit, onReset,
}: SoilRowProps) {
  const isEditing = editingField === editKey;
  const displayVal = value !== null && value !== undefined ? String(value) : '—';

  return (
    <tr className="border-b border-stone-50 last:border-0">
      <td className="py-2 text-xs text-stone-500 pr-3 whitespace-nowrap">{label}</td>
      <td className="py-2 text-xs font-mono text-stone-800 whitespace-nowrap">
        {isEditing ? (
          editType === 'select' ? (
            <select
              autoFocus
              value={editValue}
              onChange={(e) => onEditChange(e.target.value)}
              onBlur={onEditCommit}
              className="text-xs border border-emerald-400 rounded px-1 py-0.5 focus:outline-none"
            >
              {TEXTURE_CLASSES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          ) : (
            <input
              autoFocus
              type="number"
              step="0.1"
              value={editValue}
              onChange={(e) => onEditChange(e.target.value)}
              onBlur={onEditCommit}
              onKeyDown={(e) => e.key === 'Enter' && onEditCommit()}
              className="w-20 text-xs border border-emerald-400 rounded px-1 py-0.5 focus:outline-none font-mono"
            />
          )
        ) : (
          <span className={isOverridden ? 'text-emerald-700 font-semibold' : ''}>
            {displayVal}{unit ? ` ${unit}` : ''}
            {isOverridden && <span className="ml-1 text-emerald-500 text-[10px]">✎</span>}
          </span>
        )}
      </td>
      <td className="py-2 text-right whitespace-nowrap">
        <div className="flex items-center gap-1 justify-end">
          {!isEditing && (
            <button
              onClick={() => onEditStart(editKey, displayVal.replace(unit ? ` ${unit}` : '', ''))}
              className="text-[10px] text-stone-400 hover:text-emerald-600 border border-stone-200 hover:border-emerald-400 rounded px-1.5 py-0.5 transition-colors"
            >
              Edit
            </button>
          )}
          {isOverridden && !isEditing && (
            <button
              onClick={() => onReset(editKey)}
              className="text-[10px] text-stone-400 hover:text-red-500 border border-stone-200 hover:border-red-300 rounded px-1.5 py-0.5 transition-colors"
            >
              Reset
            </button>
          )}
          {hint && <span className="text-[10px] text-stone-400 hidden sm:inline">{hint}</span>}
        </div>
      </td>
    </tr>
  );
}

function HealthScoreBar({ score }: { score: number }) {
  const pct = Math.round((score / 10) * 100);
  const color =
    score >= 8 ? 'bg-emerald-500' :
    score >= 5 ? 'bg-amber-500'   :
    'bg-red-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 rounded-full bg-stone-100 overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono font-semibold text-stone-700 shrink-0">{score.toFixed(1)}/10</span>
    </div>
  );
}

function YourLandPanel({
  soilData,
  overrides,
  onOverride,
  onReset,
  provinceName,
  lat,
  lon,
  isLoading,
  dataSource,
}: {
  soilData: SoilData | undefined;
  overrides: SoilOverrides;
  onOverride: (key: keyof SoilOverrides, value: number | string) => void;
  onReset: (key: keyof SoilOverrides) => void;
  provinceName: string | null;
  lat: number;
  lon: number;
  isLoading: boolean;
  dataSource?: string;
}) {
  const [open, setOpen] = useState(true);
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');

  const handleEditStart = (key: string, currentVal: string) => {
    setEditingField(key);
    setEditValue(currentVal === '—' ? '' : currentVal);
  };

  const handleEditCommit = () => {
    if (editingField) {
      const key = editingField as keyof SoilOverrides;
      if (editValue.trim() !== '') {
        const parsed = key === 'texture_class' ? editValue : parseFloat(editValue);
        if (key !== 'texture_class' && isNaN(parsed as number)) {
          setEditingField(null);
          return;
        }
        onOverride(key, parsed as number | string);
      }
      setEditingField(null);
    }
  };

  // Displayed values: use override if set, else SoilGrids
  const dispPh    = overrides.ph               !== undefined ? overrides.ph               : soilData?.ph;
  const dispSoc   = overrides.soc_pct          !== undefined ? overrides.soc_pct          : soilData?.soc_pct;
  const dispN     = overrides.nitrogen_g_per_kg !== undefined ? overrides.nitrogen_g_per_kg : soilData?.nitrogen_g_per_kg;
  const dispTex   = overrides.texture_class     !== undefined ? overrides.texture_class    : soilData?.texture_class;

  const health = soilData?.health;

  return (
    <div className="rounded-xl border border-stone-200 bg-white shadow-sm overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <div>
          <span className="text-sm font-semibold text-stone-800">Your Land</span>
          {provinceName && (
            <span className="text-xs text-stone-500 ml-2">
              — {provinceName}, {lat.toFixed(2)}°N {lon.toFixed(2)}°E
            </span>
          )}
        </div>
        <span className="text-stone-400 text-xs">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 flex flex-col gap-3">
          {isLoading && (
            <p className="text-xs text-stone-400 italic">Loading soil data…</p>
          )}

          {!isLoading && soilData && (
            <>
              <table className="w-full">
                <tbody>
                  <SoilRow
                    label="Soil pH"
                    value={dispPh !== null && dispPh !== undefined ? Number(dispPh).toFixed(1) : null}
                    hint="Optimal: 5.5–7.0"
                    editKey="ph"
                    editType="number"
                    isOverridden={overrides.ph !== undefined}
                    editingField={editingField}
                    editValue={editValue}
                    onEditStart={handleEditStart}
                    onEditChange={setEditValue}
                    onEditCommit={handleEditCommit}
                    onReset={onReset}
                  />
                  <SoilRow
                    label="Organic carbon"
                    value={dispSoc !== null && dispSoc !== undefined ? Number(dispSoc).toFixed(1) : null}
                    unit="%"
                    hint="Good: >1.5%"
                    editKey="soc_pct"
                    editType="number"
                    isOverridden={overrides.soc_pct !== undefined}
                    editingField={editingField}
                    editValue={editValue}
                    onEditStart={handleEditStart}
                    onEditChange={setEditValue}
                    onEditCommit={handleEditCommit}
                    onReset={onReset}
                  />
                  <SoilRow
                    label="Nitrogen (total)"
                    value={dispN !== null && dispN !== undefined ? Number(dispN).toFixed(2) : null}
                    unit="g/kg"
                    editKey="nitrogen_g_per_kg"
                    editType="number"
                    isOverridden={overrides.nitrogen_g_per_kg !== undefined}
                    editingField={editingField}
                    editValue={editValue}
                    onEditStart={handleEditStart}
                    onEditChange={setEditValue}
                    onEditCommit={handleEditCommit}
                    onReset={onReset}
                  />
                  <SoilRow
                    label="Texture class"
                    value={dispTex ?? null}
                    editKey="texture_class"
                    editType="select"
                    isOverridden={overrides.texture_class !== undefined}
                    editingField={editingField}
                    editValue={editValue || (dispTex ?? 'loam')}
                    onEditStart={() => handleEditStart('texture_class', dispTex ?? 'loam')}
                    onEditChange={setEditValue}
                    onEditCommit={handleEditCommit}
                    onReset={onReset}
                  />
                  {soilData.cec_mmol_per_kg !== null && (
                    <tr className="border-b border-stone-50 last:border-0">
                      <td className="py-2 text-xs text-stone-500 pr-3">CEC</td>
                      <td className="py-2 text-xs font-mono text-stone-700">{soilData.cec_mmol_per_kg} mmol/kg</td>
                      <td />
                    </tr>
                  )}
                  <tr>
                    <td className="py-2 text-xs text-stone-500 pr-3">Salinity risk</td>
                    <td className="py-2 text-xs text-stone-700" colSpan={2}>{soilData.salinity_risk}</td>
                  </tr>
                </tbody>
              </table>

              <p className="text-[10px] text-stone-400 leading-relaxed">
                {dataSource ? DATA_SOURCE_LABELS[dataSource] ?? soilData.source : soilData.source} (250 m resolution)
                {Object.keys(overrides).length > 0 && ' + farmer measurements'}
              </p>

              {Object.keys(overrides).length === 0 && (
                <p className="text-[10px] text-stone-500 bg-amber-50 border border-amber-200 rounded px-2 py-1.5 leading-snug">
                  These are modelled estimates. Click Edit to enter your own measured values for more accurate recommendations.
                </p>
              )}

              {health && (
                <div className="border-t border-stone-100 pt-3 flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-stone-700">Soil health</span>
                    <HealthScoreBar score={health.health_score} />
                  </div>

                  <div className="flex flex-wrap gap-1">
                    {Object.entries(health.nutrient_status).map(([k, v]) => (
                      <span
                        key={k}
                        className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium capitalize ${STATUS_COLORS[v as NutrientStatus] ?? 'bg-stone-100 text-stone-600'}`}
                      >
                        {k.replace('_', ' ')}: {v}
                      </span>
                    ))}
                  </div>

                  {health.issues.length > 0 && (
                    <ul className="space-y-1">
                      {health.issues.map((issue, i) => (
                        <li key={i} className="text-[10px] text-stone-600 leading-snug bg-stone-50 rounded px-2 py-1.5">
                          • {issue}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ConfidenceBar({ rec }: { rec: CropRecommendation }) {
  const displayPct = Math.min(Math.round(rec.probability * 100), 95);
  const barColor = CONFIDENCE_BAR[rec.confidence] ?? 'bg-stone-400';
  const label = rec.confidence.charAt(0).toUpperCase() + rec.confidence.slice(1);

  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-stone-500">
          Confidence:{' '}
          <span className={`font-semibold ${rec.confidence === 'high' ? 'text-emerald-700' : rec.confidence === 'medium' ? 'text-amber-700' : 'text-red-600'}`}>
            {label}
          </span>
        </span>
        <span className="text-stone-500 font-mono">{displayPct}%</span>
      </div>
      <div className="h-2 rounded-full bg-stone-100 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${displayPct}%` }}
        />
      </div>
    </div>
  );
}

function PriceSpark({ forecast, trend }: { forecast: PriceForecast; trend: PriceTrend }) {
  const data = [
    { m: 'M1', p: forecast.month_1 },
    { m: 'M2', p: forecast.month_2 },
    { m: 'M3', p: forecast.month_3 },
    { m: 'M4', p: forecast.month_4 },
    { m: 'M5', p: forecast.month_5 },
    { m: 'M6', p: forecast.month_6 },
  ];
  const color = TREND_COLOR[trend];

  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="text-stone-400">6-month price forecast</span>
        <span className="font-semibold" style={{ color }}>{TREND_ARROW[trend]}</span>
      </div>
      <ResponsiveContainer width="100%" height={44}>
        <LineChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <Line
            type="monotone"
            dataKey="p"
            stroke={color}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="flex justify-between text-xs text-stone-400 mt-0.5">
        <span>{fmtMillions(data[0].p)}</span>
        <span className="text-stone-300">VND/tonne</span>
        <span>{fmtMillions(data[5].p)}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Farming Guide sub-components
// ---------------------------------------------------------------------------

function GuideAccordion({
  label,
  items,
  open,
  onToggle,
}: {
  label: string;
  items: string[];
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="border border-stone-100 rounded-lg overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-stone-700 hover:bg-stone-50 transition-colors text-left"
      >
        {label}
        <span className="text-stone-400 ml-2 shrink-0">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="px-3 pb-2.5 pt-1 space-y-1.5">
          {items.map((item, i) => {
            const isWarning = item.startsWith('⚠');
            return (
              <p
                key={i}
                className={`text-xs leading-snug ${
                  isWarning
                    ? 'text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1.5'
                    : 'text-stone-600'
                }`}
              >
                {isWarning ? item : `• ${item}`}
              </p>
            );
          })}
        </div>
      )}
    </div>
  );
}

function IrrigationAccordion({
  schedule,
  open,
  onToggle,
}: {
  schedule: IrrigationStage[];
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="border border-stone-100 rounded-lg overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-stone-700 hover:bg-stone-50 transition-colors text-left"
      >
        Irrigation Schedule
        <span className="text-stone-400 ml-2 shrink-0">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" style={{ minWidth: 380 }}>
            <thead>
              <tr className="text-left text-stone-400 border-b border-stone-100">
                <th className="px-3 pb-1.5 pt-2 font-medium whitespace-nowrap">Stage</th>
                <th className="pr-3 pb-1.5 pt-2 font-medium whitespace-nowrap">Days</th>
                <th className="pr-3 pb-1.5 pt-2 font-medium whitespace-nowrap">Frequency</th>
                <th className="pr-3 pb-1.5 pt-2 font-medium">Note</th>
              </tr>
            </thead>
            <tbody>
              {schedule.map((row, i) => (
                <tr key={i} className="border-b border-stone-50 last:border-0">
                  <td className="px-3 py-1.5 text-stone-700 font-medium whitespace-nowrap">{row.stage}</td>
                  <td className="pr-3 py-1.5 font-mono text-stone-500 whitespace-nowrap">{row.days}</td>
                  <td className="pr-3 py-1.5 text-stone-500 whitespace-nowrap">{row.frequency}</td>
                  <td className="pr-3 py-1.5 text-stone-400 text-[10px] leading-snug">{row.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function FarmingGuideContent({ methods }: { methods: FarmingMethods }) {
  const [openSection, setOpenSection] = useState<string | null>(null);

  const toggle = (key: string) => setOpenSection((prev) => (prev === key ? null : key));

  const sections: Array<{ key: string; label: string; items: string[] }> = [
    { key: 'land',  label: 'Land Preparation',    items: methods.land_preparation },
    { key: 'plant', label: 'Planting Method',      items: methods.planting },
    { key: 'water', label: 'Water Management',     items: methods.water_management },
    { key: 'pest',  label: 'Pest & Disease Watch', items: methods.pest_watch },
  ];

  return (
    <div className="space-y-1">
      {sections.map(({ key, label, items }) => (
        <GuideAccordion
          key={key}
          label={label}
          items={items}
          open={openSection === key}
          onToggle={() => toggle(key)}
        />
      ))}
      <IrrigationAccordion
        schedule={methods.irrigation_schedule}
        open={openSection === 'irrigation'}
        onToggle={() => toggle('irrigation')}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fertiliser application schedule timeline
// ---------------------------------------------------------------------------

function FertiliserTimeline({ schedule }: { schedule: FertiliserSchedule }) {
  return (
    <div className="mt-3 border-t border-stone-100 pt-3">
      <p className="text-xs font-semibold text-stone-600 mb-2">Application Schedule</p>
      <div className="relative">
        {schedule.applications.map((app, i) => {
          const hasWarnings = app.warnings.length > 0;
          return (
            <div key={i} className="flex gap-2 pb-2 last:pb-0">
              {/* Timeline spine */}
              <div className="flex flex-col items-center shrink-0 pt-1">
                <div className={`w-2 h-2 rounded-full shrink-0 ${hasWarnings ? 'bg-amber-400' : 'bg-stone-400'}`} />
                {i < schedule.applications.length - 1 && (
                  <div className="w-px flex-1 bg-stone-200 mt-1" />
                )}
              </div>
              {/* Card */}
              <div className={`flex-1 rounded-lg border px-2.5 py-2 mb-1 text-xs ${hasWarnings ? 'border-amber-200 bg-amber-50' : 'border-stone-100 bg-stone-50'}`}>
                <p className={`font-semibold mb-1 ${hasWarnings ? 'text-amber-800' : 'text-stone-700'}`}>
                  {app.timing}
                </p>
                <div className="flex gap-3 text-stone-600 mb-1.5">
                  {app.N_kg_per_ha > 0 && <span>N: {app.N_kg_per_ha} kg/ha</span>}
                  {app.P2O5_kg_per_ha > 0 && <span>P₂O₅: {app.P2O5_kg_per_ha} kg/ha</span>}
                  {app.K2O_kg_per_ha > 0 && <span>K₂O: {app.K2O_kg_per_ha} kg/ha</span>}
                </div>
                <p className="text-stone-500 leading-snug mb-1.5">{app.method}</p>
                {app.product_examples.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-1">
                    {app.product_examples.map((p, pi) => (
                      <span key={pi} className="bg-stone-200 text-stone-600 px-1.5 py-0.5 rounded text-[10px]">
                        {p}
                      </span>
                    ))}
                  </div>
                )}
                {app.warnings.map((w, wi) => (
                  <p key={wi} className="text-amber-700 bg-amber-100 rounded px-2 py-1 leading-snug mt-1">
                    {w}
                  </p>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      {schedule.general_notes.length > 0 && (
        <div className="border-t border-stone-100 pt-2 mt-1">
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide mb-1">General notes</p>
          <ul className="space-y-0.5">
            {schedule.general_notes.map((note, i) => (
              <li key={i} className="text-[11px] text-stone-400 leading-snug">• {note}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Harvest detail (per-crop tab view)
// ---------------------------------------------------------------------------

function HarvestDetail({ ht }: { ht: HarvestTiming }) {
  return (
    <div className="space-y-3">
      <table className="w-full text-xs">
        <tbody>
          <tr className="border-b border-stone-50">
            <td className="text-stone-500 py-1.5 pr-3">Planting</td>
            <td className="text-right font-mono text-stone-700">{ht.estimated_planting_date}</td>
          </tr>
          <tr className="border-b border-stone-50">
            <td className="text-stone-500 py-1.5 pr-3">Earliest harvest</td>
            <td className="text-right font-mono text-stone-700">{ht.earliest_harvest_date}</td>
          </tr>
          <tr className="border-b border-stone-50">
            <td className="text-stone-500 py-1.5 pr-3">Optimal window</td>
            <td className="text-right font-mono text-stone-700 text-[10px] leading-snug">
              {ht.optimal_harvest_window}
            </td>
          </tr>
          <tr>
            <td className="text-stone-500 py-1.5 pr-3 font-semibold">Recommended</td>
            <td className="text-right font-mono font-semibold text-emerald-700">
              {ht.recommended_harvest_date}
            </td>
          </tr>
        </tbody>
      </table>

      <p className="text-xs text-stone-600 bg-stone-50 border border-stone-100 rounded px-2.5 py-2 leading-snug">
        {ht.reason}
      </p>

      {ht.climate_risks.length > 0 && (
        <div className="flex flex-col gap-1">
          {ht.climate_risks.map((risk, i) => (
            <div
              key={i}
              className={`text-xs px-2.5 py-2 rounded leading-snug ${
                risk.severity === 'high'
                  ? 'bg-red-50 text-red-700 border border-red-100'
                  : 'bg-amber-50 text-amber-700 border border-amber-100'
              }`}
            >
              <p className="font-semibold mb-0.5">{risk.risk}</p>
              <p>{risk.action}</p>
            </div>
          ))}
        </div>
      )}

      {ht.harvest_tips.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide mb-1">
            Harvest tips
          </p>
          <ul className="space-y-1">
            {ht.harvest_tips.map((tip, i) => (
              <li key={i} className="text-xs text-stone-600 leading-snug">
                • {tip}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[10px] text-stone-400 leading-snug">{ht.data_basis}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Harvest Calendar — horizontal timeline per crop
// ---------------------------------------------------------------------------

function formatShortDate(d: Date): string {
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

function HarvestTimelineBar({
  plantDate, earliestDate, latestDate, optimalStart, recommendedDate, today, hasHighRisk,
}: {
  plantDate: Date; earliestDate: Date; latestDate: Date;
  optimalStart: Date; recommendedDate: Date; today: Date; hasHighRisk: boolean;
}) {
  const totalMs = latestDate.getTime() - plantDate.getTime();
  if (totalMs <= 0) return null;

  const toFrac = (d: Date) =>
    Math.max(0, Math.min(1, (d.getTime() - plantDate.getTime()) / totalMs));
  const toPct = (f: number) => `${(f * 100).toFixed(1)}%`;

  const earliestFrac = toFrac(earliestDate);
  const optStartFrac = toFrac(optimalStart);
  const todayFrac    = toFrac(today);
  const recFrac      = toFrac(recommendedDate);

  return (
    <div className="relative h-7 rounded overflow-hidden bg-stone-100 border border-stone-200">
      {/* Growing period: planting → earliest harvest */}
      <div
        className="absolute inset-y-0 bg-sky-200"
        style={{ left: '0%', width: toPct(earliestFrac) }}
      />
      {/* Early harvest zone: earliest → optimal start */}
      {optStartFrac > earliestFrac && (
        <div
          className="absolute inset-y-0 bg-emerald-200"
          style={{ left: toPct(earliestFrac), width: toPct(optStartFrac - earliestFrac) }}
        />
      )}
      {/* Optimal harvest window: optimal start → latest */}
      <div
        className="absolute inset-y-0 bg-emerald-500"
        style={{ left: toPct(optStartFrac), width: toPct(1 - optStartFrac) }}
      />
      {/* Storm risk overlay */}
      {hasHighRisk && (
        <div
          className="absolute inset-y-0 bg-red-500 opacity-40"
          style={{ left: toPct(optStartFrac), width: toPct(1 - optStartFrac) }}
        />
      )}
      {/* Planting marker */}
      <div className="absolute inset-y-0 w-1 bg-emerald-700" style={{ left: '0%' }} />
      {/* Recommended harvest marker */}
      {recFrac > 0.01 && recFrac < 0.99 && (
        <div
          className="absolute inset-y-0 w-0.5 bg-white opacity-90"
          style={{ left: toPct(recFrac) }}
        />
      )}
      {/* Today marker */}
      {todayFrac > 0.01 && todayFrac < 0.99 && (
        <div
          className="absolute inset-y-0 w-0.5 bg-stone-800"
          style={{ left: toPct(todayFrac) }}
        />
      )}
    </div>
  );
}

function HarvestTimelineRow({ rec, today }: { rec: CropRecommendation; today: Date }) {
  const ht = rec.harvest_timing;
  const plantDate       = new Date(ht.estimated_planting_date);
  const earliestDate    = new Date(ht.earliest_harvest_date);
  const latestDate      = new Date(ht.latest_harvest_date);
  const [optStartStr]   = ht.optimal_harvest_window.split(' to ');
  const optimalStart    = new Date(optStartStr);
  const recommendedDate = new Date(ht.recommended_harvest_date);
  const hasHighRisk     = ht.climate_risks.some((r) => r.severity === 'high');

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-stone-700">
          {CROP_LABELS[rec.crop] ?? rec.crop}
        </span>
        <span className="text-[10px] font-mono text-stone-400">
          Harvest by {formatShortDate(recommendedDate)}
        </span>
      </div>
      <HarvestTimelineBar
        plantDate={plantDate}
        earliestDate={earliestDate}
        latestDate={latestDate}
        optimalStart={optimalStart}
        recommendedDate={recommendedDate}
        today={today}
        hasHighRisk={hasHighRisk}
      />
      <div className="flex justify-between text-[10px] font-mono text-stone-400">
        <span>Plant {formatShortDate(plantDate)}</span>
        <span>
          Optimal {formatShortDate(optimalStart)}–{formatShortDate(latestDate)}
        </span>
      </div>
      {ht.climate_risks.length > 0 && (
        <div className="flex flex-col gap-0.5 mt-0.5">
          {ht.climate_risks.map((risk, i) => (
            <p
              key={i}
              className={`text-[10px] px-2 py-1 rounded leading-snug ${
                risk.severity === 'high'
                  ? 'bg-red-50 text-red-700 border border-red-100'
                  : 'bg-amber-50 text-amber-700 border border-amber-100'
              }`}
            >
              <span className="font-semibold">{risk.risk}: </span>
              {risk.action}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function HarvestCalendar({ recommendations }: { recommendations: CropRecommendation[] }) {
  const today = useMemo(() => new Date(), []);

  return (
    <div className="rounded-xl border border-stone-200 bg-white shadow-sm p-4 flex flex-col gap-4">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-stone-800">Harvest Calendar</h3>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-stone-400 justify-end">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-sky-200 rounded-sm inline-block border border-stone-100" />
            Growing
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-emerald-500 rounded-sm inline-block" />
            Optimal harvest
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-red-500 opacity-40 rounded-sm inline-block" />
            Storm risk
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-0.5 h-3 bg-stone-800" />
            Today
          </span>
        </div>
      </div>
      <div className="flex flex-col gap-5">
        {recommendations.map((rec) => (
          <HarvestTimelineRow key={rec.crop} rec={rec} today={today} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card guide tabs (Fertiliser | Farming Guide | Harvest)
// ---------------------------------------------------------------------------

function CardGuideTabs({ rec }: { rec: CropRecommendation }) {
  const [activeTab, setActiveTab] = useState<'fertiliser' | 'farming' | 'harvest'>('fertiliser');
  const fert = rec.fertiliser_recommendation;

  const tabs: Array<{ key: 'fertiliser' | 'farming' | 'harvest'; label: string }> = [
    { key: 'fertiliser', label: 'Fertiliser Plan' },
    { key: 'farming',    label: 'Farming Guide' },
    { key: 'harvest',    label: 'Harvest' },
  ];

  return (
    <div className="border-t border-stone-100 pt-3">
      {/* Tab bar */}
      <div className="flex gap-1 mb-3">
        {tabs.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors ${
              activeTab === key
                ? 'bg-stone-800 text-white'
                : 'text-stone-500 hover:text-stone-700 hover:bg-stone-50 border border-stone-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'fertiliser' ? (
        <div className="space-y-2">
          {/* Season totals */}
          <table className="w-full text-xs">
            <tbody>
              <tr className="border-b border-stone-50">
                <td className="text-stone-500 py-1">Total N</td>
                <td className="text-right font-mono text-stone-700">{fert.N_kg_per_ha} kg/ha</td>
              </tr>
              <tr className="border-b border-stone-50">
                <td className="text-stone-500 py-1">Total P₂O₅</td>
                <td className="text-right font-mono text-stone-700">{fert.P2O5_kg_per_ha} kg/ha</td>
              </tr>
              <tr className="border-b border-stone-50">
                <td className="text-stone-500 py-1">Total K₂O</td>
                <td className="text-right font-mono text-stone-700">{fert.K2O_kg_per_ha} kg/ha</td>
              </tr>
              {fert.lime_tonnes_per_ha > 0 && (
                <tr>
                  <td className="text-stone-500 py-1">Lime</td>
                  <td className="text-right font-mono text-stone-700">{fert.lime_tonnes_per_ha} t/ha</td>
                </tr>
              )}
            </tbody>
          </table>
          {fert.notes.length > 0 && (
            <ul className="space-y-0.5">
              {fert.notes.map((note, i) => (
                <li key={i} className="text-xs text-stone-500 leading-snug">• {note}</li>
              ))}
            </ul>
          )}
          {fert.schedule && <FertiliserTimeline schedule={fert.schedule} />}
        </div>
      ) : activeTab === 'farming' ? (
        <FarmingGuideContent methods={rec.farming_methods} />
      ) : (
        <HarvestDetail ht={rec.harvest_timing} />
      )}
    </div>
  );
}

function CropCard({ rank, rec, dimmed = false }: { rank: number; rec: CropRecommendation; dimmed?: boolean }) {
  const label = CROP_LABELS[rec.crop] ?? rec.crop;
  const badge = CONFIDENCE_BADGE[rec.confidence] ?? CONFIDENCE_BADGE.low;

  return (
    <div className={`rounded-xl border border-stone-200 bg-white shadow-sm p-4 flex flex-col gap-3 ${dimmed ? 'opacity-75' : ''}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-stone-400">#{rank}</span>
          <span className="font-semibold text-stone-800">{label}</span>
        </div>
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full capitalize shrink-0 ${badge}`}>
          {rec.confidence}
        </span>
      </div>

      <ConfidenceBar rec={rec} />

      <div className="grid grid-cols-2 gap-2">
        <div className="bg-stone-50 rounded-lg px-3 py-2">
          <p className="text-xs text-stone-400">Yield</p>
          <p className="text-sm font-semibold text-stone-700">{rec.predicted_yield_t_ha.toFixed(1)} t/ha</p>
        </div>
        <div className="bg-stone-50 rounded-lg px-3 py-2">
          <p className="text-xs text-stone-400">Revenue</p>
          <p className="text-xs font-semibold text-stone-700 leading-snug">
            {fmtVnd(rec.expected_revenue_vnd_per_ha)} VND/ha
          </p>
        </div>
      </div>

      <PriceSpark forecast={rec.price_forecast_vnd_per_tonne} trend={rec.price_trend} />
      <CardGuideTabs rec={rec} />
      <Link
        href={`/market?crop=${rec.crop}`}
        className="text-xs text-emerald-600 hover:text-emerald-800 hover:underline underline-offset-2 self-start"
      >
        View {label} price forecast →
      </Link>
    </div>
  );
}

function FarmPlanSection({ plan }: { plan: FarmPlan }) {
  const pieData = [
    ...plan.allocations.map((a) => ({
      name: CROP_LABELS[a.crop] ?? a.crop,
      value: a.area_ha,
      color: CROP_COLORS[a.crop] ?? '#6b7280',
    })),
    { name: 'Reserve', value: plan.reserve_ha, color: '#d1d5db' },
  ];

  return (
    <div className="rounded-xl border border-stone-200 bg-white shadow-sm p-4 flex flex-col gap-4">
      <h3 className="text-sm font-semibold text-stone-800">Farm Allocation Plan</h3>

      <div className="flex items-center gap-2">
        <div style={{ width: 140, height: 140, flexShrink: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={pieData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={62}
                strokeWidth={1}
                stroke="#fff"
              >
                {pieData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                formatter={(v) => [`${Number(v).toFixed(2)} ha`, '']}
                contentStyle={{ fontSize: 11, padding: '4px 8px' }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="flex-1 space-y-1.5">
          {pieData.map((d, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: d.color }} />
              <span className="text-stone-600 flex-1 truncate">{d.name}</span>
              <span className="font-mono text-stone-700 shrink-0">{d.value.toFixed(2)} ha</span>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-emerald-50 rounded-lg px-3 py-2">
        <p className="text-xs text-stone-500">Total expected revenue</p>
        <p className="text-sm font-bold text-emerald-700">
          {fmtVnd(plan.total_expected_revenue_vnd)} VND
        </p>
      </div>

      {plan.notes.length > 0 && (
        <ul className="space-y-0.5">
          {plan.notes.map((note, i) => (
            <li key={i} className="text-xs text-stone-500">
              {plan.weather_hedge_applied && i === 0 ? '⚠ ' : '• '}
              {note}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Season banner
// ---------------------------------------------------------------------------

function SeasonBanner({ info }: { info: SeasonInfo }) {
  return (
    <div className="rounded-lg bg-blue-50 border border-blue-200 px-4 py-3">
      <p className="text-sm text-blue-800">{info.banner_message}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Planting calendar (Gantt-style grid)
// ---------------------------------------------------------------------------

function PlantingCalendar({
  regionType,
  selectedMonth,
  onMonthSelect,
}: {
  regionType: string;
  selectedMonth: number | null;
  onMonthSelect: (month: number) => void;
}) {
  const allCrops = ['rice_paddy', 'coffee_green', 'cashew_raw', 'pepper_black', 'maize'];
  const monthSeasons = MONTH_TO_SEASON[regionType] ?? MONTH_TO_SEASON.mekong_delta;

  return (
    <div className="overflow-x-auto">
      <div style={{ minWidth: 460 }}>
        {/* Month header */}
        <div className="grid gap-px mb-1" style={{ gridTemplateColumns: '90px repeat(12, 1fr)' }}>
          <div />
          {MONTHS_SHORT.map((m, i) => (
            <button
              key={i}
              onClick={() => onMonthSelect(i + 1)}
              className={`text-center text-xs py-1 rounded transition-colors ${
                selectedMonth === i + 1
                  ? 'bg-emerald-600 text-white font-semibold'
                  : 'text-stone-500 hover:bg-stone-100'
              }`}
            >
              {m}
            </button>
          ))}
        </div>

        {/* Crop rows */}
        {allCrops.map((crop) => (
          <div
            key={crop}
            className="grid gap-px mb-0.5 items-center"
            style={{ gridTemplateColumns: '90px repeat(12, 1fr)' }}
          >
            <span className="text-xs text-stone-600 truncate pr-1" title={CROP_LABELS[crop]}>
              {CROP_LABELS[crop]?.split(' ')[0]}
            </span>
            {Array.from({ length: 12 }, (_, i) => {
              const season = monthSeasons[i] ?? 'none';
              const suitability = CROP_SUITABILITY[crop]?.[season] ?? 'none';
              const bg =
                suitability === 'optimal'    ? 'bg-emerald-400' :
                suitability === 'acceptable' ? 'bg-amber-300'   :
                'bg-stone-100';
              const ring = selectedMonth === i + 1 ? 'ring-1 ring-inset ring-emerald-600' : '';
              return (
                <button
                  key={i}
                  onClick={() => onMonthSelect(i + 1)}
                  className={`h-6 w-full ${bg} ${ring} transition-opacity hover:opacity-80`}
                  title={`${MONTHS_FULL[i]}: ${suitability === 'none' ? 'Not recommended' : suitability}`}
                />
              );
            })}
          </div>
        ))}

        {/* Legend */}
        <div className="flex gap-4 mt-2 text-xs text-stone-500">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-emerald-400 rounded-sm inline-block" />
            Optimal
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-amber-300 rounded-sm inline-block" />
            Acceptable
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-stone-100 border border-stone-200 rounded-sm inline-block" />
            Not recommended
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data freshness helpers
// ---------------------------------------------------------------------------

function timeAgo(isoString: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(isoString).getTime()) / 1_000);
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return m > 0 ? `${h}h ${m}m ago` : `${h}h ago`;
}

function WeatherBadge({ freshness }: { freshness: DataFreshness }) {
  const w = freshness.weather_forecast;
  if (!w.is_live) return null;
  const age = w.fetched_at ? timeAgo(w.fetched_at) : w.note;
  return (
    <div className="flex items-center gap-1.5 rounded-lg bg-sky-50 border border-sky-200 px-3 py-2 text-xs text-sky-800">
      <span>🌤</span>
      <span>
        <span className="font-semibold">Live 14-day forecast</span>
        {' '}— updated {age}
      </span>
    </div>
  );
}

const FRESHNESS_ROWS: Array<{
  key: keyof DataFreshness;
  label: string;
  dataType: string;
}> = [
  { key: 'weather_forecast', label: 'Open-Meteo',     dataType: '14-day weather' },
  { key: 'soil_data',        label: 'SoilGrids 2.0',  dataType: 'Soil properties' },
  { key: 'market_prices',    label: 'GSO baseline',   dataType: 'Market prices' },
  { key: 'ndvi',             label: 'Sentinel-2',     dataType: 'Crop cover (NDVI)' },
];

function DataSourcesFooter({ freshness }: { freshness: DataFreshness }) {
  return (
    <div className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3">
      <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-2">Data sources</p>
      <table className="w-full text-xs text-stone-600 border-collapse">
        <thead>
          <tr className="text-stone-400 text-left">
            <th className="pb-1 font-medium w-[120px]">Source</th>
            <th className="pb-1 font-medium w-[110px]">Data</th>
            <th className="pb-1 font-medium">Freshness</th>
          </tr>
        </thead>
        <tbody>
          {FRESHNESS_ROWS.map(({ key, label, dataType }) => {
            const layer = freshness[key];
            return (
              <tr key={key} className="border-t border-stone-100">
                <td className="py-1.5 pr-2">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`w-2 h-2 rounded-full shrink-0 ${layer.is_live ? 'bg-emerald-500' : 'bg-stone-300'}`}
                    />
                    {label}
                  </div>
                </td>
                <td className="py-1.5 pr-2 text-stone-400">{dataType}</td>
                <td className="py-1.5">
                  {layer.is_live && layer.fetched_at
                    ? <span className="text-emerald-700 font-medium">Live — {timeAgo(layer.fetched_at)}</span>
                    : <span className="text-stone-400">Static — {layer.note}</span>
                  }
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Results
// ---------------------------------------------------------------------------

function Results({ data }: { data: RecommendResponse }) {
  return (
    <div className="flex flex-col gap-4">
      <WeatherBadge freshness={data.data_freshness} />
      <SeasonBanner info={data.season_info} />

      <p className="text-xs text-stone-400">
        Nearest province:{' '}
        <strong className="text-stone-600">{data.location.nearest_province}</strong>
      </p>

      {data.season_info.in_transition && (
        <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide">
          Plant now — {data.season_info.season}
        </p>
      )}

      {data.recommendations.map((rec, i) => (
        <CropCard key={rec.crop} rank={i + 1} rec={rec} />
      ))}

      {data.transition && (
        <div className="flex flex-col gap-3 mt-1">
          <div className="rounded-lg bg-sky-50 border border-sky-200 px-4 py-3">
            <p className="text-sm font-medium text-sky-800">
              Upcoming: {data.transition.next_season} season in{' '}
              {data.transition.days_until} day{data.transition.days_until !== 1 ? 's' : ''}
            </p>
          </div>
          <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide">
            Plant in {data.transition.days_until} days — {data.transition.next_season}
          </p>
          {data.transition.recommendations.map((rec, i) => (
            <CropCard key={`t-${rec.crop}`} rank={i + 1} rec={rec} dimmed />
          ))}
        </div>
      )}

      {data.farm_plan && <FarmPlanSection plan={data.farm_plan} />}

      <HarvestCalendar recommendations={data.recommendations} />

      {!data.farm_plan && (
        <div className="rounded-xl border border-dashed border-stone-200 bg-stone-50 px-4 py-4 text-center">
          <p className="text-xs text-stone-400">Enter farm size above to see allocation plan.</p>
        </div>
      )}

      {data.warnings.length > 0 && (
        <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800 space-y-1">
          {data.warnings.map((w, i) => (
            <p key={i}>⚠ {w}</p>
          ))}
        </div>
      )}

      <DataSourcesFooter freshness={data.data_freshness} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

interface Props {
  lat: number | null;
  lon: number | null;
}

export default function RecommendPanel({ lat, lon }: Props) {
  const [mode, setMode]               = useState<PlanningMode>('today');
  const [targetMonth, setTargetMonth] = useState<number | null>(null);
  const [farmSizeInput, setFarmSizeInput] = useState('');
  const [isPending, setIsPending]     = useState(false);
  const [error, setError]             = useState<string | null>(null);
  const [result, setResult]           = useState<RecommendResponse | null>(null);
  const [soilOverrides, setSoilOverrides] = useState<SoilOverrides>({});

  const { data: provinces = [] } = useQuery({ queryKey: ['provinces'], queryFn: fetchProvinces });

  const { data: soilData, isLoading: soilLoading } = useQuery({
    queryKey: ['soil', lat, lon],
    queryFn: () => fetchSoilData(lat!, lon!),
    enabled: lat !== null && lon !== null,
    staleTime: 5 * 60 * 1000,  // soil data doesn't change; cache for 5 min
  });

  const province = useMemo(
    () => (lat !== null && lon !== null ? nearestProvince(lat, lon, provinces) : null),
    [lat, lon, provinces],
  );
  const regionType = regionTypeFromProvince(province);

  const farmSizeHa = farmSizeInput ? parseFloat(farmSizeInput) : null;
  const canSubmit  = lat !== null && lon !== null && (mode === 'today' || targetMonth !== null);

  const handleModeChange = (newMode: PlanningMode) => {
    setMode(newMode);
    setResult(null);
    setError(null);
    setTargetMonth(null);
  };

  const handleSoilOverride = useCallback((key: keyof SoilOverrides, value: number | string) => {
    setSoilOverrides((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleSoilReset = useCallback((key: keyof SoilOverrides) => {
    setSoilOverrides((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, []);

  const handleSubmit = useCallback(async () => {
    if (lat === null || lon === null) return;
    if (mode === 'forecast' && targetMonth === null) return;
    setIsPending(true);
    setError(null);
    setResult(null);
    try {
      const data = await fetchRecommendations({
        lat,
        lon,
        mode,
        target_month: mode === 'forecast' ? targetMonth : null,
        farm_size_ha: farmSizeHa && farmSizeHa > 0 ? farmSizeHa : null,
        soil_overrides: Object.keys(soilOverrides).length > 0 ? soilOverrides : null,
      });
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'An unexpected error occurred.');
    } finally {
      setIsPending(false);
    }
  }, [lat, lon, mode, targetMonth, farmSizeHa, soilOverrides]);

  return (
    <div className="flex flex-col gap-5">
      {/* Mode toggle */}
      <div className="flex rounded-lg border border-stone-200 overflow-hidden text-sm">
        {(['today', 'forecast'] as PlanningMode[]).map((m) => (
          <button
            key={m}
            onClick={() => handleModeChange(m)}
            className={`flex-1 py-2 font-medium transition-colors ${
              mode === m
                ? 'bg-emerald-600 text-white'
                : 'bg-white text-stone-600 hover:bg-stone-50'
            } ${m === 'forecast' ? 'border-l border-stone-200' : ''}`}
          >
            {m === 'today' ? "Today's Recommendations" : 'Plan Ahead'}
          </button>
        ))}
      </div>

      {/* Location display */}
      <div className="text-sm text-stone-500">
        {lat !== null && lon !== null ? (
          <span>
            Selected:{' '}
            <span className="font-mono text-stone-700">
              {lat.toFixed(4)}°N, {lon.toFixed(4)}°E
            </span>
          </span>
        ) : (
          <span className="italic">Click the map to select a location.</span>
        )}
      </div>

      {/* Your Land panel — shown whenever a location is selected */}
      {lat !== null && lon !== null && (
        <YourLandPanel
          soilData={result?.soil_data ?? soilData}
          overrides={soilOverrides}
          onOverride={handleSoilOverride}
          onReset={handleSoilReset}
          provinceName={province?.name ?? null}
          lat={lat}
          lon={lon}
          isLoading={soilLoading && !soilData}
          dataSource={result?.data_source}
        />
      )}

      {/* Plan Ahead: planting calendar */}
      {mode === 'forecast' && (
        <div className="flex flex-col gap-3">
          <p className="text-sm font-medium text-stone-700">12-month planting calendar</p>
          <p className="text-xs text-stone-400">
            Click a month to select your target planting time. Forecast data beyond 14 days is
            climatological — based on historical averages for this region, not a live forecast.
          </p>
          <PlantingCalendar
            regionType={regionType}
            selectedMonth={targetMonth}
            onMonthSelect={(m) => { setTargetMonth(m); setResult(null); setError(null); }}
          />
          {targetMonth !== null && (
            <p className="text-xs text-stone-500">
              Target month: <strong className="text-stone-700">{MONTHS_FULL[targetMonth - 1]}</strong>
            </p>
          )}
        </div>
      )}

      {/* Farm size (optional) */}
      <div>
        <label className="text-sm font-medium text-stone-700">
          Your farm size (hectares)
          <span className="text-stone-400 font-normal ml-1">— optional</span>
        </label>
        <input
          type="number"
          min="0"
          step="0.1"
          placeholder="e.g. 5.0"
          value={farmSizeInput}
          onChange={(e) => setFarmSizeInput(e.target.value)}
          className="mt-1.5 w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-700 placeholder-stone-300 focus:border-emerald-400 focus:outline-none focus:ring-1 focus:ring-emerald-400"
        />
      </div>

      {/* Submit */}
      <button
        onClick={() => { void handleSubmit(); }}
        disabled={!canSubmit || isPending}
        className="w-full py-2.5 px-4 rounded-lg text-sm font-semibold bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {isPending ? 'Analysing…' : 'Get Recommendations'}
      </button>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {result && <Results data={result} />}
    </div>
  );
}
