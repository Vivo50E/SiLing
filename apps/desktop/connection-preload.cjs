'use strict';
const { contextBridge, ipcRenderer } = require('electron');
if (process.isMainFrame) contextBridge.exposeInMainWorld('silingConnection', {
  read: () => ipcRenderer.invoke('siling:connection', { action: 'read' }),
  save: url => ipcRenderer.invoke('siling:connection', { action: 'save', url }),
});
