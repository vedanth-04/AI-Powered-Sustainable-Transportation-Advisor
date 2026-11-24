# Delhi advisor: demo cases

Generated 2026-11-21T14:38:53+00:00 by `python -m scripts.advisor_demo_cases`. Every number below is the advisor's own output for a real request on the real Delhi network; nothing is edited by hand.

- **Bus model:** not available in this environment, so bus times come from the timetable everywhere (No bus model source passed its checks (registry_champion: ValueError: The artifact requires a different scikit-learn version.; deployed_service: URLError: <urlopen error [Errno 111] Connection refused>; approved_bundle: ValueError: The artifact requires a different scikit-learn version.). Timetable times are used everywhere.)
- **Cab road routing:** offline rule: straight line x 1.35 at an assumed speed, times a time-of-day traffic factor
- **Network:** 10514 bus stops / 89393 bus trips, 224 metro stations, 53 rail halts

| # | Case | From → to | Top option | Time | Fare | CO₂ |
|---|---|---|---|---|---|---|
| 1 | Everyday commute, balanced | Lajpat Nagar → Karol Bagh | bus | 55 min | ₹15 | 0.50 kg |
| 2 | Tight budget | Rohini → Saket | bus + bus | 157 min | ₹30 | 1.48 kg |
| 3 | Bus on the ML corridor (Outer Ring Road) | Chirag Delhi → Nehru Place Terminal | bus | 15 min | ₹5 | 0.12 kg |
| 4 | Greenest preference | Dwarka → Rajiv Chowk | metro | 51 min | ₹54 | 0.55 kg |
| 5 | Fastest, cab allowed, far north to south | Narela → Saket | bus + metro | 138 min | ₹79 | 1.54 kg |
| 6 | Late night by auto-rickshaw | Najafgarh → Kalkaji | cab | 83 min | ₹538 | 2.46 kg |
| 7 | Women ride DTC/cluster buses free | Mayur Vihar Phase I → ITO | bus | 48 min | ₹0 | 0.30 kg |
| 8 | Suburban train in the mix | Narela (NUR) → Old Delhi (DLI) | rail | 67 min | ₹10 | 0.52 kg |
| 9 | Sunday travel | Hauz Khas → Kashmere Gate | metro | 36 min | ₹32 | 0.36 kg |
| 10 | Outside the service area | Cyber City, Gurugram → Karol Bagh | refused: `outside_delhi` | – | – | – |

## 1. Everyday commute, balanced

*What it shows:* The default request: localities typed by name, all modes, balanced ranking with reasons.

*Request:* Lajpat Nagar → Karol Bagh, Monday 23 Nov 2026, 09:00.

| Option | Leave → arrive | Time | Fare | CO₂ | Changes | Walk | Route | Bus model |
|---|---|---|---|---|---|---|---|---|
| 1 (recommended, cheapest) | 09:00 → 09:55 | 55 min | ₹15 | 0.50 kg | 0 | 584 m | walk 584 m → Bus 522A (SPL) down | no |
| 2 (fastest, lowest CO2) | 09:01 → 09:40 | 39 min | ₹43 | 0.36 kg | 1 | 0 m | Metro Violet Line → Metro Blue Line | no |
| 3 (fewest changes) | 09:00 → 09:44 | 44 min | ₹269 | 1.87 kg | 0 | 0 m | AC taxi 12.47 km | no |

*Why option 1:* Best balanced score among the options. Lowest fare: ₹15. About 17 min slower than the fastest option. No change of vehicle (Bus).
*A car alone would emit about 1.75 kg CO₂; option 1 emits 0.50 kg.*
> Road routing was not reachable, so cab times use a straight-line rule (distance x 1.35 at an assumed speed) and a traffic factor. Cab fares are Delhi meter fares and are indicative: app cabs price dynamically, and cab availability is not checked.

## 2. Tight budget

*What it shows:* Options over the ₹40 budget are flagged and options within it rank first.

*Request:* Rohini → Saket, Monday 23 Nov 2026, 17:10; budget inr: 40.

| Option | Leave → arrive | Time | Fare | CO₂ | Changes | Walk | Route | Bus model |
|---|---|---|---|---|---|---|---|---|
| 1 (recommended, cheapest) | 17:12 → 19:49 | 157 min | ₹30 | 1.48 kg | 1 | 1427 m | walk 144 m → Bus 988 down → Bus 448 up → walk 1283 m | no |
| 2 | 17:12 → 19:40 | 148 min | ₹40 | 1.51 kg | 3 | 247 m | walk 144 m → Bus 988 down → Bus 479 up → Bus 536 up → Bus 427A down → walk 103 m | no |
| 3 (over budget) | 17:12 → 19:47 | 154 min | ₹45 (over budget) | 1.45 kg | 2 | 1141 m | walk 144 m → Bus 988 down → Bus 567 down → Bus 523 up → walk 997 m | no |
| 4 (over budget) | 17:12 → 19:38 | 146 min | ₹50 (over budget) | 1.47 kg | 4 | 477 m | walk 144 m → Bus 988 down → Bus 448 up → Bus (-)OUTERMUDRIKA → Bus 428 up → Bus 356 down → walk 333 m | no |
| 5 (lowest CO2, over budget) | 17:11 → 18:44 | 94 min | ₹59 (over budget) | 0.90 kg | 2 | 256 m | walk 144 m → Bus DW-3 down → walk 112 m → Metro Red Line → Metro Yellow Line | no |
| 6 (over budget) | 17:13 → 18:47 | 94 min | ₹74 (over budget) | 1.14 kg | 1 | 248 m | walk 144 m → Bus 106 down → walk 104 m → Metro Yellow Line | no |
| 7 (fastest, over budget) | 17:10 → 18:37 | 87 min | ₹144 (over budget) | 1.41 kg | 1 | 0 m | AC taxi 2.98 km → Metro Yellow Line | no |

*Why option 1:* Best balanced score among the options within your ₹40 budget. Lowest fare: ₹30. About 70 min slower than the fastest option. 1 change(s): Bus.
*A car alone would emit about 4.76 kg CO₂; option 1 emits 1.48 kg.*
*Budget:* 2 option(s) cost ₹40 or less.
> Road routing was not reachable, so cab times use a straight-line rule (distance x 1.35 at an assumed speed) and a traffic factor. Cab fares are Delhi meter fares and are indicative: app cabs price dynamically, and cab availability is not checked.

## 3. Bus on the ML corridor (Outer Ring Road)

*What it shows:* The only place the trained bus model is used: Chirag Delhi to Nehru Place eastbound, evening peak.

*Request:* Chirag Delhi → Nehru Place Terminal, Monday 23 Nov 2026, 17:10; modes: ['bus', 'metro', 'rail'].

| Option | Leave → arrive | Time | Fare | CO₂ | Changes | Walk | Route | Bus model |
|---|---|---|---|---|---|---|---|---|
| 1 (recommended, cheapest, fastest, fewest changes) | 17:10 → 17:25 | 15 min | ₹5 | 0.12 kg | 0 | 163 m | walk 163 m → Bus 764 up | no |
| 2 (lowest CO2) | 17:13 → 17:31 | 18 min | ₹21 | 0.06 kg | 0 | 476 m | Metro Magenta Line → walk 476 m | no |

*Why option 1:* Best balanced score among the options. Lowest fare: ₹5. Fastest arrival (17:25). No change of vehicle (Bus).
*A car alone would emit about 0.50 kg CO₂; option 1 emits 0.12 kg.*

## 4. Greenest preference

*What it shows:* Ranking by CO2 per trip; metro beats bus and cab here.

*Request:* Dwarka → Rajiv Chowk, Monday 23 Nov 2026, 08:30; priority: greenest.

| Option | Leave → arrive | Time | Fare | CO₂ | Changes | Walk | Route | Bus model |
|---|---|---|---|---|---|---|---|---|
| 1 (recommended, fastest, fewest changes, lowest CO2) | 08:33 → 09:25 | 51 min | ₹54 | 0.55 kg | 0 | 0 m | Metro Blue Line | no |
| 2 (cheapest) | 08:32 → 10:24 | 111 min | ₹15 | 1.04 kg | 0 | 1142 m | walk 740 m → Bus 859 down → walk 402 m | no |
| 3 | 08:32 → 10:21 | 109 min | ₹25 | 1.01 kg | 1 | 1084 m | walk 740 m → Bus 859 down → Bus 85 down → walk 344 m | no |
| 4 | 08:32 → 10:19 | 107 min | ₹35 | 0.98 kg | 2 | 953 m | walk 609 m → Bus 822 down → Bus 859A down → Bus 490 up → walk 344 m | no |
| 5 | 08:30 → 09:53 | 83 min | ₹542 | 3.91 kg | 0 | 0 m | AC taxi 26.09 km | no |

*Why option 1:* Best greenest score among the options. Costs ₹39 more than the cheapest option. Fastest arrival (09:25). No change of vehicle (Metro).
*A car alone would emit about 3.65 kg CO₂; option 1 emits 0.55 kg.*
> Road routing was not reachable, so cab times use a straight-line rule (distance x 1.35 at an assumed speed) and a traffic factor. Cab fares are Delhi meter fares and are indicative: app cabs price dynamically, and cab availability is not checked.

## 5. Fastest, cab allowed, far north to south

*What it shows:* Cab feeder joined to the metro, cab only and public transport at evening peak traffic. The fastest preference still weighs fare, so a much dearer option must save real time to be recommended.

*Request:* Narela → Saket, Monday 23 Nov 2026, 18:30; priority: fastest.

| Option | Leave → arrive | Time | Fare | CO₂ | Changes | Walk | Route | Bus model |
|---|---|---|---|---|---|---|---|---|
| 1 (recommended, lowest CO2) | 18:32 → 20:50 | 138 min | ₹79 | 1.54 kg | 1 | 894 m | walk 499 m → Bus 120 down → walk 395 m → Metro Yellow Line | no |
| 2 | 18:38 → 21:52 | 194 min | ₹35 | 1.97 kg | 2 | 922 m | walk 679 m → Bus 120E down → Bus 502 up → walk 140 m → Bus 427A down → walk 103 m | no |
| 3 | 18:32 → 21:50 | 198 min | ₹50 | 2.06 kg | 3 | 602 m | walk 499 m → Bus 120 down → Bus 19 down → Bus 505 up → Bus 463 down → walk 103 m | no |
| 4 | 18:32 → 21:48 | 196 min | ₹55 | 2.04 kg | 4 | 602 m | walk 499 m → Bus 120 down → Bus 19 down → Bus 505 up → Bus 523 up → Bus 427A down → walk 103 m | no |
| 5 (cheapest) | 18:38 → 22:06 | 208 min | ₹30 | 2.15 kg | 1 | 760 m | walk 679 m → Bus 120E down → Bus 522 down → walk 81 m | no |
| 6 (fastest) | 18:31 → 20:40 | 129 min | ₹407 | 3.42 kg | 1 | 0 m | AC taxi 16.15 km → Metro Yellow Line | no |
| 7 (fewest changes) | 18:30 → 21:10 | 161 min | ₹1024 | 7.53 kg | 0 | 0 m | AC taxi 50.2 km | no |

*Why option 1:* Best fastest score among the options. Costs ₹49 more than the cheapest option. About 9 min slower than the fastest option. 1 change(s): Bus + Metro.
*A car alone would emit about 7.03 kg CO₂; option 1 emits 1.54 kg.*
> Road routing was not reachable, so cab times use a straight-line rule (distance x 1.35 at an assumed speed) and a traffic factor. Cab fares are Delhi meter fares and are indicative: app cabs price dynamically, and cab availability is not checked.

## 6. Late night by auto-rickshaw

*What it shows:* Night meter charge (11 pm to 5 am) and the auto-rickshaw tariff.

*Request:* Najafgarh → Kalkaji, Monday 23 Nov 2026, 23:30; cab type: auto.

| Option | Leave → arrive | Time | Fare | CO₂ | Changes | Walk | Route | Bus model |
|---|---|---|---|---|---|---|---|---|
| 1 (recommended, cheapest, fastest, fewest changes, lowest CO2) | 23:30 → 00:52 (+1 day) | 83 min | ₹538 | 2.46 kg | 0 | 0 m | Auto-rickshaw 37.93 km | no |

*Why option 1:* Best balanced score among the options. Lowest fare: ₹538. Fastest arrival (00:52 (+1 day)). No change of vehicle (Auto). Auto fare is an indicative meter fare; pickup time is an assumption and availability is not checked.
*A car alone would emit about 5.31 kg CO₂; option 1 emits 2.46 kg.*
> Road routing was not reachable, so cab times use a straight-line rule (distance x 1.35 at an assumed speed) and a traffic factor. Cab fares are Delhi meter fares and are indicative: app cabs price dynamically, and cab availability is not checked.

## 7. Women ride DTC/cluster buses free

*What it shows:* Pink-ticket free bus travel and the metro smart-card discount change the cheapest option.

*Request:* Mayur Vihar Phase I → ITO, Monday 23 Nov 2026, 10:00; priority: cheapest; women free bus: True; smart card: True.

| Option | Leave → arrive | Time | Fare | CO₂ | Changes | Walk | Route | Bus model |
|---|---|---|---|---|---|---|---|---|
| 1 (recommended, cheapest) | 10:01 → 10:49 | 48 min | ₹0 | 0.30 kg | 0 | 1188 m | walk 838 m → Bus 309 down → walk 351 m | no |
| 2 (lowest CO2) | 10:01 → 10:41 | 40 min | ₹28.8 | 0.17 kg | 1 | 966 m | walk 520 m → Metro Pink Line → Metro Blue Line → walk 445 m | no |
| 3 | 10:01 → 10:44 | 44 min | ₹80.8 | 0.39 kg | 2 | 520 m | walk 520 m → Metro Pink Line → Metro Blue Line → AC taxi 1.59 km | no |
| 4 | 10:00 → 10:41 | 41 min | ₹87.8 | 0.47 kg | 1 | 445 m | AC taxi 1.97 km → Metro Blue Line → walk 445 m | no |
| 5 (fastest, fewest changes) | 10:00 → 10:33 | 34 min | ₹192 | 1.29 kg | 0 | 0 m | AC taxi 8.61 km | no |

*Why option 1:* Best cheapest score among the options. Lowest fare: ₹0. About 14 min slower than the fastest option. No change of vehicle (Bus).
*A car alone would emit about 1.21 kg CO₂; option 1 emits 0.30 kg.*
> Bus fares set to ₹0: women travel free on DTC and cluster buses (pink ticket).
> Metro fares include the 10% smart-card discount (off-peak extra discount not applied).
> Road routing was not reachable, so cab times use a straight-line rule (distance x 1.35 at an assumed speed) and a traffic factor. Cab fares are Delhi meter fares and are indicative: app cabs price dynamically, and cab availability is not checked.

## 8. Suburban train in the mix

*What it shows:* Northern Railway passenger/MEMU trains (2016 timetable) between two Delhi stations, against bus and cab.

*Request:* Narela (NUR) → Old Delhi (DLI), Monday 23 Nov 2026, 07:00.

| Option | Leave → arrive | Time | Fare | CO₂ | Changes | Walk | Route | Bus model |
|---|---|---|---|---|---|---|---|---|
| 1 (recommended, cheapest, lowest CO2) | 07:38 → 08:45 | 67 min | ₹10 | 0.52 kg | 0 | 0 m | Train 64002 Panipat Delhi EMU | no |
| 2 (fastest, fewest changes) | 07:00 → 08:15 | 76 min | ₹691 | 5.03 kg | 0 | 0 m | AC taxi 33.53 km | no |

*Why option 1:* Best balanced score among the options. Lowest fare: ₹10. Shorter door-to-door time than the fastest-arriving option (it leaves later). No change of vehicle (Train).
*A car alone would emit about 4.69 kg CO₂; option 1 emits 0.52 kg.*
> Road routing was not reachable, so cab times use a straight-line rule (distance x 1.35 at an assumed speed) and a traffic factor. Cab fares are Delhi meter fares and are indicative: app cabs price dynamically, and cab availability is not checked.

## 9. Sunday travel

*What it shows:* Sunday metro fare slabs, and the note that the weekday metro timetable stands in for weekends.

*Request:* Hauz Khas → Kashmere Gate, Sunday 29 Nov 2026, 11:00.

| Option | Leave → arrive | Time | Fare | CO₂ | Changes | Walk | Route | Bus model |
|---|---|---|---|---|---|---|---|---|
| 1 (recommended, fastest, fewest changes, lowest CO2) | 11:01 → 11:37 | 36 min | ₹32 | 0.36 kg | 0 | 0 m | Metro Yellow Line | no |
| 2 (cheapest) | 11:05 → 12:22 | 78 min | ₹15 | 0.73 kg | 0 | 766 m | walk 583 m → Bus 501 down → walk 183 m | no |
| 3 | 11:01 → 12:16 | 75 min | ₹20 | 0.70 kg | 1 | 692 m | walk 583 m → Bus 502 down → Bus AIRPORTEXP.-4 down → walk 109 m | no |
| 4 | 11:02 → 12:11 | 69 min | ₹25 | 0.71 kg | 2 | 264 m | walk 155 m → Bus 512 down → Bus 502 down → Bus AIRPORTEXP.-4 down → walk 109 m | no |
| 5 | 11:00 → 11:50 | 50 min | ₹398 | 2.83 kg | 0 | 0 m | AC taxi 18.9 km | no |

*Why option 1:* Best balanced score among the options. Costs ₹17 more than the cheapest option. Fastest arrival (11:37). No change of vehicle (Metro).
*A car alone would emit about 2.65 kg CO₂; option 1 emits 0.36 kg.*
> The DMRC feed has almost no weekend trips, so the weekday metro timetable is used; weekend frequencies are usually lower.
> Sunday metro fare slabs applied (DMRC national holiday/Sunday fares; other national holidays are not detected).
> Road routing was not reachable, so cab times use a straight-line rule (distance x 1.35 at an assumed speed) and a traffic factor. Cab fares are Delhi meter fares and are indicative: app cabs price dynamically, and cab availability is not checked.

## 10. Outside the service area

*What it shows:* A start outside the Delhi NCT boundary is refused with a clear reason instead of a guessed route.

*Request:* Cyber City, Gurugram → Karol Bagh, Monday 23 Nov 2026, 09:00.

*Result:* refused with `outside_delhi`: The starting point (28.4950, 77.0895) is outside Delhi (NCT boundary). This advisor covers places inside the National Capital Territory of Delhi only.
