# Sydney-area Small, Low-Shedding, Low-Odour Dog Adoption Index

Daily-refreshed index of small, low-shedding, low-odour dogs available for adoption at shelters within ~4 hours' drive of Sydney CBD (NSW + ACT). Most recently found entries appear first. New additions are marked **[NEW yyyy-mm-dd]**.

- **Last refreshed:** 2026-05-25
- **Filter:** Small (≤~10 kg / toy / small) AND a low-shedding, low-odour breed — Toy/Mini Poodle, Bichon, Maltese, Shih Tzu, Havanese, Yorkshire/Silky Terrier, Coton, Bolognese, Lhasa Apso, Mini Schnauzer, Chinese Crested, Bedlington, etc. Crosses qualify only if **every** named parent is low-shed (e.g. maltipoo, schnoodle, poochon ✓; cavoodle, labradoodle, ×pug ✗). Listing must explicitly state breed.
- **Status legend:** `available` / `on-hold` / `adopted`. Adopted dogs are pruned on each refresh.
- **Note:** entries dated before 2026-05-24 predate this criteria change and may not meet the size/coat rules above.

---

## Current candidates

<!-- DOGS:BEGIN (auto-generated from state.json by src/render.py — do not edit) -->

### [NEW 2026-05-24] Kev — Poodle (Toy) x Pug, 10 months, male
- **URL:** https://www.wollongong.nsw.gov.au/animal-adoptions/dogs/kev
- **Shelter:** City of Wollongong Animal Shelter (Wollongong, NSW)
- **Status:** available · **Fee:** not stated · **Size:** toy
- **date_indexed:** 2026-05-24
- Young toy poodle–pug cross available at Wollongong city shelter; fee not listed on council page.

### [NEW 2026-05-20] Milo — Labradoodle, 8y, male
- **URL:** https://www.petrescue.com.au/listings/1187908
- **Shelter:** Dog Rescue Newcastle (Newcastle, NSW)
- **Status:** available · **Fee:** $300 · **Size:** medium
- **date_indexed:** 2026-05-20
- Incredibly social and friendly Labradoodle with a beautiful nature, though he resource-guards around food and must be the only pet in the home.

### [NEW 2026-05-20] Darryl — Poodle Mix, 5y, male
- **URL:** https://www.petrescue.com.au/listings/1188309
- **Shelter:** SMART Animal Sanctuary & Rehoming Centre (Kunama, NSW — borderline >4hr drive, verify before travel)
- **Status:** available · **Fee:** $1,500 · **Size:** small (5.6 kg)
- **date_indexed:** 2026-05-20
- Social and affectionate ex-outdoor dog who gets along with small dogs and is eager to find a loving indoor home.

### [NEW 2026-05-20] Marmalade — Toy Poodle Mix, 6y, male
- **URL:** https://www.petrescue.com.au/listings/1187055
- **Shelter:** Sydney Animal Second-Chance Inc. (Waterloo, NSW)
- **Status:** on-hold (reviewing applications) · **Fee:** not stated · **Size:** small
- **date_indexed:** 2026-05-20
- Delightful, obedient toy poodle mix who is playful and energetic but prefers homes without young children and must be the only dog.

### [NEW 2026-05-20] Norman — Cavoodle, young adult, male
- **URL:** https://www.petrescue.com.au/listings/1182860
- **Shelter:** Maggie's Rescue Co-operative Ltd (Warrimoo, NSW — Blue Mountains)
- **Status:** on-hold (adoption pending) · **Fee:** not stated · **Size:** small (3 kg)
- **date_indexed:** 2026-05-20
- Tiny charming cavoodle with big personality who needs experienced adult-only owners willing to work with complex behavioural needs.

### [NEW 2026-05-20] Pablo — Miniature Poodle, ~4y, male
- **URL:** https://www.petrescue.com.au/listings/1178685
- **Shelter:** Ozzi Hearts 4 Paws (San Remo, NSW — Lake Macquarie)
- **Status:** on-hold (adoption pending) · **Fee:** not stated · **Size:** small
- **date_indexed:** 2026-05-20
- Former breeding stud who has settled beautifully in rescue, enjoying cuddles and making friends easily with other dogs and cats.

### [NEW 2026-05-20] Tillie — Cavoodle, 17 months, female
- **URL:** https://www.petrescue.com.au/listings/1053716
- **Shelter:** Sydney Animal Second-Chance Inc. (Panania, NSW)
- **Status:** on-hold (adoption pending) · **Fee:** not stated · **Size:** small (3 kg)
- **date_indexed:** 2026-05-20
- Former breeding facility dog who is initially shy with strangers but loves to snuggle on the lounge once settled.

### [NEW 2026-05-20] Bindi — Australian Shepherd x Poodle, 1–2y, female
- **URL:** https://www.deniseatpaws.com.au/adopt-a-pet
- **Shelter:** Denise at Paws (Mid North Coast, NSW — verify location is within 4hr drive)
- **Status:** available · **Fee:** $650 · **Size:** large (26 kg)
- **date_indexed:** 2026-05-20
- Energetic, intelligent Australian Shepherd x Poodle cross seeking active home. Listed on shelter's own page rather than a per-dog URL.

<!-- DOGS:END -->

---

## Monitored shelters

The daily refresh's scrape targets live in **[shelters.json](shelters.json)** — single source of truth. To add, remove, or correct a shelter, edit that file. The cron job reads it directly each run.

---

## Notes on coverage gaps (from initial sweep)

- Some council/independent sites use JavaScript-rendered listings (BMACC, Sutherland Shire, Campbelltown, Eurobodalla, Dog Rescue Newcastle's own page, ACT DAS, Hawkesbury CAS, Blacktown PetsOnline). The static-fetch sweep returned 403 / empty content on these. **The daily refresh leans on their PetRescue cross-posts** wherever the shelter publishes there; for those that don't (e.g. BMACC, Sutherland Shire's own pages), the cron-job's subagents will attempt the Chrome MCP if connected and otherwise note the page as `unreachable`.
- Aus Poodle Haven's site was returning ECONNREFUSED on 2026-05-19. The daily job will keep retrying.
- No poodle/doodle-specific rescue groups were found in the PetRescue NSW directory (357 groups checked) beyond what's listed above.
