# Dog Finder: Daily Adoption Alerts for Australian Rescue Dogs

Dog Finder emails people a daily list of newly listed rescue dogs that match what they are looking for. It works like a price tracker: there is no account and no password. A subscriber describes the dog they want, confirms their email address, and receives a daily email when new matches appear. Every email carries a private link to view, edit, or cancel that search.

**Status:** proposed product requirements, not a verified account of implementation status. This product is intended to replace the personal pipeline (see *Retiring the Personal Pipeline*). The original defaults under *Agreed Defaults* are confirmed; review additions clarify edge cases and launch dependencies. Remaining decisions appear under *Open Questions*.

## Product Principles

- **No accounts.** Private, unguessable links grant access. A search link manages one search; a separate address-wide link manages every search for that address. Treat both as credentials.
- **Include uncertain matches.** Missing information should produce a note saying what to check, rather than silently exclude a dog. Coverage and AI assessment cannot guarantee finding every suitable dog.
- **Only send what's new.** Avoid repeating a listing within a search, and send no match email on a day with nothing new. Confirmation, recovery, and expiry reminders are separate service emails.
- **Respect the inbox.** Only requested confirmation or recovery emails may be sent before verification. Match emails require an activated search. Every email identifies the sender; emails for an activated search offer cancellation.
- **Free, with limits.** There are no payment or billing flows. Per-address limits discourage abuse; service-wide capacity and cost controls are also needed.

## Creating a Search

- The user should be able to create a search from the website without signing up, by filling in one form:
    - **Email address** (required).
    - **Home postcode** (required), used to identify the subscriber's home state.
    - **Include interstate adoption** (required yes/no choice; see *Matching*).
    - **Search name** (required), e.g. "Small dog for Mum", used in email subjects and on the management page.
    - **What you are looking for** (required free text, maximum 300 characters after trimming surrounding whitespace). Explain that AI assesses this description, prompt for the preferences that matter most, and show a remaining-character count. Example: "A calm, low-shedding small adult dog for an apartment with a cat". Ask users to avoid names, contact details, and sensitive personal information.
- The form should say plainly that the description is read by AI, and that results are a shortlist to check with the shelter, not a guarantee.
- The form should refuse an invalid email address, an unknown postcode, an omitted search name or description, or an unselected interstate-adoption choice, and explain what to fix without clearing the other fields. The server should also reject a description that exceeds the same 300-character limit, preserving the entered description and explaining the limit.
- After submitting, the user should see a "check your inbox" page. To prevent spam, nothing is matched or sent until the user verifies their email address and activates the search.
- One verified email address can hold several independent searches, up to a fixed limit on active searches. Pending, cancelled, and expired searches do not count. Enforce the limit when activating or renewing, including simultaneous requests. Explain a reached limit only after verification and offer access to existing searches; public submission pages must not reveal whether an address already subscribes.

## Confirming a Search

- After submitting, the user should receive one verification email that summarises the search criteria. It has an "Activate this search" link and says that a recipient who did not request the search should discard the email.
- The activation link should open a page with a button, and act only when the button is pressed. Mail security scanners follow links automatically, so a link alone must never activate a search.
- Confirmation links should expire with the pending search and be usable only once. An invalid or expired link should explain how to request a new one; repeated confirmation must not create another search.
- Confirming activates the search and opens its management page. That page says an email arrives after a later daily run only when a dog newly matches; it does not send a catch-up catalogue of dogs already available at activation.
- A server housekeeping task should periodically delete a search that is never verified after its short confirmation period.
- Repeated submissions for the same address should not send more than a few confirmation emails per day, so the form can't be used to flood someone's inbox.

## Daily Match Emails

- On activation or a matching-criteria edit, establish a baseline of currently available listings. Existing available listings are not an initial catalogue, even if AI assessment happens later. Renaming a search does not reset its baseline.
- If a source has no trustworthy snapshot, show that its baseline is pending. Its first successful refresh establishes the baseline without sending a catch-up catalogue; other ready sources can proceed normally.
- A new candidate is a listing first observed after the baseline, or one explicitly changing from unavailable to available after it. A description update alone does not make an existing available listing new. A failed refresh or a listing's temporary absence does not establish that it became unavailable.
- A daily email should list matching candidates not previously sent to that search, ranked by fit, up to a cap. When candidates exceed the cap, state how many remain. Retain the remainder for later emails while they remain available and match the current criteria. Delayed assessment or delivery must not lose candidates merely because another day has passed.
- No email should be sent on a day with no new matches.
- Each search should get its own email. Searches that share an address are never combined into one digest.
- The subject should name the search and the count, e.g. "3 new dogs for Small dog for Mum".
- For each dog, show the available photo, name, breed, age, sex, size, suburb and state, adoption fee, rescue group, on-hold status, and original listing link. Label relevant missing facts as unknown; do not invent them. Where location data allows it, show an approximate straight-line distance from the home postcode, clearly labelled as an estimate.
- Each dog should carry a one-line reason it matches the description. A borderline dog carries a "check with the shelter" note naming what to confirm, e.g. "check: coat type not stated".
- Every daily match email should include the search's management link, a separate long, unguessable link to view and manage all active searches for that email address, a cancel link, a one-click unsubscribe that email clients can show natively, the date the search expires, why the recipient is getting the email, and who sends it.
- Emails should read well on a phone and still make sense when images are blocked.

## Managing a Search

- The user should be able to open a search's management page from any of its emails, without logging in.
- The management page should show the search's criteria, its expiry date, and when it last sent an email. It should show the email address partly masked, because anyone holding the link can see the page.
- Management credentials should be separate from public listing/search identifiers and unsubscribe credentials. Keep them out of analytics, logs, and referrers to external sites. Reading a page must not change a search; edits, cancellation, and renewal require an explicit action. Native one-click unsubscribe is the separate machine-action exception.
- The user should be able to open an all-searches management page from the separate link in any daily email, without logging in. That page should list every active search for that email address and offer edit and cancel controls for each one.
- The user should be able to edit any criterion except the email address, using the same validation as creation. Changing matching criteria resets the baseline and discards pending candidates under the old criteria, while preserving the history of listings already sent. Renaming preserves both the baseline and pending candidates.
- To use a different email address, the user should create a new search. That confirms the new address and keeps the link from being used to redirect a search to someone else.
- The user should be able to cancel a search from the management page, or with the cancel link in any email after one confirming button press. Cancellation stops future sends, including queued match emails and reminders; an email already accepted by the provider cannot be recalled. Repeating cancellation should be harmless.
- One-click unsubscribe from an email client should cancel that search without opening a page.
- After cancellation, the management link should show that the search was cancelled and offer to start a new one. It should not reveal the old criteria once the search's data has been deleted.

## Expiry and Renewal

- A search should expire after a fixed term from confirmation, so people who have already adopted stop getting emails without doing anything.
- Shortly before expiry, the user should receive one reminder per expiry date with a "Keep searching" link. Its button sets expiry to the later of the existing expiry and one full term from renewal, so repeated clicks cannot accumulate extra terms.
- Renewing should be possible from the management page at any time before expiry.
- An expired search should stop sending, and its management page should offer renewal for a grace period. After that, a server housekeeping task should periodically delete its data as if cancelled.
- Renewal before expiry preserves the baseline. Renewal during the grace period requires an available active-search slot and establishes a fresh baseline, with no catch-up for the inactive period; retain the history of listings already sent.

## Recovering Lost Links

- The user should be able to enter their email address on a "Find my alerts" page and receive an email with a long, unguessable link to manage all of that address's active alerts. The email should also list expired alerts still within their grace period, each with its renewal management link.
- The page should show the same response whether or not the address has any searches, so it can't be used to find out who subscribes.
- Recovery emails should be rate-limited per address, in the same way as confirmation emails.
- Recovery should let the verified recipient replace private management links if a link was shared or exposed, invalidating the old credentials.

## Matching

- A dog is a candidate match when its listing supports suitability or leaves relevant details unknown. Exclude clear conflicts with the description; label uncertainty. Apply location and availability rules separately from AI assessment.
- When interstate adoption is not included, exclude a dog whose listed state differs from the subscriber's home state. When interstate adoption is included, exclude an out-of-state dog whose listing explicitly prohibits adoption into the subscriber's state.
- An interstate restriction does not exclude a dog in the subscriber's own state. Unknown location or adoption eligibility should produce a "check with the shelter" note. If a postcode maps to more than one state or territory, ask the user to choose rather than silently assigning one.
- A listing that omits a detail relevant to the user's description should not be excluded for that omission. It is sent with a note naming the missing detail, in keeping with "include uncertain matches".
- A dog should be ranked by how well it fits: confident matches first, then dogs sent with a "check" note. Within each group, the AI's assessed fit determines the order.
- A dog listed with an adopted status should never be sent. An on-hold dog may be sent, marked as on hold.
- A dog is identified by a source-scoped, stable per-dog listing identity, not by a page URL alone. A parser should use the source's listing ID where available; for a page containing several dogs, it must instead supply a stable per-dog identifier such as a card ID or canonical page URL plus a stable fragment. The identity must distinguish dogs sharing one page and remain the same across daily refreshes while the same listing remains available. A dog re-listed under a new source listing identity is treated as new, and so may reach a search a second time.

## Coverage

- At launch, the service should cover dogs listed on PetRescue in every Australian state and territory. This includes the many rescue groups and councils that post there.
- The website should state which sources are covered and that some large shelters with their own websites are not yet included, so users know to check those directly.
- Listings should be refreshed once a day, and emails sent after the refresh at a consistent published time and time zone. Display the latest successful refresh and any coverage outage on the website.

## Privacy and Consent

- Store only data needed to operate the service: email address, criteria, link credentials stored securely, baseline and pending-candidate state, sent-listing history, lifecycle timestamps, and limited delivery, abuse-prevention, and suppression records.
- Delete cancelled and fully expired search data within a published retention period, and unconfirmed search data after its confirmation window. Preserve data needed by other searches for the same address. Retain only minimal suppression records needed to prevent sending again to blocked addresses, and disclose retention for logs and backups.
- The website should have a short privacy page covering what is stored, why, how long it is kept, and how to delete it (cancel the search).
- The privacy page should say that a search's free-text description and the public listing text are sent to a third-party AI provider, which may process them outside Australia. Do not include the email, postcode, interstate-adoption choice, or search-name fields in AI requests. Explain that personal details typed into the description will be processed with that text.
- Do not sell email addresses or share them for advertising. Disclose service providers that process them to deliver the service, including the email provider. Do not add tracking pixels or rewrite links for tracking in emails.

## Operating the Service

These stories are for the operator, not subscribers.

- If a source's parsing fails or unexpectedly returns no dogs, the operator should be alerted. That day's emails should still go out for the sources that worked, and no email should imply the failed source had no new dogs.
- If AI judging fails for some dogs, hold them for retry without losing their eligibility. Alert the operator to persistent failures. Before sending delayed candidates, recheck current known availability and the search's active state and criteria.
- Record a dog as sent only after the email provider accepts the email; acceptance does not guarantee inbox delivery. Use a durable send record and provider idempotency where supported so retries do not duplicate an accepted batch. If acceptance is unknown after a timeout, reconcile it before retrying; do not promise exactly-once delivery without provider support.
- The operator should be able to see aggregate health: active searches, emails sent, bounces and complaints, and source failures. Browsing individual subscribers' email addresses is not part of this view.
- Hard bounces and spam complaints should suppress all mail to that address and cancel its searches. New submissions must not bypass suppression.
- Rate-limit submissions and recovery by address and request source, bound pending searches, and set service-wide AI/email budgets. If capacity is exhausted, explain delays or temporarily stop accepting new searches; alert the operator and preserve pending work.

## Retiring the Personal Pipeline

- The single-user Sydney pipeline (systemd timer, `data/state.json`, `data/dog-index.md`, and the Codex judge running on a personal subscription) should be retired once the service replaces it. Reusable, tested parts (the PetRescue parser, deduplication, and the fail-loud source manifest) move into the service.
- Git history remains the record of the personal index. No personal-pipeline data is migrated into the service.

## Not Planned

- User accounts, passwords, or social login.
- Payments, paid tiers, or advertising.
- A combined daily digest across searches that share an address.
- Match emails on days with no new matches.
- Emails about status changes (on hold, adopted) for dogs already sent.
- Drive-time routing or distance-based search filters. Any displayed distance is straight-line.
- Species other than dogs.
- SMS, push notifications, or a mobile app.
- Shelters whose listings only render with JavaScript, at launch. Revisit once PetRescue coverage is live, and only with a sandboxed scraper, not the personal pipeline's unsandboxed browser agent.

## Agreed Defaults

These values apply to the requirements above.

| Setting | Decision |
|---|---|
| Ranking | Confident matches first, then "check" matches, each ordered by AI-assessed fit |
| Active searches per email address | 5 |
| Initial active subscriber limit | 250 distinct verified email addresses with at least one active search; enforce at activation and grace-period renewal |
| Monthly operating budget | US$50 target, US$100 ceiling before tax; alert above the target and defer work before exceeding the ceiling (see DESIGN.md) |
| Maximum dogs in one email | 20 |
| Unconfirmed search lifetime | 7 days |
| Confirmation/recovery emails per address | 3 per day combined |
| Search term | 90 days |
| Expiry reminder | 7 days before expiry |
| Post-expiry renewal grace period | 30 days |
| Daily email schedule | 1:00 pm Sydney time for everyone, following Sydney daylight saving changes |
| Source permission | Contact PetRescue before public launch to confirm permitted use, attribution, and any API/feed arrangement; approval is not yet established |

## Open Questions

- Service name and domain remain undecided.
- Set and publish search-data deletion deadlines and retention periods for logs, backups, and suppression records.
- Decide how long to retain pending work during prolonged outages; initial capacity and spending limits are agreed above.
- Verify that chosen providers support listing access and reuse, the stated AI data handling, and email unsubscribe and retry requirements before implementation commitments.

## Minimum Launch Checks

- Creating, confirming, receiving a match, editing, recovering access, renewing, and cancelling work end to end without an account.
- Old listings stay out of a new baseline; overflow and failed assessments survive daily runs; edits and grace-period renewal follow the stated baseline rules.
- Link scanners cannot activate, edit, renew, or cancel searches by fetching a page. A search link cannot manage another search, and public forms do not disclose subscribers.
- Quotas hold under simultaneous requests. Cancellation, expiry, bounces, and complaints prevent queued sends. Provider timeouts do not trigger blind retries.
- Source failures are visible, recovery does not send a catch-up catalogue of baseline listings, and published deletion deadlines are enforced.
- Source permission, provider suitability, sender identity, privacy information, and the unresolved launch values above are settled before public launch.
