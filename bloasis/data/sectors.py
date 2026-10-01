"""SIC → GICS-like sector mapping (#92).

`RiskEvaluator` caps exposure per sector, so every symbol needs one. There is
no free point-in-time GICS source; EDGAR, which this project already caches
for every registrant it reads 10-Ks from, assigns each one a 4-digit SIC code.
This module maps those codes onto the eleven GICS sector names.

The mapping is approximate by construction — SIC is an industry-of-product
taxonomy, GICS a market one. Known systematic disagreements:

- SIC 7370-7379 (computer services) puts internet platforms (GOOGL, META)
  in Information Technology; GICS has them in Communication Services.
- SIC 7389 (misc. business services) puts payment networks in Industrials;
  GICS has them in Financials.
- Lab instruments (SIC 3826) go to Health Care, other instruments
  (382x) to Information Technology, following where GICS puts most of them.
- Mixed codes stay on one sector rather than per-company overrides: 7389
  (payments, consulting, marketplaces), 7320 (rating agencies vs. credit
  bureaus), 381x/382x (defense electronics vs. test equipment).

Measured against the current S&P 500's GICS sectors (2026-10-01): 82.9%
agreement before the parent-code carve-outs above (6324, 4400/448x,
4700/472x, 3020-3021, 7900), which were chosen on that same sample — see
`docs/e2e/sic-sectors-checklist.md` for the in-sample caveat.

Like the 10-K history, the SIC code is the registrant's *current* one, so a
backtest reads today's classification for past dates.
"""

from __future__ import annotations

SECTORS: tuple[str, ...] = (
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
)

_COMM = "Communication Services"
_DISC = "Consumer Discretionary"
_STAP = "Consumer Staples"
_ENGY = "Energy"
_FIN = "Financials"
_HC = "Health Care"
_IND = "Industrials"
_IT = "Information Technology"
_MAT = "Materials"
_RE = "Real Estate"
_UTIL = "Utilities"

#: (low, high, sector), inclusive, **first match wins** — narrow carve-outs
#: come before the broad range they sit in.
_RANGES: tuple[tuple[int, int, str | None], ...] = (
    # Agriculture, forestry, fishing
    (100, 999, _STAP),
    # Mining
    (1000, 1099, _MAT),  # metal ores
    (1200, 1399, _ENGY),  # coal, oil & gas extraction and services
    (1400, 1499, _MAT),  # nonmetallic minerals
    # Construction
    (1520, 1531, _DISC),  # residential builders
    (1500, 1799, _IND),
    # Manufacturing
    (2000, 2199, _STAP),  # food, beverages, tobacco
    (2200, 2399, _DISC),  # textiles, apparel
    (2400, 2499, _MAT),  # lumber
    (2500, 2599, _DISC),  # furniture
    (2600, 2699, _MAT),  # paper, containers
    (2700, 2799, _COMM),  # printing & publishing
    (2830, 2836, _HC),  # drugs, biologicals
    (2840, 2844, _STAP),  # soap, detergents, cosmetics
    (2800, 2899, _MAT),  # other chemicals
    (2900, 2999, _ENGY),  # petroleum refining
    (3020, 3021, _DISC),  # rubber & plastics footwear
    (3000, 3099, _MAT),  # rubber & plastics
    (3100, 3199, _DISC),  # leather, footwear
    (3200, 3399, _MAT),  # stone, glass, primary metals
    (3400, 3499, _IND),  # fabricated metal products
    (3570, 3579, _IT),  # computers & office equipment
    (3500, 3599, _IND),  # industrial machinery
    (3630, 3639, _DISC),  # household appliances
    (3651, 3652, _DISC),  # household audio & video
    (3660, 3679, _IT),  # communications equipment, semiconductors, components
    (3600, 3699, _IND),  # other electrical equipment
    (3710, 3716, _DISC),  # motor vehicles & parts
    (3750, 3751, _DISC),  # motorcycles, bicycles
    (3790, 3799, _DISC),  # recreational vehicles
    (3700, 3799, _IND),  # aircraft, ships, rail equipment, defense
    (3826, 3826, _HC),  # laboratory analytical instruments
    (3840, 3851, _HC),  # medical & dental instruments, ophthalmic goods
    (3800, 3899, _IT),  # other instruments
    (3940, 3949, _DISC),  # toys, sporting goods
    (3900, 3999, _IND),  # misc. manufacturing
    # Transportation, communications, utilities
    (4400, 4400, _DISC),  # water transportation parent code: cruise lines
    (4480, 4489, _DISC),  # passenger water transportation
    (4400, 4499, _IND),  # freight water transportation
    (4700, 4700, _DISC),  # transportation services parent code: online travel
    (4720, 4729, _DISC),  # passenger transportation arrangement (travel agencies)
    (4000, 4799, _IND),  # rail, trucking, air, logistics
    (4800, 4899, _COMM),  # telephone, broadcasting, cable
    (4922, 4925, _ENGY),  # natural gas transmission & distribution pipelines
    (4950, 4959, _IND),  # sanitary services, waste
    (4900, 4999, _UTIL),
    # Wholesale trade
    (5122, 5122, _HC),  # drugs & druggists' sundries
    (5140, 5149, _STAP),  # groceries
    (5180, 5182, _STAP),  # beer, wine, spirits
    (5000, 5199, _IND),
    # Retail trade
    (5310, 5399, _STAP),  # general merchandise / variety stores
    (5400, 5499, _STAP),  # food stores
    (5912, 5912, _STAP),  # drug stores
    (5200, 5999, _DISC),
    # Finance, insurance, real estate
    (6324, 6324, _HC),  # hospital & medical service plans (managed care)
    (6500, 6553, _RE),
    (6798, 6798, _RE),  # REITs
    (6000, 6799, _FIN),
    # Services
    (7000, 7099, _DISC),  # hotels, lodging
    (7200, 7299, _DISC),  # personal services
    (7370, 7379, _IT),  # computer programming, software, data processing
    (7300, 7399, _IND),  # other business services
    (7500, 7599, _IND),  # auto rental & repair
    (7800, 7899, _COMM),  # motion pictures
    (7900, 7900, _COMM),  # amusement parent code: live entertainment
    (7900, 7999, _DISC),  # amusement & recreation
    (8000, 8099, _HC),  # health services
    (8731, 8731, _HC),  # commercial physical & biological research
    (8200, 8299, _DISC),  # education
    (8000, 8999, _IND),  # engineering, accounting, management services
    # Public administration and non-operating shells: no sector.
    (9000, 9999, None),
)


def sector_for_sic(sic: str | None) -> str | None:
    """GICS-like sector for a 4-digit SIC code, or None when unmappable."""
    if sic is None:
        return None
    try:
        code = int(str(sic).strip())
    except ValueError:
        return None
    for low, high, sector in _RANGES:
        if low <= code <= high:
            return sector
    return None
