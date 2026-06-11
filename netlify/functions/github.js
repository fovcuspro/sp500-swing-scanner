const REPO = 'fovcuspro/sp500-swing-scanner';
const BASE = 'https://api.github.com';

exports.handler = async (event) => {
  const cors = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json',
  };

  if (event.httpMethod === 'OPTIONS') return { statusCode: 200, headers: cors };
  if (event.httpMethod !== 'POST')
    return { statusCode: 405, headers: cors, body: JSON.stringify({ error: 'Method not allowed' }) };

  const token = process.env.GITHUB_TOKEN;
  if (!token)
    return { statusCode: 500, headers: cors, body: JSON.stringify({ error: 'Server misconfigured — GITHUB_TOKEN not set' }) };

  const gh = {
    Authorization: `token ${token}`,
    Accept: 'application/vnd.github.v3+json',
    'Content-Type': 'application/json',
    'User-Agent': 'swing-scanner/1.0',
  };

  let body;
  try { body = JSON.parse(event.body || '{}'); }
  catch { return { statusCode: 400, headers: cors, body: JSON.stringify({ error: 'Invalid JSON body' }) }; }

  const { action } = body;

  try {
    // Trigger both workflows
    if (action === 'run') {
      const ref = JSON.stringify({ ref: 'main' });
      const [r1, r2] = await Promise.all([
        fetch(`${BASE}/repos/${REPO}/actions/workflows/daily_scan.yml/dispatches`,      { method: 'POST', headers: gh, body: ref }),
        fetch(`${BASE}/repos/${REPO}/actions/workflows/daily_portfolio.yml/dispatches`, { method: 'POST', headers: gh, body: ref }),
      ]);
      if (r1.status !== 204 || r2.status !== 204) {
        const err = await (r1.status !== 204 ? r1 : r2).json().catch(() => ({}));
        throw new Error(err.message || 'Failed to trigger workflows');
      }
      return { statusCode: 200, headers: cors, body: JSON.stringify({ ok: true }) };
    }

    // Read portfolio.json (returns positions + SHA needed for writes)
    if (action === 'get_portfolio') {
      const r = await fetch(`${BASE}/repos/${REPO}/contents/portfolio.json`, { headers: gh });
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.message || `GitHub ${r.status}`); }
      const data = await r.json();
      const positions = JSON.parse(Buffer.from(data.content, 'base64').toString('utf8'));
      return { statusCode: 200, headers: cors, body: JSON.stringify({ positions, sha: data.sha }) };
    }

    // Write portfolio.json
    if (action === 'save_portfolio') {
      const { positions, sha, message } = body;
      const content = Buffer.from(JSON.stringify(positions, null, 2) + '\n').toString('base64');
      const r = await fetch(`${BASE}/repos/${REPO}/contents/portfolio.json`, {
        method: 'PUT', headers: gh,
        body: JSON.stringify({ message: message || 'portfolio: update', content, sha }),
      });
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.message || `GitHub ${r.status}`); }
      return { statusCode: 200, headers: cors, body: JSON.stringify({ ok: true }) };
    }

    // Proxy Groq insights request — keeps API key server-side
    if (action === 'insights') {
      const apiKey = process.env.GROQ_API_KEY;
      if (!apiKey) throw new Error('GROQ_API_KEY not set on server');

      const { prompt } = body;
      const r = await fetch('https://api.groq.com/openai/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model: 'llama-3.1-8b-instant',
          max_tokens: 1000,
          temperature: 0.4,
          messages: [
            {
              role: 'system',
              content: `You are a quantitative trading strategy analyst reviewing performance data for a momentum pullback scanner on the S&P 500.
The scanner uses these rules: Price > 50 MA > 200 MA, RSI 40-52, pullback 3-8% from 20-day high, volume > 1.3x average, bullish candle.
Scoring weights: Trend 40%, Pullback quality 40%, Volume 20%.

Respond ONLY with a valid JSON array of insight objects. No preamble, no markdown, no backticks.
Each insight object must have exactly these fields:
- "title": string (max 8 words, specific and actionable)
- "body": string (2-3 sentences of specific, data-driven analysis)
- "action": string (one concrete next step, max 15 words)
- "priority": "high" | "medium" | "low"
- "type": "warn" | "good" | "info" | "alert" | "idea"

Generate 4-6 insights. Be specific — reference actual numbers from the data. If data is thin, reason about parameter quality and structural issues instead.`,
            },
            { role: 'user', content: prompt },
          ],
        }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error(e.error?.message || `Groq API error ${r.status}`);
      }
      const data = await r.json();
      const raw = data.choices?.[0]?.message?.content || '[]';
      const cleaned = raw.replace(/```json|```/g, '').trim();
      const insights = JSON.parse(cleaned);
      return { statusCode: 200, headers: cors, body: JSON.stringify({ insights }) };
    }

    return { statusCode: 400, headers: cors, body: JSON.stringify({ error: `Unknown action: ${action}` }) };

  } catch (err) {
    return { statusCode: 500, headers: cors, body: JSON.stringify({ error: err.message }) };
  }
};
