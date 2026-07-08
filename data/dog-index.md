# Sydney-area Small, Low-Shedding, Low-Odour Dog Adoption Index

Daily-refreshed index of small, low-shedding, low-odour dogs available for adoption at shelters within ~4 hours' drive of Sydney CBD (NSW + ACT). Most recently found entries appear first. New additions are marked **[NEW yyyy-mm-dd]**.

- **Last refreshed:** 2026-07-08
- **Filter:** Small (≤~10 kg / toy / small) AND a low-shedding, low-odour breed — Toy/Mini Poodle, Bichon, Maltese, Shih Tzu, Havanese, Yorkshire/Silky Terrier, Coton, Bolognese, Lhasa Apso, Mini Schnauzer, Chinese Crested, Bedlington, etc. Crosses qualify only if **every** named parent is low-shed (e.g. maltipoo, schnoodle, poochon ✓; cavoodle, labradoodle, ×pug ✗). Listing must explicitly state breed.
- **Status legend:** `available` / `on-hold` / `adopted`. Adopted dogs are pruned on each refresh.
- **Note:** entries dated before 2026-05-24 predate this criteria change and may not meet the size/coat rules above.

---

## Current candidates

<!-- DOGS:BEGIN (auto-generated from state.json by src/render.py — do not edit) -->

### [NEW 2026-07-07] Cheeky Boy — Bichon Frise x Poodle (Toy) Mix, not stated, Male
- **URL:** https://www.petrescue.com.au/listings/1202467
- **Shelter:** PetRescue NSW poodle search (aggregator) (San Remo, NSW)
- **Status:** on-hold · **Fee:** $1,500.00 · **Size:** Small
- **date_indexed:** 2026-07-07
- Male poochon (Bichon Frise × Toy Poodle), small, San Remo NSW, $1,500 adoption fee.

### [NEW 2026-07-07] Tully — Bichon Frise x Poodle (Toy) Mix, not stated, Female
- **URL:** https://www.petrescue.com.au/listings/1202486
- **Shelter:** PetRescue NSW poodle search (aggregator) (San Remo, NSW)
- **Status:** on-hold · **Fee:** $1,500.00 · **Size:** Small
- **date_indexed:** 2026-07-07
- Female poochon (Bichon Frise × Toy Poodle), small, San Remo NSW, $1,500 adoption fee.

### [NEW 2026-07-05] Bindi — Maltese X Shih Tzu, approx. 2 years, Female
- **URL:** https://www.paws.com.au/FosterCare/FosterCareDogs.html
- **Shelter:** PAWS (Providing Animals with Support) (Sydney Metropolitan area)
- **Status:** available · **Fee:** not stated · **Size:** Toy
- **date_indexed:** 2026-07-05
- Maltese x Shih Tzu cross, approx. 2 years, female, toy size, available in Sydney via PAWS foster care.

### [NEW 2026-07-02] Fluffy — Maltese x Australian Silky Terrier Mix, not stated, Male
- **URL:** https://www.petrescue.com.au/listings/1201259
- **Shelter:** PetRescue NSW poodle search (aggregator) (Running Stream, NSW)
- **Status:** on-hold · **Fee:** $1,500.00 · **Size:** Small
- **date_indexed:** 2026-07-02
- Male Maltese × Australian Silky Terrier, small, Running Stream NSW; both parents low-shedding; $1,500.  _(verify drive time)_

### [NEW 2026-06-26] Snowball - 9 Year Old Maltese X — Maltese Mix, not stated, Female
- **URL:** https://www.petrescue.com.au/listings/1200348
- **Shelter:** PetRescue NSW poodle search (aggregator) (Valentine, NSW)
- **Status:** on-hold · **Fee:** $400.00 · **Size:** Small
- **date_indexed:** 2026-06-26
- Female Maltese mix (second parent unstated), small, Valentine NSW near Newcastle; $400.  _(verify coat/breed)_

### [NEW 2026-06-25] Benny & Toko — Shih Tzu x Maltese, not stated, Male
- **URL:** https://www.petrescue.com.au/listings/1200245
- **Shelter:** PetRescue NSW poodle search (aggregator) (Erskineville, NSW)
- **Status:** available · **Fee:** $1,000.00 · **Size:** Small
- **date_indexed:** 2026-06-25
- Male Shih Tzu × Maltese pair (malshi), small, Erskineville inner Sydney NSW; $1,000.

### [NEW 2026-06-12] Marney — Maltese / Shih Tzu, 12 years 1 month, Female
- **URL:** https://www.rspcansw.org.au/adopt/pet/651411/
- **Shelter:** RSPCA NSW Rescuoodles program (Unanderra, NSW)
- **Status:** available · **Fee:** $500.00 · **Size:** Small
- **date_indexed:** 2026-06-12
- Senior female Malshi (Maltese × Shih Tzu), 12 years, RSPCA Illawarra Unanderra NSW, $500.

### [NEW 2026-06-10] Marney — Maltese, not stated, Female
- **URL:** https://www.petrescue.com.au/listings/1197293
- **Shelter:** RSPCA NSW Illawarra Shelter (Unanderra) (Cordeaux Heights, NSW)
- **Status:** available · **Fee:** $500.00 · **Size:** Small
- **date_indexed:** 2026-06-10
- Female Maltese, small, $500, RSPCA Illawarra Shelter, Cordeaux Heights NSW.

### [NEW 2026-05-31] Alfie — Shih Tzu x Maltese, 3 years, Male
- **URL:** https://www.awlnsw.com.au/animal/a3gMo000003CKiqIAG/
- **Shelter:** AWL NSW Eurobodalla Branch (Eurobodalla Branch)
- **Status:** available · **Fee:** $400 · **Size:** Small
- **date_indexed:** 2026-05-31
- Shih Tzu × Maltese male, 3 years, small, $400 at AWL Eurobodalla; qualifying low-shed cross.  _(verify drive time)_

<!-- DOGS:END -->

---

## Monitored shelters

The daily refresh's scrape targets live in **[shelters.json](shelters.json)** — single source of truth. To add, remove, or correct a shelter, edit that file. The cron job reads it directly each run.

---

## Notes on coverage gaps (from initial sweep)

- Some council/independent sites use JavaScript-rendered listings (BMACC, Sutherland Shire, Campbelltown, Eurobodalla, Dog Rescue Newcastle's own page, ACT DAS, Hawkesbury CAS, Blacktown PetsOnline). The static-fetch sweep returned 403 / empty content on these. **The daily refresh leans on their PetRescue cross-posts** wherever the shelter publishes there; for those that don't (e.g. BMACC, Sutherland Shire's own pages), the cron-job's subagents will attempt the Chrome MCP if connected and otherwise note the page as `unreachable`.
- Aus Poodle Haven's site was returning ECONNREFUSED on 2026-05-19. The daily job will keep retrying.
- No poodle/doodle-specific rescue groups were found in the PetRescue NSW directory (357 groups checked) beyond what's listed above.
