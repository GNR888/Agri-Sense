"""Province registry: capital centroids and confirmed agricultural farm points.

``capital_lat/lon`` — used for map display and nearest-province lookup.
``farm_lat/lon``    — verified to sit over the province's dominant cropland;
                      used for remote-sensing ingestion (NDVI, soil, climate).
                      Never use the capital for ingestion: Vietnamese provincial
                      capitals sit on rivers/coasts and sample water or urban.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProvinceInfo:
    name: str           # English display name
    name_vi: str        # Vietnamese name with diacritics
    region: str         # broad agroecological region
    dominant_crop: str  # primary crop system

    capital_lat: float
    capital_lon: float

    # Confirmed agricultural land — see per-entry rationale below.
    farm_lat: float
    farm_lon: float
    farm_note: str


# Keys are short snake_case province IDs used throughout the pipeline.
PROVINCES: dict[str, ProvinceInfo] = {
    # ------------------------------------------------------------------ Mekong Delta
    "can_tho": ProvinceInfo(
        name="Cần Thơ",
        name_vi="Cần Thơ",
        region="Mekong Delta",
        dominant_crop="rice (triple-crop)",
        capital_lat=10.0341,
        capital_lon=105.7880,
        # Thới Lai district, ~15 km west of the city centre.  Flat irrigated
        # paddies well clear of the Hậu River and urban fringe.  Three rice
        # crops/yr (Đông Xuân + Hè Thu + Mùa) with clear NDVI cycles.
        farm_lat=10.05,
        farm_lon=105.55,
        farm_note="Thới Lai district — irrigated rice paddy, away from Hậu River",
    ),
    "kien_giang": ProvinceInfo(
        name="Kiên Giang",
        name_vi="Kiên Giang",
        region="Mekong Delta",
        dominant_crop="rice / shrimp-rice rotation",
        capital_lat=10.0125,
        capital_lon=105.0800,
        # Giồng Riềng district, the inland rice belt of Kiên Giang.
        # The capital Rạch Giá is a coastal city; Giồng Riềng is flat paddy
        # far from the shrimp-tidal zone and from the Gulf coast.
        farm_lat=9.92,
        farm_lon=105.38,
        farm_note="Giồng Riềng district — inland rice paddy, away from coastal tidal zone",
    ),
    "an_giang": ProvinceInfo(
        name="An Giang",
        name_vi="An Giang",
        region="Mekong Delta",
        dominant_crop="rice (flood-recession triple-crop)",
        capital_lat=10.3826,
        capital_lon=105.4361,
        # Châu Phú district on the Mekong floodplain.  This zone achieves
        # three rice crops per year using annual flood recession; highest
        # average yields in the delta.  Clear of Long Xuyên urban footprint.
        farm_lat=10.52,
        farm_lon=105.15,
        farm_note="Châu Phú district — Mekong flood-recession paddy, triple-crop zone",
    ),
    # ------------------------------------------------------------------ Red River Delta
    "thai_binh": ProvinceInfo(
        name="Thái Bình",
        name_vi="Thái Bình",
        region="Red River Delta",
        dominant_crop="rice (double-crop)",
        capital_lat=20.4464,
        capital_lon=106.3398,
        # Tiền Hải district, coastal flat paddy — the most intensively farmed
        # zone in the Red River Delta.  Double-crop rice (Đông Xuân + Hè Thu)
        # with very high productivity.  Avoiding the tidal fringe.
        farm_lat=20.32,
        farm_lon=106.52,
        farm_note="Tiền Hải district — flat coastal paddy, double-crop rice belt",
    ),
    # ------------------------------------------------------------------ North-Central Coast
    "nghe_an": ProvinceInfo(
        name="Nghệ An",
        name_vi="Nghệ An",
        region="North-Central Coast",
        dominant_crop="rice / cassava / groundnut",
        capital_lat=18.6733,
        capital_lon=105.6922,
        # Yên Thành district, the alluvial rice plain in the centre of Nghệ An.
        # Vinh city is on the coast/river; Yên Thành is the province's rice
        # basket — flat, irrigated, with some cassava on sandy soils nearby.
        farm_lat=19.01,
        farm_lon=105.48,
        farm_note="Yên Thành district — alluvial rice plain, principal paddy zone of Nghệ An",
    ),
    # ------------------------------------------------------------------ Central Coast
    "quang_nam": ProvinceInfo(
        name="Quảng Nam",
        name_vi="Quảng Nam",
        region="Central Coast",
        dominant_crop="rice / cassava",
        capital_lat=15.5736,
        capital_lon=108.4736,
        # Thăng Bình district coastal rice plain, west of the national highway.
        # Lower yields than the delta; one or two crops depending on rainfall.
        # Avoiding the coastal sand dunes and the urban core of Tam Kỳ.
        farm_lat=15.72,
        farm_lon=108.10,
        farm_note="Thăng Bình/Duy Xuyên coastal plain — single/double-crop rice + cassava",
    ),
    # ------------------------------------------------------------------ Central Highlands
    "dak_lak": ProvinceInfo(
        name="Đắk Lắk",
        name_vi="Đắk Lắk",
        region="Central Highlands",
        dominant_crop="Robusta coffee",
        capital_lat=12.6797,
        capital_lon=108.0377,
        # Cư M'gar district, NE of Buôn Ma Thuột — the heart of Đắk Lắk's
        # Robusta coffee belt.  Basaltic red soil, 400–600 m elevation.
        # Coffee is an evergreen perennial; NDVI should be high (0.6–0.8)
        # and relatively stable year-round with only a mild dry-season dip.
        farm_lat=12.95,
        farm_lon=108.18,
        farm_note="Cư M'gar district — Robusta coffee on basaltic red soil, 400–600 m",
    ),
    "lam_dong": ProvinceInfo(
        name="Lâm Đồng",
        name_vi="Lâm Đồng",
        region="Central Highlands",
        dominant_crop="Arabica coffee / vegetables / tea",
        capital_lat=11.9407,
        capital_lon=108.4384,
        # Lâm Hà district, west of Đà Lạt at 900–1 000 m.  Arabica coffee,
        # vegetables (cabbage, tomato), and some tea.  Đà Lạt city itself is
        # urban and sits at 1 500 m; Lâm Hà is the main agricultural area
        # at a lower, more representative plantation altitude.
        farm_lat=11.72,
        farm_lon=108.20,
        farm_note="Lâm Hà district — Arabica coffee + vegetables at 900–1 000 m elevation",
    ),
    # ------------------------------------------------------------------ South-East
    "dong_nai": ProvinceInfo(
        name="Đồng Nai",
        name_vi="Đồng Nai",
        region="South-East",
        dominant_crop="rubber / cashew / industrial crops",
        capital_lat=10.9574,
        capital_lon=106.8426,
        # Định Quán/Tân Phú district in northern Đồng Nai — rolling terrain
        # covered with rubber and cashew plantations.  Biên Hòa is heavily
        # industrial; Tân Phú is the rural/agricultural north.
        farm_lat=11.32,
        farm_lon=107.18,
        farm_note="Tân Phú/Định Quán district — rubber and cashew plantations, far from Biên Hòa industrial zone",
    ),
    # ------------------------------------------------------------------ Mekong Delta (additional)
    "dong_thap": ProvinceInfo(
        name="Đồng Tháp",
        name_vi="Đồng Tháp",
        region="Mekong Delta",
        dominant_crop="rice (flood-recession triple-crop) / lotus",
        capital_lat=10.4667,
        capital_lon=105.6333,
        # Tam Nông district, floodplain paddies north of Cao Lãnh.  Classic
        # triple-crop rice on deep alluvial soils; the Tam Nông wetland reserve
        # sits nearby but the paddies are well-defined cropland.
        farm_lat=10.60,
        farm_lon=105.48,
        farm_note="Tam Nông district — deep-alluvial flood-recession paddy, away from Cao Lãnh city",
    ),
    "soc_trang": ProvinceInfo(
        name="Sóc Trăng",
        name_vi="Sóc Trăng",
        region="Mekong Delta",
        dominant_crop="rice / shrimp-rice rotation",
        capital_lat=9.6025,
        capital_lon=105.9739,
        # Mỹ Xuyên district — inland triple-crop rice belt, well away from the
        # tidal/shrimp zone in the coastal south.  Khmer-dominated farming area
        # with high rice productivity.
        farm_lat=9.73,
        farm_lon=105.88,
        farm_note="Mỹ Xuyên district — inland triple-crop paddy, far from coastal shrimp-tidal zone",
    ),
    # ------------------------------------------------------------------ Central Highlands (additional)
    "gia_lai": ProvinceInfo(
        name="Gia Lai",
        name_vi="Gia Lai",
        region="Central Highlands",
        dominant_crop="Robusta coffee / pepper / rubber",
        capital_lat=13.9667,
        capital_lon=108.0000,
        # Chư Prông district, SW of Pleiku — the main coffee and pepper
        # belt of Gia Lai on basaltic red soils.  Pleiku city itself sits
        # on higher basalt plateau; Chư Prông is the principal plantation area.
        farm_lat=13.77,
        farm_lon=107.89,
        farm_note="Chư Prông district — Robusta coffee + pepper on basaltic red soil, SW of Pleiku",
    ),
    # ------------------------------------------------------------------ Red River Delta (additional)
    "nam_dinh": ProvinceInfo(
        name="Nam Định",
        name_vi="Nam Định",
        region="Red River Delta",
        dominant_crop="rice (double-crop)",
        capital_lat=20.4200,
        capital_lon=106.1683,
        # Nghĩa Hưng district, southern Nam Định — flat coastal-plain double-crop
        # paddies.  Nam Định city is partly urban; Nghĩa Hưng is the province's
        # most productive rice area, clear of the Red River estuary.
        farm_lat=20.25,
        farm_lon=106.28,
        farm_note="Nghĩa Hưng district — flat coastal-plain double-crop paddy, southern Nam Định",
    ),
}

# Maps Vietnamese province display names (as they appear in GSO data) to PROVINCES keys.
PROVINCE_NAME_TO_KEY: dict[str, str] = {info.name_vi: key for key, info in PROVINCES.items()}
