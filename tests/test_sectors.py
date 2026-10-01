"""SIC → GICS-like sector mapping (#92).

The risk evaluator's `max_sector_concentration` needs a sector per symbol.
EDGAR already gives every registrant a 4-digit SIC code; these tests pin the
mapping from SIC to the eleven GICS-style sector names.
"""

from __future__ import annotations

import pytest

from bloasis.data.sectors import SECTORS, sector_for_sic


@pytest.mark.parametrize(
    ("sic", "sector"),
    [
        ("2834", "Health Care"),  # pharmaceutical preparations
        ("2836", "Health Care"),  # biological products
        ("3841", "Health Care"),  # surgical & medical instruments
        ("8062", "Health Care"),  # hospitals
        ("5122", "Health Care"),  # drug wholesale (MCK, COR)
        ("3674", "Information Technology"),  # semiconductors
        ("3571", "Information Technology"),  # electronic computers
        ("7372", "Information Technology"),  # prepackaged software
        ("3663", "Information Technology"),  # communications equipment
        ("6022", "Financials"),  # state commercial banks
        ("6311", "Financials"),  # life insurance
        ("6211", "Financials"),  # security brokers
        ("6798", "Real Estate"),  # REITs
        ("6531", "Real Estate"),  # real estate agents & managers
        ("4911", "Utilities"),  # electric services
        ("4931", "Utilities"),  # electric & other services combined
        ("1311", "Energy"),  # crude petroleum & natural gas
        ("2911", "Energy"),  # petroleum refining
        ("4922", "Energy"),  # natural gas transmission (KMI, WMB)
        ("2000", "Consumer Staples"),  # food
        ("2080", "Consumer Staples"),  # beverages
        ("2844", "Consumer Staples"),  # perfumes, cosmetics
        ("5411", "Consumer Staples"),  # grocery stores
        ("5331", "Consumer Staples"),  # variety stores (WMT, DG)
        ("3711", "Consumer Discretionary"),  # motor vehicles
        ("5961", "Consumer Discretionary"),  # catalog & mail-order (AMZN)
        ("5812", "Consumer Discretionary"),  # eating places
        ("1531", "Consumer Discretionary"),  # operative builders
        ("7011", "Consumer Discretionary"),  # hotels & motels
        ("4813", "Communication Services"),  # telephone communications
        ("4841", "Communication Services"),  # cable TV
        ("2711", "Communication Services"),  # newspapers
        ("3721", "Industrials"),  # aircraft
        ("3560", "Industrials"),  # general industrial machinery
        ("4011", "Industrials"),  # railroads
        ("4512", "Industrials"),  # air transportation
        ("4953", "Industrials"),  # refuse systems (WM, RSG)
        ("2800", "Materials"),  # chemicals
        ("1040", "Materials"),  # gold & silver ores
        ("3312", "Materials"),  # steel works
        ("2650", "Materials"),  # paperboard containers
        # GICS sub-industry carve-outs, checked against the S&P 500 (#92 E2E)
        ("6324", "Health Care"),  # hospital & medical service plans (UNH, ELV)
        ("4400", "Consumer Discretionary"),  # water transportation parent: cruise lines
        ("4481", "Consumer Discretionary"),  # deep sea passenger transportation
        ("4412", "Industrials"),  # deep sea foreign freight stays Industrials
        ("4700", "Consumer Discretionary"),  # transportation services parent: BKNG, EXPE
        ("4724", "Consumer Discretionary"),  # travel agencies
        ("4731", "Industrials"),  # freight forwarding (CHRW, EXPD)
        ("3021", "Consumer Discretionary"),  # rubber & plastics footwear (NKE)
        ("7900", "Communication Services"),  # amusement parent: live entertainment
        ("7990", "Consumer Discretionary"),  # misc. amusement (casinos) stays
    ],
)
def test_sector_for_sic(sic: str, sector: str) -> None:
    assert sector_for_sic(sic) == sector


@pytest.mark.parametrize("sic", [None, "", "  ", "abc", "9995", "0"])
def test_unmappable_sic_is_none(sic: str | None) -> None:
    # 9995 is "non-operating establishments" (blank-check shells).
    assert sector_for_sic(sic) is None


def test_every_code_maps_to_a_known_sector_or_none() -> None:
    # Guards typos in the range table: no code can map to a name outside the
    # eleven sectors the risk evaluator buckets on.
    assert len(SECTORS) == 11
    produced = {sector_for_sic(f"{code:04d}") for code in range(100, 10_000)}
    assert produced - {None} <= set(SECTORS)
    assert produced - {None} == set(SECTORS)  # and every sector is reachable
