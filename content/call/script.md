# Cold Call Script — Discovery Outreach

For human execution or a consent-based dialer only (see compliance.py
operating-hours + DNC gate). Do not call numbers on the DNC list or outside
the configured market window.

## Opening
"Hi {{first_name}}, this is {{sender_name}} calling from {{company_display_name}} —
did I catch you at a bad time?"

- If bad time: "No problem — is there a better time in the next couple of
  days, or should I follow up by email instead?" → log outcome, offer
  email/booking link, end call.
- If ok: continue.

## Reason for call
"{{value_prop_short}} I was calling {{sub_vertical}} teams like {{company_name}}
specifically because {{intent_signal_1_or_fallback}} — figured it was worth
a quick conversation to see if it's relevant."

## Discovery questions
1. "How is {{company_name}} currently handling overflow {{sub_vertical}} work when things get busy?"
2. "What does the team look like right now — mostly in-house, or do you already use outside support for any of it?"
3. "If capacity became a bottleneck in the next quarter, what would that look like for you?"

## Objection handling

**"We already have an in-house team / vendor."**
"Makes sense — most teams we work with do too. We usually come in as
overflow support rather than a replacement, so it's less about switching
and more about having flex capacity when things spike. Would it be worth
a short call to see if that pattern fits how you work?"

**"Not interested / no budget."**
"Understood, appreciate you saying so directly. Would it be OK if I sent a
short email so you have something to reference if that changes later?" →
if no, mark do_not_contact and end.

**"Send me something in writing first."**
"Happy to — I'll send a short note to {{email}} with {{booking_link}} in case
it's useful later. Anything specific you'd want it to cover?"

**"How is this different from [competitor / current vendor]?"**
"[NEEDS REAL DATA — differentiation vs. named competitors must come from
Constrox; do not improvise a comparison on the call]. What I can say
directly is: {{value_prop_long}}"

## Close
- If interested: book discovery call directly using {{booking_link}}, confirm
  timezone, log deal stage → "Discovery Scheduled".
- If not now: ask permission for one follow-up touch, log stage → "Contacted", set follow-up reminder.
- If not interested: log stage → "Closed Lost", reason, and honor any DNC request immediately.
