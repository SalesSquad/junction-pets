// Node wrapper for the Kättely-based eligibility proofs (server side: needs python3, libsodium and a
// Kättely checkout at KATTELY_PATH). The private value is passed on stdin and never logged.
import { spawn } from "node:child_process";

const SCRIPT = new URL("./eligibility.py", import.meta.url).pathname;

function run(cmd, payload) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON ?? "python3", [SCRIPT, cmd], { stdio: ["pipe", "pipe", "pipe"] });
    let out = "";
    let err = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) return reject(new Error(`eligibility bridge exited ${code}: ${err.slice(0, 200)}`));
      try {
        resolve(JSON.parse(out));
      } catch {
        reject(new Error("eligibility bridge returned invalid JSON"));
      }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}

/** Prove 0 <= value <= threshold without revealing value. Returns null when the value is not eligible. */
export async function proveEligibility({ value, threshold, bits = 32, context }) {
  const r = await run("prove", { value, threshold, bits, context });
  return r.ok ? r.proof : null;
}

export async function verifyEligibility(proof) {
  const r = await run("verify", { proof });
  return r.ok === true && r.valid === true;
}

/** True when the bridge can run here (python3 + Kättely + libsodium). */
export async function eligibilityAvailable() {
  try {
    const p = await proveEligibility({ value: 1, threshold: 2, bits: 4, context: { probe: true } });
    return !!p && (await verifyEligibility(p));
  } catch {
    return false;
  }
}
