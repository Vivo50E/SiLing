'use strict';
const { contextBridge, ipcRenderer } = require('electron');

// No bridge in terminal frames. The main process independently checks every
// sender, frame and URL; hiding a method in JavaScript is not authorization.
if (process.isMainFrame) {
  contextBridge.exposeInMainWorld('silingDesktop', {
    version: 1,
    request: message => ipcRenderer.invoke('siling:browser', message),
    onState: callback => {
      const listener = (_event, state) => callback(state);
      ipcRenderer.on('siling:browser-state', listener);
      return () => ipcRenderer.removeListener('siling:browser-state', listener);
    },
  });
}
