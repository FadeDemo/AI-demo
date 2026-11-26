const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

function fixture({
  selected = "/workspace/project/.venv/bin/python",
  venv = "/workspace/project/.venv",
  closeTerminal = true,
  analysisMatches = true,
  configurationReadyAfter = 0,
  projectReadyAfter = 0,
  changeProjectsOnSelect = false,
  searchPath = "./project/.venv",
  venvRealPath = "/workspace/project/.venv",
} = {}) {
  const commands = [];
  const sent = [];
  let closeListener;
  let disposed = false;
  let result;
  let configurationChecks = 0;
  let projectChecks = 0;
  let selectionCalls = 0;
  let selectionChecks;
  let projectPath = "project";
  const terminal = {
    processId: Promise.resolve(123),
    sendText(command) {
      sent.push(command);
      result = { attempt: sent.length - 1, shell_pid: 123, venv, python: selected };
    },
    dispose() {
      disposed = true;
      if (closeTerminal) closeListener(terminal);
    },
  };
  const api = {
    resolveEnvironment: async () => ({ id: "environment" }),
    setEnvironment: async () => {
      selectionCalls++;
      selectionChecks = { configurationChecks, projectChecks };
      if (changeProjectsOnSelect) projectPath = "old-project";
    },
    getEnvironment: async () => ({ execInfo: { run: { executable: selected } } }),
    getPythonProject: () => ({
      uri: { fsPath: ++projectChecks > projectReadyAfter ? "/workspace/project" : "/workspace" },
    }),
  };
  let analysisInterpreter;
  const analysisUpdates = [];
  const analysisListeners = new Set();
  const configListeners = new Set();
  const notifications = [];
  const warnings = [];
  const subscribe = (listeners, fn) => {
    listeners.add(fn);
    return { dispose: () => listeners.delete(fn) };
  };
  const changeInterpreter = (interpreter) => {
    analysisInterpreter = interpreter;
    for (const listener of analysisListeners) notifications.push(listener());
  };
  const pythonApi = {
    environments: {
      updateActiveEnvironmentPath: async (interpreter, scope) => {
        analysisUpdates.push({ interpreter, scope });
        if (analysisMatches) changeInterpreter(interpreter);
      },
    },
    settings: {
      getExecutionDetails: () => ({ execCommand: [analysisInterpreter] }),
      onDidChangeExecutionDetails: (fn) => subscribe(analysisListeners, fn),
    },
  };
  const vscode = {
    workspace: {
      workspaceFolders: [{ uri: { fsPath: "/workspace" } }],
      getConfiguration: (section) => ({
        get: (key) => {
          if (section !== "python-envs") return ["${workspaceFolder}/project/.venv/bin/python"];
          if (key === "pythonProjects") {
            configurationChecks++;
            return [
              {
                path: configurationChecks > configurationReadyAfter ? projectPath : "old-project",
                envManager: "ms-python.python:venv",
                packageManager: "ms-python.python:pip",
              },
            ];
          }
          return [searchPath];
        },
      }),
      onDidChangeConfiguration: (fn) => subscribe(configListeners, fn),
    },
    env: { appName: "Visual Studio Code" },
    Uri: { file: (value) => value },
    commands: { executeCommand: async (value) => commands.push(value) },
    extensions: {
      getExtension: (id) => ({
        activate: async () => (id === "ms-python.python" ? pythonApi : api),
      }),
    },
    window: {
      showWarningMessage: (message) => warnings.push(message),
      createTerminal: (options) => {
        assert.equal(options.env, undefined);
        return terminal;
      },
      onDidCloseTerminal: (callback) => {
        closeListener = callback;
        return { dispose() {} };
      },
    },
  };
  const fakeFs = {
    realpathSync: (value) => (value === "/workspace/project/.venv" ? venvRealPath : value),
    existsSync: () => true,
    mkdtempSync: () => "/private/probe",
    readFileSync: () => JSON.stringify(result),
    rmSync() {},
  };
  const modules = {
    vscode,
    "node:fs": fakeFs,
    "node:path": path,
    "node:os": { homedir: () => "/home/test" },
    "node:http": {},
    "node:crypto": crypto,
    "./package.json": { version: "test", useVenvRevision: "test" },
  };
  const context = vm.createContext({
    require: (name) => modules[name],
    module: { exports: {} },
    setTimeout: (fn) => {
      setImmediate(fn);
      return 1;
    },
    clearTimeout() {},
    process,
  });
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "extension.js"), "utf8") +
      "\nmodule.exports.dispatch = dispatch; module.exports.sync = synchronizeConfiguredAnalysis; module.exports.watch = watchConfiguredAnalysis; module.exports.createActivation = createTerminalActivation;",
    context,
  );
  return {
    dispatch: context.module.exports.dispatch,
    sync: context.module.exports.sync,
    watch: context.module.exports.watch,
    activate: context.module.exports.activate,
    createActivation: context.module.exports.createActivation,
    vscode,
    api,
    commands,
    analysisUpdates,
    changeInterpreter,
    analysisInterpreter: () => analysisInterpreter,
    changeConfiguration: () => {
      for (const listener of configListeners)
        notifications.push(listener({ affectsConfiguration: () => true }));
    },
    settle: async () => {
      while (notifications.length) await Promise.all(notifications.splice(0));
    },
    warnings,
    sent,
    disposed: () => disposed,
    configurationChecks: () => configurationChecks,
    projectChecks: () => projectChecks,
    selectionCalls: () => selectionCalls,
    selectionChecks: () => selectionChecks,
  };
}

const request = {
  workspace: "/workspace",
  project: "/workspace/project",
  interpreter: "/workspace/project/.venv/bin/python",
};

test("wrong workspace cannot cause a reload", async () => {
  const value = fixture();
  await assert.rejects(value.dispatch({ action: "reload", workspace: "/other" }), /not open/);
  assert.deepEqual(value.commands, []);
});

test("selection requires API read-back to match", async () => {
  const value = fixture({ selected: "/other/python" });
  await assert.rejects(value.dispatch({ ...request, action: "select" }), /read-back/);
});

test("project must belong to workspace", async () => {
  await assert.rejects(
    fixture().dispatch({ ...request, project: "/workspace-other", action: "select" }),
    /outside/,
  );
});

test("selection waits for both the target configuration and tracked project", async () => {
  const value = fixture({ configurationReadyAfter: 2, projectReadyAfter: 3 });
  await value.dispatch({ ...request, action: "select" });
  assert.ok(value.configurationChecks() > 2);
  assert.ok(value.projectChecks() > 3);
  assert.ok(value.selectionChecks().configurationChecks > 2);
  assert.ok(value.selectionChecks().projectChecks > 3);
  assert.equal(value.selectionCalls(), 1);
});

test("selection fails without changing environment if the project configuration stays stale", async () => {
  const value = fixture({ configurationReadyAfter: Infinity });
  await assert.rejects(value.dispatch({ ...request, action: "select" }), /did not load/);
  assert.equal(value.selectionCalls(), 0);
});

test("selection fails if the project configuration changes during the API call", async () => {
  const value = fixture({ changeProjectsOnSelect: true });
  await assert.rejects(value.dispatch({ ...request, action: "select" }), /configuration changed/);
  assert.equal(value.selectionCalls(), 1);
});

test("selection waits for the target environment search path", async () => {
  const value = fixture({ searchPath: "./old-project/.venv" });
  await assert.rejects(value.dispatch({ ...request, action: "select" }), /did not load/);
  assert.equal(value.selectionCalls(), 0);
});

test("selection supports a project at the workspace root", async () => {
  const interpreter = "/workspace/.venv/bin/python";
  const value = fixture({ selected: interpreter });
  value.api.getPythonProject = () => ({ uri: { fsPath: "/workspace" } });
  value.vscode.workspace.getConfiguration = () => ({
    get: (key) =>
      key === "pythonProjects"
        ? [
            {
              path: ".",
              envManager: "ms-python.python:venv",
              packageManager: "ms-python.python:pip",
            },
          ]
        : ["./.venv"],
  });
  await value.dispatch({
    workspace: "/workspace",
    project: "/workspace",
    interpreter,
    action: "select",
  });
  assert.equal(value.selectionCalls(), 1);
});

test("selection resolves a symlinked virtual environment in the search path", async () => {
  const value = fixture({ searchPath: "./shared-venv", venvRealPath: "/workspace/shared-venv" });
  await value.dispatch({ ...request, action: "select" });
  assert.equal(value.selectionCalls(), 1);
});

test("probe observes activation and disposes only its terminal", async () => {
  const value = fixture();
  const result = await value.dispatch({ ...request, action: "probe" });
  assert.equal(result.venv, "/workspace/project/.venv");
  assert.equal(value.disposed(), true);
  assert.equal(value.sent.length, 1);
  assert.ok(!value.sent[0].includes("activate"));
});

test("missing activation fails and still disposes terminal", async () => {
  const value = fixture({ venv: null });
  await assert.rejects(
    value.dispatch({ ...request, action: "probe" }),
    /did not automatically activate/,
  );
  assert.equal(value.disposed(), true);
});

test("cleanup failure preserves the activation failure", async () => {
  const value = fixture({ venv: null, closeTerminal: false });
  await assert.rejects(
    value.dispatch({ ...request, action: "probe" }),
    /did not automatically activate.*cleanup failed:.*disposal was not confirmed/,
  );
});

test("selection also synchronizes the workspace language-service interpreter", async () => {
  const value = fixture();
  await value.dispatch({ ...request, action: "select" });
  assert.deepEqual(value.analysisUpdates, [
    { interpreter: request.interpreter, scope: request.workspace },
  ]);
});

test("successful project selection cannot hide a stale analysis interpreter", async () => {
  await assert.rejects(
    fixture({ analysisMatches: false }).dispatch({ ...request, action: "select" }),
    /Language service interpreter read-back/,
  );
});

test("automatic synchronization resolves existing workspace configuration", async () => {
  const value = fixture();
  await value.sync();
  assert.deepEqual(value.analysisUpdates, [
    { interpreter: request.interpreter, scope: request.workspace },
  ]);
});

test("late startup selection is repaired without reacting endlessly to our own updates", async () => {
  const value = fixture();
  const context = { subscriptions: [] };
  await value.watch(context);
  await value.settle();
  assert.equal(value.analysisUpdates.length, 1);

  value.changeInterpreter("/opt/homebrew/bin/python3");
  await value.settle();
  assert.equal(value.analysisInterpreter(), request.interpreter);
  assert.equal(value.analysisUpdates.length, 2);
  assert.deepEqual(value.warnings, []);

  for (const subscription of context.subscriptions) subscription.dispose();
  value.changeInterpreter("/other/python");
  value.changeConfiguration();
  await value.settle();
  assert.equal(value.analysisUpdates.length, 2);
});

test("interpreter notifications use the latest configured target", async () => {
  const value = fixture();
  await value.watch({ subscriptions: [] });
  await value.settle();
  const interpreter = "/workspace/another/.venv/bin/python";
  value.vscode.workspace.getConfiguration = () => ({ get: () => [interpreter] });
  value.changeConfiguration();
  await value.settle();
  assert.equal(value.analysisInterpreter(), interpreter);

  value.changeInterpreter(request.interpreter);
  await value.settle();
  assert.equal(value.analysisInterpreter(), interpreter);
  assert.equal(value.analysisUpdates.length, 3);
});

test("interpreter changes do not select an environment without use-venv configuration", async () => {
  const value = fixture();
  value.vscode.workspace.getConfiguration = () => ({ get: () => undefined });
  await value.watch({ subscriptions: [] });
  value.changeInterpreter("/other/python");
  await value.settle();
  assert.deepEqual(value.analysisUpdates, []);
  assert.equal(value.analysisInterpreter(), "/other/python");
});

test("activation in VS Code has no side effects", () => {
  const value = fixture();
  value.activate({ subscriptions: [] });
  assert.deepEqual(value.analysisUpdates, []);
});

function activationFixture() {
  const value = fixture();
  const events = {};
  let setting;
  let saved;
  const disposed = [];
  const target = "/workspace/project/.venv/bin/python";
  value.vscode.ConfigurationTarget = { Global: 1 };
  value.vscode.tasks = { taskExecutions: [] };
  value.vscode.workspace.getConfiguration = (section) =>
    section === "pylint"
      ? { get: () => [target] }
      : {
          inspect: () => ({ globalValue: setting }),
          update: async (key, next, scope) => {
            assert.equal(scope, 1);
            setting = next;
          },
        };
  for (const name of [
    "onDidOpenTerminal",
    "onDidChangeTerminalShellIntegration",
    "onDidCloseTerminal",
  ]) {
    value.vscode.window[name] = (fn) => {
      events[name] = fn;
      return { dispose() {} };
    };
  }
  value.vscode.window.showWarningMessage = () => {};
  value.vscode.commands.registerCommand = () => ({ dispose() {} });
  const controller = value.createActivation({
    globalState: {
      get: () => saved,
      update: async (key, next) => {
        saved = next;
      },
    },
    subscriptions: disposed,
  });
  const sent = [];
  const terminal = {
    creationOptions: { cwd: "/workspace/project", shellPath: "/bin/zsh" },
    sendText: (command) => sent.push(command),
  };
  return {
    controller,
    events,
    terminal,
    sent,
    value,
    setting: () => setting,
    saved: () => saved,
  };
}

test("takeover waits for stable shell integration and activates only once", async () => {
  const f = activationFixture();
  await f.controller.enable();
  assert.equal(f.setting(), "off");
  f.events.onDidOpenTerminal(f.terminal);
  assert.deepEqual(f.sent, []);
  f.terminal.shellIntegration = { cwd: { fsPath: "/workspace/project" } };
  f.events.onDidChangeTerminalShellIntegration({ terminal: f.terminal });
  f.events.onDidChangeTerminalShellIntegration({ terminal: f.terminal });
  assert.deepEqual(f.sent, ["source '/workspace/project/.venv/bin/activate'"]);
});

test("restoration removes an originally absent setting and survives re-enable", async () => {
  const f = activationFixture();
  await f.controller.enable();
  await f.controller.enable();
  assert.equal(f.saved().original, null);
  await f.controller.restore();
  assert.equal(f.setting(), undefined);
  await f.controller.enable();
  assert.equal(f.setting(), undefined);
});

test("takeover skips tasks and terminals outside the selected project", async () => {
  const f = activationFixture();
  await f.controller.enable();
  f.terminal.shellIntegration = { cwd: { fsPath: "/elsewhere" } };
  f.events.onDidOpenTerminal(f.terminal);
  f.terminal.shellIntegration.cwd.fsPath = "/workspace/project";
  f.value.vscode.tasks.taskExecutions.push({ terminal: f.terminal });
  f.events.onDidOpenTerminal(f.terminal);
  assert.deepEqual(f.sent, []);
});

test("new terminal without explicit cwd uses shell integration cwd", async () => {
  const f = activationFixture();
  await f.controller.enable();
  delete f.terminal.creationOptions.cwd;
  f.events.onDidOpenTerminal(f.terminal);
  f.terminal.shellIntegration = { cwd: { fsPath: "/workspace/project" } };
  f.events.onDidChangeTerminalShellIntegration({ terminal: f.terminal });
  assert.equal(f.sent.length, 1);
});

test("closed terminal cannot receive a late activation command", async () => {
  const f = activationFixture();
  await f.controller.enable();
  f.events.onDidOpenTerminal(f.terminal);
  f.events.onDidCloseTerminal(f.terminal);
  f.terminal.shellIntegration = { cwd: { fsPath: "/workspace/project" } };
  f.events.onDidChangeTerminalShellIntegration({ terminal: f.terminal });
  assert.deepEqual(f.sent, []);
});

test("integration without initial cwd does not discard pending activation", async () => {
  const f = activationFixture();
  await f.controller.enable();
  delete f.terminal.creationOptions.cwd;
  f.terminal.shellIntegration = {};
  f.events.onDidOpenTerminal(f.terminal);
  assert.deepEqual(f.sent, []);
  f.terminal.shellIntegration.cwd = { fsPath: "/workspace/project" };
  // Polling must handle cwd arriving without another integration event.
  await new Promise(setImmediate);
  assert.equal(f.sent.length, 1);
});
