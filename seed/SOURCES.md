# Seed data sources

Hero VIN `19XFB2F58EE214879`: NHTSA vPIC decodes it as **2014 HONDA Civic LX, 1.8L, 4 cyl** (check digit valid; response cached in `seed/cache/nhtsa/`). The serial number is made up; the VIN is not a real registered car.

Part numbers below come from web research on 2026-11-20 (full log: `seed/parts_research.json`). **verified** = a public retailer or OEM-dealer page shows the part number with the fitment. Everything else is **illustrative** (`part_brands.illustrative=1`).
**ValuMax** is a fictional economy brand (the no-buy brand). Vendors (Mission Auto Supply, Bayshore Parts Co., PartsDepot Online) and the shop are fictional. **All prices are illustrative** wholesale numbers chosen for the demo; they are not quotes from real stores.

Notes from research: the 2014 Civic 1.8 (non-GX) downstream O2 is Honda 36532-R1B-A01 / Denso 234-4979 (many listings wrongly push 36532-RNA-A01 / Denso 234-4350, which are GX/older). The F-150 is modeled as the 3.5L naturally aspirated V6 (not EcoBoost).

| part_id | type | position | OEM no | brand | brand part no | status | source |
|---|---|---|---|---|---|---|---|
| P-CIV14-O2-DN | o2_sensor | downstream | 36532-R1B-A01 | Denso | 234-4979 | verified | https://www.autopartsprime.com/p/2014-honda-civic-oxygen-sensor |
| P-CIV14-O2-DN | o2_sensor | downstream | 36532-R1B-A01 | NTK | 24134 | illustrative | https://www.delcoribo.com/p/oxs1030-acura-36532r1ba01,36532-r1b-a01-oxygen-sensors |
| P-CIV14-O2-DN | o2_sensor | downstream | 36532-R1B-A01 | Bosch | 15009 | illustrative | https://www.partcatalog.com/products/bosch-15009-oxygen-sensor |
| P-CIV14-O2-DN | o2_sensor | downstream | 36532-R1B-A01 | ValuMax | VMX-OS4979 | fictional |  |
| P-CIV14-AF-UP | o2_sensor | upstream | 36531-R1A-A01 | Denso | 234-9119 | verified | https://www.autopartsprime.com/p/2014-honda-civic-oxygen-sensor |
| P-CIV14-AF-UP | o2_sensor | upstream | 36531-R1A-A01 | NTK | 25700 | verified | https://www.autopartsprime.com/p/2014-honda-civic-oxygen-sensor |
| P-OIL-HON | oil_filter |  | 15400-PLM-A02 | Honda | 15400-PLM-A02 | verified | https://www.hondapartsnow.com/oem-2014-honda-civic-oil_filter.html |
| P-OIL-HON | oil_filter |  | 15400-PLM-A02 | WIX | 57356 | verified | https://www.autopartsprime.com/p/2019-honda-cr-v-oil-filter |
| P-CIV14-PAD-F | brake_pads | front | 45022-TR3-A02 | Wagner | QC1578 | verified | https://www.autopartsprime.com/p/2014-honda-civic-brake-pad-set |
| P-CIV14-PAD-F | brake_pads | front | 45022-TR3-A02 | Honda | 45022-TR3-A02 | verified | https://www.autopartsprime.com/p/2014-honda-civic-brake-pad-set |
| P-CIV14-ROT-F | brake_rotor | front | 45251-TR0-A00 | Bosch | 50011470 | illustrative |  |
| P-CIV14-ROT-F | brake_rotor | front | 45251-TR0-A00 | Wagner | BD126030E | illustrative |  |
| P-CIV14-AIR | engine_air_filter |  | 17220-R1A-A01 | Honda | 17220-R1A-A01 | verified | https://hondapartsnow.com/oem-2014-honda-civic-air_filter.html |
| P-HON-CABIN | cabin_air_filter |  | 80292-SDA-407 | Honda | 80292-SDA-407 | verified | https://hondapartsnow.com/oem-2014-honda-civic-cabin_air_filter.html |
| P-WIPER-26 | wiper_blade | driver 26in |  | Bosch | 26A | illustrative | https://www.finditparts.com/products/4598722 |
| P-WIPER-22 | wiper_blade | passenger 22in |  | Bosch | 22A | verified | https://www.canadiantire.ca/en/pdp/bosch-icon-fx-dual-rubber-wiper-blade-assorted-sizes-0219320p.0219333.html |
| P-WIPER-20 | wiper_blade | passenger 20in |  | Bosch | 20A | verified | https://www.walmart.com/browse/auto-tires/all-wiper-blades/bosch/91083_1749920_3219238_2503355/YnJhbmQ6Qm9zY2gie |
| P-WIPER-17 | wiper_blade | passenger 17in |  | Bosch | 17A | illustrative | https://www.canadiantire.ca/en/pdp/17a-bosch-icon-wiper-0219320p.0219323.html |
| P-F150-ALT | alternator |  | FL3Z-10346-D | Motorcraft | GL-8772 | verified | https://www.ford.com/product/alternator-p4000124829 |
| P-F150-ALT | alternator |  | FL3Z-10346-D | Remy | 23050 | illustrative | https://www.autopartsprime.com/p/2016-ford-f-150-alternator |
| P-F150-STR | starter |  | CK4Z-11002-C | Motorcraft | CK4Z-11002-C | illustrative | https://www.fordpartsdeal.com/parts-select/2016-ford-f-150-starter |
| P-F150-STR | starter |  | CK4Z-11002-C | Remy | 16198F | illustrative |  |
| P-F150-OIL | oil_filter |  | FL-500S | Motorcraft | FL-500S | verified | https://www.ford.com/product/engine-oil-filter-p4000147027 |
| P-F150-PAD-F | brake_pads | front | HL3Z-2001-A | Motorcraft | BRF-1586 | illustrative |  |
| P-F150-PAD-F | brake_pads | front | HL3Z-2001-A | Akebono | ACT1414 | illustrative |  |
| P-F150-BELT | serpentine_belt |  | BR3E-8620-AB | Gates | K060930 | illustrative |  |
| P-F150-BELT | serpentine_belt |  | BR3E-8620-AB | Motorcraft | JK6-930 | illustrative |  |
| P-OIL-TOY | oil_filter |  | 04152-YZZA1 | Toyota | 04152-YZZA1 | verified | https://www.autopartsprime.com/p/2018-toyota-camry-oil-filter |
| P-OIL-TOY | oil_filter |  | 04152-YZZA1 | WIX | WL10332 | illustrative | https://www.autopartsprime.com/p/2018-toyota-camry-oil-filter |
| P-CAM18-PAD-F | brake_pads | front | 04465-0E060 | Wagner | ZD2076 | verified | https://www.autopartsprime.com/p/2018-toyota-camry-brake-pad-set |
| P-CAM18-PAD-F | brake_pads | front | 04465-0E060 | Toyota | 04465-0E060 | verified | https://www.autopartsprime.com/p/2018-toyota-camry-brake-pad-set |
| P-CAM18-STR | starter |  | 28100-F0060 | Toyota | 28100-F0060 | verified | https://www.autopartsprime.com/p/2018-toyota-camry-starter |
| P-CAM18-STR | starter |  | 28100-F0060 | Denso | 280-0458 | illustrative |  |
| P-CAM18-AIR | engine_air_filter |  | 17801-F0020 | Denso | 143-3611 | illustrative |  |
| P-CAM18-AIR | engine_air_filter |  | 17801-F0020 | Bosch | 5611WS | illustrative |  |
| P-CAM18-CABIN | cabin_air_filter |  | 87139-XU002 | Denso | 453-2004 | illustrative |  |
| P-CAM18-CABIN | cabin_air_filter |  | 87139-XU002 | Bosch | 6045C | illustrative |  |
| P-ALT15-STR | starter |  | 23300-3TA0A | Remy | 16198 | verified | https://www.autopartsprime.com/p/2015-nissan-altima-starter |
| P-ALT15-STR | starter |  | 23300-3TA0A | Nissan | 2330M-3TA0CRW | verified | https://www.autopartsprime.com/p/2015-nissan-altima-starter |
| P-ALT15-STR | starter |  | 23300-3TA0A | ValuMax | VMX-ST16198 | fictional |  |
| P-ALT15-ALT | alternator |  | 23100-3TA1A | Denso | 210-4003 | verified | https://www.autopartsprime.com/p/2015-nissan-altima-alternator |
| P-ALT15-COIL | ignition_coil |  | 22448-1KT1A | Denso | 673-4028 | verified | https://www.autopartsprime.com/p/2015-nissan-altima-ignition-coil |
| P-ALT15-PAD-F | brake_pads | front | D1060-3TA0A | Akebono | ACT1650 | verified | https://www.autopartsprime.com/p/2015-nissan-altima-brake-pad-set |
| P-ALT15-PAD-F | brake_pads | front | D1060-3TA0A | Wagner | QC1650 | verified | https://www.autopartsprime.com/p/2015-nissan-altima-brake-pad-set |
| P-OIL-NIS | oil_filter |  | 15208-65F0E | Nissan | 15208-65F0E | illustrative |  |
| P-OIL-NIS | oil_filter |  | 15208-65F0E | Bosch | 3311 | illustrative |  |
| P-SIL17-ALT | alternator |  | 84143543 | ACDelco | 84143543 | verified | https://parts.chevrolet.com/product/gm-genuine-parts-alternator-84143543 |
| P-SIL17-ALT | alternator |  | 84143543 | Denso | 210-5390 | illustrative |  |
| P-SIL17-STR | starter |  | 12695760 | ACDelco | 12695760 | verified | https://lordco.com/Product/Starter-ACD12695760 |
| P-SIL17-STR | starter |  | 12695760 | Bosch | SR8580X | illustrative |  |
| P-SIL17-BELT | serpentine_belt |  | 12626076 | Gates | K060714 | verified | https://www.autopartsprime.com/p/2017-chevrolet-silverado-1500-serpentine-belt |
| P-OIL-GM | oil_filter |  | PF63 | ACDelco | PF63 | illustrative | https://parts.chevrolet.com/product/acdelco-gm-original-equipment-engine-oil-filter-12735811 |
| P-SIL17-CAL-F | brake_caliper | front left | 84320931 | ACDelco | 172-2701 | illustrative |  |
| P-SIL17-CAL-F | brake_caliper | front left | 84320931 | Wagner | TQM24046 | illustrative |  |
| P-SIL17-TIE | tie_rod_end | front outer | 84173385 | Moog | ES801233 | illustrative |  |
| P-SIL17-TIE | tie_rod_end | front outer | 84173385 | ACDelco | 45A1430 | illustrative |  |
| P-CRV19-AIR | engine_air_filter |  | 17220-5AA-A00 | Honda | 17220-5AA-A00 | verified | https://www.autopartsprime.com/p/2019-honda-cr-v-air-filter |
| P-CRV19-AIR | engine_air_filter |  | 17220-5AA-A00 | WIX | WA10417 | verified | https://www.autopartsprime.com/p/2019-honda-cr-v-air-filter |
| P-CRV19-PAD-F | brake_pads | front | 45022-TLA-A01 | Akebono | ACT1089A | illustrative |  |
| P-CRV19-PAD-F | brake_pads | front | 45022-TLA-A01 | Wagner | QC1089A | illustrative |  |
| P-BRAKLEEN | brake_cleaner |  | 05089 | CRC | 05089 | verified | https://www.ebay.com/itm/195173008096 |
| P-ATF-HON | atf |  | 08200-9008 | Honda | 08200-9008 | verified | https://zoro.com/genuine-honda-dw-1-1-quart-atf-dw-1-honda-08200-9008-08200-9008/i/G2125301 |
| P-COOL-HON | coolant |  | OL999-9011 | Honda | OL999-9011 | verified | https://www.bernardiparts.com/Honda-Anti-Freeze-Coolant-Type-2__0L999-9011.aspx |
| P-COOL-TOY | coolant |  | 00272-1LLAC | Toyota | 00272-1LLAC | illustrative |  |
| P-BULB-9005 | bulb | headlight high | 9005 | Bosch | 9005ST | illustrative |  |
| P-BULB-7443 | bulb | tail/stop | 7443 | Bosch | 7443 | illustrative |  |
