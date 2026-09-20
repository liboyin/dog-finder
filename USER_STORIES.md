# Dog Finder: Daily Adoption Alerts for Australian Rescue Dogs

Dog Finder emails people a daily list of newly listed rescue dogs that match what they are looking for. It works like a price tracker: there is no account and no password. A subscriber describes the dog they want, confirms their email address, and receives a daily email when new matches appear. Every email carries a private link to view, edit, or cancel that search.

**Status:** planned product. None of these stories is implemented yet. The repository currently runs a single-user Sydney pipeline, described in [README.md](README.md), which this product replaces (see *Retiring the Personal Pipeline*). Stories below are accepted decisions unless they appear under *Open Questions*.

## Product Principles

- **No accounts.** A search is identified by a long, unguessable ID. Whoever holds a search's private link can manage that search, and nothing else.
- **Never silently miss a dog.** When the service is unsure whether a dog fits, it sends the dog with a note saying what to check, rather than dropping it.
- **Only send what's new.** A dog is sent to a search at most once, and no email is sent on a day with nothing new.
- **Respect the inbox.** Nothing is sent to an address until its owner confirms. Every email identifies the sender and offers a working cancel link.
- **Free, with limits.** The service is free to use. Limits on searches per address keep the running cost bounded and discourage abuse. There are no payment or billing flows.

## Creating a Search

- The user should be able to create a search from the website without signing up, by filling in one form:
    - **Email address** (required).
    - **Home postcode** (required), used to identify the subscriber's home state.
    - **Include interstate adoption** (required yes/no choice; see *Matching*).
    - **Search name** (required), e.g. "Small dog for Mum", used in email subjects and on the management page.
    - **What you are looking for** (required free text, maximum 300 characters after leading and trailing whitespace is removed). The field should prominently explain that the AI uses this description to assess suitability, and give a short, useful prompt such as: "Include the dog's size, age, breed or coat preferences, temperament, household, other pets, children, activity level, accessibility needs, and budget where they matter." It should show several examples, including "A calm, low-shedding small adult dog for an apartment with a cat", "An active medium or large dog to join a hiking family; okay with teenagers", and "Any friendly senior dog suitable for a quiet home". It should show a live remaining-character count and prevent further entry at the limit.
- The form should say plainly that the description is read by AI, and that results are a shortlist to check with the shelter, not a guarantee.
- The form should refuse an invalid email address, an unknown postcode, an omitted search name or description, or an unselected interstate-adoption choice, and explain what to fix without clearing the other fields. The server should also reject a description that exceeds the same 300-character limit, preserving the entered description and explaining the limit.
- After submitting, the user should see a "check your inbox" page. To prevent spam, nothing is matched or sent until the user verifies their email address and activates the search.
- One verified email address can hold several independent searches, up to a fixed limit on active searches; cancelled and fully expired searches do not count towards that limit. When the limit is reached, the form should say so and point to the lost-link recovery page, so the user can cancel or edit an existing search instead.

## Confirming a Search

- After submitting, the user should receive one verification email that summarises the search criteria. It has an "Activate this search" link and says that a recipient who did not request the search should discard the email.
- The activation link should open a page with a button, and act only when the button is pressed. Mail security scanners follow links automatically, so a link alone must never activate a search.
- Confirming activates the search and opens its management page. That page says an email arrives after a later daily run only when a dog newly matches; it does not send a catch-up catalogue of dogs already available at activation.
- A server housekeeping task should periodically delete a search that is never verified after its short confirmation period.
- Repeated submissions for the same address should not send more than a few confirmation emails per day, so the form can't be used to flood someone's inbox.

## Daily Match Emails

- When a search is confirmed, the service should establish a baseline of currently available matches and not send them as an initial catalogue. Editing a search establishes a new baseline in the same way.
- A daily email should list only new matches that have not previously been sent to that search, ranked from best to worst match, up to a cap. A new match is a dog newly listed or newly becoming available and matching after the current baseline was established. When new matches exceed the cap, the email should say how many were left out and suggest making the description more specific on the management page. Dogs left out are not marked as sent, so they can appear in a later email.
- No email should be sent on a day with no new matches.
- Each search should get its own email. Searches that share an address are never combined into one digest.
- The subject should name the search and the count, e.g. "3 new dogs for Small dog for Mum".
- For each dog, the email should show: photo, name, breed, age, sex, size, suburb and state, approximate distance from the subscriber's postcode, adoption fee, rescue group, on-hold status where listed, and a link to the original listing.
- Each dog should carry a one-line reason it matches the description. A borderline dog carries a "check with the shelter" note naming what to confirm, e.g. "check: coat type not stated".
- Every daily match email should include the search's management link, a separate long, unguessable link to view and manage all active searches for that email address, a cancel link, a one-click unsubscribe that email clients can show natively, the date the search expires, why the recipient is getting the email, and who sends it.
- Emails should read well on a phone and still make sense when images are blocked.

## Managing a Search

- The user should be able to open a search's management page from any of its emails, without logging in.
- The management page should show the search's criteria, its expiry date, and when it last sent an email. It should show the email address partly masked, because anyone holding the link can see the page.
- The user should be able to open an all-searches management page from the separate link in any daily email, without logging in. That page should list every active search for that email address and offer edit and cancel controls for each one.
- The user should be able to edit any criterion except the email address. Saving an edit establishes a new baseline, so it does not send all currently available dogs that match the new criteria; later emails include only new matches.
- To use a different email address, the user should create a new search. That confirms the new address and keeps the link from being used to redirect a search to someone else.
- The user should be able to cancel a search from the management page, or with the cancel link in any email after one confirming button press. Cancelling stops all future emails at once.
- One-click unsubscribe from an email client should cancel that search without opening a page.
- After cancellation, the management link should show that the search was cancelled and offer to start a new one. It should not reveal the old criteria once the search's data has been deleted.

## Expiry and Renewal

- A search should expire after a fixed term from confirmation, so people who have already adopted stop getting emails without doing anything.
- Shortly before expiry, the user should receive one reminder email with a "Keep searching" link. The link opens a page whose button extends the search by another full term.
- Renewing should be possible from the management page at any time before expiry.
- An expired search should stop sending, and its management page should offer renewal for a grace period. After that, a server housekeeping task should periodically delete its data as if cancelled.

## Recovering Lost Links

- The user should be able to enter their email address on a "Find my alerts" page and receive an email with a long, unguessable link to manage all of that address's active alerts. The email should also list expired alerts still within their grace period, each with its renewal management link.
- The page should show the same response whether or not the address has any searches, so it can't be used to find out who subscribes.
- Recovery emails should be rate-limited per address, in the same way as confirmation emails.

## Matching

- A dog should match only when the AI judges it suitable for the user's free-text description and it meets the search's interstate-adoption choice.
- When interstate adoption is not included, a dog whose listed state differs from the subscriber's postcode state should be excluded. When interstate adoption is included, a dog whose listing says it cannot be adopted interstate should still be excluded.
- A listing that omits a detail relevant to the user's description should not be excluded for that omission. It is sent with a note naming the missing detail, in keeping with "never silently miss a dog".
- A dog should be ranked by how well it fits: confident matches first, then dogs sent with a "check" note. Within each group, the AI's assessed fit determines the order.
- A dog listed with an adopted status should never be sent. An on-hold dog may be sent, marked as on hold.
- A dog is identified by a source-scoped, stable per-dog listing identity, not by a page URL alone. A parser should use the source's listing ID where available; for a page containing several dogs, it must instead supply a stable per-dog identifier such as a card ID or canonical page URL plus a stable fragment. The identity must distinguish dogs sharing one page and remain the same across daily refreshes while the same listing remains available. A dog re-listed under a new source listing identity is treated as new, and so may reach a search a second time.

## Coverage

- At launch, the service should cover dogs listed on PetRescue in every Australian state and territory. This includes the many rescue groups and councils that post there.
- The website should state which sources are covered and that some large shelters with their own websites are not yet included, so users know to check those directly.
- Listings should be refreshed once a day, and emails sent after the refresh at a consistent morning time.

## Privacy and Consent

- The service should store only what it needs: the email address, the search criteria, which dogs were sent to each search, and the timestamps needed for confirmation, rate limits, and expiry.
- Cancelled, never-confirmed, and fully expired searches should have their email address and criteria deleted.
- The website should have a short privacy page covering what is stored, why, how long it is kept, and how to delete it (cancel the search).
- The privacy page should say that a search's free-text description and the public listing text are sent to a third-party AI provider, which may process them outside Australia. The email address, postcode, interstate-adoption choice, and search name should never be sent to the AI provider.
- The service should not sell or share email addresses, and should not add tracking pixels or rewrite links for tracking in emails.

## Operating the Service

These stories are for the operator, not subscribers.

- If a source's parsing fails or unexpectedly returns no dogs, the operator should be alerted. That day's emails should still go out for the sources that worked, and no email should imply the failed source had no new dogs.
- If AI judging fails for some dogs, those dogs should be held and retried on the next run, never sent unjudged or dropped.
- A dog should be recorded as sent to a search only after the email provider accepts the email. A failed send is retried on the next run without duplicating dogs already delivered.
- The operator should be able to see aggregate health: active searches, emails sent, bounces and complaints, and source failures. Browsing individual subscribers' email addresses is not part of this view.
- Hard-bouncing addresses and spam complaints should cancel the affected searches automatically, to protect delivery for everyone else.

## Retiring the Personal Pipeline

- The single-user Sydney pipeline (systemd timer, `data/state.json`, `data/dog-index.md`, and the Codex judge running on a personal subscription) should be retired once the service replaces it. Reusable, tested parts (the PetRescue parser, deduplication, and the fail-loud source manifest) move into the service.
- Git history remains the record of the personal index. No personal-pipeline data is migrated into the service.

## Not Planned

- User accounts, passwords, or social login.
- Payments, paid tiers, or advertising.
- A combined daily digest across searches that share an address.
- Emails on days with no new matches.
- Emails about status changes (on hold, adopted) for dogs already sent.
- Drive-time routing or distance-based search filters. Any displayed distance is straight-line.
- Species other than dogs.
- SMS, push notifications, or a mobile app.
- Shelters whose listings only render with JavaScript, at launch. Revisit once PetRescue coverage is live, and only with a sandboxed scraper, not the personal pipeline's unsandboxed browser agent.

## Open Questions

Values and choices still to confirm. The story they affect is in brackets.

| # | Question | Proposed default |
|---|---|---|
| Q1 | Ranking: confident matches, then "check" matches, each by AI-assessed fit? [Matching] | As written above |
| Q2 | Active searches per email address [Creating] | 5 |
| Q3 | Maximum dogs in one email [Daily emails] | 20 |
| Q4 | Unconfirmed search lifetime; confirmation/recovery emails per address per day [Confirming] | 7 days; 3 per day |
| Q5 | Search term; reminder lead time; post-expiry grace period [Expiry] | 90 days; 7 days; 30 days |
| Q6 | Daily email time and time zone [Coverage] | 1:00 pm Sydney time for everyone |
| Q7 | Does PetRescue permit this use of its listings, and does it want attribution or an API/feed arrangement? [Coverage] | Contact PetRescue before public launch |
| Q8 | Service name and domain [all emails and pages] | Undecided |
