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
} = {}) {
  const commands = [];
  const sent = [];
  let closeListener;
  let disposed = false;
  let result;
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
    setEnvironment: async () => {},
    getEnvironment: async () => ({ execInfo: { run: { executable: selected } } }),
  };
  const vscode = {
    workspace: { workspaceFolders: [{ uri: { fsPath: "/workspace" } }] },
    Uri: { file: (value) => value },
    commands: { executeCommand: async (value) => commands.push(value) },
    extensions: { getExtension: () => ({ activate: async () => api }) },
    window: {
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
    realpathSync: (value) => value,
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
      "\nmodule.exports.dispatch = dispatch;",
    context,
  );
  return {
    dispatch: context.module.exports.dispatch,
    api,
    commands,
    sent,
    disposed: () => disposed,
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
