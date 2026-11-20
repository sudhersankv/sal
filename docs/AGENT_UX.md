# Sal: agent-first UX

Sal is the product. The dashboard is a window into Sal, not a set of reports. Every surface answers three questions: **what is Sal doing, what does it need from me, and why did it do that?**

## Principles
1. **Sal speaks first.** Sal brings up what matters now: things waiting on the owner, risks (stock-outs, late vendors, missing credits) and what it did on its own. The owner rarely has to go looking.
2. **Every action is a card with a status.** `planned → waiting on you → in progress → done | refused | failed`. Each card has **Approve / Decline** when it needs the owner, and **Why?** always.
3. **Why? is one tap away.** It opens the trace: what Sal looked at (sources: Senso rule, SingleStore history, SIE verdict, Cognee memory, NHTSA), what it rejected and why, what it chose, the money, and the policy checks it passed.
4. **It adapts.** Sal remembers preferences and patterns in Cognee: preferred vendors, quiet hours, how much detail the owner wants, which approvals the owner always grants. It uses them, and says when it does ("You usually OK Mission for starters, so I went ahead"). It never changes the owner's rules (Senso) on its own; it proposes them.
5. **Same Sal everywhere.** Telegram and the dashboard share one memory and one action list. Approving in one updates the other.
6. **No internal jargon in front of people.** No run IDs, event names, "RO event" or tool names in messages. Plain parts-counter language with numbers.

## Telegram (the main way to interact)
**Voice:** a terse, competent parts guy texting the owner. Short lines with numbers: cost, quantity, ETA, vendor.

**Inbound (owner or tech → Sal), free-form; Sal works out the intent:**
| Intent | Example | Sal does |
|---|---|---|
| Urgent part for a job | "Civic bay 2, P0141, promised 3pm" | Sources, quotes, orders inside the rules, replies with part / vendor / cost / ETA |
| Stock question | "are we low for the Civics next week?" | Checks stock against bookings and lists what's short and what it costs to cover |
| Go-ahead | "yea go get them" | Acts on the previous proposal, then confirms with order, total and ETA |
| Order status | "where's the Bosch order?" | Status and ETA, and flags it if it's late |
| Vendor question | "is Bayshore still late?" | Scorecard numbers and a recommendation |
| Bill / statement | 📎 PDF or 📷 photo | Parses it (SIE), reconciles it, reports what's missing, drafts a dispute (not sent) |
| Preference | "don't ping me after 7pm", "always use Mission for starters" | Remembers it (Cognee); if it changes a rule, proposes the rule for approval |
| Why | "why Mission?" / tapping **Why?** | Short reason plus the 2–3 sources |

**Outbound (Sal → owner), proactive:**
- **Needs you:** over-cap orders and rule proposals, with **Approve / Decline / Why?** buttons. Over-cap orders also carry the **Persona** verification link.
- **Done:** "Ordered 1× Denso O2 @ Mission $41, here 10:20."
- **Heads-up:** stock-outs coming from bookings, late deliveries, missing core credits.
- **Daily brief (morning):** what arrives today, what's low, what's waiting on you, spend so far this week.

**Commands (shortcuts; free text always works):** `/today` brief · `/stock` low items · `/orders` open orders · `/waiting` approvals · `/why <order|job>` trace · `/demo` simulated week (hidden).

**Mechanics:** show a typing indicator while working. Send one reply per request, then follow-ups only when the state changes. Inline keyboards for every decision. Edit the original message when a status changes instead of spamming.

## Dashboard
- **Home = Sal.** A live feed of Sal's action cards (with waiting-on-you pinned on top), a chat box to talk to Sal (same brain as Telegram), and the **3D parts room** showing stock levels with live reactions.
- **Inventory · Orders · Jobs · Vendors:** drill-downs. Every row has **Why?** linking to the trace.
- **Activity & Trace:** conversations (Telegram + UI), the action timeline, the full event trace (sources, reasons, money, raw JSON) and integration status (which sponsors are live).
- **Demo:** the Mon–Sun simulation, kept out of the main experience.
