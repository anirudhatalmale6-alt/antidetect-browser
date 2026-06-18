const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('nickets', {
  launchChrome: (chromePath, args, profileId) =>
    ipcRenderer.invoke('launch-chrome', chromePath, args, profileId),
  stopChrome: (pid) =>
    ipcRenderer.invoke('stop-chrome', pid),
  isElectron: true
})
