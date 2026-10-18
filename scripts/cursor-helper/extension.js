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
      await synchronizeAnalysis(request.workspace, request.interpreter);
      return { interpreter: selected.execInfo.run.executable };
    }
    case "terminal-status":
      return vscode.window.terminals.map((terminal) => ({
        name: terminal.name,
        cwd: terminal.shellIntegration?.cwd?.fsPath,
        options: {
          cwd: terminal.creationOptions.cwd,
          shellPath: terminal.creationOptions.shellPath,
          hideFromUser: terminal.creationOptions.hideFromUser,
          pty: "pty" in terminal.creationOptions,
        },
        integration: !!terminal.shellIntegration,
        task: vscode.tasks.taskExecutions.some((task) => task.terminal === terminal),
      }));
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
  let terminal;
  if (request.userEntry) {
    const before = new Set(vscode.window.terminals);
    await vscode.commands.executeCommand("workbench.action.terminal.new");
    terminal = vscode.window.activeTerminal;
    if (!terminal || before.has(terminal))
      throw new Error("New terminal command did not return a new active terminal");
  } else {
    terminal = vscode.window.createTerminal({
      name: `use-venv check ${session}`,
      cwd: project,
      isTransient: true,
    });
  }
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

// Serialize automatic and explicitly requested updates to the legacy Python API.
let analysisQueue = Promise.resolve();
function synchronizeAnalysis(workspace, interpreter) {
  const operation = analysisQueue
    .catch(() => {})
    .then(async () => {
      const extension = vscode.extensions.getExtension("ms-python.python");
      if (!extension) throw new Error("Python extension is not installed");
      const api = await extension.activate();
      if (!api?.environments?.updateActiveEnvironmentPath || !api?.settings?.getExecutionDetails)
        throw new Error("Python extension does not expose interpreter synchronization APIs");
      const scope = vscode.Uri.file(workspace);
      await api.environments.updateActiveEnvironmentPath(interpreter, scope);
      for (let attempt = 0; attempt < 50; attempt++) {
        const details = await api.settings.getExecutionDetails(scope);
        if (details.execCommand?.[0] === interpreter) return;
        await sleep(100);
      }
      throw new Error("Language service interpreter read-back did not match the requested path");
    });
  analysisQueue = operation;
  return operation;
}

async function synchronizeConfiguredAnalysis() {
  for (const folder of vscode.workspace.workspaceFolders || []) {
    // use-venv already maintains this exact executable for every editor.
    const configured = vscode.workspace.getConfiguration("pylint", folder.uri).get("interpreter");
    if (!Array.isArray(configured) || configured.length !== 1 || typeof configured[0] !== "string")
      continue;
    const interpreter = configured[0].replaceAll("${workspaceFolder}", folder.uri.fsPath);
    if (!path.isAbsolute(interpreter) || !fs.existsSync(interpreter)) continue;
    await synchronizeAnalysis(folder.uri.fsPath, interpreter);
  }
}

// The takeover uses only stable terminal APIs; no terminal output subscription.
const activationStateKey = "terminalActivationTakeover";
function createTerminalActivation(context) {
  let enabled = false;
  const pending = new Map();
  const completed = new WeakSet();
  const configuration = () => vscode.workspace.getConfiguration("python-envs");
  const warn = (message) => vscode.window.showWarningMessage(`use-venv: ${message}`);
  function target(terminal) {
    const options = terminal.creationOptions;
    if (!options || "pty" in options || options.hideFromUser || terminal.exitStatus) return;
    if (vscode.tasks.taskExecutions.some((task) => task.terminal === terminal)) return;
    const cwd = terminal.shellIntegration?.cwd?.fsPath || options.cwd?.fsPath || options.cwd;
    if (typeof cwd !== "string") return;
    for (const folder of vscode.workspace.workspaceFolders || []) {
      const config = vscode.workspace.getConfiguration("pylint", folder.uri).get("interpreter");
      if (!Array.isArray(config) || config.length !== 1 || typeof config[0] !== "string") continue;
      const interpreter = config[0].replaceAll("${workspaceFolder}", folder.uri.fsPath);
      if (!path.isAbsolute(interpreter)) continue;
      const project = path.dirname(path.dirname(path.dirname(interpreter)));
      if (project !== folder.uri.fsPath && !project.startsWith(folder.uri.fsPath + path.sep))
        continue;
      if (cwd !== project && !cwd.startsWith(project + path.sep)) continue;
      const script = path.join(path.dirname(interpreter), "activate");
      if (fs.existsSync(interpreter) && fs.existsSync(script)) return script;
    }
  }
  function clear(terminal) {
    clearTimeout(pending.get(terminal));
    pending.delete(terminal);
  }
  function ready(terminal) {
    if (!enabled || !pending.has(terminal) || !terminal.shellIntegration) return;
    // Shell integration may exist before it has reported the initial cwd.
    const cwd =
      terminal.shellIntegration.cwd?.fsPath ||
      terminal.creationOptions.cwd?.fsPath ||
      terminal.creationOptions.cwd;
    if (typeof cwd !== "string") return;
    const script = target(terminal);
    clear(terminal);
    if (!script || completed.has(terminal)) return;
    const shell = path.basename(terminal.creationOptions.shellPath || process.env.SHELL || "");
    if (!["zsh", "bash"].includes(shell)) {
      warn("Automatic activation currently supports zsh and bash only.");
      return;
    }
    completed.add(terminal);
    terminal.sendText(`source ${quote(script)}`, true);
  }
  function opened(terminal) {
    if (!enabled || completed.has(terminal) || pending.has(terminal)) return;
    if (
      !terminal.creationOptions ||
      "pty" in terminal.creationOptions ||
      terminal.creationOptions.hideFromUser
    )
      return;
    let attempts = 0;
    const poll = () => {
      if (!enabled || !pending.has(terminal)) return;
      ready(terminal);
      if (!pending.has(terminal)) return;
      if (++attempts >= 100) {
        clear(terminal);
        warn(
          "Terminal shell integration or working directory was not ready within 10 seconds; activation was skipped.",
        );
        return;
      }
      pending.set(terminal, setTimeout(poll, 100));
    };
    pending.set(terminal, undefined);
    poll();
  }

  async function enable() {
    if (context.globalState.get(activationStateKey)?.disabled) return;
    const folders = vscode.workspace.workspaceFolders || [];
    if (folders.length !== 1 || vscode.env.remoteName || process.platform === "win32") return;
    const config = vscode.workspace.getConfiguration("pylint", folders[0].uri).get("interpreter");
    if (!Array.isArray(config) || typeof config[0] !== "string") return;
    const interpreter = config[0].replaceAll("${workspaceFolder}", folders[0].uri.fsPath);
    if (
      !path.isAbsolute(interpreter) ||
      !fs.existsSync(path.join(path.dirname(interpreter), "activate"))
    )
      return;
    if (!context.globalState.get(activationStateKey)) {
      const original = configuration().inspect("terminal.autoActivationType")?.globalValue;
      await context.globalState.update(activationStateKey, { original: original ?? null });
    }
    await configuration().update(
      "terminal.autoActivationType",
      "off",
      vscode.ConfigurationTarget.Global,
    );
    enabled = true;
  }
  async function restore() {
    enabled = false;
    for (const terminal of pending.keys()) clear(terminal);
    const state = context.globalState.get(activationStateKey);
    if (!state) return;
    // Persist the opt-out before restoring, so a reload cannot re-enable takeover.
    await context.globalState.update(activationStateKey, { ...state, disabled: true });
    if (configuration().inspect("terminal.autoActivationType")?.globalValue === "off") {
      await configuration().update(
        "terminal.autoActivationType",
        state.original ?? undefined,
        vscode.ConfigurationTarget.Global,
      );
    }
  }
  context.subscriptions.push(
    vscode.window.onDidOpenTerminal(opened),
    vscode.window.onDidChangeTerminalShellIntegration((event) => ready(event.terminal)),
    vscode.window.onDidCloseTerminal(clear),
    vscode.commands.registerCommand("use-venv.restoreTerminalActivation", restore),
    {
      dispose() {
        enabled = false;
        for (const terminal of pending.keys()) clear(terminal);
      },
    },
  );
  return { enable, restore };
}

async function activate(context) {
  if (!/cursor/i.test(vscode.env.appName)) return;
  const activation = createTerminalActivation(context);
  await activation.enable();
  const sync = () => {
    synchronizeConfiguredAnalysis().catch((error) => {
      vscode.window.showWarningMessage(`use-venv: ${error.message}`);
    });
  };
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("pylint.interpreter")) {
        sync();
        activation
          .enable()
          .catch((error) => vscode.window.showWarningMessage(`use-venv: ${error.message}`));
      }
    }),
  );
  sync();
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
