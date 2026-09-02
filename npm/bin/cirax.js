#!/usr/bin/env node
// cirax bin shim: execs the Python CLI installed into the package venv.
//
// npm >= 12 blocks lifecycle scripts for installed packages by default, so
// the shim bootstraps the Python core itself on first invocation (idempotent;
// postinstall just pre-warms the same thing for people who allow scripts).
"use strict";

const { spawn, spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const pkgRoot = path.join(__dirname, "..");
const venv = path.join(pkgRoot, ".venv");
const venvBin = process.platform === "win32"
  ? path.join(venv, "Scripts")
  : path.join(venv, "bin");
const bin = path.join(venvBin, "cirax");

function ensureCore() {
  if (fs.existsSync(bin)) return true;
  console.error("cirax: first run — installing the Python core (one time)...");
  const res = spawnSync(process.execPath,
    [path.join(pkgRoot, "scripts", "postinstall.js")], { stdio: "inherit" });
  if (res.status !== 0 || !fs.existsSync(bin)) {
    console.error(
      "cirax: could not install the Python core automatically.\n" +
      "  Needs `uv` or python3 + pip on PATH, then:\n" +
      "    npm rebuild cirax\n" +
      "  Or install into the package venv manually:\n" +
      `    uv venv ${venv} && uv pip install --python ${path.join(venvBin, "python")} ${pkgRoot}`
    );
    return false;
  }
  return true;
}

if (!ensureCore()) process.exit(1);

const child = spawn(bin, process.argv.slice(2), { stdio: "inherit" });
child.on("error", (err) => {
  console.error("cirax: failed to launch:", err.message);
  process.exit(1);
});
child.on("close", (code) => process.exit(code ?? 1));
