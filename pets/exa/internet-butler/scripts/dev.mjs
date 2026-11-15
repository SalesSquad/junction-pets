#!/usr/bin/env node
// Start the key-holding relay and the Vite dev server together; stop both on Ctrl-C.
import { spawn } from "node:child_process";

// Node's fetch ignores HTTPS_PROXY unless told otherwise; respect it on proxied networks.
const relayEnv = process.env.HTTPS_PROXY || process.env.https_proxy ? { ...process.env, NODE_USE_ENV_PROXY: "1" } : process.env;

const procs = [
  spawn(process.execPath, ["relay/server.mjs"], { stdio: "inherit", env: relayEnv }),
  spawn(process.execPath, ["node_modules/vite/bin/vite.js"], { stdio: "inherit", env: process.env }),
];
const stop = () => procs.forEach((p) => p.kill("SIGTERM"));
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
procs.forEach((p) => p.on("exit", (code) => { if (code) { stop(); process.exitCode = code; } }));
