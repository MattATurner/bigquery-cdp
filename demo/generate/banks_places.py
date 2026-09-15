"""Synthetic Australian geographical models for MDM address generation.

Includes a canonical list of cities and their real-world suburbs mapped to standard
4-digit postcodes. In Australia the suburb alone is not enough to place an address:
suburb names repeat across states (Newtown is in NSW, VIC, QLD and TAS), so it is
**suburb + state + postcode together** that is load-bearing. Postcodes are stored as
integers, which means the Northern Territory's ``08xx`` range loses its leading zero
natively -- ``0812`` becomes ``812`` -- reflecting a common data-entry error that the
pipeline must handle. Darwin is in the city list specifically to produce that drift;
no other state's postcodes start with a zero.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Cities.
#
#   (city_name, std_dialling_code, region_profile, [(suburb, postcode), ...], weight)
#
# ``std`` is the Australian area code: '02' (NSW/ACT), '03' (VIC/TAS),
# '07' (QLD), '08' (SA/WA/NT). ``region_profile`` must be one of
# DEFAULT / METRO_SYDNEY / METRO_MELBOURNE / METRO_PERTH / REGIONAL -- those keys
# are shared with banks_names.NAME_GROUP_WEIGHTS_BY_REGION.
#
# Suburbs are real and are paired with their real postcode for that city. The
# demo is about address matching, so a wrong postcode would be a visible defect.
# Weights are roughly proportional to real population.
# ---------------------------------------------------------------------------

CITIES: list[tuple[str, str, str, list[tuple[str, int]], int]] = [
    ('Sydney', '02', 'METRO_SYDNEY', [
        ('Sydney', 2000), ('Haymarket', 2000), ('The Rocks', 2000), ('Pyrmont', 2009),
        ('Darlinghurst', 2010), ('Potts Point', 2011), ('Elizabeth Bay', 2011), ('Alexandria', 2015),
        ('Rosebery', 2018), ('Paddington', 2021), ('Bondi Junction', 2022), ('Bronte', 2024),
        ('Randwick', 2031), ('Kingsford', 2032), ('Coogee', 2034), ('Maroubra', 2035),
        ('Annandale', 2038), ('Rozelle', 2039), ('Balmain', 2041), ('Newtown', 2042),
        ('Five Dock', 2046), ('Drummoyne', 2047), ('Stanmore', 2048), ('North Sydney', 2060),
        ('Crows Nest', 2065), ('St Leonards', 2065), ('Chatswood', 2067), ('Hornsby', 2077),
        ('Dee Why', 2099), ('Ryde', 2112), ('Eastwood', 2122), ('Ashfield', 2131),
        ('Burwood', 2134), ('Strathfield', 2135), ('Concord', 2137), ('Homebush', 2140),
        ('Lidcombe', 2141), ('Auburn', 2144), ('Westmead', 2145), ('Kings Langley', 2147),
        ('Castle Hill', 2154), ('Merrylands', 2160), ('Cabramatta', 2166), ('Liverpool', 2170),
        ('Lakemba', 2195), ('Punchbowl', 2196), ('Bankstown', 2200), ('Marrickville', 2204),
        ('Rockdale', 2216), ('Hurstville', 2220), ('Miranda', 2228), ('Cronulla', 2230),
        ('Sutherland', 2232), ('St Marys', 2760), ('Quakers Hill', 2763), ('Rooty Hill', 2766),
    ], 1700),
    ('Melbourne', '03', 'METRO_MELBOURNE', [
        ('Melbourne', 3000), ('East Melbourne', 3002), ('West Melbourne', 3003), ('Docklands', 3008),
        ('Footscray', 3011), ('Seddon', 3011), ('Williamstown', 3016), ('Altona', 3018),
        ('Sunshine', 3020), ('St Albans', 3021), ('Kensington', 3031), ('Ascot Vale', 3032),
        ('Moonee Ponds', 3039), ('North Melbourne', 3051), ('Parkville', 3052), ('Carlton North', 3054),
        ('Brunswick West', 3055), ('Brunswick', 3056), ('Coburg', 3058), ('Fitzroy', 3065),
        ('Collingwood', 3066), ('Fitzroy North', 3068), ('Northcote', 3070), ('Thornbury', 3071),
        ('Kew', 3101), ('Balwyn', 3103), ('Richmond', 3121), ('Hawthorn', 3122),
        ('Camberwell', 3124), ('Armadale', 3143), ('Malvern', 3144), ('Glen Waverley', 3150),
        ('Caulfield', 3162), ('Oakleigh', 3166), ('Springvale', 3171), ('Dandenong', 3175),
        ('Toorak', 3142), ('Prahran', 3181), ('Windsor', 3181), ('St Kilda', 3182),
        ('Elwood', 3184), ('Cheltenham', 3192), ('Mentone', 3194), ('Bentleigh', 3204),
        ('Albert Park', 3206), ('Middle Park', 3206),
    ], 1650),
    ('Brisbane', '07', 'REGIONAL', [
        ('Brisbane City', 4000), ('Spring Hill', 4000), ('Teneriffe', 4005), ('Fortitude Valley', 4006),
        ('Bowen Hills', 4006), ('Herston', 4006), ('Hamilton', 4007), ('Clayfield', 4011),
        ('Chermside', 4032), ('Aspley', 4034), ('Everton Park', 4053), ('Mitchelton', 4053),
        ('Red Hill', 4059), ('Ashgrove', 4060), ('Paddington', 4064), ('Milton', 4064),
        ('Auchenflower', 4066), ('Mount Coot-tha', 4066), ('St Lucia', 4067), ('Indooroopilly', 4068),
        ('Kenmore', 4069), ('Chapel Hill', 4069), ('Highgate Hill', 4101), ('South Brisbane', 4101),
        ('Dutton Park', 4102), ('Annerley', 4103), ('Coorparoo', 4151), ('Camp Hill', 4152),
        ('Morningside', 4170), ('Cannon Hill', 4170), ('Hawthorne', 4171), ('Wynnum', 4178),
    ], 1100),
    ('Perth', '08', 'METRO_PERTH', [
        ('Perth', 6000), ('Northbridge', 6003), ('East Perth', 6004), ('West Perth', 6005),
        ('Leederville', 6007), ('Shenton Park', 6008), ('Nedlands', 6009), ('Cottesloe', 6011),
        ('Mosman Park', 6012), ('Floreat', 6014), ('Mount Hawthorn', 6016), ('Osborne Park', 6017),
        ('Karrinyup', 6018), ('Doubleview', 6018), ('Balcatta', 6021), ('Mount Lawley', 6050),
        ('Maylands', 6051), ('Bayswater', 6053), ('Yokine', 6060), ('Joondanna', 6060),
        ('Victoria Park', 6100), ('Bentley', 6102), ('Rossmoyne', 6148), ('South Perth', 6151),
        ('Como', 6152), ('Booragoon', 6154), ('Willetton', 6155), ('Melville', 6156),
        ('Fremantle', 6160), ('South Fremantle', 6162), ("O'Connor", 6163), ('Spearwood', 6163),
    ], 900),
    ('Adelaide', '08', 'REGIONAL', [
        ('Adelaide', 5000), ('North Adelaide', 5006), ('Woodville', 5011), ('Semaphore', 5019),
        ('West Lakes', 5021), ('Henley Beach', 5022), ('Findon', 5023), ('Fulham Gardens', 5024),
        ('Marion', 5043), ('Morphettville', 5043), ('Glenelg', 5045), ('Blackwood', 5051),
        ('Unley', 5061), ('Parkside', 5063), ('Glenside', 5065), ('Toorak Gardens', 5065),
        ('Norwood', 5067), ('Kent Town', 5067), ('Payneham', 5070), ('Hectorville', 5073),
        ('Campbelltown', 5074), ('Walkerville', 5081), ('Prospect', 5082), ('Enfield', 5085),
        ('Modbury', 5092), ('Salisbury', 5108),
    ], 620),
    ('Gold Coast', '07', 'REGIONAL', [
        ('Beenleigh', 4207), ('Ormeau', 4208), ('Coomera', 4209), ('Nerang', 4211),
        ('Helensvale', 4212), ('Ashmore', 4214), ('Southport', 4215), ('Labrador', 4215),
        ('Surfers Paradise', 4217), ('Main Beach', 4217), ('Broadbeach', 4218), ('Mermaid Beach', 4218),
        ('Miami', 4220), ('Burleigh Heads', 4220), ('Palm Beach', 4221), ('Currumbin', 4223),
        ('Tugun', 4224), ('Coolangatta', 4225), ('Robina', 4226), ('Varsity Lakes', 4227),
    ], 420),
    ('Canberra', '02', 'REGIONAL', [
        ('Barton', 2600), ('Deakin', 2600), ('Yarralumla', 2600), ('Ainslie', 2602),
        ('Dickson', 2602), ('Watson', 2602), ("O'Connor", 2602), ('Griffith', 2603),
        ('Kingston', 2604), ('Narrabundah', 2604), ('Garran', 2605), ('Hughes', 2605),
        ('Holder', 2611), ('Braddon', 2612), ('Reid', 2612), ('Turner', 2612),
        ('Scullin', 2614), ('Hawker', 2614), ('Bruce', 2617), ('Kaleen', 2617),
    ], 260),
    ('Newcastle', '02', 'REGIONAL', [
        ('Belmont', 2280), ('Warners Bay', 2282), ('Cardiff', 2285), ('Wallsend', 2287),
        ('Adamstown', 2289), ('Charlestown', 2290), ('Merewether', 2291), ('Wickham', 2293),
        ('Carrington', 2294), ('Stockton', 2295), ('Waratah', 2298), ('Georgetown', 2298),
        ('Lambton', 2299), ('Jesmond', 2299), ('Newcastle', 2300), ('The Hill', 2300),
        ('Bar Beach', 2300), ('Newcastle West', 2302), ('Hamilton', 2303), ('Mayfield', 2304),
    ], 230),
    ('Wollongong', '02', 'REGIONAL', [
        ('Wollongong', 2500), ('North Wollongong', 2500), ('Gwynneville', 2500), ('Keiraville', 2500),
        ('Mangerton', 2500), ('Mount Keira', 2500), ('Warrawong', 2502), ('Port Kembla', 2505),
        ('Berkeley', 2506), ('Thirroul', 2515), ('Austinmer', 2515), ('Bulli', 2516),
        ('Woonona', 2517), ('Corrimal', 2518), ('Fairy Meadow', 2519), ('Figtree', 2525),
        ('Unanderra', 2526), ('Albion Park', 2527), ('Shellharbour', 2529), ('Dapto', 2530),
    ], 180),
    ('Hobart', '03', 'REGIONAL', [
        ('Hobart', 7000), ('West Hobart', 7000), ('North Hobart', 7000), ('Mount Stuart', 7000),
        ('Battery Point', 7004), ('South Hobart', 7004), ('Sandy Bay', 7005), ('New Town', 7008),
        ('Lenah Valley', 7008), ('Moonah', 7009), ('Claremont', 7011), ('Berriedale', 7011),
        ('Lindisfarne', 7015), ('Risdon Vale', 7016), ('Bellerive', 7018), ('Howrah', 7018),
        ('Rosny Park', 7018), ('Mornington', 7018), ('Kingston', 7050), ('Blackmans Bay', 7052),
    ], 150),
    ('Geelong', '03', 'REGIONAL', [
        ('Norlane', 3214), ('Corio', 3214), ('North Geelong', 3215), ('Bell Park', 3215),
        ('Bell Post Hill', 3215), ('Hamlyn Heights', 3215), ('Belmont', 3216), ('Highton', 3216),
        ('Waurn Ponds', 3216), ('Grovedale', 3216), ('Geelong West', 3218), ('Herne Hill', 3218),
        ('Manifold Heights', 3218), ('East Geelong', 3219), ('Whittington', 3219), ('Thomson', 3219),
        ('St Albans Park', 3219), ('Geelong', 3220), ('Newtown', 3220), ('South Geelong', 3220),
    ], 145),
    ('Townsville', '07', 'REGIONAL', [
        ('Townsville City', 4810), ('South Townsville', 4810), ('North Ward', 4810), ('Belgian Gardens', 4810),
        ('Railway Estate', 4810), ('West End', 4810), ('Hyde Park', 4812), ('Mundingburra', 4812),
        ('Hermit Park', 4812), ('Currajong', 4812), ('Aitkenvale', 4814), ('Cranbrook', 4814),
        ('Heatley', 4814), ('Douglas', 4814), ('Annandale', 4814), ('Garbutt', 4814),
        ('Condon', 4815), ('Rasmussen', 4815), ('Kirwan', 4817), ('Thuringowa Central', 4817),
    ], 110),
    ('Cairns', '07', 'REGIONAL', [
        ('Woree', 4868), ('White Rock', 4868), ('Bayview Heights', 4868), ('Edmonton', 4869),
        ('Cairns City', 4870), ('Parramatta Park', 4870), ('Portsmith', 4870), ('Manunda', 4870),
        ('Westcourt', 4870), ('Earlville', 4870), ('Whitfield', 4870), ('Edge Hill', 4870),
        ('Stratford', 4870), ('Redlynch', 4870), ('Smithfield', 4878), ('Holloways Beach', 4878),
        ('Machans Beach', 4878), ('Trinity Beach', 4879), ('Kewarra Beach', 4879), ('Clifton Beach', 4879),
    ], 95),
    # Darwin: the ONLY producer of the leading-zero trap. NT postcodes are 08xx,
    # and Python cannot write 0812 as an int literal at all -- it is 812 here,
    # which is exactly the drift the loyalty source depends on. Do not remove
    # Darwin and do not drop its weight to zero: that silently deletes a
    # hard-case signal the pipeline is built to catch.
    ('Darwin', '08', 'REGIONAL', [
        ('Darwin City', 800), ('Coconut Grove', 810), ('Nightcliff', 810), ('Millner', 810),
        ('Moil', 810), ('Brinkin', 810), ('Wanguri', 810), ('Casuarina', 810),
        ('Anula', 812), ('Wulagi', 812), ('Malak', 812), ('Larrakeyah', 820),
        ('Stuart Park', 820), ('Fannie Bay', 820), ('Bayview', 820), ('Ludmilla', 820),
        ('Berrimah', 828), ('Palmerston City', 830), ('Driver', 830), ('Moulden', 830),
        ('Durack', 830), ('Bakewell', 832), ('Bellamack', 832), ('Johnston', 832),
    ], 90),
    ('Launceston', '03', 'REGIONAL', [
        ('Mowbray', 7248), ('Invermay', 7248), ('Newnham', 7248), ('South Launceston', 7249),
        ('Kings Meadows', 7249), ('Youngtown', 7249), ('Launceston', 7250), ('East Launceston', 7250),
        ('West Launceston', 7250), ('Norwood', 7250), ('Newstead', 7250), ('Ravenswood', 7250),
        ('Riverside', 7250), ('Trevallyn', 7250), ('Prospect', 7250), ('Summerhill', 7250),
        ('St Leonards', 7250),
    ], 55),
    ('Toowoomba', '07', 'REGIONAL', [
        ('Toowoomba City', 4350), ('East Toowoomba', 4350), ('South Toowoomba', 4350), ('North Toowoomba', 4350),
        ('Newtown', 4350), ('Harristown', 4350), ('Rangeville', 4350), ('Middle Ridge', 4350),
        ('Centenary Heights', 4350), ('Darling Heights', 4350), ('Kearneys Spring', 4350), ('Wilsonton', 4350),
        ('Glenvale', 4350), ('Mount Lofty', 4350), ('Cotswold Hills', 4350), ('Highfields', 4352),
        ('Withcott', 4352),
    ], 52),
    ('Ballarat', '03', 'REGIONAL', [
        ('Ballarat Central', 3350), ('Ballarat East', 3350), ('Ballarat North', 3350), ('Soldiers Hill', 3350),
        ('Newington', 3350), ('Lake Wendouree', 3350), ('Golden Point', 3350), ('Redan', 3350),
        ('Alfredton', 3350), ('Mount Clear', 3350), ('Mount Helen', 3350), ('Canadian', 3350),
        ('Black Hill', 3350), ('Invermay Park', 3350), ('Brown Hill', 3350), ('Miners Rest', 3352),
        ('Wendouree', 3355), ('Sebastopol', 3356), ('Delacombe', 3356),
    ], 48),
    ('Bendigo', '03', 'REGIONAL', [
        ('Bendigo', 3550), ('Long Gully', 3550), ('Ironbark', 3550), ('Quarry Hill', 3550),
        ('Flora Hill', 3550), ('Kennington', 3550), ('White Hills', 3550), ('North Bendigo', 3550),
        ('East Bendigo', 3550), ('Spring Gully', 3550), ('Maiden Gully', 3551), ('Epsom', 3551),
        ('Ascot', 3551), ('Strathfieldsaye', 3551), ('Junortoun', 3551), ('Golden Square', 3555),
        ('Kangaroo Flat', 3555), ('Eaglehawk', 3556),
    ], 44),
]

# ---------------------------------------------------------------------------
# Streets. Australian thoroughfare vocabulary (Street, Road, Avenue, Drive,
# Court, Place, Crescent, Parade, Terrace, Close, Way, Grove, Esplanade,
# Circuit, Boulevard, Lane, Rise, Highway) over ordinary Australian street-name
# stock -- botanical, explorer/surveyor and plain civic names.
# ---------------------------------------------------------------------------

STREETS: list[tuple[str, int]] = [
    ('Acacia Boulevard', 2), ('Acacia Circuit', 4), ('Acacia Lane', 7), ('Acacia Place', 3),
    ('Acacia Street', 3), ('Acacia Way', 7), ('Albert Crescent', 7), ('Albert Lane', 6),
    ('Albert Parade', 6), ('Banksia Court', 10), ('Banksia Street', 8), ('Barkly Close', 11),
    ('Barkly Grove', 2), ('Barkly Place', 8), ('Barrack Boulevard', 4), ('Barrack Rise', 5),
    ('Barrack Road', 4), ('Barrack Way', 3), ('Bayview Rise', 7), ('Bayview Road', 5),
    ('Beach Circuit', 1), ('Beach Esplanade', 11), ('Beach Grove', 6), ('Beach Way', 4),
    ('Bellbird Parade', 12), ('Bellbird Terrace', 10), ('Boronia Boulevard', 1), ('Boronia Close', 1),
    ('Boronia Grove', 9), ('Bottlebrush Avenue', 12), ('Bottlebrush Crescent', 5), ('Bottlebrush Grove', 3),
    ('Bottlebrush Parade', 7), ('Boundary Court', 6), ('Bourke Boulevard', 7), ('Bourke Drive', 11),
    ('Bourke Grove', 12), ('Brisbane Boulevard', 2), ('Brisbane Circuit', 5), ('Brisbane Highway', 8),
    ('Brisbane Lane', 4), ('Canning Grove', 10), ('Canning Lane', 6), ('Canning Parade', 12),
    ('Canning Terrace', 11), ('Castlereagh Court', 10), ('Church Close', 8), ('Clarence Avenue', 10),
    ('Clarence Court', 3), ('Clarence Crescent', 2), ('Clarence Lane', 10), ('Collins Close', 3),
    ('Collins Crescent', 8), ('Collins Rise', 1), ('Cook Avenue', 1), ('Cook Close', 5),
    ('Cook Parade', 4), ('Cook Terrace', 12), ('Coolibah Close', 9), ('Coolibah Parade', 4),
    ('Cowper Rise', 3), ('Crown Crescent', 1), ('Crown Rise', 9), ('Currawong Close', 5),
    ('Currawong Parade', 9), ('Darling Esplanade', 6), ('Darling Parade', 6), ('Eucalyptus Grove', 11),
    ('Eucalyptus Parade', 3), ('Eucalyptus Rise', 5), ('Eucalyptus Road', 7), ('Flinders Place', 7),
    ('Flinders Road', 6), ('Flinders Way', 2), ('Forrest Rise', 9), ('Forrest Road', 5),
    ('Fraser Parade', 9), ('George Parade', 1), ('George Rise', 3), ('George Way', 4),
    ('Gipps Avenue', 2), ('Gipps Crescent', 5), ('Gipps Drive', 3), ('Gipps Grove', 11),
    ('Gipps Terrace', 10), ('Grevillea Avenue', 12), ('Grevillea Circuit', 3), ('Grevillea Grove', 1),
    ('Grevillea Place', 12), ('Grevillea Street', 10), ('Hargrave Avenue', 4), ('Hargrave Drive', 5),
    ('Hargrave Grove', 2), ('Hargrave Rise', 12), ('Hargrave Terrace', 2), ('Hay Close', 7),
    ('Hay Lane', 8), ('High Avenue', 6), ('High Circuit', 10), ('High Lane', 11),
    ('High Road', 7), ('Hume Boulevard', 3), ('Hume Close', 5), ('Hume Highway', 4),
    ('Hume Road', 3), ('Ironbark Circuit', 7), ('Ironbark Rise', 1), ('Ironbark Street', 5),
    ('Jacaranda Crescent', 9), ('Jacaranda Grove', 8), ('Jacaranda Lane', 10), ('Jacaranda Parade', 6),
    ('Jacaranda Rise', 4), ('Jarrah Avenue', 1), ('Jarrah Terrace', 11), ('Karri Boulevard', 11),
    ('Karri Place', 4), ('King Boulevard', 8), ('King Parade', 5), ('King Place', 5),
    ('King Terrace', 6), ('Kingfisher Circuit', 11), ('Kookaburra Avenue', 1), ('Kurrajong Boulevard', 12),
    ('Kurrajong Drive', 6), ('Kurrajong Road', 8), ('Kurrajong Street', 6), ('Kurrajong Way', 4),
    ('Lonsdale Place', 10), ('Macarthur Drive', 2), ('Macarthur Terrace', 7), ('Macquarie Boulevard', 2),
    ('Macquarie Circuit', 8), ('Macquarie Drive', 2), ('Macquarie Parade', 9), ('Macquarie Terrace', 12),
    ('Mallee Close', 8), ('Mallee Way', 9), ('Melaleuca Boulevard', 3), ('Melaleuca Parade', 2),
    ('Melaleuca Street', 8), ('Melaleuca Way', 1), ('Mill Circuit', 7), ('Mill Crescent', 9),
    ('Mill Lane', 12), ('Mill Parade', 2), ('Mill Way', 4), ('Mitchell Avenue', 2),
    ('Mitchell Lane', 10), ('Mitchell Parade', 12), ('Mitchell Terrace', 7), ('Morphett Court', 12),
    ('Morphett Street', 2), ('Mulga Circuit', 7), ('Mulga Grove', 9), ('Mulga Rise', 3),
    ('Murray Drive', 4), ('Murray Way', 4), ('Myrtle Avenue', 3), ('Myrtle Circuit', 3),
    ('Myrtle Lane', 11), ('Myrtle Rise', 12), ('Oxford Drive', 7), ('Oxford Parade', 6),
    ('Oxford Street', 9), ('Paperbark Crescent', 12), ('Paperbark Lane', 3), ('Paperbark Terrace', 10),
    ('Park Avenue', 1), ('Park Drive', 8), ('Parkes Court', 9), ('Parkes Grove', 12),
    ('Parkes Road', 7), ('Pitt Circuit', 3), ('Pitt Court', 10), ('Pitt Place', 8),
    ('Pitt Road', 9), ('Pitt Terrace', 5), ('Queen Boulevard', 1), ('Queen Court', 11),
    ('Queen Drive', 8), ('Queen Way', 9), ('Railway Avenue', 7), ('Railway Way', 4),
    ('Riverside Drive', 6), ('Riverside Esplanade', 3), ('Riverside Way', 6), ('Rosella Rise', 12),
    ('Sandalwood Way', 9), ('Station Lane', 7), ('Station Way', 4), ('Sturt Avenue', 2),
    ('Sturt Highway', 2), ('Sturt Lane', 3), ('Sturt Road', 9), ('Swanston Way', 3),
    ('Tallowwood Place', 5), ('Tallowwood Rise', 1), ('Tallowwood Way', 2), ('Torrens Esplanade', 7),
    ('Torrens Parade', 4), ('Victoria Grove', 6), ('Victoria Lane', 2), ('Victoria Terrace', 1),
    ('Wandoo Court', 6), ('Wandoo Grove', 6), ('Wandoo Road', 10), ('Wandoo Way', 4),
    ('Waratah Circuit', 4), ('Waratah Crescent', 11), ('Waratah Terrace', 1), ('Waratah Way', 6),
    ('Wattle Circuit', 9), ('Wattle Close', 10), ('Wattle Rise', 5), ('William Circuit', 9),
    ('William Drive', 5), ('William Grove', 10), ('William Place', 5), ('William Way', 3),
    ('Yarra Crescent', 4), ('Yarra Parade', 11),
]

BUILDING_PREFIXES: list[str] = [
    "", "", "", "Flat {n}, ", "Unit {n}, ", "Apartment {n}, ", "{n}/"
]

# Invented apartment-complex names. No real building is named here; the pattern
# is deliberately a generic botanical/bird word plus a generic complex noun.
NAMED_BUILDINGS: list[str] = [
    "Wattle Grove Residences", "Banksia Court Apartments", "Jacaranda Place Residences",
    "Kurrajong Rise Apartments", "Waratah Park Residences", "Bottlebrush Court Apartments",
    "Melaleuca Terraces", "Ironbark Quarter Apartments", "Casuarina Green Residences",
    "Lorikeet Landing Apartments", "Rosella Court Residences", "Paperbark Place Apartments",
    "Grevillea Gardens Residences", "Bluegum Quarter Apartments", "Coolibah Court Residences"
]

# ---------------------------------------------------------------------------
# Punctuation and spacing drift in suburb names.
#
# This replaces the old accented-suburb pool. Australia has very few place
# names carrying a diacritic, so inventing accented suburbs to exercise the
# address-normalisation path would be dishonest data. What Australian address
# data *does* carry in volume is punctuation drift: the apostrophe in the
# Irish 'O'' prefix dropped or turned into a space, 'St' expanded to 'Saint',
# a possessive apostrophe added or removed, and hyphens lost.
#
# Every canonical name below is a real Australian suburb; the second element is
# the drifted form a source system would plausibly store. The list is the pool,
# so it stays a list and is indexed by the caller's own dense counter -- see the
# note in generate.py. Do NOT index it off a stride derived from the outer loop
# variable; that is how half the old pool became unreachable.
# ---------------------------------------------------------------------------

PUNCTUATION_SUBURBS: list[tuple[str, str]] = [
    ("O'Connor", "OConnor"),                       # ACT 2602 / WA 6163
    ("O'Connor", "O Connor"),
    ("O'Halloran Hill", "OHalloran Hill"),         # SA 5158
    ("O'Halloran Hill", "O Halloran Hill"),
    ("O'Sullivan Beach", "OSullivan Beach"),       # SA 5166
    ("O'Sullivan Beach", "O Sullivan Beach"),
    ("St Kilda", "Saint Kilda"),                   # VIC 3182
    ("St Leonards", "Saint Leonards"),             # NSW 2065 / TAS 7250
    ("St Marys", "St Mary's"),                     # NSW 2760
    ("St Marys", "Saint Marys"),
    ("St Albans", "Saint Albans"),                 # VIC 3021
    ("St Peters", "Saint Peters"),                 # NSW 2044 / SA 5069
    ("St Ives", "Saint Ives"),                     # NSW 2075
    ("St Lucia", "Saint Lucia"),                   # QLD 4067
    ("Kings Langley", "King's Langley"),           # NSW 2147
    ("Kings Meadows", "King's Meadows"),           # TAS 7249
    ("Kings Park", "King's Park"),                 # NSW 2148 / VIC 3021
    ("Queens Park", "Queen's Park"),               # NSW 2022 / WA 6107
    ("Mount Coot-tha", "Mount Coot Tha"),          # QLD 4066 -- genuine hyphen
    ("Mount Coot-tha", "Mt Coot-tha"),
    ("Brighton-Le-Sands", "Brighton Le Sands"),    # NSW 2216 -- genuine hyphen
    ("Brighton-Le-Sands", "Brighton-le-Sands"),
]

MOBILE_PREFIXES: list[tuple[str, int]] = [
    ("041", 20),
    ("042", 16),
    ("043", 13),
    ("040", 11),
    ("045", 10),
    ("047", 8),
    ("048", 7),
    ("046", 6),
    ("049", 5),
    ("044", 4),
]

EMAIL_DOMAINS: list[tuple[str, int]] = [
    ("gmail.com", 100), ("hotmail.com", 45), ("bigpond.com", 40),
    ("outlook.com", 30), ("yahoo.com.au", 20), ("icloud.com", 15),
    ("me.com", 10), ("hotmail.com.au", 8), ("live.com", 8),
    ("optusnet.com.au", 8), ("iinet.net.au", 5), ("tpg.com.au", 5),
    ("bigpond.net.au", 4), ("internode.on.net", 4), ("westnet.com.au", 3),
    ("dodo.com.au", 3), ("ozemail.com.au", 2), ("googlemail.com", 2),
    ("outlook.com.au", 2), ("protonmail.com", 1)
]

# DOMAIN_DRIFT and DOMAIN_CANON are a matched pair: every non-canonical domain
# reachable through DRIFT must have a CANON entry pointing back, or email
# normalisation silently stops converging.
DOMAIN_DRIFT: dict[str, str] = {
    "gmail.com": "googlemail.com",
    "googlemail.com": "gmail.com",
    "hotmail.com": "hotmail.com.au",
    "hotmail.com.au": "hotmail.com",
    "outlook.com": "outlook.com.au",
    "outlook.com.au": "outlook.com",
    "icloud.com": "me.com",
    "me.com": "icloud.com",
    "yahoo.com": "yahoo.com.au",
    "yahoo.com.au": "yahoo.com",
    "bigpond.com": "bigpond.net.au",
    "bigpond.net.au": "bigpond.com",
}

DOMAIN_CANON: dict[str, str] = {
    "googlemail.com": "gmail.com",
    "hotmail.com.au": "hotmail.com",
    "outlook.com.au": "outlook.com",
    "me.com": "icloud.com",
    "yahoo.com.au": "yahoo.com",
    "bigpond.net.au": "bigpond.com",
}

EMAIL_TAGS: list[str] = [
    "shop", "groceries", "points", "deals", "specials", "receipts",
    "junk", "news", "retail", "orders", "loyalty", "spam"
]
