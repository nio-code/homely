from typing import Dict, Tuple

# ZIP codes that represent "near 92697" (UCI campus — no residential inventory)
TARGET_ZIPS = ["92602", "92603", "92606", "92612", "92614", "92618", "92620"]

CONCURRENCY = 10          # asyncio worker count
TARGET_QUALIFIED = 500    # stop after this many pass all filters
PAGES_PER_SOURCE_ZIP = 8  # max pages to paginate per (source, zip) pair
REQUEST_TIMEOUT = 20.0    # seconds

# Hard filters applied to every listing before scoring
FILTERS = {
    "beds_min": 3,
    "baths_min": 2,
    "sqft_min": 1000,
    "property_types": {"sfr", "single_family", "house", "detached"},
}

# User-agent rotation pool (mimics real browsers)
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Market rent benchmarks (3BR SFH, $/month) — sourced from Zumper/RentHop/Apartments.com May 2026
# Keyed by (zip_code, bedroom_count)
MARKET_RENT: Dict[Tuple[str, int], int] = {
    ("92602", 3): 5500, ("92602", 4): 6600, ("92602", 5): 7700,
    ("92603", 3): 5000, ("92603", 4): 6000, ("92603", 5): 7000,
    ("92606", 3): 4800, ("92606", 4): 5760, ("92606", 5): 6720,
    ("92612", 3): 4200, ("92612", 4): 5040, ("92612", 5): 5880,
    ("92614", 3): 4500, ("92614", 4): 5400, ("92614", 5): 6300,
    ("92618", 3): 4600, ("92618", 4): 5520, ("92618", 5): 6440,
    ("92620", 3): 4500, ("92620", 4): 5400, ("92620", 5): 6300,
    ("92697", 3): 4200, ("92697", 4): 5040, ("92697", 5): 5880,
}

# Median sqft per bedroom count (used to adjust rent by size)
MEDIAN_SQFT = {3: 1500, 4: 2000, 5: 2500}

# Per-source rate limiting: max concurrent requests
SOURCE_CONCURRENCY = {
    "coldwell_banker": 3,
    "compass":         2,
    "redfin":          2,
    "remax":           2,
    "century21":       2,
    "bhhs":            2,
    "trulia":          2,
    "homesnap":        1,
    "homes_com":       2,
    "point2":          2,
}
