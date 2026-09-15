"""Reference data banks for the synthetic MDM demo generator.

ALL DATA IN THIS FILE IS SYNTHETIC AND INVENTED. No real person, address, email
address, telephone number or loyalty account is represented here. Names and
place names are drawn from public frequency distributions and from published
Australian geography; the combinations the generator produces are random and
do not describe anybody.

This module is an aggregator. The bulk reference data lives in two siblings so
that neither file becomes unreadable:

    banks_names.py    names by cultural group, diminutives, variants, diacritic
                      and name-order families
    banks_places.py   cities, suburbs, postcodes, streets, phone prefixes,
                      email domains

Everything they export is re-exported here, so the rest of the generator only
ever imports ``banks``. This module adds the derived indexes (flattened pools,
reverse group lookups, city -> region profile) and the commerce banks, which
are small enough to keep inline.

No real retailer, banner, loyalty programme or competitor is named anywhere.
The loyalty scheme is referred to by the generic noun "loyalty card" -- see
``LOYALTY_PROGRAMME`` at the foot of this file for why it is not a name.
"""

from __future__ import annotations

from banks_names import (  # noqa: F401  (re-exported)
    CROSS_GROUP_RATE,
    DIACRITIC_FORENAMES,
    DIACRITIC_SURNAMES,
    DIMINUTIVES,
    FEMALE_FORENAMES_BY_GROUP,
    MALE_FORENAMES_BY_GROUP,
    NAME_GROUP_WEIGHTS,
    NAME_GROUP_WEIGHTS_BY_REGION,
    NAME_ORDER_FAMILIES,
    SURNAMES_BY_GROUP,
    SURNAME_VARIANTS,
    TRANSLITERATION_FORENAMES,
    TRANSLITERATION_SURNAMES,
)
from banks_places import (  # noqa: F401  (re-exported)
    BUILDING_PREFIXES,
    CITIES,
    DOMAIN_CANON,
    DOMAIN_DRIFT,
    EMAIL_DOMAINS,
    EMAIL_TAGS,
    MOBILE_PREFIXES,
    NAMED_BUILDINGS,
    PUNCTUATION_SUBURBS,
    STREETS,
)

# ---------------------------------------------------------------------------
# Derived indexes.
# ---------------------------------------------------------------------------


def _flatten(by_group: dict[str, list[tuple[str, int]]]) -> list[tuple[str, int]]:
    """Collapse the group-keyed pools into one weighted pool.

    A name appearing in more than one group (Lee is Korean and Anglo; Singh
    appears across South Asian groups) has its weights summed, which is the
    correct national frequency for it.
    """
    totals: dict[str, int] = {}
    for pool in by_group.values():
        for name, weight in pool:
            totals[name] = totals.get(name, 0) + weight
    return sorted(totals.items())


def _reverse(by_group: dict[str, list[tuple[str, int]]]) -> dict[str, str]:
    """name -> its group. Where a name is shared, the heaviest group wins."""
    best: dict[str, tuple[str, int]] = {}
    for group, pool in by_group.items():
        for name, weight in pool:
            if name not in best or weight > best[name][1]:
                best[name] = (group, weight)
    return {name: group for name, (group, _) in best.items()}


MALE_FORENAMES: list[tuple[str, int]] = _flatten(MALE_FORENAMES_BY_GROUP)
FEMALE_FORENAMES: list[tuple[str, int]] = _flatten(FEMALE_FORENAMES_BY_GROUP)
SURNAMES: list[tuple[str, int]] = _flatten(SURNAMES_BY_GROUP)

SURNAME_GROUP: dict[str, str] = _reverse(SURNAMES_BY_GROUP)
FORENAME_GROUP: dict[str, str] = {
    **_reverse(MALE_FORENAMES_BY_GROUP),
    **_reverse(FEMALE_FORENAMES_BY_GROUP),
}

# city -> region profile, for biasing the ethnic mix of names by where the
# person lives. Sydney is far more diverse than regional Australia.
CITY_PROFILE: dict[str, str] = {row[0]: row[2] for row in CITIES}

# canonical suburb -> drifted spelling. Unlike the accent case there is nothing
# mechanical to derive here: dropping an apostrophe, expanding "St" to "Saint"
# or losing a hyphen is not a Unicode normalisation, which is exactly why this
# slice exercises the address path rather than the name-folding path.
#
# NOTE: a canonical name may carry more than one drifted form (O'Connor drifts
# to both "OConnor" and "O Connor"), so this dict is lossy -- the last pair for
# a given canonical wins. Use PUNCTUATION_SUBURBS itself when you need every
# variant, and PUNCTUATION_SUBURB_CANON to go the other way.
PUNCTUATION_SUBURB_MAP: dict[str, str] = dict(PUNCTUATION_SUBURBS)

# drifted spelling -> canonical. This direction is injective and is the one
# normalisation actually wants.
PUNCTUATION_SUBURB_CANON: dict[str, str] = {
    drifted: canonical for canonical, drifted in PUNCTUATION_SUBURBS
}

# ---------------------------------------------------------------------------
# Commerce. Grocery categories with Australian dollar ranges.
#
# Baskets are bimodal in a real grocery file: a lot of small top-up shops and a
# smaller number of large weekly ones. That is modelled by the wide ranges on
# the food categories rather than by a separate distribution.
# ---------------------------------------------------------------------------

POS_CATEGORIES: list[tuple[str, int, float, float]] = [
    # (category, weight, min amount AUD, max amount AUD)
    ("GROCERY_MIXED", 26, 6.50, 385.00),
    ("PRODUCE", 13, 3.20, 68.00),
    ("CHILLED_DAIRY", 11, 4.10, 72.00),
    ("MEAT_SEAFOOD", 9, 8.90, 148.00),
    ("BAKERY", 7, 2.50, 34.00),
    ("FROZEN", 6, 4.00, 86.00),
    ("PANTRY", 6, 5.50, 120.00),
    ("BEVERAGES", 5, 3.00, 64.00),
    ("BEER_WINE", 5, 12.00, 210.00),
    ("HOUSEHOLD", 4, 4.50, 96.00),
    ("HEALTH_BEAUTY", 4, 3.80, 88.00),
    ("FUEL", 4, 25.00, 165.00),
    ("BABY", 2, 9.00, 92.00),
    ("PET", 2, 5.00, 78.00),
    ("DELI", 2, 4.20, 46.00),
    ("GENERAL_MERCH", 2, 6.00, 140.00),
    ("CAFE", 2, 4.50, 38.00),
]

# Sole traders who would plausibly shop for a business at a grocery retailer.
BUSINESS_TRADES: list[tuple[str, list[str]]] = [
    ("Catering", ["Catering", "Catering Services", "Event Catering"]),
    ("Cafe", ["Cafe", "Coffee Co", "Espresso Bar"]),
    ("FoodTruck", ["Kitchen", "Food Truck", "Street Kitchen"]),
    ("Lawnmowing", ["Lawnmowing", "Lawn & Garden", "Mowing Services"]),
    ("Landscaping", ["Landscapes", "Landscaping", "Garden Design"]),
    ("Cleaning", ["Cleaning Services", "Commercial Cleaning", "Property Care"]),
    ("Building", ["Builders", "Building Services", "Construction"]),
    ("Plumbing", ["Plumbing", "Plumbing & Gas", "Plumbing Services"]),
    ("Electrical", ["Electrical", "Electrical Services", "Electrical Contracting"]),
    ("Painting", ["Painting", "Painting & Decorating", "Decorators"]),
    ("Courier", ["Couriers", "Courier Services", "Delivery Co"]),
    ("Childcare", ["Early Learning", "Childcare", "Home Based Care"]),
    ("RestHome", ["Rest Home", "Care Home", "Retirement Care"]),
    ("Shearing", ["Shearing", "Shearing Contractors", "Wool Services"]),
    ("Orchard", ["Orchard Services", "Orchards", "Packhouse Services"]),
    ("Panelbeating", ["Panelbeaters", "Panel & Paint", "Autobody"]),
    ("Fishing", ["Fishing Charters", "Charters", "Marine Services"]),
    ("Consulting", ["Consulting", "Associates", "Advisory"]),
]

# Drawn with rng.choice, so repetition IS the weighting. "Pty Ltd" is the
# idiomatic Australian proprietary-company suffix and is deliberately the most
# common; bare "Ltd"/"Limited" are public-company forms and are rarer on a
# sole-trader or small-business file. The blanks keep most trading names
# unsuffixed.
BUSINESS_SUFFIXES: list[str] = [
    "Pty Ltd", "Pty Ltd", "Pty Ltd", "Ltd", "Limited", "& Sons", "", "", ""
]

# Invented data brokers. Deliberately not modelled on any real vendor.
ENRICH_VENDORS: list[tuple[str, float, float]] = [
    ("AcmeData", 0.42, 0.94),
    ("Kurrajong Audience Partners", 0.28, 0.79),
    ("Longitude Consumer Graph", 0.30, 0.82),
    ("Harbour Insight", 0.55, 0.97),
    ("Clearsight Data Co", 0.45, 0.91),
    ("Bellbird Consumer Data", 0.38, 0.88),
]

AGENT_IDS: list[str] = [f"AG-{i:03d}" for i in range(101, 181)]

# How the loyalty scheme is referred to everywhere in the corpus.
#
# This is deliberately a GENERIC NOUN and not a scheme name. It read
# "Club Card" until review, which is Tesco Clubcard -- one of the best-known
# loyalty brands in the world, and the space does not disguise it. In a demo
# that is specifically about grocery loyalty data it is the one context where
# a reader is certain to make the association. The docstring at the head of
# this file asserted that no real loyalty programme was named, two lines
# above naming one; the assertion had been there longer than the violation.
#
# Do NOT replace this with an invented scheme name. Any plausible-sounding
# name risks colliding with a real programme somewhere, and the obvious
# Australian candidates are all taken: "Everyday Rewards" (Woolworths),
# "flybuys" (Coles), "Qantas Frequent Flyer", and "Onecard" -- with Tesco's
# "Clubcard" waiting offshore for anyone who thinks a space makes it safe.
# A generic noun cannot collide.
LOYALTY_PROGRAMME = "loyalty card"
