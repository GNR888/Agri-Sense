'use client';

import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { MapContainer, TileLayer, Marker, Popup, useMapEvents } from 'react-leaflet';
import { useQuery } from '@tanstack/react-query';
import { fetchProvinces } from '@/lib/api';
import type { Province } from '@/lib/api';

// Fix default marker icon URLs broken by webpack asset hashing
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

const selectedIcon = L.divIcon({
  html: '<div style="width:16px;height:16px;border-radius:50%;background:#059669;border:3px solid white;box-shadow:0 1px 5px rgba(0,0,0,0.4)"></div>',
  className: '',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

function ClickHandler({ onSelect }: { onSelect: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      onSelect(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

interface Props {
  onLocationSelect: (lat: number, lon: number) => void;
  selectedLat: number | null;
  selectedLon: number | null;
}

export default function VietnamMap({ onLocationSelect, selectedLat, selectedLon }: Props) {
  const { data: provinces = [] } = useQuery({
    queryKey: ['provinces'],
    queryFn: fetchProvinces,
  });

  return (
    <MapContainer
      center={[16, 107]}
      zoom={6}
      style={{ height: '100%', width: '100%', minHeight: '480px' }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ClickHandler onSelect={onLocationSelect} />
      {provinces.map((p: Province) => (
        <Marker
          key={p.key}
          position={[p.lat, p.lon]}
          eventHandlers={{ click: () => onLocationSelect(p.lat, p.lon) }}
        >
          <Popup>
            <strong>{p.name}</strong>
            <br />
            <span className="text-stone-500">{p.name_vi}</span>
            <br />
            <span className="text-xs text-stone-400">{p.region}</span>
          </Popup>
        </Marker>
      ))}
      {selectedLat !== null && selectedLon !== null && (
        <Marker position={[selectedLat, selectedLon]} icon={selectedIcon} />
      )}
    </MapContainer>
  );
}
