// postinstall: create a private venv inside the npm package and install the
// bundled Python core into it (the pyright pattern).
//
// Resolution order for the Python source:
//   1. ./python    — the bundled copy (present in the published npm tarball,
//                    created by `npm run build:python`)
//   2. ../         — developing from a git checkout of the repo
//
// Installer order: uv (fast, no external Python needed) → python3 venv+pip.

"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const pkgRoot = path.join(__dirname, "..");
const venv = path.join(pkgRoot, ".venv");
const venvBin = process.platform === "win32"
  ? path.join(venv, "Scripts")
  : path.join(venv, "bin");

function srcDir() {
  const bundled = path.join(pkgRoot, "python");
  if (fs.existsSync(path.join(bundled, "pyproject.toml"))) return bundled;
  const repo = path.join(pkgRoot, "..");
  if (fs.existsSync(path.join(repo, "pyproject.toml"))) return repo;
  return null;
}

function run(cmd, args, opts) {
  const res = spawnSync(cmd, args, { stdio: "inherit", ...(opts || {}) });
  return res.status === 0;
}

function main() {
  if (process.env.CIRAX_SKIP_POSTINSTALL === "1") {
    console.log("cirax: CIRAX_SKIP_POSTINSTALL=1, skipping Python install");
    return;
  }
  const src = srcDir();
  if (!src) {
    console.error("cirax: no bundled Python source found; " +
                  "run `npm run build:python` before publishing");
    process.exit(1);
  }

  fs.rmSync(venv, { recursive: true, force: true });

  if (spawnSync("uv", ["--version"]).status === 0) {
    console.log("cirax: installing Python core with uv");
    if (run("uv", ["venv", venv]) &&
        run("uv", ["pip", "install", "--python", path.join(venvBin, "python"), src])) {
      return done();
    }
    console.error("cirax: uv install failed, falling back to python3/pip");
  }

  const py = spawnSync("python3", ["--version"]).status === 0 ? "python3"
    : spawnSync("python", ["--version"]).status === 0 ? "python" : null;
  if (!py) {
    console.error("cirax: need uv or python3 on PATH to install the core");
    process.exit(1);
  }
  if (!run(py, ["-m", "venv", venv])) process.exit(1);
  const pip = path.join(venvBin, "pip");
  if (!run(pip, ["install", "--upgrade", "pip"])) process.exit(1);
  if (!run(pip, ["install", src])) process.exit(1);
  done();
}

function done() {
  const exe = path.join(venvBin, "cirax");
  if (!fs.existsSync(exe)) {
    console.error("cirax: install finished but " + exe + " is missing");
    process.exit(1);
  }
  console.log("cirax: ready — try `npx cirax doctor`");
}

main();
