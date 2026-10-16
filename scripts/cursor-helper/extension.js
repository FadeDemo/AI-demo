const vscode = require("vscode");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const http = require("node:http");
const crypto = require("node:crypto");

const root = path.join(os.homedir(), "Library/Application Support/use-venv/helper");
const manifest = require("./package.json");
const session = crypto.randomUUID();
const token = crypto.randomBytes(32).toString("hex");
let server;
let descriptor;
let busy = false;
let reloadPending = false;

function scheduleReload() {
  reloadPending = true;
  setTimeout(() => {
    vscode.commands.executeCommand("workbench.action.reloadWindow").catch(() => {
      reloadPending = false;
    });
  }, 100);
}

async function dispatch(request) {
  const folders = (vscode.workspace.workspaceFolders || []).map((f) =>
    fs.realpathSync(f.uri.fsPath),
  );
  if (!folders.includes(request.workspace))
    throw new Error("Target workspace is not open in this window");
  switch (request.action) {
    case "ping":
      return { session, folders, version: manifest.version, revision: manifest.useVenvRevision };
    case "reload":
      scheduleReload();
      return { session };
    case "select": {
      const project = checkedProject(request);
      const extension = vscode.extensions.getExtension("ms-python.vscode-python-envs");
      if (!extension) throw new Error("Python Environments is not installed");
      const api = await extension.activate();
      if (!api?.resolveEnvironment || !api?.setEnvironment || !api?.getEnvironment)
        throw new Error("Python Environments does not expose the required selection API");
      const environment = await api.resolveEnvironment(vscode.Uri.file(request.interpreter));
      if (!environment) throw new Error("Python Environments could not resolve the interpreter");
      const scope = vscode.Uri.file(project);
      await api.setEnvironment(scope, environment);
      const selected = await api.getEnvironment(scope);
      if (selected?.execInfo?.run?.executable !== request.interpreter)
        throw new Error("Interpreter selection read-back did not match the requested path");
      return { interpreter: selected.execInfo.run.executable };
    }
    case "probe":
      return probeTerminal(request);
    default:
      throw new Error("Unsupported helper action");
  }
}

function checkedProject(request) {
  const project = fs.realpathSync(request.project);
  if (project !== request.workspace && !project.startsWith(request.workspace + path.sep))
    throw new Error("Project is outside the target workspace");
  if (typeof request.interpreter !== "string" || !path.isAbsolute(request.interpreter))
    throw new Error("Interpreter must be an absolute path");
  return project;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const quote = (value) => "'" + value.replaceAll("'", "'\\''") + "'";

async function probeTerminal(request) {
  const project = checkedProject(request);
  const directory = fs.mkdtempSync(path.join(root, "probe-"));
  const resultPath = path.join(directory, "result.json");
  const terminal = vscode.window.createTerminal({
    name: `use-venv check ${session}`,
    cwd: project,
    isTransient: true,
  });
  let closed = false;
  const listener = vscode.window.onDidCloseTerminal((value) => {
    if (value === terminal) closed = true;
  });
  let result;
  let failure;
  try {
    const pid = await Promise.race([terminal.processId, sleep(5000).then(() => undefined)]);
    if (!pid) throw new Error("Test terminal did not create a shell within 5 seconds");
    // Shell startup and environment activation may still be writing commands.
    // Prefer the shell integration readiness signal, with a bounded fallback.
    for (let poll = 0; !terminal.shellIntegration && poll < 50; poll++) await sleep(100);
    for (let attempt = 0; attempt < 12; attempt++) {
      const code = `import json,os,shutil,sys;from pathlib import Path;Path(${JSON.stringify(resultPath)}).write_text(json.dumps({'attempt':${attempt},'shell_pid':int(sys.argv[1]),'venv':os.getenv('VIRTUAL_ENV'),'python':shutil.which('python')}))`;
      terminal.sendText(`${quote(request.interpreter)} -c ${quote(code)} "$$"`, true);
      let data;
      for (let poll = 0; poll < 50; poll++) {
        if (closed) throw new Error("Test terminal closed before verification");
        try {
          data = JSON.parse(fs.readFileSync(resultPath, "utf8"));
        } catch {
          /* Wait for the atomic shell result. */
        }
        if (data?.attempt === attempt) break;
        await sleep(100);
      }
      if (data?.attempt !== attempt) {
        if (attempt === 11) throw new Error("Terminal probe produced no result");
        continue;
      }
      if (data.shell_pid !== pid) throw new Error("Terminal probe shell identity mismatch");
      if (
        request.requireActivation === false ||
        (data.venv === path.dirname(path.dirname(request.interpreter)) &&
          data.python === request.interpreter)
      ) {
        result = data;
        break;
      }
      await sleep(500);
    }
    if (!result)
      throw new Error(
        "New terminal did not automatically activate the selected virtual environment",
      );
  } catch (error) {
    failure = error;
  }
  try {
    terminal.dispose();
    for (let poll = 0; !closed && poll < 50; poll++) await sleep(100);
    if (closed) fs.rmSync(directory, { recursive: true });
    else
      throw new Error(`Test terminal disposal was not confirmed; probe retained at ${directory}`);
  } catch (error) {
    failure = failure
      ? new AggregateError([failure, error], `${failure.message}; cleanup failed: ${error.message}`)
      : error;
  } finally {
    listener.dispose();
  }
  if (failure) throw failure;
  return result;
}

function activate(context) {
  fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  if (fs.lstatSync(root).isSymbolicLink())
    throw new Error("Helper state directory must not be a symlink");
  fs.chmodSync(root, 0o700);
  descriptor = path.join(root, `${session}.json`);
  server = http.createServer(async (req, res) => {
    res.setHeader("Content-Type", "application/json");
    if (
      req.method !== "POST" ||
      req.headers.authorization !== `Bearer ${token}` ||
      req.headers.origin
    ) {
      res.writeHead(403).end(JSON.stringify({ error: "Unauthorized" }));
      return;
    }
    let body = "";
    try {
      for await (const chunk of req) {
        body += chunk;
        if (body.length > 16384) throw new Error("Request too large");
      }
      const request = JSON.parse(body);
      if (request.action === "ping" || request.action === "reload") {
        res.end(JSON.stringify({ result: await dispatch(request) }));
        return;
      }
      if (busy || reloadPending) throw new Error("Helper is busy");
      busy = true;
      let timer;
      try {
        const deadline = new Promise((_, reject) => {
          timer = setTimeout(
            () => {
              scheduleReload();
              const error = new Error(
                "Helper operation timed out; reloading to cancel pending work",
              );
              error.reloading = true;
              reject(error);
            },
            request.action === "probe" ? 75000 : 40000,
          );
        });
        res.end(JSON.stringify({ result: await Promise.race([dispatch(request), deadline]) }));
      } finally {
        clearTimeout(timer);
        busy = false;
      }
    } catch (error) {
      res
        .writeHead(400)
        .end(JSON.stringify({ error: error.message, reloading: error.reloading === true }));
    }
  });
  server.requestTimeout = 60000;
  server.listen(0, "127.0.0.1", () => {
    fs.writeFileSync(
      descriptor,
      JSON.stringify({ port: server.address().port, token, session, pid: process.pid }),
      { mode: 0o600 },
    );
  });
  context.subscriptions.push({ dispose: deactivate });
}

function deactivate() {
  server?.close();
  if (descriptor && fs.existsSync(descriptor)) fs.unlinkSync(descriptor);
}

module.exports = { activate, deactivate };
