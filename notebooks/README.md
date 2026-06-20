# SkinGraph — Interview Q&A

This file is a living Q&A. The questions are written as if a **job recruiter** were
asking them in an interview. The answers are written so that **someone with no
technical background** can follow along — no jargon left unexplained, no acronyms
hiding meaning.

New questions get appended to the end.

---

## Q1. Describe the project in under a minute.

SkinGraph is an app that reads the back of a skincare bottle and tells you, in plain
language, whether the product is safe for *your* skin and how it fits into the
routine you already use.

Here's the problem it solves: skincare labels are genuinely hard to read. They're
often wrapped around a curved bottle, photographed at an angle, half-glared-out,
and crammed with tiny ingredient names in a mix of Japanese, Korean, and English.
Even when you *can* read them, most people can't tell a helpful ingredient from one
their skin reacts badly to.

SkinGraph does that work for you. You snap a photo of the label through a web page.
Behind the scenes the app cleans the image up, reads it with a vision AI, looks up
every ingredient against a curated safety database, checks the new product against
the products already on your "shelf," and writes you a short bilingual
(Japanese/English) note: *is this safe for you, does it clash with anything you
already own, and is it worth adding.*

The interesting engineering part is that it doesn't blindly trust the AI. AI
"reading" is probabilistic — it can hallucinate an ingredient that isn't there. So
the app has guardrails: it rejects unusable photos before spending money on AI
calls, it grounds every AI-extracted ingredient against a verified registry, and
the actual safety check is done with deterministic rules rather than the AI — so
the parts that matter for your skin aren't left to guesswork.

It's live on the web, built to deploy anywhere, and tuned especially for the
Japanese and Korean skincare markets, where labels are the hardest to read and the
most rewarding to get right.

---

## Upcoming questions

The questions below are queued for answering. When one gets answered, move it up into
a numbered **Q#** entry above this section (in the same plain-language voice) and
delete it from here.

### About the project itself
- **What problem were you actually trying to solve, and who has this problem?** *(the "why" behind it)*
- **How is this different from an app that just OCRs a label and lists ingredients?** *(the differentiator — guardrails/grounding)*
- **Walk me through what happens from the moment I upload a photo to the moment I see my result.** *(end-to-end flow)*
- **What can go wrong, and how does the app handle it?** *(failure modes — bad photo, AI hallucination, unknown ingredient)*
- **What's a feature you're proud of that most people wouldn't notice?** *(the clever engineering bits)*

### About the business / impact
- **Who is this for, and would they actually pay for it?** *(audience & value)*
- **How do you know it's accurate enough to trust with someone's skin?** *(evaluation harness)*
- **What does it cost you to run, and where does that cost come from?** *(cost-saving design — Flash-first, Pro-when-needed)*
- **What's live today versus what's still a prototype?** *(honest scoping — Railway live, AWS/Terraform reference-only)*

### About you as an engineer
- **What was the hardest part to build, and how did you approach it?** *(judgment + process)*
- **What would you do differently if you started over?** *(self-awareness)*
- **What did you learn that you didn't know going in?** *(growth)*
- **How do you decide what to build next?** *(prioritization)*

### Classic recruiter closers
- **Tell me about a trade-off you made and why you chose it.**
- **If I gave you three more months and a budget, what would you do with it?**
- **Why this project — of all the things you could build, why skincare labels?** *(motivation)*