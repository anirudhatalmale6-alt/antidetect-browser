const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('nickets', {
  launchChrome: (chromePath, args, env) =>
    ipcRenderer.invoke('launch-chrome', chromePath, args, env),
  stopChrome: (pid) =>
    ipcRenderer.invoke('stop-chrome', pid),
  isElectron: true
})
