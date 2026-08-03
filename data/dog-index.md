# Sydney-area Small, Low-Shedding, Low-Odour Dog Adoption Index

Daily-refreshed index of small, low-shedding, low-odour dogs available for adoption at shelters within ~4 hours' drive of Sydney CBD (NSW + ACT). Most recently found entries appear first. New additions are marked **[NEW yyyy-mm-dd]**.

- **Last refreshed:** 2026-08-03
- **Filter:** Small (≤~10 kg / toy / small) AND a low-shedding, low-odour breed — Toy/Mini Poodle, Bichon, Maltese, Shih Tzu, Havanese, Yorkshire/Silky Terrier, Coton, Bolognese, Lhasa Apso, Mini Schnauzer, Chinese Crested, Bedlington, etc. Crosses qualify only if **every** named parent is low-shed (e.g. maltipoo, schnoodle, poochon ✓; cavoodle, labradoodle, ×pug ✗). Listing must explicitly state breed.
- **Status legend:** `available` / `on-hold` / `adopted`. Adopted dogs are pruned on each refresh.
- **Note:** entries dated before 2026-05-24 predate this criteria change and may not meet the size/coat rules above.

---

## Current candidates

<!-- DOGS:BEGIN (auto-generated from state.json by src/render.py — do not edit) -->

### [NEW 2026-08-03] Kong — Poodle (Toy), not stated, Male
- **URL:** https://www.petrescue.com.au/listings/1207419
- **Shelter:** RSPCA Sydney Shelter (Yagoona) (Yagoona West, NSW)
- **Status:** available · **Fee:** not stated · **Size:** Small
- **date_indexed:** 2026-08-03
- Toy Poodle Kong is a small, low-shedding, low-odour dog available through RSPCA Sydney Shelter in Yagoona.

### [NEW 2026-08-01] Sweet little Toastie — Yorkshire Terrier, not stated, Male
- **URL:** https://www.petrescue.com.au/listings/1206888
- **Shelter:** Ozzi Hearts 4 Paws (Cooranbong, NSW)
- **Status:** on-hold · **Fee:** $950.00 · **Size:** Small
- **date_indexed:** 2026-08-01
- Small Yorkshire Terrier in Cooranbong, NSW; explicitly low-shedding and low-odour breed.

### [NEW 2026-07-29] Inka — Poodle (Toy), not stated, Female
- **URL:** https://www.petrescue.com.au/listings/1206486
- **Shelter:** Wally's Dog Rescue (Mosman, NSW)
- **Status:** on-hold · **Fee:** $700.00 · **Size:** Small
- **date_indexed:** 2026-07-29
- Small female Toy Poodle in Mosman, NSW; explicitly low-shedding and low-odour breed.

### [NEW 2026-07-29] Tika — Poodle (Toy), not stated, Male
- **URL:** https://www.petrescue.com.au/listings/1206489
- **Shelter:** Wally's Dog Rescue (Mosman, NSW)
- **Status:** available · **Fee:** $700.00 · **Size:** Small
- **date_indexed:** 2026-07-29
- Small male Toy Poodle in Mosman, NSW; explicitly low-shedding and low-odour breed.

### [NEW 2026-07-13] Winny — Poodle, not stated, Male
- **URL:** https://www.petrescue.com.au/listings/1203575
- **Shelter:** Rovertel Rescue (Orange, NSW)
- **Status:** on-hold · **Fee:** $1,600.00 · **Size:** Small
- **date_indexed:** 2026-07-13
- Small male Poodle in Orange NSW ($1600); confirm Toy or Miniature variety, not Standard.  _(verify coat/breed)_

### [NEW 2026-07-05] Bindi — Maltese X Shih Tzu, approx. 2 years, Female
- **URL:** https://www.paws.com.au/FosterCare/FosterCareDogs.html#bindi
- **Shelter:** PAWS (Providing Animals with Support) (Sydney Metropolitan area)
- **Status:** available · **Fee:** not stated · **Size:** Toy
- **date_indexed:** 2026-07-05
- Toy-sized Maltese–Shih Tzu cross with two explicitly qualifying low-shed parent breeds, available through PAWS in the Sydney metropolitan area.

### [NEW 2026-06-25] Benny & Toko — Shih Tzu x Maltese, not stated, Male
- **URL:** https://www.petrescue.com.au/listings/1200245
- **Shelter:** Dog Rescue Newcastle (Erskineville, NSW)
- **Status:** on-hold · **Fee:** $1,000.00 · **Size:** Small
- **date_indexed:** 2026-06-25
- Male Shih Tzu × Maltese pair (malshi), small, Erskineville inner Sydney NSW; $1,000.

### [NEW 2026-06-10] Marney — Maltese, not stated, Female
- **URL:** https://www.petrescue.com.au/listings/1197293
- **Shelter:** RSPCA Illawarra Shelter (Cordeaux Heights, NSW)
- **Status:** available · **Fee:** $500.00 · **Size:** Small
- **date_indexed:** 2026-06-10
- Female Maltese, small, $500, RSPCA Illawarra Shelter, Cordeaux Heights NSW.

### [NEW 2026-05-31] Alfie — Shih Tzu x Maltese, 3 years, Male
- **URL:** https://www.awlnsw.com.au/animal/a3gMo000003CKiqIAG/
- **Shelter:** AWL NSW Eurobodalla Branch (Eurobodalla Branch)
- **Status:** available · **Fee:** $400 · **Size:** Small
- **date_indexed:** 2026-05-31
- Shih Tzu x Maltese male, 3 years, small, $400 at AWL Eurobodalla; qualifying low-shed cross.  _(verify drive time)_

<!-- DOGS:END -->

---

## Monitored shelters

The daily refresh's scrape targets live in **[shelters.json](../config/shelters.json)** — single source of truth. To add, remove, or correct a shelter, edit that file. The systemd timer reads it directly each run.

---

## Notes on coverage gaps (from initial sweep)

- Some council/independent sites use JavaScript-rendered listings (BMACC, Sutherland Shire, Campbelltown, Eurobodalla, Dog Rescue Newcastle's own page, ACT DAS, Hawkesbury CAS, Blacktown PetsOnline). The static-fetch sweep returned 403 / empty content on these. **The daily refresh leans on their PetRescue cross-posts** wherever the shelter publishes there; for those that don't (e.g. BMACC, Sutherland Shire's own pages), the systemd timer uses the configured Playwright MCP and otherwise notes the page as `unreachable`.
- Aus Poodle Haven's site was returning ECONNREFUSED on 2026-05-19. The daily job will keep retrying.
- No poodle/doodle-specific rescue groups were found in the PetRescue NSW directory (357 groups checked) beyond what's listed above.
