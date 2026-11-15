#!/usr/bin/env node
// Second, cross-family judge: OpenAI labels every judge batch with the same blind instructions.
// The key is read from the owner's local credential file at runtime and never printed or stored.
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";

const here = new URL(".", import.meta.url);
const MODEL = process.env.JUDGE_MODEL || "gpt-5.4-mini";
const envFile = process.env.OPENAI_ENV_FILE || `${homedir()}/.config/openai/factory-decisions.env`;
const key = readFileSync(envFile, "utf8").match(/^OPENAI_API_KEY=(.+)$/m)?.[1]?.trim().replace(/^["']|["']$/g, "");
if (!key) throw new Error("OPENAI_API_KEY not found in the credential file");
const instructions = readFileSync(new URL("judge/PROMPT.md", here), "utf8");
const batches = readdirSync(new URL("judge/", here)).filter((f) => /^batch\d+\.json$/.test(f)).sort((a, b) => parseInt(a.slice(5)) - parseInt(b.slice(5)));

async function judge(items) {
  for (let attempt = 0; attempt < 4; attempt++) {
    const r = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
      body: JSON.stringify({
        model: MODEL,
        response_format: { type: "json_object" },
        messages: [
          { role: "system", content: `${instructions}\n\nReturn a JSON object {"labels": [...]} where labels is the array described above.` },
          { role: "user", content: JSON.stringify(items) },
        ],
      }),
    });
    if (r.status === 429 || r.status >= 500) { await new Promise((s) => setTimeout(s, 2000 * 2 ** attempt)); continue; }
    const j = await r.json();
    if (!r.ok) throw new Error(`OpenAI HTTP ${r.status}: ${j.error?.message?.slice(0, 200)}`);
    return { labels: JSON.parse(j.choices[0].message.content).labels, usage: j.usage };
  }
  throw new Error("OpenAI retries exhausted");
}

const all = [];
let tokensIn = 0, tokensOut = 0;
const queue = [...batches];
await Promise.all(Array.from({ length: 4 }, async () => {
  while (queue.length) {
    const f = queue.shift();
    const items = JSON.parse(readFileSync(new URL(`judge/${f}`, here), "utf8"));
    const { labels, usage } = await judge(items);
    tokensIn += usage?.prompt_tokens ?? 0;
    tokensOut += usage?.completion_tokens ?? 0;
    const got = new Set(labels.map((l) => l.item));
    const missing = items.filter((i) => !got.has(i.item)).length;
    all.push(...labels);
    console.log(`${f}: ${labels.length} labels${missing ? `, ${missing} missing` : ""}`);
  }
}));
all.sort((a, b) => a.item - b.item);
writeFileSync(new URL("judge/openai_labels.json", here), JSON.stringify(all, null, 1));
console.log(`model ${MODEL}: ${all.length} labels, tokens in ${tokensIn}, out ${tokensOut}`);
