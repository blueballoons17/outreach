# UK Email Sequence

Segment: UK AEC firms. Tone: direct, low-hype, references TPS/PECR-compliant
opt-out. Merge fields are filled from config/constrox_facts.json and the
contact/company record — see src/constrox_sdr/content/email_sequences.py.

Any field still reading "[NEEDS REAL DATA...]" after rendering blocks the
message from being queued (see compliance.py).

---

## Step 1 — Day 0
Subject: Quick question about {{company_name}}'s {{sub_vertical}} capacity

Body:
Hi {{first_name}},

{{value_prop_short}}

Noticed {{company_name}} {{intent_signal_1_or_fallback}} — often a sign that drawing/estimating capacity gets tight before headcount catches up.

Worth a 15-minute call to see if {{company_display_name}} could take some of that load off your team?

{{sender_name}}
{{sender_title}}, {{company_display_name}}

{{unsubscribe_footer}}

---

## Step 2 — Day 3
Subject: Re: Quick question about {{company_name}}'s {{sub_vertical}} capacity

Body:
Hi {{first_name}},

Following up in case this landed at a busy moment.

{{value_prop_long}}

If capacity planning isn't a live issue right now, no worries — feel free to say so and I'll close the loop.

{{sender_name}}

{{unsubscribe_footer}}

---

## Step 3 — Day 8
Subject: How {{company_display_name}} supports {{sub_vertical}} teams

Body:
Hi {{first_name}},

A short summary of what we do, in case it's useful to forward internally:

{{services_bullet_list}}

Happy to send over more detail or jump on a call — whichever's easier for you.

{{sender_name}}

{{unsubscribe_footer}}

---

## Step 4 — Day 14 (breakup)
Subject: Should I close this out?

Body:
Hi {{first_name}},

I'll assume the timing isn't right and stop following up here — if that changes, my note is at {{booking_link}}.

All the best with the {{sub_vertical}} pipeline.

{{sender_name}}

{{unsubscribe_footer}}
