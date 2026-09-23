# AI Engineer Assignment — Perfect Saturday Planner

## Build a "Perfect Saturday Planner" Agent

Build a small AI-powered agent that helps someone plan a fun Saturday.

The user gives their city, budget, available time, mood, interests, and constraints. Your agent should create a personalised plan that feels useful, practical, and fun.

**Build this as a hosted web app.** We need a live URL we can open, type into, and test ourselves — no local setup on our end. Use any stack you like.

---

We value simplicity and product thinking more than polish.

You may use ChatGPT, Claude, Cursor, Copilot, Replit, Lovable, or any AI coding tool — just be ready to explain your decisions.

---

## Required Input

Your app should accept:

```json
{
  "city": "Bangalore",
  "budget": 2000,
  "available_time": "4 hours",
  "mood": "tired but wants to do something fun",
  "interests": ["food", "music", "walks"],
  "constraints": ["vegetarian", "avoid crowded places"]
}
```

Free-text input is also fine if you prefer a more conversational feel.

---

## Required Behaviour

Your agent should:

- **Hosted UI** — deployed and accessible via a public URL (Vercel, Netlify, Streamlit Cloud, Railway, anything)
- Understand the user's preferences
- Use **at least 3 tools/functions** — not one giant prompt
- Generate a realistic, specific plan
- Explain why each part of the plan fits the user
- Handle at least one failure case gracefully
- Show a simple trace of what the agent did

---

## Example Tools

You can mock all of these. **No real APIs required.**

- `parseUserPreferences(input)`
- `getActivityOptions(city, interests)`
- `getFoodOptions(city, budget, constraints)`
- `estimateCost(plan)`
- `validatePlan(plan, constraints)`
- `generateFinalPlan(context)`

Mock data is fine for the base submission. If you want to go further, see Bonus Points below.

---

## Bonus Points

- **Real data instead of mocks** — if you can find a free or scrappy way to pull real places (Google Places API, Zomato/Swiggy for food, Meetup or Insider for events, Foursquare, OpenStreetMap, even a quick web scrape) that's a strong signal. We're not looking for perfect API integration — we're looking for resourcefulness.
- Streaming "agent is thinking" trace
- A fallback plan when no options match
- Agent asks 1–2 clarifying questions when input is vague
- Agent explains trade-offs (e.g. "this place is slightly over budget but fits your mood better")
- Agent avoids making unrealistic suggestions

---

## What to Submit

1. **Live URL** — required. We will open it and test it.
2. GitHub repo or zip file
3. README with run instructions (for running locally)
4. 2–3 lines on how you used AI tools during the build
